-- ============================================================================
-- S.S.I. SHADOW - BigQuery Schema: identity_graph
-- ============================================================================
-- Identity resolution graph - links different identifiers to a canonical ID
-- Enables cross-device and cross-session user tracking
-- ============================================================================

CREATE TABLE IF NOT EXISTS `ssi_shadow.identity_graph` (
  -- ========================================================================
  -- Core Fields
  -- ========================================================================
  canonical_id STRING NOT NULL OPTIONS(description="Primary/canonical user identifier"),
  linked_id STRING NOT NULL OPTIONS(description="Linked identifier (ssi_id, email_hash, etc)"),
  
  -- ========================================================================
  -- Match Information
  -- ========================================================================
  id_type STRING NOT NULL OPTIONS(description="Type of linked_id: ssi_id, email_hash, phone_hash, fbp, external_id"),
  match_type STRING NOT NULL OPTIONS(description="How match was determined: deterministic, probabilistic_fbp, probabilistic_session"),
  match_confidence FLOAT64 OPTIONS(description="Confidence score 0.0 to 1.0"),
  match_source STRING OPTIONS(description="Source of match: email_login, checkout, form_submit, behavioral"),
  
  -- ========================================================================
  -- Temporal Data
  -- ========================================================================
  first_seen TIMESTAMP OPTIONS(description="First time this link was observed"),
  last_seen TIMESTAMP OPTIONS(description="Last time this link was observed"),
  link_count INT64 DEFAULT 1 OPTIONS(description="Number of times this link was observed"),
  
  -- ========================================================================
  -- Metadata
  -- ========================================================================
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
  is_active BOOL DEFAULT TRUE OPTIONS(description="Whether this link is still active"),
  
  -- ========================================================================
  -- Deduplication
  -- ========================================================================
  link_hash STRING OPTIONS(description="Hash of canonical_id + linked_id for deduplication")
)
CLUSTER BY canonical_id, linked_id, id_type
OPTIONS (
  description = 'Identity resolution graph for cross-device tracking'
);

-- ============================================================================
-- Table: identity_clusters
-- ============================================================================
-- Stores the resolved identity clusters with metadata
-- Updated by the stitch_identities procedure
-- ============================================================================

CREATE TABLE IF NOT EXISTS `ssi_shadow.identity_clusters` (
  -- ========================================================================
  -- Core Fields
  -- ========================================================================
  canonical_id STRING NOT NULL OPTIONS(description="Canonical/primary identifier for the cluster"),
  cluster_size INT64 OPTIONS(description="Number of linked identifiers"),
  
  -- ========================================================================
  -- Known Identifiers
  -- ========================================================================
  ssi_ids ARRAY<STRING> OPTIONS(description="All SSI IDs in this cluster"),
  email_hashes ARRAY<STRING> OPTIONS(description="All email hashes in this cluster"),
  phone_hashes ARRAY<STRING> OPTIONS(description="All phone hashes in this cluster"),
  fbp_ids ARRAY<STRING> OPTIONS(description="All FBP cookies in this cluster"),
  external_ids ARRAY<STRING> OPTIONS(description="All external IDs in this cluster"),
  
  -- ========================================================================
  -- Cluster Quality
  -- ========================================================================
  has_email BOOL OPTIONS(description="Cluster has at least one email"),
  has_phone BOOL OPTIONS(description="Cluster has at least one phone"),
  has_external_id BOOL OPTIONS(description="Cluster has external ID"),
  deterministic_links INT64 OPTIONS(description="Number of deterministic links"),
  probabilistic_links INT64 OPTIONS(description="Number of probabilistic links"),
  avg_confidence FLOAT64 OPTIONS(description="Average confidence of links"),
  
  -- ========================================================================
  -- Temporal Data
  -- ========================================================================
  first_seen TIMESTAMP OPTIONS(description="First activity in cluster"),
  last_seen TIMESTAMP OPTIONS(description="Last activity in cluster"),
  
  -- ========================================================================
  -- Metadata
  -- ========================================================================
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
CLUSTER BY canonical_id
OPTIONS (
  description = 'Resolved identity clusters'
);

-- ============================================================================
-- Table: identity_merge_log
-- ============================================================================
-- Audit log of identity merges for debugging and compliance
-- ============================================================================

CREATE TABLE IF NOT EXISTS `ssi_shadow.identity_merge_log` (
  merge_id STRING NOT NULL OPTIONS(description="Unique merge operation ID"),
  merge_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
  
  -- What was merged
  source_canonical_id STRING NOT NULL OPTIONS(description="ID being merged FROM"),
  target_canonical_id STRING NOT NULL OPTIONS(description="ID being merged INTO"),
  
  -- Why it was merged
  merge_reason STRING OPTIONS(description="Reason for merge: same_email, same_phone, same_fbp, same_session"),
  match_confidence FLOAT64 OPTIONS(description="Confidence of the merge"),
  
  -- Impact
  identifiers_moved INT64 OPTIONS(description="Number of identifiers moved"),
  events_updated INT64 OPTIONS(description="Number of events updated"),
  
  -- Metadata
  triggered_by STRING OPTIONS(description="What triggered the merge: procedure, manual, api")
)
PARTITION BY DATE(merge_time)
OPTIONS (
  description = 'Audit log of identity merges',
  partition_expiration_days = 90
);

-- ============================================================================
-- Sample Queries
-- ============================================================================

-- Get all identifiers for a canonical ID
-- SELECT *
-- FROM `project.ssi_shadow.identity_graph`
-- WHERE canonical_id = 'canonical_123'
-- ORDER BY match_confidence DESC;

-- Find canonical ID for an SSI ID
-- SELECT canonical_id
-- FROM `project.ssi_shadow.identity_graph`
-- WHERE linked_id = 'ssi_abc123'
--   AND id_type = 'ssi_id'
-- LIMIT 1;

-- Get cluster statistics
-- SELECT
--   COUNT(DISTINCT canonical_id) as total_clusters,
--   AVG(cluster_size) as avg_cluster_size,
--   SUM(CASE WHEN has_email THEN 1 ELSE 0 END) as clusters_with_email,
--   SUM(CASE WHEN cluster_size > 1 THEN 1 ELSE 0 END) as multi_device_clusters
-- FROM `project.ssi_shadow.identity_clusters`;
