#!/bin/bash
# =============================================================================
# S.S.I. SHADOW - Pub/Sub Setup Script
# =============================================================================
# Configura a infraestrutura de Pub/Sub no GCP para event decoupling
#
# Arquitetura:
#   Worker (Edge) → Pub/Sub (raw-events) → Cloud Function → BigQuery
#
# Uso:
#   ./setup_pubsub.sh --project=my-project --region=us-central1
#
# Requer:
#   - gcloud CLI instalado e autenticado
#   - Permissões: Pub/Sub Admin, Cloud Functions Developer
# =============================================================================

set -e

# =============================================================================
# CONFIGURAÇÃO
# =============================================================================

# Defaults
PROJECT_ID=""
REGION="us-central1"
TOPIC_NAME="raw-events"
SUBSCRIPTION_NAME="raw-events-consumer"
DEAD_LETTER_TOPIC="raw-events-dlq"
FUNCTION_NAME="pubsub-consumer"
FUNCTION_MEMORY="512MB"
FUNCTION_TIMEOUT="60s"
MAX_INSTANCES=100
MIN_INSTANCES=0
BQ_DATASET="ssi_shadow"
BQ_TABLE="events_raw"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# =============================================================================
# PARSE ARGUMENTS
# =============================================================================

for arg in "$@"; do
  case $arg in
    --project=*)
      PROJECT_ID="${arg#*=}"
      shift
      ;;
    --region=*)
      REGION="${arg#*=}"
      shift
      ;;
    --topic=*)
      TOPIC_NAME="${arg#*=}"
      shift
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --help)
      echo "Usage: $0 [options]"
      echo ""
      echo "Options:"
      echo "  --project=PROJECT_ID    GCP Project ID (required)"
      echo "  --region=REGION         GCP Region (default: us-central1)"
      echo "  --topic=TOPIC_NAME      Pub/Sub topic name (default: raw-events)"
      echo "  --dry-run               Show commands without executing"
      echo "  --help                  Show this help message"
      exit 0
      ;;
    *)
      echo "Unknown option: $arg"
      exit 1
      ;;
  esac
done

# Validate required args
if [ -z "$PROJECT_ID" ]; then
  echo -e "${RED}Error: --project is required${NC}"
  echo "Usage: $0 --project=my-project"
  exit 1
fi

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

run_cmd() {
  if [ "$DRY_RUN" = true ]; then
    echo -e "${YELLOW}[DRY-RUN]${NC} $*"
  else
    echo -e "${GREEN}[RUNNING]${NC} $*"
    eval "$*"
  fi
}

log_info() {
  echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
  echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
  echo -e "${RED}[ERROR]${NC} $1"
}

# =============================================================================
# MAIN SETUP
# =============================================================================

echo ""
echo "============================================"
echo "  S.S.I. SHADOW - Pub/Sub Setup"
echo "============================================"
echo ""
echo "Project:      $PROJECT_ID"
echo "Region:       $REGION"
echo "Topic:        $TOPIC_NAME"
echo "Subscription: $SUBSCRIPTION_NAME"
echo ""

# Set project
log_info "Setting GCP project..."
run_cmd "gcloud config set project $PROJECT_ID"

# Enable APIs
log_info "Enabling required APIs..."
run_cmd "gcloud services enable pubsub.googleapis.com"
run_cmd "gcloud services enable cloudfunctions.googleapis.com"
run_cmd "gcloud services enable cloudbuild.googleapis.com"
run_cmd "gcloud services enable bigquery.googleapis.com"

# =============================================================================
# CREATE PUB/SUB TOPICS
# =============================================================================

log_info "Creating Pub/Sub topic: $TOPIC_NAME..."
if gcloud pubsub topics describe $TOPIC_NAME --project=$PROJECT_ID &>/dev/null; then
  log_warn "Topic $TOPIC_NAME already exists, skipping..."
else
  run_cmd "gcloud pubsub topics create $TOPIC_NAME \
    --project=$PROJECT_ID \
    --message-retention-duration=7d \
    --labels=env=production,app=ssi-shadow"
fi

log_info "Creating Dead Letter Queue topic: $DEAD_LETTER_TOPIC..."
if gcloud pubsub topics describe $DEAD_LETTER_TOPIC --project=$PROJECT_ID &>/dev/null; then
  log_warn "DLQ topic $DEAD_LETTER_TOPIC already exists, skipping..."
else
  run_cmd "gcloud pubsub topics create $DEAD_LETTER_TOPIC \
    --project=$PROJECT_ID \
    --message-retention-duration=14d \
    --labels=env=production,app=ssi-shadow,type=dlq"
fi

# =============================================================================
# CREATE PUB/SUB SUBSCRIPTION
# =============================================================================

log_info "Creating Pub/Sub subscription: $SUBSCRIPTION_NAME..."
if gcloud pubsub subscriptions describe $SUBSCRIPTION_NAME --project=$PROJECT_ID &>/dev/null; then
  log_warn "Subscription $SUBSCRIPTION_NAME already exists, skipping..."
else
  run_cmd "gcloud pubsub subscriptions create $SUBSCRIPTION_NAME \
    --project=$PROJECT_ID \
    --topic=$TOPIC_NAME \
    --ack-deadline=60 \
    --message-retention-duration=7d \
    --expiration-period=never \
    --dead-letter-topic=$DEAD_LETTER_TOPIC \
    --max-delivery-attempts=5 \
    --min-retry-delay=10s \
    --max-retry-delay=600s \
    --enable-message-ordering \
    --labels=env=production,app=ssi-shadow"
fi

# =============================================================================
# CREATE SERVICE ACCOUNT (for Cloud Function)
# =============================================================================

SA_NAME="pubsub-consumer-sa"
SA_EMAIL="$SA_NAME@$PROJECT_ID.iam.gserviceaccount.com"

log_info "Creating service account: $SA_NAME..."
if gcloud iam service-accounts describe $SA_EMAIL --project=$PROJECT_ID &>/dev/null; then
  log_warn "Service account already exists, skipping..."
else
  run_cmd "gcloud iam service-accounts create $SA_NAME \
    --project=$PROJECT_ID \
    --display-name='Pub/Sub Consumer Service Account' \
    --description='Service account for Pub/Sub consumer Cloud Function'"
fi

# Grant permissions
log_info "Granting IAM permissions..."
run_cmd "gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member=serviceAccount:$SA_EMAIL \
  --role=roles/bigquery.dataEditor \
  --condition=None"

run_cmd "gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member=serviceAccount:$SA_EMAIL \
  --role=roles/pubsub.subscriber \
  --condition=None"

run_cmd "gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member=serviceAccount:$SA_EMAIL \
  --role=roles/monitoring.metricWriter \
  --condition=None"

# =============================================================================
# DEPLOY CLOUD FUNCTION
# =============================================================================

log_info "Deploying Cloud Function: $FUNCTION_NAME..."

FUNCTION_DIR="$(dirname "$0")/../functions"

if [ ! -f "$FUNCTION_DIR/pubsub_consumer.py" ]; then
  log_error "pubsub_consumer.py not found in $FUNCTION_DIR"
  exit 1
fi

# Create requirements.txt for function
cat > "$FUNCTION_DIR/requirements-pubsub.txt" << EOF
functions-framework==3.*
google-cloud-bigquery>=3.0.0
google-cloud-monitoring>=2.0.0
prometheus-client>=0.17.0
flask>=2.0.0
EOF

run_cmd "gcloud functions deploy $FUNCTION_NAME \
  --project=$PROJECT_ID \
  --region=$REGION \
  --runtime=python311 \
  --trigger-topic=$TOPIC_NAME \
  --entry-point=handle_pubsub_message \
  --source=$FUNCTION_DIR \
  --memory=$FUNCTION_MEMORY \
  --timeout=$FUNCTION_TIMEOUT \
  --max-instances=$MAX_INSTANCES \
  --min-instances=$MIN_INSTANCES \
  --service-account=$SA_EMAIL \
  --set-env-vars=GCP_PROJECT_ID=$PROJECT_ID,BQ_DATASET=$BQ_DATASET,BQ_TABLE=$BQ_TABLE,BATCH_SIZE=100,BATCH_TIMEOUT_MS=1000 \
  --labels=env=production,app=ssi-shadow"

# =============================================================================
# CREATE ALERTS
# =============================================================================

log_info "Creating monitoring alerts..."

# Alert for high consumer lag
cat > /tmp/consumer-lag-alert.json << EOF
{
  "displayName": "Pub/Sub Consumer Lag High",
  "combiner": "OR",
  "conditions": [
    {
      "displayName": "Unacked messages > 10000",
      "conditionThreshold": {
        "filter": "resource.type=\"pubsub_subscription\" AND metric.type=\"pubsub.googleapis.com/subscription/num_undelivered_messages\" AND resource.labels.subscription_id=\"$SUBSCRIPTION_NAME\"",
        "comparison": "COMPARISON_GT",
        "thresholdValue": 10000,
        "duration": "300s",
        "aggregations": [
          {
            "alignmentPeriod": "60s",
            "perSeriesAligner": "ALIGN_MEAN"
          }
        ]
      }
    }
  ],
  "alertStrategy": {
    "autoClose": "604800s"
  },
  "notificationChannels": []
}
EOF

# Alert for DLQ messages
cat > /tmp/dlq-alert.json << EOF
{
  "displayName": "Pub/Sub DLQ Messages Present",
  "combiner": "OR",
  "conditions": [
    {
      "displayName": "DLQ has messages",
      "conditionThreshold": {
        "filter": "resource.type=\"pubsub_topic\" AND metric.type=\"pubsub.googleapis.com/topic/message_sizes\" AND resource.labels.topic_id=\"$DEAD_LETTER_TOPIC\"",
        "comparison": "COMPARISON_GT",
        "thresholdValue": 0,
        "duration": "60s",
        "aggregations": [
          {
            "alignmentPeriod": "60s",
            "perSeriesAligner": "ALIGN_COUNT"
          }
        ]
      }
    }
  ],
  "alertStrategy": {
    "autoClose": "604800s"
  },
  "notificationChannels": []
}
EOF

log_info "Alerts created (configure notification channels in GCP Console)"

# =============================================================================
# OUTPUT SUMMARY
# =============================================================================

echo ""
echo "============================================"
echo "  Setup Complete!"
echo "============================================"
echo ""
echo "Resources created:"
echo "  - Topic: projects/$PROJECT_ID/topics/$TOPIC_NAME"
echo "  - DLQ Topic: projects/$PROJECT_ID/topics/$DEAD_LETTER_TOPIC"
echo "  - Subscription: projects/$PROJECT_ID/subscriptions/$SUBSCRIPTION_NAME"
echo "  - Cloud Function: $FUNCTION_NAME"
echo "  - Service Account: $SA_EMAIL"
echo ""
echo "Worker configuration:"
echo "  Add to wrangler.toml:"
echo ""
echo "  [vars]"
echo "  USE_PUBSUB = \"true\""
echo "  PUBSUB_TOPIC = \"$TOPIC_NAME\""
echo "  BIGQUERY_PROJECT_ID = \"$PROJECT_ID\""
echo ""
echo "Monitoring:"
echo "  - View topic: https://console.cloud.google.com/cloudpubsub/topic/detail/$TOPIC_NAME?project=$PROJECT_ID"
echo "  - View subscription: https://console.cloud.google.com/cloudpubsub/subscription/detail/$SUBSCRIPTION_NAME?project=$PROJECT_ID"
echo "  - View function logs: https://console.cloud.google.com/functions/details/$REGION/$FUNCTION_NAME?project=$PROJECT_ID"
echo ""
echo "Test:"
echo "  gcloud pubsub topics publish $TOPIC_NAME --message='{\"test\": true}' --project=$PROJECT_ID"
echo ""
