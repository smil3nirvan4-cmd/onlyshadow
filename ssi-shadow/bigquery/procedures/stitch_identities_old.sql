-- ============================================================================
-- S.S.I. SHADOW - Identity Stitching Procedure
-- ============================================================================
-- Runs daily to resolve identities across sessions and devices
-- Uses deterministic matching (email, phone) and probabilistic matching (fbp, session)
-- ============================================================================

CREATE OR REPLACE PROCEDURE `ssi_shadow.stitch_identities`()
BEGIN
  DECLARE run_id STRING DEFAULT GENERATE_UUID();
  DECLARE start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP();
  DECLARE rows_processed INT64 DEFAULT 0;
  
  -- Log start
  SELECT CONCAT('Starting identity stitching run: ', run_id) AS log_message;

  -- ========================================================================
  -- STEP 1: Deterministic Matching - Email
  -- ========================================================================
  -- If two ssi_ids share the same email_hash, they are the same person
  -- ========================================================================
  
  CREATE TEMP TABLE temp_email_matches AS
  SELECT
    email_hash,
    ARRAY_AGG(DISTINCT ssi_id) AS ssi_ids,
    MIN(event_time) AS first_seen,
    MAX(event_time) AS last_seen,
    COUNT(DISTINCT ssi_id) AS match_count
  FROM `ssi_shadow.events_raw`
  WHERE email_hash IS NOT NULL
    AND event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 365 DAY)
  GROUP BY email_hash
  HAVING COUNT(DISTINCT ssi_id) > 1;

  -- Insert email-based links into identity graph
  INSERT INTO `ssi_shadow.identity_graph` (
    canonical_id,
    linked_id,
    id_type,
    match_type,
    match_confidence,
    match_source,
    first_seen,
    last_seen,
    link_count,
    created_at,
    updated_at
  )
  SELECT
    -- Use the oldest ssi_id as canonical
    (SELECT ssi_id FROM UNNEST(ssi_ids) AS ssi_id ORDER BY ssi_id LIMIT 1) AS canonical_id,
    ssi_id AS linked_id,
    'ssi_id' AS id_type,
    'deterministic' AS match_type,
    1.0 AS match_confidence,
    'email_match' AS match_source,
    first_seen,
    last_seen,
    1 AS link_count,
    CURRENT_TIMESTAMP(),
    CURRENT_TIMESTAMP()
  FROM temp_email_matches, UNNEST(ssi_ids) AS ssi_id
  WHERE NOT EXISTS (
    SELECT 1 FROM `ssi_shadow.identity_graph` ig
    WHERE ig.linked_id = ssi_id
  );

  SET rows_processed = rows_processed + @@row_count;
  SELECT CONCAT('Email matches: ', @@row_count) AS log_message;

  -- ========================================================================
  -- STEP 2: Deterministic Matching - Phone
  -- ========================================================================
  -- If two ssi_ids share the same phone_hash, they are the same person
  -- ========================================================================
  
  CREATE TEMP TABLE temp_phone_matches AS
  SELECT
    phone_hash,
    ARRAY_AGG(DISTINCT ssi_id) AS ssi_ids,
    MIN(event_time) AS first_seen,
    MAX(event_time) AS last_seen,
    COUNT(DISTINCT ssi_id) AS match_count
  FROM `ssi_shadow.events_raw`
  WHERE phone_hash IS NOT NULL
    AND event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 365 DAY)
  GROUP BY phone_hash
  HAVING COUNT(DISTINCT ssi_id) > 1;

  -- Insert phone-based links
  INSERT INTO `ssi_shadow.identity_graph` (
    canonical_id,
    linked_id,
    id_type,
    match_type,
    match_confidence,
    match_source,
    first_seen,
    last_seen,
    link_count,
    created_at,
    updated_at
  )
  SELECT
    (SELECT ssi_id FROM UNNEST(ssi_ids) AS ssi_id ORDER BY ssi_id LIMIT 1) AS canonical_id,
    ssi_id AS linked_id,
    'ssi_id' AS id_type,
    'deterministic' AS match_type,
    1.0 AS match_confidence,
    'phone_match' AS match_source,
    first_seen,
    last_seen,
    1 AS link_count,
    CURRENT_TIMESTAMP(),
    CURRENT_TIMESTAMP()
  FROM temp_phone_matches, UNNEST(ssi_ids) AS ssi_id
  WHERE NOT EXISTS (
    SELECT 1 FROM `ssi_shadow.identity_graph` ig
    WHERE ig.linked_id = ssi_id
  );

  SET rows_processed = rows_processed + @@row_count;
  SELECT CONCAT('Phone matches: ', @@row_count) AS log_message;

  -- ========================================================================
  -- STEP 3: Probabilistic Matching - FBP Cookie (90 days)
  -- ========================================================================
  -- Same fbp cookie within 90 days = likely same browser/person
  -- Lower confidence than email/phone
  -- ========================================================================
  
  CREATE TEMP TABLE temp_fbp_matches AS
  SELECT
    fbp,
    ARRAY_AGG(DISTINCT ssi_id) AS ssi_ids,
    MIN(event_time) AS first_seen,
    MAX(event_time) AS last_seen,
    COUNT(DISTINCT ssi_id) AS match_count
  FROM `ssi_shadow.events_raw`
  WHERE fbp IS NOT NULL
    AND event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY)
  GROUP BY fbp
  HAVING COUNT(DISTINCT ssi_id) > 1;

  -- Insert FBP-based links (lower confidence)
  INSERT INTO `ssi_shadow.identity_graph` (
    canonical_id,
    linked_id,
    id_type,
    match_type,
    match_confidence,
    match_source,
    first_seen,
    last_seen,
    link_count,
    created_at,
    updated_at
  )
  SELECT
    (SELECT ssi_id FROM UNNEST(ssi_ids) AS ssi_id ORDER BY ssi_id LIMIT 1) AS canonical_id,
    ssi_id AS linked_id,
    'ssi_id' AS id_type,
    'probabilistic_fbp' AS match_type,
    0.8 AS match_confidence,  -- Lower confidence for probabilistic
    'fbp_match' AS match_source,
    first_seen,
    last_seen,
    1 AS link_count,
    CURRENT_TIMESTAMP(),
    CURRENT_TIMESTAMP()
  FROM temp_fbp_matches, UNNEST(ssi_ids) AS ssi_id
  WHERE NOT EXISTS (
    SELECT 1 FROM `ssi_shadow.identity_graph` ig
    WHERE ig.linked_id = ssi_id
      AND ig.match_type = 'deterministic'  -- Don't override deterministic matches
  );

  SET rows_processed = rows_processed + @@row_count;
  SELECT CONCAT('FBP matches: ', @@row_count) AS log_message;

  -- ========================================================================
  -- STEP 4: Probabilistic Matching - Session (IP + UA + Timezone, 30 min)
  -- ========================================================================
  -- Same IP, User Agent, and Timezone within 30 minutes = likely same person
  -- Useful for users who clear cookies
  -- ========================================================================
  
  CREATE TEMP TABLE temp_session_matches AS
  WITH session_fingerprint AS (
    SELECT
      ssi_id,
      event_time,
      ip_hash,
      user_agent,
      timezone,
      CONCAT(ip_hash, '|', user_agent, '|', timezone) AS session_fp
    FROM `ssi_shadow.events_raw`
    WHERE ip_hash IS NOT NULL
      AND user_agent IS NOT NULL
      AND event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
  )
  SELECT
    s1.session_fp,
    ARRAY_AGG(DISTINCT s1.ssi_id) AS ssi_ids,
    MIN(s1.event_time) AS first_seen,
    MAX(s1.event_time) AS last_seen
  FROM session_fingerprint s1
  INNER JOIN session_fingerprint s2
    ON s1.session_fp = s2.session_fp
    AND s1.ssi_id != s2.ssi_id
    AND ABS(TIMESTAMP_DIFF(s1.event_time, s2.event_time, MINUTE)) <= 30
  GROUP BY s1.session_fp
  HAVING COUNT(DISTINCT s1.ssi_id) > 1;

  -- Insert session-based links (lowest confidence)
  INSERT INTO `ssi_shadow.identity_graph` (
    canonical_id,
    linked_id,
    id_type,
    match_type,
    match_confidence,
    match_source,
    first_seen,
    last_seen,
    link_count,
    created_at,
    updated_at
  )
  SELECT
    (SELECT ssi_id FROM UNNEST(ssi_ids) AS ssi_id ORDER BY ssi_id LIMIT 1) AS canonical_id,
    ssi_id AS linked_id,
    'ssi_id' AS id_type,
    'probabilistic_session' AS match_type,
    0.6 AS match_confidence,  -- Lowest confidence
    'session_match' AS match_source,
    first_seen,
    last_seen,
    1 AS link_count,
    CURRENT_TIMESTAMP(),
    CURRENT_TIMESTAMP()
  FROM temp_session_matches, UNNEST(ssi_ids) AS ssi_id
  WHERE NOT EXISTS (
    SELECT 1 FROM `ssi_shadow.identity_graph` ig
    WHERE ig.linked_id = ssi_id
      AND ig.match_confidence > 0.6  -- Don't override higher confidence matches
  );

  SET rows_processed = rows_processed + @@row_count;
  SELECT CONCAT('Session matches: ', @@row_count) AS log_message;

  -- ========================================================================
  -- STEP 5: Resolve Canonical IDs (transitive closure)
  -- ========================================================================
  -- If A → B and B → C, then A, B, C should all have the same canonical_id
  -- ========================================================================
  
  -- This is a simplified version - for large graphs, use iterative approach
  UPDATE `ssi_shadow.identity_graph` AS ig
  SET canonical_id = (
    SELECT MIN(canonical_id)
    FROM `ssi_shadow.identity_graph` ig2
    WHERE ig2.canonical_id = ig.canonical_id
       OR ig2.linked_id = ig.canonical_id
       OR ig2.canonical_id = ig.linked_id
  )
  WHERE TRUE;

  SELECT CONCAT('Transitive closure update: ', @@row_count) AS log_message;

  -- ========================================================================
  -- STEP 6: Update events_raw with canonical_id
  -- ========================================================================
  
  UPDATE `ssi_shadow.events_raw` AS e
  SET canonical_id = (
    SELECT canonical_id
    FROM `ssi_shadow.identity_graph` ig
    WHERE ig.linked_id = e.ssi_id
      AND ig.id_type = 'ssi_id'
    ORDER BY ig.match_confidence DESC
    LIMIT 1
  )
  WHERE canonical_id IS NULL
    AND event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY);

  SELECT CONCAT('Events updated: ', @@row_count) AS log_message;

  -- ========================================================================
  -- STEP 7: Update identity_clusters table
  -- ========================================================================
  
  DELETE FROM `ssi_shadow.identity_clusters` WHERE TRUE;

  INSERT INTO `ssi_shadow.identity_clusters` (
    canonical_id,
    cluster_size,
    ssi_ids,
    email_hashes,
    phone_hashes,
    fbp_ids,
    external_ids,
    has_email,
    has_phone,
    has_external_id,
    deterministic_links,
    probabilistic_links,
    avg_confidence,
    first_seen,
    last_seen,
    created_at,
    updated_at
  )
  SELECT
    canonical_id,
    COUNT(DISTINCT linked_id) AS cluster_size,
    ARRAY_AGG(DISTINCT CASE WHEN id_type = 'ssi_id' THEN linked_id END IGNORE NULLS) AS ssi_ids,
    ARRAY_AGG(DISTINCT CASE WHEN id_type = 'email_hash' THEN linked_id END IGNORE NULLS) AS email_hashes,
    ARRAY_AGG(DISTINCT CASE WHEN id_type = 'phone_hash' THEN linked_id END IGNORE NULLS) AS phone_hashes,
    ARRAY_AGG(DISTINCT CASE WHEN id_type = 'fbp' THEN linked_id END IGNORE NULLS) AS fbp_ids,
    ARRAY_AGG(DISTINCT CASE WHEN id_type = 'external_id' THEN linked_id END IGNORE NULLS) AS external_ids,
    LOGICAL_OR(id_type = 'email_hash') AS has_email,
    LOGICAL_OR(id_type = 'phone_hash') AS has_phone,
    LOGICAL_OR(id_type = 'external_id') AS has_external_id,
    COUNTIF(match_type = 'deterministic') AS deterministic_links,
    COUNTIF(match_type LIKE 'probabilistic%') AS probabilistic_links,
    AVG(match_confidence) AS avg_confidence,
    MIN(first_seen) AS first_seen,
    MAX(last_seen) AS last_seen,
    CURRENT_TIMESTAMP(),
    CURRENT_TIMESTAMP()
  FROM `ssi_shadow.identity_graph`
  WHERE is_active = TRUE
  GROUP BY canonical_id;

  SELECT CONCAT('Clusters updated: ', @@row_count) AS log_message;

  -- ========================================================================
  -- Cleanup temp tables
  -- ========================================================================
  DROP TABLE IF EXISTS temp_email_matches;
  DROP TABLE IF EXISTS temp_phone_matches;
  DROP TABLE IF EXISTS temp_fbp_matches;
  DROP TABLE IF EXISTS temp_session_matches;

  -- Log completion
  SELECT CONCAT(
    'Identity stitching completed. Run: ', run_id,
    ', Duration: ', TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), start_time, SECOND), 's',
    ', Rows processed: ', rows_processed
  ) AS log_message;

END;

-- ============================================================================
-- Schedule this procedure to run daily
-- ============================================================================
-- Run in Cloud Scheduler or BigQuery scheduled queries:
-- CALL `project.ssi_shadow.stitch_identities`();
