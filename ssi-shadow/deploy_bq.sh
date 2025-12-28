#!/bin/bash
# =============================================================================
# S.S.I. SHADOW - BigQuery Deploy Script
# =============================================================================
# Automated deployment of BigQuery resources for SSI Shadow
#
# Usage: ./deploy_bq.sh <PROJECT_ID> [LOCATION] [--dry-run]
#
# Examples:
#   ./deploy_bq.sh my-gcp-project
#   ./deploy_bq.sh my-gcp-project US
#   ./deploy_bq.sh my-gcp-project southamerica-east1
#   ./deploy_bq.sh my-gcp-project US --dry-run
#
# Prerequisites:
#   - gcloud CLI installed and authenticated
#   - bq CLI installed (comes with gcloud)
#   - Project must exist and user must have BigQuery Admin role
#
# Author: SSI Shadow Team
# Version: 1.0.0
# =============================================================================

set -e  # Exit on error

# =============================================================================
# Configuration
# =============================================================================

PROJECT_ID="${1:-}"
LOCATION="${2:-US}"
DRY_RUN=false
DATASET="ssi_shadow"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# =============================================================================
# Functions
# =============================================================================

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_step() {
    echo -e "\n${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}▶${NC} $1"
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

run_bq() {
    local description="$1"
    shift
    
    if [ "$DRY_RUN" = true ]; then
        log_info "[DRY-RUN] Would execute: bq $*"
        return 0
    fi
    
    log_info "$description"
    if bq "$@" 2>&1; then
        log_success "$description - Done"
        return 0
    else
        log_warning "$description - May already exist or failed"
        return 0  # Don't fail on errors (table may exist)
    fi
}

run_query() {
    local description="$1"
    local query="$2"
    
    if [ "$DRY_RUN" = true ]; then
        log_info "[DRY-RUN] Would execute query: ${description}"
        echo "$query" | head -c 200
        echo "..."
        return 0
    fi
    
    log_info "$description"
    if bq query --use_legacy_sql=false --project_id="$PROJECT_ID" "$query" 2>&1; then
        log_success "$description - Done"
        return 0
    else
        log_warning "$description - May already exist"
        return 0
    fi
}

show_usage() {
    echo "Usage: $0 <PROJECT_ID> [LOCATION] [--dry-run]"
    echo ""
    echo "Arguments:"
    echo "  PROJECT_ID    GCP Project ID (required)"
    echo "  LOCATION      BigQuery dataset location (default: US)"
    echo "                Options: US, EU, asia-east1, southamerica-east1, etc."
    echo "  --dry-run     Show what would be executed without making changes"
    echo ""
    echo "Examples:"
    echo "  $0 my-gcp-project"
    echo "  $0 my-gcp-project US"
    echo "  $0 my-gcp-project southamerica-east1 --dry-run"
    echo ""
    echo "Prerequisites:"
    echo "  1. gcloud CLI installed: https://cloud.google.com/sdk/docs/install"
    echo "  2. Authenticated: gcloud auth login"
    echo "  3. Project exists: gcloud projects describe PROJECT_ID"
    echo "  4. BigQuery API enabled: gcloud services enable bigquery.googleapis.com"
    exit 1
}

check_prerequisites() {
    log_step "Checking Prerequisites"
    
    # Check gcloud
    if ! command -v gcloud &> /dev/null; then
        log_error "gcloud CLI not found. Please install: https://cloud.google.com/sdk/docs/install"
        exit 1
    fi
    log_success "gcloud CLI found"
    
    # Check bq
    if ! command -v bq &> /dev/null; then
        log_error "bq CLI not found. Please install: gcloud components install bq"
        exit 1
    fi
    log_success "bq CLI found"
    
    # Check authentication
    if ! gcloud auth list 2>&1 | grep -q "ACTIVE"; then
        log_error "Not authenticated. Run: gcloud auth login"
        exit 1
    fi
    log_success "gcloud authenticated"
    
    # Check project exists
    if ! gcloud projects describe "$PROJECT_ID" &> /dev/null; then
        log_error "Project '$PROJECT_ID' not found or no access"
        exit 1
    fi
    log_success "Project '$PROJECT_ID' found"
    
    # Check BigQuery API
    if ! gcloud services list --enabled --project="$PROJECT_ID" 2>&1 | grep -q "bigquery.googleapis.com"; then
        log_warning "BigQuery API may not be enabled. Enabling..."
        if [ "$DRY_RUN" = false ]; then
            gcloud services enable bigquery.googleapis.com --project="$PROJECT_ID"
        fi
    fi
    log_success "BigQuery API enabled"
}

# =============================================================================
# Parse Arguments
# =============================================================================

for arg in "$@"; do
    case $arg in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --help|-h)
            show_usage
            ;;
    esac
done

if [ -z "$PROJECT_ID" ]; then
    log_error "PROJECT_ID is required"
    show_usage
fi

# =============================================================================
# Main Deployment
# =============================================================================

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║           S.S.I. SHADOW - BigQuery Deployment                ║"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║  Project:  $PROJECT_ID"
echo "║  Dataset:  $DATASET"
echo "║  Location: $LOCATION"
echo "║  Dry Run:  $DRY_RUN"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# Check prerequisites
check_prerequisites

# =============================================================================
# Step 1: Create Dataset
# =============================================================================

log_step "Step 1: Creating Dataset"

run_bq "Creating dataset ${DATASET}" \
    mk \
    --dataset \
    --location="$LOCATION" \
    --description="S.S.I. SHADOW - Server-Side Intelligence for Optimized Ads" \
    --label=team:marketing \
    --label=system:ssi_shadow \
    "${PROJECT_ID}:${DATASET}"

# =============================================================================
# Step 2: Create events_raw Table
# =============================================================================

log_step "Step 2: Creating events_raw Table (Main Events)"

EVENTS_RAW_SQL="
CREATE TABLE IF NOT EXISTS \`${PROJECT_ID}.${DATASET}.events_raw\` (
  -- Core Identifiers
  event_id STRING NOT NULL OPTIONS(description='Unique event identifier'),
  ssi_id STRING NOT NULL OPTIONS(description='SSI Shadow user identifier'),
  session_id STRING OPTIONS(description='Session identifier'),
  canonical_id STRING OPTIONS(description='Resolved identity from identity graph'),
  organization_id STRING OPTIONS(description='Organization/tenant identifier'),
  
  -- Event Information
  event_name STRING NOT NULL OPTIONS(description='Event type: PageView, Purchase, Lead, etc'),
  event_time TIMESTAMP NOT NULL OPTIONS(description='When the event occurred'),
  event_source STRING DEFAULT 'ghost' OPTIONS(description='Source: ghost, server, import'),
  
  -- Click IDs (Ad Platform)
  fbclid STRING OPTIONS(description='Facebook Click ID'),
  gclid STRING OPTIONS(description='Google Click ID'),
  ttclid STRING OPTIONS(description='TikTok Click ID'),
  msclkid STRING OPTIONS(description='Microsoft Click ID'),
  fbc STRING OPTIONS(description='Facebook Click Cookie'),
  fbp STRING OPTIONS(description='Facebook Browser Cookie'),
  
  -- Page Information
  url STRING OPTIONS(description='Full page URL'),
  referrer STRING OPTIONS(description='HTTP referrer'),
  title STRING OPTIONS(description='Page title'),
  
  -- User Data (Hashed PII)
  email_hash STRING OPTIONS(description='SHA-256 hash of email'),
  phone_hash STRING OPTIONS(description='SHA-256 hash of phone'),
  external_id STRING OPTIONS(description='External user ID'),
  
  -- Device Information
  user_agent STRING OPTIONS(description='Browser User-Agent'),
  ip_country STRING OPTIONS(description='Country from IP'),
  ip_city STRING OPTIONS(description='City from IP'),
  language STRING OPTIONS(description='Browser language'),
  
  -- E-commerce
  value FLOAT64 OPTIONS(description='Transaction value'),
  currency STRING DEFAULT 'BRL' OPTIONS(description='Currency code'),
  content_ids ARRAY<STRING> OPTIONS(description='Product IDs'),
  content_type STRING OPTIONS(description='Content type'),
  content_category STRING OPTIONS(description='Product category'),
  num_items INT64 OPTIONS(description='Number of items'),
  order_id STRING OPTIONS(description='Order ID'),
  
  -- Trust Score
  trust_score FLOAT64 OPTIONS(description='Trust score 0.0 to 1.0'),
  trust_action STRING OPTIONS(description='Action: allow, challenge, block'),
  block_reasons ARRAY<STRING> OPTIONS(description='Reasons for blocking'),
  
  -- ML Predictions
  ltv_tier STRING OPTIONS(description='LTV tier: VIP, High, Medium, Low'),
  churn_risk STRING OPTIONS(description='Churn risk: Critical, High, Medium, Low'),
  propensity_score FLOAT64 OPTIONS(description='Purchase propensity 0-1'),
  
  -- Bid Optimization
  bid_strategy STRING OPTIONS(description='Bid strategy applied'),
  bid_multiplier FLOAT64 OPTIONS(description='Bid multiplier'),
  
  -- CAPI Status
  platforms_sent ARRAY<STRING> OPTIONS(description='Platforms event was sent to'),
  platform_success INT64 OPTIONS(description='Number of successful sends'),
  platform_responses JSON OPTIONS(description='Platform response details'),
  
  -- Metadata
  processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP() OPTIONS(description='When processed'),
  worker_version STRING OPTIONS(description='Worker version')
)
PARTITION BY DATE(event_time)
CLUSTER BY ssi_id, event_name, organization_id
OPTIONS (
  description='Raw events from SSI Shadow tracking',
  labels=[('team', 'marketing'), ('system', 'ssi_shadow')],
  partition_expiration_days=365,
  require_partition_filter=false
);
"

run_query "Creating events_raw table" "$EVENTS_RAW_SQL"

# =============================================================================
# Step 3: Create identity_graph Table
# =============================================================================

log_step "Step 3: Creating identity_graph Table"

IDENTITY_GRAPH_SQL="
CREATE TABLE IF NOT EXISTS \`${PROJECT_ID}.${DATASET}.identity_graph\` (
  canonical_id STRING NOT NULL OPTIONS(description='Primary user identifier'),
  linked_id STRING NOT NULL OPTIONS(description='Linked identifier'),
  id_type STRING NOT NULL OPTIONS(description='Type: ssi_id, email_hash, phone_hash, fbp'),
  match_type STRING NOT NULL OPTIONS(description='Match type: deterministic, probabilistic'),
  match_confidence FLOAT64 OPTIONS(description='Confidence 0.0 to 1.0'),
  match_source STRING OPTIONS(description='Source: email_login, checkout, form'),
  first_seen TIMESTAMP OPTIONS(description='First time linked'),
  last_seen TIMESTAMP OPTIONS(description='Last time seen'),
  link_count INT64 DEFAULT 1 OPTIONS(description='Times this link was observed'),
  organization_id STRING OPTIONS(description='Organization ID'),
  is_active BOOL DEFAULT TRUE OPTIONS(description='Link is active'),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
CLUSTER BY canonical_id, linked_id, id_type
OPTIONS (
  description='Identity resolution graph for cross-device tracking'
);
"

run_query "Creating identity_graph table" "$IDENTITY_GRAPH_SQL"

# =============================================================================
# Step 4: Create identity_clusters Table
# =============================================================================

log_step "Step 4: Creating identity_clusters Table"

IDENTITY_CLUSTERS_SQL="
CREATE TABLE IF NOT EXISTS \`${PROJECT_ID}.${DATASET}.identity_clusters\` (
  canonical_id STRING NOT NULL OPTIONS(description='Canonical identifier'),
  cluster_size INT64 OPTIONS(description='Number of linked identifiers'),
  ssi_ids ARRAY<STRING> OPTIONS(description='All SSI IDs'),
  email_hashes ARRAY<STRING> OPTIONS(description='All email hashes'),
  phone_hashes ARRAY<STRING> OPTIONS(description='All phone hashes'),
  fbp_ids ARRAY<STRING> OPTIONS(description='All FBP cookies'),
  external_ids ARRAY<STRING> OPTIONS(description='All external IDs'),
  has_email BOOL OPTIONS(description='Has email'),
  has_phone BOOL OPTIONS(description='Has phone'),
  has_external_id BOOL OPTIONS(description='Has external ID'),
  deterministic_links INT64 OPTIONS(description='Deterministic link count'),
  probabilistic_links INT64 OPTIONS(description='Probabilistic link count'),
  avg_confidence FLOAT64 OPTIONS(description='Average confidence'),
  first_seen TIMESTAMP OPTIONS(description='First activity'),
  last_seen TIMESTAMP OPTIONS(description='Last activity'),
  organization_id STRING OPTIONS(description='Organization ID'),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
CLUSTER BY canonical_id
OPTIONS (
  description='Resolved identity clusters'
);
"

run_query "Creating identity_clusters table" "$IDENTITY_CLUSTERS_SQL"

# =============================================================================
# Step 5: Create user_profiles Table
# =============================================================================

log_step "Step 5: Creating user_profiles Table"

USER_PROFILES_SQL="
CREATE TABLE IF NOT EXISTS \`${PROJECT_ID}.${DATASET}.user_profiles\` (
  canonical_id STRING NOT NULL OPTIONS(description='Canonical user identifier'),
  organization_id STRING OPTIONS(description='Organization ID'),
  
  -- Identifiers
  primary_ssi_id STRING OPTIONS(description='Primary SSI ID'),
  primary_email_hash STRING OPTIONS(description='Primary email hash'),
  primary_phone_hash STRING OPTIONS(description='Primary phone hash'),
  external_ids ARRAY<STRING> OPTIONS(description='External IDs'),
  
  -- RFM Metrics
  first_seen TIMESTAMP OPTIONS(description='First activity'),
  last_seen TIMESTAMP OPTIONS(description='Last activity'),
  days_since_first_seen INT64 OPTIONS(description='Days since first activity'),
  days_since_last_seen INT64 OPTIONS(description='Days since last activity'),
  total_sessions INT64 DEFAULT 0 OPTIONS(description='Total sessions'),
  total_pageviews INT64 DEFAULT 0 OPTIONS(description='Total pageviews'),
  total_events INT64 DEFAULT 0 OPTIONS(description='Total events'),
  total_purchases INT64 DEFAULT 0 OPTIONS(description='Total purchases'),
  total_revenue FLOAT64 DEFAULT 0.0 OPTIONS(description='Total revenue'),
  avg_order_value FLOAT64 OPTIONS(description='Average order value'),
  
  -- RFM Scores
  rfm_recency_score INT64 OPTIONS(description='Recency score 1-5'),
  rfm_frequency_score INT64 OPTIONS(description='Frequency score 1-5'),
  rfm_monetary_score INT64 OPTIONS(description='Monetary score 1-5'),
  rfm_segment STRING OPTIONS(description='RFM segment'),
  
  -- ML Predictions
  ltv_90d FLOAT64 OPTIONS(description='Predicted 90-day LTV'),
  ltv_tier STRING OPTIONS(description='LTV tier'),
  churn_probability FLOAT64 OPTIONS(description='Churn probability'),
  churn_risk STRING OPTIONS(description='Churn risk level'),
  propensity_score FLOAT64 OPTIONS(description='Purchase propensity'),
  propensity_tier STRING OPTIONS(description='Propensity tier'),
  
  -- Device Info
  primary_device_type STRING OPTIONS(description='Primary device'),
  is_multi_device BOOL OPTIONS(description='Multi-device user'),
  device_count INT64 OPTIONS(description='Device count'),
  
  -- Metadata
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
CLUSTER BY canonical_id, organization_id
OPTIONS (
  description='Consolidated user profiles with RFM and ML predictions'
);
"

run_query "Creating user_profiles table" "$USER_PROFILES_SQL"

# =============================================================================
# Step 6: Create ml_predictions Table
# =============================================================================

log_step "Step 6: Creating ml_predictions Table"

ML_PREDICTIONS_SQL="
CREATE TABLE IF NOT EXISTS \`${PROJECT_ID}.${DATASET}.ml_predictions\` (
  canonical_id STRING NOT NULL OPTIONS(description='User identifier'),
  organization_id STRING OPTIONS(description='Organization ID'),
  
  -- LTV Predictions
  ltv_30d FLOAT64 OPTIONS(description='Predicted 30-day LTV'),
  ltv_90d FLOAT64 OPTIONS(description='Predicted 90-day LTV'),
  ltv_365d FLOAT64 OPTIONS(description='Predicted 365-day LTV'),
  ltv_tier STRING OPTIONS(description='LTV tier'),
  
  -- Churn Predictions
  churn_probability FLOAT64 OPTIONS(description='Churn probability'),
  churn_risk STRING OPTIONS(description='Churn risk level'),
  days_to_churn INT64 OPTIONS(description='Predicted days to churn'),
  
  -- Propensity Predictions
  propensity_score FLOAT64 OPTIONS(description='Purchase propensity'),
  propensity_tier STRING OPTIONS(description='Propensity tier'),
  
  -- Model Info
  model_version STRING OPTIONS(description='Model version'),
  prediction_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP() OPTIONS(description='When predicted'),
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
PARTITION BY DATE(updated_at)
CLUSTER BY canonical_id, organization_id
OPTIONS (
  description='ML model predictions',
  partition_expiration_days=90
);
"

run_query "Creating ml_predictions table" "$ML_PREDICTIONS_SQL"

# =============================================================================
# Step 7: Create platform_requests Table (CAPI Audit Log)
# =============================================================================

log_step "Step 7: Creating platform_requests Table (CAPI Audit)"

PLATFORM_REQUESTS_SQL="
CREATE TABLE IF NOT EXISTS \`${PROJECT_ID}.${DATASET}.platform_requests\` (
  request_id STRING NOT NULL OPTIONS(description='Request identifier'),
  event_id STRING NOT NULL OPTIONS(description='Related event ID'),
  organization_id STRING OPTIONS(description='Organization ID'),
  platform STRING NOT NULL OPTIONS(description='Platform: meta, google, tiktok, etc'),
  
  -- Request Details
  endpoint STRING OPTIONS(description='API endpoint called'),
  method STRING OPTIONS(description='HTTP method'),
  request_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP() OPTIONS(description='When requested'),
  
  -- Response Details
  status STRING OPTIONS(description='Status: success, error, retry'),
  status_code INT64 OPTIONS(description='HTTP status code'),
  response_time_ms INT64 OPTIONS(description='Response time in ms'),
  error_message STRING OPTIONS(description='Error message if failed'),
  
  -- Retry Info
  attempt_number INT64 DEFAULT 1 OPTIONS(description='Attempt number'),
  will_retry BOOL DEFAULT FALSE OPTIONS(description='Will retry'),
  
  -- Metadata
  worker_version STRING OPTIONS(description='Worker version'),
  timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
PARTITION BY DATE(timestamp)
CLUSTER BY platform, organization_id, status
OPTIONS (
  description='CAPI request audit log',
  partition_expiration_days=30
);
"

run_query "Creating platform_requests table" "$PLATFORM_REQUESTS_SQL"

# =============================================================================
# Step 8: Create Views
# =============================================================================

log_step "Step 8: Creating Dashboard Views"

# Overview Metrics View
OVERVIEW_VIEW_SQL="
CREATE OR REPLACE VIEW \`${PROJECT_ID}.${DATASET}.v_dashboard_overview\` AS
WITH today_metrics AS (
  SELECT
    organization_id,
    COUNT(*) as events,
    COUNT(DISTINCT ssi_id) as unique_users,
    SUM(CASE WHEN event_name = 'Purchase' THEN value ELSE 0 END) as revenue,
    COUNTIF(event_name = 'Purchase') as conversions,
    AVG(trust_score) as avg_trust_score,
    COUNTIF(trust_action = 'block') as blocked
  FROM \`${PROJECT_ID}.${DATASET}.events_raw\`
  WHERE DATE(event_time) = CURRENT_DATE()
  GROUP BY organization_id
),
yesterday_metrics AS (
  SELECT
    organization_id,
    COUNT(*) as events,
    COUNT(DISTINCT ssi_id) as unique_users,
    SUM(CASE WHEN event_name = 'Purchase' THEN value ELSE 0 END) as revenue,
    COUNTIF(event_name = 'Purchase') as conversions
  FROM \`${PROJECT_ID}.${DATASET}.events_raw\`
  WHERE DATE(event_time) = DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY)
  GROUP BY organization_id
)
SELECT
  t.organization_id,
  t.events as events_today,
  y.events as events_yesterday,
  t.unique_users as users_today,
  y.unique_users as users_yesterday,
  t.revenue as revenue_today,
  y.revenue as revenue_yesterday,
  t.conversions as conversions_today,
  y.conversions as conversions_yesterday,
  t.avg_trust_score,
  SAFE_DIVIDE(t.blocked, t.events) as block_rate,
  CURRENT_TIMESTAMP() as updated_at
FROM today_metrics t
LEFT JOIN yesterday_metrics y USING (organization_id);
"

run_query "Creating v_dashboard_overview view" "$OVERVIEW_VIEW_SQL"

# Funnel View
FUNNEL_VIEW_SQL="
CREATE OR REPLACE VIEW \`${PROJECT_ID}.${DATASET}.v_conversion_funnel\` AS
SELECT
  organization_id,
  DATE(event_time) as date,
  COUNTIF(event_name = 'PageView') as pageviews,
  COUNTIF(event_name = 'ViewContent') as product_views,
  COUNTIF(event_name = 'AddToCart') as add_to_cart,
  COUNTIF(event_name = 'InitiateCheckout') as checkouts,
  COUNTIF(event_name = 'Purchase') as purchases,
  COUNT(DISTINCT ssi_id) as unique_users,
  SUM(CASE WHEN event_name = 'Purchase' THEN value ELSE 0 END) as revenue
FROM \`${PROJECT_ID}.${DATASET}.events_raw\`
WHERE event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
GROUP BY organization_id, date
ORDER BY date DESC;
"

run_query "Creating v_conversion_funnel view" "$FUNNEL_VIEW_SQL"

# Platform Status View
PLATFORM_VIEW_SQL="
CREATE OR REPLACE VIEW \`${PROJECT_ID}.${DATASET}.v_platform_status\` AS
SELECT
  organization_id,
  platform,
  COUNT(*) as total_requests,
  COUNTIF(status = 'success') as successful,
  COUNTIF(status = 'error') as failed,
  SAFE_DIVIDE(COUNTIF(status = 'success'), COUNT(*)) as success_rate,
  AVG(response_time_ms) as avg_latency_ms,
  APPROX_QUANTILES(response_time_ms, 100)[OFFSET(99)] as p99_latency_ms,
  MAX(CASE WHEN status = 'success' THEN timestamp END) as last_success,
  MAX(CASE WHEN status = 'error' THEN error_message END) as last_error
FROM \`${PROJECT_ID}.${DATASET}.platform_requests\`
WHERE timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
GROUP BY organization_id, platform;
"

run_query "Creating v_platform_status view" "$PLATFORM_VIEW_SQL"

# =============================================================================
# Step 9: Verify Deployment
# =============================================================================

log_step "Step 9: Verifying Deployment"

if [ "$DRY_RUN" = false ]; then
    echo ""
    log_info "Listing created tables..."
    bq ls --project_id="$PROJECT_ID" "${DATASET}"
    
    echo ""
    log_info "Table schemas:"
    for table in events_raw identity_graph identity_clusters user_profiles ml_predictions platform_requests; do
        echo ""
        log_info "Schema for ${table}:"
        bq show --schema --project_id="$PROJECT_ID" "${PROJECT_ID}:${DATASET}.${table}" 2>/dev/null | head -20 || log_warning "Table ${table} not found"
    done
fi

# =============================================================================
# Summary
# =============================================================================

log_step "Deployment Summary"

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                    DEPLOYMENT COMPLETE                       ║"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║  Project:     $PROJECT_ID"
echo "║  Dataset:     $DATASET"
echo "║  Location:    $LOCATION"
echo "║                                                              ║"
echo "║  Tables Created:                                             ║"
echo "║    ✓ events_raw         (partitioned by day)                ║"
echo "║    ✓ identity_graph                                         ║"
echo "║    ✓ identity_clusters                                      ║"
echo "║    ✓ user_profiles                                          ║"
echo "║    ✓ ml_predictions     (partitioned by day)                ║"
echo "║    ✓ platform_requests  (partitioned by day)                ║"
echo "║                                                              ║"
echo "║  Views Created:                                              ║"
echo "║    ✓ v_dashboard_overview                                   ║"
echo "║    ✓ v_conversion_funnel                                    ║"
echo "║    ✓ v_platform_status                                      ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

if [ "$DRY_RUN" = true ]; then
    log_warning "This was a DRY RUN - no changes were made"
    echo ""
fi

# =============================================================================
# Next Steps
# =============================================================================

echo "📋 Next Steps:"
echo ""
echo "1. Configure Worker to send events:"
echo "   export GCP_PROJECT_ID=$PROJECT_ID"
echo "   export BIGQUERY_DATASET=$DATASET"
echo ""
echo "2. Test with a sample event:"
echo "   bq query --use_legacy_sql=false \\"
echo "     \"INSERT INTO \\\`$PROJECT_ID.$DATASET.events_raw\\\` (event_id, ssi_id, event_name, event_time) VALUES ('test_001', 'ssi_test', 'PageView', CURRENT_TIMESTAMP())\""
echo ""
echo "3. Verify data:"
echo "   bq query --use_legacy_sql=false \\"
echo "     \"SELECT * FROM \\\`$PROJECT_ID.$DATASET.events_raw\\\` LIMIT 10\""
echo ""
echo "4. Deploy stored procedures (optional):"
echo "   bq query --use_legacy_sql=false < bigquery/procedures/stitch_identities.sql"
echo "   bq query --use_legacy_sql=false < bigquery/procedures/compute_user_profiles.sql"
echo ""

log_success "BigQuery deployment completed successfully! 🚀"
