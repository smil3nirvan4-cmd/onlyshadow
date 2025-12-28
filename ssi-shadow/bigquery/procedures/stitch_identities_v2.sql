-- ============================================================================
-- S.S.I. SHADOW - Identity Stitching Procedure (Production-Grade)
-- ============================================================================
-- Version: 2.0.0
-- Author: SSI Shadow Team
-- Description: Resolve identities using Connected Components algorithm
-- 
-- Features:
--   - Deterministic matching (email, phone, external_id)
--   - Probabilistic matching (fbp cookie, session fingerprint)
--   - Connected Components via iterative label propagation
--   - Incremental processing (only new data each day)
--   - Merge logging for audit/compliance
--   - Performance optimized for large datasets
--
-- Run daily via Cloud Scheduler:
--   CALL `project.ssi_shadow.stitch_identities`();
--
-- Parameters:
--   @process_date: Date to process (default: yesterday)
--   @full_rebuild: If TRUE, rebuilds entire graph (slow, use sparingly)
-- ============================================================================

CREATE OR REPLACE PROCEDURE `ssi_shadow.stitch_identities`(
  IN process_date DATE DEFAULT NULL,
  IN full_rebuild BOOL DEFAULT FALSE
)
BEGIN
  -- ===========================================================================
  -- VARIABLES
  -- ===========================================================================
  DECLARE run_id STRING DEFAULT GENERATE_UUID();
  DECLARE start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP();
  DECLARE target_date DATE;
  DECLARE iteration INT64 DEFAULT 0;
  DECLARE max_iterations INT64 DEFAULT 20;  -- Prevent infinite loops
  DECLARE changes_made INT64 DEFAULT 1;
  DECLARE total_pairs_extracted INT64 DEFAULT 0;
  DECLARE total_edges_created INT64 DEFAULT 0;
  DECLARE total_nodes_updated INT64 DEFAULT 0;

  -- Set target date (default to yesterday for daily runs)
  SET target_date = COALESCE(process_date, DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY));

  -- ===========================================================================
  -- LOGGING TABLE (for monitoring)
  -- ===========================================================================
  CREATE TEMP TABLE IF NOT EXISTS stitch_log (
    log_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
    step STRING,
    message STRING,
    row_count INT64
  );

  INSERT INTO stitch_log (step, message) VALUES 
    ('START', FORMAT('Run ID: %s, Date: %s, Full Rebuild: %t', run_id, CAST(target_date AS STRING), full_rebuild));

  -- ===========================================================================
  -- STEP 1: EXTRACT IDENTIFIER PAIRS FROM EVENTS
  -- ===========================================================================
  -- Create edges between identifiers that appear together in the same event
  -- Each edge represents a potential identity link
  -- ===========================================================================

  INSERT INTO stitch_log (step, message) VALUES ('STEP 1', 'Extracting identifier pairs from events');

  -- Create temp table for today's identifier pairs
  CREATE OR REPLACE TEMP TABLE today_identifier_pairs AS
  WITH event_identifiers AS (
    -- Extract all non-null identifiers from events
    SELECT
      event_id,
      ssi_id,
      email_hash,
      phone_hash,
      fbp,
      external_id,
      -- Session fingerprint for probabilistic matching
      CASE 
        WHEN ip_hash IS NOT NULL AND user_agent IS NOT NULL 
        THEN SHA256(CONCAT(ip_hash, '|', user_agent, '|', COALESCE(timezone, '')))
        ELSE NULL 
      END AS session_fp,
      event_time,
      CASE 
        WHEN email_hash IS NOT NULL OR phone_hash IS NOT NULL OR external_id IS NOT NULL 
        THEN 'deterministic'
        ELSE 'probabilistic'
      END AS match_quality
    FROM `ssi_shadow.events_raw`
    WHERE 
      -- Date filter
      (full_rebuild = TRUE AND event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 365 DAY))
      OR (full_rebuild = FALSE AND DATE(event_time) = target_date)
  ),
  
  -- Generate all identifier pairs from the same event
  identifier_pairs AS (
    -- SSI ID <-> Email Hash (Deterministic, confidence 1.0)
    SELECT DISTINCT
      ssi_id AS id1,
      email_hash AS id2,
      'ssi_id' AS id1_type,
      'email_hash' AS id2_type,
      'deterministic' AS match_type,
      1.0 AS confidence,
      'email_match' AS match_source,
      MIN(event_time) OVER (PARTITION BY ssi_id, email_hash) AS first_seen,
      MAX(event_time) OVER (PARTITION BY ssi_id, email_hash) AS last_seen
    FROM event_identifiers
    WHERE email_hash IS NOT NULL
    
    UNION ALL
    
    -- SSI ID <-> Phone Hash (Deterministic, confidence 1.0)
    SELECT DISTINCT
      ssi_id AS id1,
      phone_hash AS id2,
      'ssi_id' AS id1_type,
      'phone_hash' AS id2_type,
      'deterministic' AS match_type,
      1.0 AS confidence,
      'phone_match' AS match_source,
      MIN(event_time) OVER (PARTITION BY ssi_id, phone_hash) AS first_seen,
      MAX(event_time) OVER (PARTITION BY ssi_id, phone_hash) AS last_seen
    FROM event_identifiers
    WHERE phone_hash IS NOT NULL
    
    UNION ALL
    
    -- SSI ID <-> External ID (Deterministic, confidence 1.0)
    SELECT DISTINCT
      ssi_id AS id1,
      external_id AS id2,
      'ssi_id' AS id1_type,
      'external_id' AS id2_type,
      'deterministic' AS match_type,
      1.0 AS confidence,
      'external_id_match' AS match_source,
      MIN(event_time) OVER (PARTITION BY ssi_id, external_id) AS first_seen,
      MAX(event_time) OVER (PARTITION BY ssi_id, external_id) AS last_seen
    FROM event_identifiers
    WHERE external_id IS NOT NULL
    
    UNION ALL
    
    -- SSI ID <-> FBP Cookie (Probabilistic, confidence 0.85)
    -- FBP persists for 90 days, high reliability
    SELECT DISTINCT
      ssi_id AS id1,
      fbp AS id2,
      'ssi_id' AS id1_type,
      'fbp' AS id2_type,
      'probabilistic_cookie' AS match_type,
      0.85 AS confidence,
      'fbp_match' AS match_source,
      MIN(event_time) OVER (PARTITION BY ssi_id, fbp) AS first_seen,
      MAX(event_time) OVER (PARTITION BY ssi_id, fbp) AS last_seen
    FROM event_identifiers
    WHERE fbp IS NOT NULL
      AND event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY)
    
    UNION ALL
    
    -- SSI ID <-> Session Fingerprint (Probabilistic, confidence 0.6)
    -- Same browser/device within session
    SELECT DISTINCT
      ssi_id AS id1,
      CAST(session_fp AS STRING) AS id2,
      'ssi_id' AS id1_type,
      'session_fp' AS id2_type,
      'probabilistic_session' AS match_type,
      0.6 AS confidence,
      'session_match' AS match_source,
      MIN(event_time) OVER (PARTITION BY ssi_id, session_fp) AS first_seen,
      MAX(event_time) OVER (PARTITION BY ssi_id, session_fp) AS last_seen
    FROM event_identifiers
    WHERE session_fp IS NOT NULL
      AND event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
  )
  SELECT * FROM identifier_pairs
  WHERE id1 IS NOT NULL AND id2 IS NOT NULL;

  SET total_pairs_extracted = (SELECT COUNT(*) FROM today_identifier_pairs);
  
  INSERT INTO stitch_log (step, message, row_count) VALUES 
    ('STEP 1', 'Identifier pairs extracted', total_pairs_extracted);

  -- ===========================================================================
  -- STEP 2: BUILD EDGES TABLE (UNDIRECTED GRAPH)
  -- ===========================================================================
  -- Create edges for the identity graph
  -- Each edge connects two identifiers that belong to the same person
  -- ===========================================================================

  INSERT INTO stitch_log (step, message) VALUES ('STEP 2', 'Building edge list for graph');

  -- Create edges from SSI_IDs that share common identifiers
  CREATE OR REPLACE TEMP TABLE identity_edges AS
  WITH shared_email AS (
    -- SSI IDs that share the same email
    SELECT DISTINCT
      a.id1 AS ssi_id_1,
      b.id1 AS ssi_id_2,
      'email_hash' AS shared_type,
      1.0 AS confidence,
      LEAST(a.first_seen, b.first_seen) AS first_seen,
      GREATEST(a.last_seen, b.last_seen) AS last_seen
    FROM today_identifier_pairs a
    JOIN today_identifier_pairs b
      ON a.id2 = b.id2 
      AND a.id2_type = 'email_hash'
      AND b.id2_type = 'email_hash'
      AND a.id1 < b.id1  -- Prevent duplicates and self-loops
  ),
  
  shared_phone AS (
    -- SSI IDs that share the same phone
    SELECT DISTINCT
      a.id1 AS ssi_id_1,
      b.id1 AS ssi_id_2,
      'phone_hash' AS shared_type,
      1.0 AS confidence,
      LEAST(a.first_seen, b.first_seen) AS first_seen,
      GREATEST(a.last_seen, b.last_seen) AS last_seen
    FROM today_identifier_pairs a
    JOIN today_identifier_pairs b
      ON a.id2 = b.id2 
      AND a.id2_type = 'phone_hash'
      AND b.id2_type = 'phone_hash'
      AND a.id1 < b.id1
  ),
  
  shared_external AS (
    -- SSI IDs that share the same external_id
    SELECT DISTINCT
      a.id1 AS ssi_id_1,
      b.id1 AS ssi_id_2,
      'external_id' AS shared_type,
      1.0 AS confidence,
      LEAST(a.first_seen, b.first_seen) AS first_seen,
      GREATEST(a.last_seen, b.last_seen) AS last_seen
    FROM today_identifier_pairs a
    JOIN today_identifier_pairs b
      ON a.id2 = b.id2 
      AND a.id2_type = 'external_id'
      AND b.id2_type = 'external_id'
      AND a.id1 < b.id1
  ),
  
  shared_fbp AS (
    -- SSI IDs that share the same FBP cookie
    SELECT DISTINCT
      a.id1 AS ssi_id_1,
      b.id1 AS ssi_id_2,
      'fbp' AS shared_type,
      0.85 AS confidence,
      LEAST(a.first_seen, b.first_seen) AS first_seen,
      GREATEST(a.last_seen, b.last_seen) AS last_seen
    FROM today_identifier_pairs a
    JOIN today_identifier_pairs b
      ON a.id2 = b.id2 
      AND a.id2_type = 'fbp'
      AND b.id2_type = 'fbp'
      AND a.id1 < b.id1
    -- Only if they occurred within 90 days of each other
    WHERE ABS(TIMESTAMP_DIFF(a.last_seen, b.last_seen, DAY)) <= 90
  ),
  
  shared_session AS (
    -- SSI IDs that share the same session fingerprint (within 30 min)
    SELECT DISTINCT
      a.id1 AS ssi_id_1,
      b.id1 AS ssi_id_2,
      'session_fp' AS shared_type,
      0.6 AS confidence,
      LEAST(a.first_seen, b.first_seen) AS first_seen,
      GREATEST(a.last_seen, b.last_seen) AS last_seen
    FROM today_identifier_pairs a
    JOIN today_identifier_pairs b
      ON a.id2 = b.id2 
      AND a.id2_type = 'session_fp'
      AND b.id2_type = 'session_fp'
      AND a.id1 < b.id1
    -- Only if they occurred within 30 minutes of each other
    WHERE ABS(TIMESTAMP_DIFF(a.last_seen, b.last_seen, MINUTE)) <= 30
  ),
  
  all_edges AS (
    SELECT * FROM shared_email
    UNION ALL
    SELECT * FROM shared_phone
    UNION ALL
    SELECT * FROM shared_external
    UNION ALL
    SELECT * FROM shared_fbp
    UNION ALL
    SELECT * FROM shared_session
  )
  -- Keep highest confidence edge between any pair
  SELECT
    ssi_id_1,
    ssi_id_2,
    ARRAY_AGG(shared_type ORDER BY confidence DESC LIMIT 1)[OFFSET(0)] AS shared_type,
    MAX(confidence) AS confidence,
    MIN(first_seen) AS first_seen,
    MAX(last_seen) AS last_seen
  FROM all_edges
  GROUP BY ssi_id_1, ssi_id_2;

  SET total_edges_created = (SELECT COUNT(*) FROM identity_edges);
  
  INSERT INTO stitch_log (step, message, row_count) VALUES 
    ('STEP 2', 'Identity edges created', total_edges_created);

  -- ===========================================================================
  -- STEP 3: CONNECTED COMPONENTS (ITERATIVE LABEL PROPAGATION)
  -- ===========================================================================
  -- Find connected components in the identity graph
  -- Each component = one canonical identity
  -- Uses iterative min-label propagation until convergence
  -- ===========================================================================

  INSERT INTO stitch_log (step, message) VALUES ('STEP 3', 'Computing connected components');

  -- Initialize nodes: each SSI ID starts as its own component (label = itself)
  CREATE OR REPLACE TEMP TABLE node_labels AS
  SELECT DISTINCT ssi_id, ssi_id AS component_label
  FROM (
    SELECT ssi_id_1 AS ssi_id FROM identity_edges
    UNION DISTINCT
    SELECT ssi_id_2 AS ssi_id FROM identity_edges
  );

  -- Also add all SSI IDs from today's pairs that might not have edges
  INSERT INTO node_labels
  SELECT DISTINCT id1 AS ssi_id, id1 AS component_label
  FROM today_identifier_pairs
  WHERE id1_type = 'ssi_id'
    AND id1 NOT IN (SELECT ssi_id FROM node_labels);

  -- Iterative Label Propagation
  -- In each iteration, each node adopts the minimum label among itself and neighbors
  WHILE changes_made > 0 AND iteration < max_iterations DO
    SET iteration = iteration + 1;
    
    -- Compute new labels (minimum of current label and all neighbor labels)
    CREATE OR REPLACE TEMP TABLE new_labels AS
    WITH neighbor_labels AS (
      -- Get all neighbor labels through edges
      SELECT 
        n.ssi_id,
        n.component_label AS current_label,
        e.ssi_id_2 AS neighbor,
        n2.component_label AS neighbor_label
      FROM node_labels n
      JOIN identity_edges e ON n.ssi_id = e.ssi_id_1
      JOIN node_labels n2 ON e.ssi_id_2 = n2.ssi_id
      
      UNION ALL
      
      -- Edges are undirected, so check both directions
      SELECT 
        n.ssi_id,
        n.component_label AS current_label,
        e.ssi_id_1 AS neighbor,
        n2.component_label AS neighbor_label
      FROM node_labels n
      JOIN identity_edges e ON n.ssi_id = e.ssi_id_2
      JOIN node_labels n2 ON e.ssi_id_1 = n2.ssi_id
    ),
    min_labels AS (
      SELECT
        ssi_id,
        LEAST(current_label, MIN(neighbor_label)) AS new_label
      FROM neighbor_labels
      GROUP BY ssi_id, current_label
    )
    SELECT
      n.ssi_id,
      COALESCE(m.new_label, n.component_label) AS component_label
    FROM node_labels n
    LEFT JOIN min_labels m ON n.ssi_id = m.ssi_id;

    -- Count changes
    SET changes_made = (
      SELECT COUNT(*)
      FROM node_labels old
      JOIN new_labels new ON old.ssi_id = new.ssi_id
      WHERE old.component_label != new.component_label
    );

    -- Update labels
    CREATE OR REPLACE TEMP TABLE node_labels AS
    SELECT * FROM new_labels;

    INSERT INTO stitch_log (step, message, row_count) VALUES 
      ('STEP 3', FORMAT('Iteration %d completed', iteration), changes_made);
  END WHILE;

  INSERT INTO stitch_log (step, message, row_count) VALUES 
    ('STEP 3', FORMAT('Converged after %d iterations', iteration), 
     (SELECT COUNT(DISTINCT component_label) FROM node_labels));

  -- ===========================================================================
  -- STEP 4: UPDATE IDENTITY GRAPH TABLE
  -- ===========================================================================
  -- Merge new component assignments into the identity_graph table
  -- Handle both new links and updates to existing links
  -- ===========================================================================

  INSERT INTO stitch_log (step, message) VALUES ('STEP 4', 'Updating identity_graph table');

  -- Use the minimum ssi_id in each component as the canonical_id
  CREATE OR REPLACE TEMP TABLE canonical_mapping AS
  SELECT
    ssi_id,
    component_label AS canonical_id,
    MIN(component_label) OVER (PARTITION BY component_label) AS final_canonical_id
  FROM node_labels;

  -- Update the canonical mapping to use the actual minimum
  CREATE OR REPLACE TEMP TABLE final_mapping AS
  SELECT DISTINCT
    ssi_id,
    final_canonical_id AS canonical_id
  FROM canonical_mapping;

  -- Prepare records for identity_graph
  CREATE OR REPLACE TEMP TABLE new_graph_records AS
  SELECT
    fm.canonical_id,
    fm.ssi_id AS linked_id,
    'ssi_id' AS id_type,
    COALESCE(ie.shared_type, 'self') AS match_type,
    COALESCE(ie.confidence, 1.0) AS match_confidence,
    COALESCE(ie.shared_type, 'identity') AS match_source,
    COALESCE(ie.first_seen, CURRENT_TIMESTAMP()) AS first_seen,
    COALESCE(ie.last_seen, CURRENT_TIMESTAMP()) AS last_seen,
    1 AS link_count
  FROM final_mapping fm
  LEFT JOIN identity_edges ie 
    ON (fm.ssi_id = ie.ssi_id_1 OR fm.ssi_id = ie.ssi_id_2);

  -- Also add the identifier pairs (email_hash, phone_hash, etc.) to the graph
  INSERT INTO new_graph_records
  SELECT DISTINCT
    fm.canonical_id,
    ip.id2 AS linked_id,
    ip.id2_type AS id_type,
    ip.match_type,
    ip.confidence AS match_confidence,
    ip.match_source,
    ip.first_seen,
    ip.last_seen,
    1 AS link_count
  FROM today_identifier_pairs ip
  JOIN final_mapping fm ON ip.id1 = fm.ssi_id
  WHERE ip.id2_type != 'session_fp';  -- Don't store session fingerprints

  -- MERGE into identity_graph (UPSERT logic)
  MERGE `ssi_shadow.identity_graph` AS target
  USING (
    SELECT
      canonical_id,
      linked_id,
      id_type,
      -- Use highest confidence match type for this pair
      ARRAY_AGG(match_type ORDER BY match_confidence DESC LIMIT 1)[OFFSET(0)] AS match_type,
      MAX(match_confidence) AS match_confidence,
      ARRAY_AGG(match_source ORDER BY match_confidence DESC LIMIT 1)[OFFSET(0)] AS match_source,
      MIN(first_seen) AS first_seen,
      MAX(last_seen) AS last_seen,
      SUM(link_count) AS link_count
    FROM new_graph_records
    GROUP BY canonical_id, linked_id, id_type
  ) AS source
  ON target.canonical_id = source.canonical_id 
    AND target.linked_id = source.linked_id
    AND target.id_type = source.id_type
  
  WHEN MATCHED THEN UPDATE SET
    match_confidence = GREATEST(target.match_confidence, source.match_confidence),
    match_type = CASE 
      WHEN source.match_confidence > target.match_confidence THEN source.match_type
      ELSE target.match_type
    END,
    last_seen = GREATEST(target.last_seen, source.last_seen),
    link_count = target.link_count + source.link_count,
    updated_at = CURRENT_TIMESTAMP()
  
  WHEN NOT MATCHED THEN INSERT (
    canonical_id, linked_id, id_type, match_type, match_confidence,
    match_source, first_seen, last_seen, link_count, created_at, updated_at, is_active
  ) VALUES (
    source.canonical_id, source.linked_id, source.id_type, source.match_type,
    source.match_confidence, source.match_source, source.first_seen, source.last_seen,
    source.link_count, CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP(), TRUE
  );

  SET total_nodes_updated = @@row_count;
  
  INSERT INTO stitch_log (step, message, row_count) VALUES 
    ('STEP 4', 'Identity graph updated', total_nodes_updated);

  -- ===========================================================================
  -- STEP 5: TRANSITIVE CLOSURE (MERGE COMPONENTS)
  -- ===========================================================================
  -- Handle cases where new edges connect previously separate components
  -- This merges the smaller component into the larger one
  -- ===========================================================================

  INSERT INTO stitch_log (step, message) VALUES ('STEP 5', 'Performing transitive closure on existing graph');

  -- Find canonical IDs that should be merged (they share a linked_id)
  CREATE OR REPLACE TEMP TABLE merge_candidates AS
  SELECT DISTINCT
    g1.canonical_id AS old_canonical_id,
    g2.canonical_id AS new_canonical_id
  FROM `ssi_shadow.identity_graph` g1
  JOIN `ssi_shadow.identity_graph` g2
    ON g1.linked_id = g2.linked_id
    AND g1.id_type = g2.id_type
    AND g1.canonical_id > g2.canonical_id  -- Merge into smaller ID
  WHERE g1.is_active = TRUE AND g2.is_active = TRUE;

  -- Log merges
  INSERT INTO `ssi_shadow.identity_merge_log` (
    merge_id, source_canonical_id, target_canonical_id,
    merge_reason, match_confidence, identifiers_moved, triggered_by
  )
  SELECT
    GENERATE_UUID(),
    old_canonical_id,
    new_canonical_id,
    'transitive_closure',
    1.0,
    (SELECT COUNT(*) FROM `ssi_shadow.identity_graph` 
     WHERE canonical_id = old_canonical_id AND is_active = TRUE),
    'stitch_identities_procedure'
  FROM merge_candidates;

  -- Update canonical IDs
  UPDATE `ssi_shadow.identity_graph`
  SET 
    canonical_id = (
      SELECT MIN(new_canonical_id) 
      FROM merge_candidates 
      WHERE merge_candidates.old_canonical_id = identity_graph.canonical_id
    ),
    updated_at = CURRENT_TIMESTAMP()
  WHERE canonical_id IN (SELECT old_canonical_id FROM merge_candidates);

  INSERT INTO stitch_log (step, message, row_count) VALUES 
    ('STEP 5', 'Components merged', (SELECT COUNT(*) FROM merge_candidates));

  -- ===========================================================================
  -- STEP 6: UPDATE EVENTS_RAW WITH CANONICAL IDs
  -- ===========================================================================
  -- Backfill canonical_id on events that don't have one yet
  -- ===========================================================================

  INSERT INTO stitch_log (step, message) VALUES ('STEP 6', 'Updating events with canonical IDs');

  -- Update today's events
  UPDATE `ssi_shadow.events_raw` e
  SET canonical_id = (
    SELECT g.canonical_id
    FROM `ssi_shadow.identity_graph` g
    WHERE g.linked_id = e.ssi_id
      AND g.id_type = 'ssi_id'
      AND g.is_active = TRUE
    ORDER BY g.match_confidence DESC
    LIMIT 1
  )
  WHERE DATE(e.event_time) = target_date
    AND e.canonical_id IS NULL;

  INSERT INTO stitch_log (step, message, row_count) VALUES 
    ('STEP 6', 'Events updated with canonical IDs', @@row_count);

  -- ===========================================================================
  -- STEP 7: UPDATE IDENTITY_CLUSTERS TABLE
  -- ===========================================================================
  -- Rebuild the clusters summary table
  -- ===========================================================================

  INSERT INTO stitch_log (step, message) VALUES ('STEP 7', 'Rebuilding identity clusters');

  -- Delete old clusters for affected canonical IDs
  DELETE FROM `ssi_shadow.identity_clusters`
  WHERE canonical_id IN (
    SELECT DISTINCT canonical_id FROM final_mapping
  );

  -- Insert updated clusters
  INSERT INTO `ssi_shadow.identity_clusters` (
    canonical_id, cluster_size, ssi_ids, email_hashes, phone_hashes,
    fbp_ids, external_ids, has_email, has_phone, has_external_id,
    deterministic_links, probabilistic_links, avg_confidence,
    first_seen, last_seen, created_at, updated_at
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
    COUNTIF(match_type IN ('deterministic', 'email_hash', 'phone_hash', 'external_id')) AS deterministic_links,
    COUNTIF(match_type LIKE 'probabilistic%') AS probabilistic_links,
    AVG(match_confidence) AS avg_confidence,
    MIN(first_seen) AS first_seen,
    MAX(last_seen) AS last_seen,
    CURRENT_TIMESTAMP() AS created_at,
    CURRENT_TIMESTAMP() AS updated_at
  FROM `ssi_shadow.identity_graph`
  WHERE is_active = TRUE
    AND canonical_id IN (SELECT DISTINCT canonical_id FROM final_mapping)
  GROUP BY canonical_id;

  INSERT INTO stitch_log (step, message, row_count) VALUES 
    ('STEP 7', 'Clusters rebuilt', @@row_count);

  -- ===========================================================================
  -- STEP 8: CLEANUP & STATISTICS
  -- ===========================================================================

  INSERT INTO stitch_log (step, message) VALUES ('STEP 8', 'Generating statistics');

  -- Generate run statistics
  CREATE OR REPLACE TEMP TABLE run_stats AS
  SELECT
    run_id,
    target_date AS process_date,
    full_rebuild,
    start_time,
    CURRENT_TIMESTAMP() AS end_time,
    TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), start_time, SECOND) AS duration_seconds,
    total_pairs_extracted,
    total_edges_created,
    total_nodes_updated,
    iteration AS convergence_iterations,
    (SELECT COUNT(DISTINCT canonical_id) FROM `ssi_shadow.identity_graph` WHERE is_active = TRUE) AS total_identities,
    (SELECT COUNT(*) FROM `ssi_shadow.identity_graph` WHERE is_active = TRUE) AS total_links,
    (SELECT AVG(cluster_size) FROM `ssi_shadow.identity_clusters`) AS avg_cluster_size,
    (SELECT MAX(cluster_size) FROM `ssi_shadow.identity_clusters`) AS max_cluster_size,
    (SELECT COUNT(*) FROM `ssi_shadow.identity_clusters` WHERE cluster_size > 1) AS multi_device_identities;

  -- Output final log
  INSERT INTO stitch_log (step, message) 
  SELECT 'COMPLETE', FORMAT(
    'Duration: %ds | Pairs: %d | Edges: %d | Nodes: %d | Iterations: %d | Total Identities: %d',
    duration_seconds, total_pairs_extracted, total_edges_created, 
    total_nodes_updated, convergence_iterations, total_identities
  )
  FROM run_stats;

  -- Output results (visible in BigQuery console)
  SELECT * FROM stitch_log ORDER BY log_time;
  SELECT * FROM run_stats;

  -- Cleanup temp tables
  DROP TABLE IF EXISTS today_identifier_pairs;
  DROP TABLE IF EXISTS identity_edges;
  DROP TABLE IF EXISTS node_labels;
  DROP TABLE IF EXISTS new_labels;
  DROP TABLE IF EXISTS canonical_mapping;
  DROP TABLE IF EXISTS final_mapping;
  DROP TABLE IF EXISTS new_graph_records;
  DROP TABLE IF EXISTS merge_candidates;
  DROP TABLE IF EXISTS stitch_log;
  DROP TABLE IF EXISTS run_stats;

END;


-- ============================================================================
-- HELPER PROCEDURE: Get canonical ID for an identifier
-- ============================================================================
CREATE OR REPLACE PROCEDURE `ssi_shadow.get_canonical_id`(
  IN identifier STRING,
  IN identifier_type STRING,  -- 'ssi_id', 'email_hash', 'phone_hash', 'fbp', 'external_id'
  OUT canonical_id STRING
)
BEGIN
  SET canonical_id = (
    SELECT g.canonical_id
    FROM `ssi_shadow.identity_graph` g
    WHERE g.linked_id = identifier
      AND g.id_type = identifier_type
      AND g.is_active = TRUE
    ORDER BY g.match_confidence DESC
    LIMIT 1
  );
END;


-- ============================================================================
-- HELPER PROCEDURE: Get all identifiers for a canonical ID
-- ============================================================================
CREATE OR REPLACE PROCEDURE `ssi_shadow.get_identity_cluster`(
  IN p_canonical_id STRING
)
BEGIN
  SELECT
    linked_id,
    id_type,
    match_type,
    match_confidence,
    first_seen,
    last_seen,
    link_count
  FROM `ssi_shadow.identity_graph`
  WHERE canonical_id = p_canonical_id
    AND is_active = TRUE
  ORDER BY match_confidence DESC, id_type;
END;


-- ============================================================================
-- SCHEDULED QUERY SETUP (Run in BigQuery Console)
-- ============================================================================
-- 
-- 1. Go to BigQuery Console > Scheduled Queries
-- 2. Create new scheduled query
-- 3. Set schedule: Daily at 2:00 AM UTC
-- 4. Query:
--    CALL `your-project.ssi_shadow.stitch_identities`(NULL, FALSE);
--
-- For manual full rebuild (use sparingly):
--    CALL `your-project.ssi_shadow.stitch_identities`(NULL, TRUE);
--
-- ============================================================================


-- ============================================================================
-- MONITORING QUERIES
-- ============================================================================

-- Check identity resolution coverage
-- SELECT
--   DATE(event_time) AS date,
--   COUNT(*) AS total_events,
--   COUNTIF(canonical_id IS NOT NULL) AS resolved_events,
--   ROUND(COUNTIF(canonical_id IS NOT NULL) / COUNT(*) * 100, 2) AS resolution_rate
-- FROM `ssi_shadow.events_raw`
-- WHERE event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
-- GROUP BY 1
-- ORDER BY 1 DESC;

-- Check cluster quality
-- SELECT
--   CASE 
--     WHEN cluster_size = 1 THEN 'Single ID'
--     WHEN cluster_size BETWEEN 2 AND 5 THEN '2-5 IDs'
--     WHEN cluster_size BETWEEN 6 AND 10 THEN '6-10 IDs'
--     ELSE '10+ IDs'
--   END AS cluster_category,
--   COUNT(*) AS num_clusters,
--   SUM(CASE WHEN has_email THEN 1 ELSE 0 END) AS with_email,
--   SUM(CASE WHEN has_phone THEN 1 ELSE 0 END) AS with_phone,
--   ROUND(AVG(avg_confidence), 3) AS avg_confidence
-- FROM `ssi_shadow.identity_clusters`
-- GROUP BY 1
-- ORDER BY 1;

-- Recent merge activity
-- SELECT
--   DATE(merge_time) AS date,
--   COUNT(*) AS merges,
--   SUM(identifiers_moved) AS total_ids_merged
-- FROM `ssi_shadow.identity_merge_log`
-- WHERE merge_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
-- GROUP BY 1
-- ORDER BY 1 DESC;
