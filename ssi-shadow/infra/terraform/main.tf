# =============================================================================
# S.S.I. ORACLE — TERRAFORM INFRASTRUCTURE AS CODE
# =============================================================================
# 
# Provê infraestrutura completa em:
# - GCP: BigQuery, Vertex AI, Cloud Functions, Cloud Scheduler
# - Cloudflare: Workers, KV Namespaces
#
# USO:
# 1. terraform init
# 2. terraform plan -var-file="prod.tfvars"
# 3. terraform apply -var-file="prod.tfvars"
#
# =============================================================================

terraform {
  required_version = ">= 1.5.0"
  
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.0"
    }
  }
  
  # Backend remoto (recomendado para produção)
  # backend "gcs" {
  #   bucket = "ssi-oracle-terraform-state"
  #   prefix = "terraform/state"
  # }
}

# =============================================================================
# VARIÁVEIS
# =============================================================================

variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "region" {
  description = "GCP Region"
  type        = string
  default     = "us-central1"
}

variable "environment" {
  description = "Environment (dev, staging, prod)"
  type        = string
  default     = "prod"
}

variable "cloudflare_account_id" {
  description = "Cloudflare Account ID"
  type        = string
}

variable "cloudflare_api_token" {
  description = "Cloudflare API Token"
  type        = string
  sensitive   = true
}

variable "domain" {
  description = "Domain for SSI endpoint"
  type        = string
}

variable "meta_pixel_id" {
  description = "Meta Pixel ID"
  type        = string
}

variable "meta_access_token" {
  description = "Meta CAPI Access Token"
  type        = string
  sensitive   = true
}

variable "google_ads_customer_id" {
  description = "Google Ads Customer ID"
  type        = string
  default     = ""
}

variable "telegram_bot_token" {
  description = "Telegram Bot Token for alerts"
  type        = string
  sensitive   = true
  default     = ""
}

variable "telegram_chat_id" {
  description = "Telegram Chat ID for alerts"
  type        = string
  default     = ""
}

# =============================================================================
# PROVIDERS
# =============================================================================

provider "google" {
  project = var.project_id
  region  = var.region
}

provider "cloudflare" {
  api_token = var.cloudflare_api_token
}

# =============================================================================
# GCP: BIGQUERY
# =============================================================================

resource "google_bigquery_dataset" "ssi_oracle" {
  dataset_id    = "ssi_oracle"
  friendly_name = "SSI Oracle Dataset"
  description   = "Data lake for SSI Oracle tracking system"
  location      = "US"
  
  labels = {
    environment = var.environment
    managed_by  = "terraform"
  }
  
  # Retenção de 365 dias para tabelas sem partição
  default_table_expiration_ms = 31536000000  # 365 dias
}

# Tabela: Events
resource "google_bigquery_table" "events" {
  dataset_id = google_bigquery_dataset.ssi_oracle.dataset_id
  table_id   = "events"
  
  time_partitioning {
    type  = "DAY"
    field = "event_time"
  }
  
  clustering = ["event_name", "ssi_id"]
  
  schema = file("${path.module}/../bigquery/schemas/events_schema.json")
  
  labels = {
    environment = var.environment
  }
}

# Tabela: Sessions
resource "google_bigquery_table" "sessions" {
  dataset_id = google_bigquery_dataset.ssi_oracle.dataset_id
  table_id   = "sessions"
  
  time_partitioning {
    type  = "DAY"
    field = "session_start"
  }
  
  clustering = ["ssi_id"]
  
  schema = file("${path.module}/../bigquery/schemas/sessions_schema.json")
  
  labels = {
    environment = var.environment
  }
}

# Tabela: Users
resource "google_bigquery_table" "users" {
  dataset_id = google_bigquery_dataset.ssi_oracle.dataset_id
  table_id   = "users"
  
  clustering = ["ssi_id"]
  
  schema = file("${path.module}/../bigquery/schemas/users_schema.json")
  
  labels = {
    environment = var.environment
  }
}

# Tabela: Model Predictions
resource "google_bigquery_table" "predictions" {
  dataset_id = google_bigquery_dataset.ssi_oracle.dataset_id
  table_id   = "predictions"
  
  time_partitioning {
    type  = "DAY"
    field = "predicted_at"
  }
  
  schema = <<EOF
[
  {"name": "ssi_id", "type": "STRING", "mode": "REQUIRED"},
  {"name": "model_name", "type": "STRING", "mode": "REQUIRED"},
  {"name": "model_version", "type": "STRING", "mode": "REQUIRED"},
  {"name": "predicted_ltv", "type": "FLOAT64", "mode": "NULLABLE"},
  {"name": "predicted_intent", "type": "FLOAT64", "mode": "NULLABLE"},
  {"name": "predicted_churn", "type": "FLOAT64", "mode": "NULLABLE"},
  {"name": "confidence", "type": "FLOAT64", "mode": "NULLABLE"},
  {"name": "predicted_at", "type": "TIMESTAMP", "mode": "REQUIRED"}
]
EOF
  
  labels = {
    environment = var.environment
  }
}

# Tabela: Identity Graph
resource "google_bigquery_table" "identity_graph" {
  dataset_id = google_bigquery_dataset.ssi_oracle.dataset_id
  table_id   = "identity_graph"
  
  schema = <<EOF
[
  {"name": "ssi_id", "type": "STRING", "mode": "REQUIRED"},
  {"name": "fbp_ids", "type": "STRING", "mode": "REPEATED"},
  {"name": "fbc_ids", "type": "STRING", "mode": "REPEATED"},
  {"name": "canvas_hashes", "type": "STRING", "mode": "REPEATED"},
  {"name": "webgl_hashes", "type": "STRING", "mode": "REPEATED"},
  {"name": "email_hashes", "type": "STRING", "mode": "REPEATED"},
  {"name": "phone_hashes", "type": "STRING", "mode": "REPEATED"},
  {"name": "related_ssi_ids", "type": "STRING", "mode": "REPEATED"},
  {"name": "master_ssi_id", "type": "STRING", "mode": "NULLABLE"},
  {"name": "confidence_score", "type": "FLOAT64", "mode": "NULLABLE"},
  {"name": "first_seen", "type": "TIMESTAMP", "mode": "REQUIRED"},
  {"name": "last_seen", "type": "TIMESTAMP", "mode": "REQUIRED"},
  {"name": "updated_at", "type": "TIMESTAMP", "mode": "REQUIRED"}
]
EOF
  
  labels = {
    environment = var.environment
  }
}

# =============================================================================
# GCP: VERTEX AI
# =============================================================================

# Dataset para treinamento
resource "google_vertex_ai_dataset" "ltv_dataset" {
  display_name        = "ssi-ltv-training-data"
  metadata_schema_uri = "gs://google-cloud-aiplatform/schema/dataset/metadata/tabular_1.0.0.yaml"
  region              = var.region
  
  labels = {
    environment = var.environment
    model_type  = "ltv"
  }
}

resource "google_vertex_ai_dataset" "intent_dataset" {
  display_name        = "ssi-intent-training-data"
  metadata_schema_uri = "gs://google-cloud-aiplatform/schema/dataset/metadata/tabular_1.0.0.yaml"
  region              = var.region
  
  labels = {
    environment = var.environment
    model_type  = "intent"
  }
}

# Feature Store (opcional, para features em tempo real)
# resource "google_vertex_ai_featurestore" "ssi_features" {
#   name   = "ssi_oracle_features"
#   region = var.region
#   
#   online_serving_config {
#     fixed_node_count = 1
#   }
# }

# =============================================================================
# GCP: CLOUD STORAGE
# =============================================================================

resource "google_storage_bucket" "ssi_oracle" {
  name     = "${var.project_id}-ssi-oracle"
  location = "US"
  
  uniform_bucket_level_access = true
  
  versioning {
    enabled = true
  }
  
  lifecycle_rule {
    condition {
      age = 90
    }
    action {
      type          = "SetStorageClass"
      storage_class = "NEARLINE"
    }
  }
  
  lifecycle_rule {
    condition {
      age = 365
    }
    action {
      type          = "SetStorageClass"
      storage_class = "COLDLINE"
    }
  }
  
  labels = {
    environment = var.environment
  }
}

# Bucket para modelos ONNX
resource "google_storage_bucket" "models" {
  name     = "${var.project_id}-ssi-models"
  location = "US"
  
  uniform_bucket_level_access = true
  
  versioning {
    enabled = true
  }
  
  labels = {
    environment = var.environment
  }
}

# =============================================================================
# GCP: SERVICE ACCOUNT
# =============================================================================

resource "google_service_account" "ssi_oracle" {
  account_id   = "ssi-oracle-sa"
  display_name = "SSI Oracle Service Account"
  description  = "Service account for SSI Oracle system"
}

# Permissões
resource "google_project_iam_member" "bigquery_admin" {
  project = var.project_id
  role    = "roles/bigquery.admin"
  member  = "serviceAccount:${google_service_account.ssi_oracle.email}"
}

resource "google_project_iam_member" "vertex_ai_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.ssi_oracle.email}"
}

resource "google_project_iam_member" "storage_admin" {
  project = var.project_id
  role    = "roles/storage.admin"
  member  = "serviceAccount:${google_service_account.ssi_oracle.email}"
}

# Gerar chave JSON para o Worker
resource "google_service_account_key" "ssi_oracle_key" {
  service_account_id = google_service_account.ssi_oracle.name
}

# =============================================================================
# GCP: CLOUD SCHEDULER (para jobs periódicos)
# =============================================================================

# Job: Retreinar modelo LTV (semanal)
resource "google_cloud_scheduler_job" "retrain_ltv" {
  name        = "ssi-retrain-ltv-weekly"
  description = "Retreina modelo LTV semanalmente"
  schedule    = "0 3 * * 0"  # Domingo às 3AM
  time_zone   = "America/Sao_Paulo"
  
  http_target {
    http_method = "POST"
    uri         = "https://${var.region}-${var.project_id}.cloudfunctions.net/trigger-ltv-training"
    
    oidc_token {
      service_account_email = google_service_account.ssi_oracle.email
    }
  }
}

# Job: Identity Graph Update (a cada 4 horas)
resource "google_cloud_scheduler_job" "identity_graph" {
  name        = "ssi-identity-graph-update"
  description = "Atualiza Identity Graph"
  schedule    = "0 */4 * * *"  # A cada 4 horas
  time_zone   = "America/Sao_Paulo"
  
  http_target {
    http_method = "POST"
    uri         = "https://${var.region}-${var.project_id}.cloudfunctions.net/update-identity-graph"
    
    oidc_token {
      service_account_email = google_service_account.ssi_oracle.email
    }
  }
}

# Job: Kill Switch Check (a cada hora)
resource "google_cloud_scheduler_job" "kill_switch" {
  name        = "ssi-kill-switch-check"
  description = "Verifica IVT e aciona kill switch se necessário"
  schedule    = "0 * * * *"  # A cada hora
  time_zone   = "America/Sao_Paulo"
  
  http_target {
    http_method = "POST"
    uri         = "https://${var.region}-${var.project_id}.cloudfunctions.net/check-kill-switch"
    
    oidc_token {
      service_account_email = google_service_account.ssi_oracle.email
    }
  }
}

# =============================================================================
# CLOUDFLARE: KV NAMESPACES
# =============================================================================

resource "cloudflare_workers_kv_namespace" "ssi_sessions" {
  account_id = var.cloudflare_account_id
  title      = "ssi-sessions-${var.environment}"
}

resource "cloudflare_workers_kv_namespace" "ssi_identities" {
  account_id = var.cloudflare_account_id
  title      = "ssi-identities-${var.environment}"
}

resource "cloudflare_workers_kv_namespace" "ssi_cache" {
  account_id = var.cloudflare_account_id
  title      = "ssi-cache-${var.environment}"
}

resource "cloudflare_workers_kv_namespace" "ssi_models" {
  account_id = var.cloudflare_account_id
  title      = "ssi-models-${var.environment}"
}

# =============================================================================
# CLOUDFLARE: WORKER
# =============================================================================

resource "cloudflare_worker_script" "ssi_gateway" {
  account_id = var.cloudflare_account_id
  name       = "ssi-gateway-${var.environment}"
  content    = file("${path.module}/../workers/gateway/dist/index.js")
  
  # KV Bindings
  kv_namespace_binding {
    name         = "SSI_SESSIONS"
    namespace_id = cloudflare_workers_kv_namespace.ssi_sessions.id
  }
  
  kv_namespace_binding {
    name         = "SSI_IDENTITIES"
    namespace_id = cloudflare_workers_kv_namespace.ssi_identities.id
  }
  
  kv_namespace_binding {
    name         = "SSI_CACHE"
    namespace_id = cloudflare_workers_kv_namespace.ssi_cache.id
  }
  
  kv_namespace_binding {
    name         = "SSI_MODELS"
    namespace_id = cloudflare_workers_kv_namespace.ssi_models.id
  }
  
  # Secrets (variáveis de ambiente)
  secret_text_binding {
    name = "META_PIXEL_ID"
    text = var.meta_pixel_id
  }
  
  secret_text_binding {
    name = "META_ACCESS_TOKEN"
    text = var.meta_access_token
  }
  
  secret_text_binding {
    name = "GCP_SERVICE_ACCOUNT_KEY"
    text = base64decode(google_service_account_key.ssi_oracle_key.private_key)
  }
}

# Route para o Worker
resource "cloudflare_worker_route" "ssi_route" {
  zone_id     = data.cloudflare_zone.domain.id
  pattern     = "ssi.${var.domain}/*"
  script_name = cloudflare_worker_script.ssi_gateway.name
}

data "cloudflare_zone" "domain" {
  name = var.domain
}

# =============================================================================
# OUTPUTS
# =============================================================================

output "bigquery_dataset_id" {
  value       = google_bigquery_dataset.ssi_oracle.dataset_id
  description = "BigQuery Dataset ID"
}

output "service_account_email" {
  value       = google_service_account.ssi_oracle.email
  description = "Service Account Email"
}

output "storage_bucket" {
  value       = google_storage_bucket.ssi_oracle.name
  description = "GCS Bucket for data"
}

output "models_bucket" {
  value       = google_storage_bucket.models.name
  description = "GCS Bucket for ONNX models"
}

output "kv_sessions_id" {
  value       = cloudflare_workers_kv_namespace.ssi_sessions.id
  description = "Cloudflare KV Sessions Namespace ID"
}

output "kv_identities_id" {
  value       = cloudflare_workers_kv_namespace.ssi_identities.id
  description = "Cloudflare KV Identities Namespace ID"
}

output "worker_url" {
  value       = "https://ssi.${var.domain}"
  description = "SSI Gateway Worker URL"
}

output "setup_commands" {
  value = <<-EOT
    
    ============================================================
    SSI ORACLE - SETUP COMPLETO
    ============================================================
    
    1. Salvar Service Account Key:
       terraform output -raw service_account_key | base64 -d > sa-key.json
    
    2. Configurar BigQuery:
       bq query --use_legacy_sql=false < ../bigquery/schemas/schema.sql
    
    3. Deploy Ghost Script:
       Adicione ao seu site:
       <script src="https://ssi.${var.domain}/ghost.js"></script>
    
    4. Testar endpoint:
       curl -X POST https://ssi.${var.domain}/ingest \
         -H "Content-Type: application/json" \
         -d '{"event_name":"PageView","url":"https://example.com"}'
    
    ============================================================
  EOT
  description = "Setup commands after apply"
}
