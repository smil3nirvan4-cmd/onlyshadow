# S.S.I. SHADOW - BigQuery Data Lake

Data lake para armazenamento de eventos, identity graph e perfis de usuário.

## 📊 Arquitetura

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              BigQuery                                    │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐              │
│  │  events_raw  │───▶│identity_graph│───▶│user_profiles │              │
│  │  (partitioned)│    │              │    │  (RFM, LTV)  │              │
│  └──────────────┘    └──────────────┘    └──────────────┘              │
│         │                   │                   │                       │
│         ▼                   ▼                   ▼                       │
│  ┌──────────────────────────────────────────────────────┐              │
│  │                      Views                            │              │
│  │  • v_daily_events_summary  • v_rfm_distribution      │              │
│  │  • v_funnel_analysis       • v_bot_detection_stats   │              │
│  │  • v_capi_delivery_stats   • v_high_value_at_risk   │              │
│  └──────────────────────────────────────────────────────┘              │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

## 🚀 Setup Inicial

### 1. Criar Dataset

```bash
bq mk --dataset \
  --description "S.S.I. SHADOW - Server-Side Tracking" \
  --location US \
  your-project:ssi_shadow
```

### 2. Criar Tabelas

```bash
# Eventos raw
bq query --use_legacy_sql=false < schemas/events_raw.sql

# Identity Graph
bq query --use_legacy_sql=false < schemas/identity_graph.sql

# User Profiles
bq query --use_legacy_sql=false < schemas/user_profiles.sql
```

### 3. Criar Procedures

```bash
# Identity Stitching
bq query --use_legacy_sql=false < procedures/stitch_identities.sql

# User Profile Computation
bq query --use_legacy_sql=false < procedures/compute_user_profiles.sql
```

### 4. Criar Views

```bash
bq query --use_legacy_sql=false < views/dashboard_metrics.sql
```

### 5. Agendar Procedures

No BigQuery Console ou via API:

```sql
-- Executar diariamente às 02:00 UTC
-- Schedule > Create new scheduled query

-- Identity Stitching (rodar primeiro)
CALL `your-project.ssi_shadow.stitch_identities`();

-- User Profiles (rodar após identity stitching)
CALL `your-project.ssi_shadow.compute_user_profiles`();
```

## 📁 Estrutura de Arquivos

```
bigquery/
├── schemas/
│   ├── events_raw.sql        # Tabela principal de eventos
│   ├── identity_graph.sql    # Vinculação de identidades
│   └── user_profiles.sql     # Perfis consolidados
├── procedures/
│   ├── stitch_identities.sql # Identity resolution
│   └── compute_user_profiles.sql # RFM & LTV
├── views/
│   └── dashboard_metrics.sql # Views para dashboards
└── README.md
```

## 📊 Schema: events_raw

Tabela principal com todos os eventos de tracking.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| event_id | STRING | ID único do evento |
| ssi_id | STRING | ID do usuário (SSI) |
| canonical_id | STRING | ID resolvido (identity graph) |
| event_name | STRING | PageView, Purchase, Lead, etc |
| event_time | TIMESTAMP | Quando ocorreu |
| fbclid, gclid, ttclid | STRING | Click IDs das plataformas |
| fbc, fbp | STRING | Cookies do Meta |
| email_hash, phone_hash | STRING | PII hasheado |
| trust_score | FLOAT64 | Score de confiança (0-1) |
| trust_action | STRING | allow, challenge, block |
| value, currency | FLOAT64, STRING | Dados de e-commerce |
| meta_sent, google_sent | BOOL | Status de envio CAPI |

**Particionamento:** Por `event_time` (diário)
**Clustering:** Por `ssi_id`, `event_name`, `canonical_id`

## 🔗 Identity Graph

Sistema de vinculação de identidades cross-device.

### Tipos de Match

| Tipo | Confiança | Descrição |
|------|-----------|-----------|
| deterministic | 1.0 | Email ou telefone igual |
| probabilistic_fbp | 0.8 | Mesmo cookie FBP |
| probabilistic_session | 0.6 | Mesmo IP+UA+Timezone em 30min |

### Como Funciona

1. **Determinístico:** Se dois ssi_ids compartilham o mesmo email_hash ou phone_hash, são vinculados
2. **Probabilístico FBP:** Mesmo cookie _fbp em 90 dias = provável mesmo browser
3. **Probabilístico Sessão:** Mesmo IP + User-Agent + Timezone em 30 minutos = provável mesma pessoa

### Exemplo de Uso

```sql
-- Encontrar canonical_id de um ssi_id
SELECT canonical_id
FROM `ssi_shadow.identity_graph`
WHERE linked_id = 'ssi_abc123'
  AND id_type = 'ssi_id'
ORDER BY match_confidence DESC
LIMIT 1;

-- Todos os eventos de um usuário (cross-device)
SELECT *
FROM `ssi_shadow.events_raw`
WHERE canonical_id = 'canonical_xyz';
```

## 📈 User Profiles

Perfis consolidados com métricas RFM e predições.

### Métricas RFM

| Segmento | R | F | M | Descrição |
|----------|---|---|---|-----------|
| Champions | 5 | 5 | 5 | Top em tudo |
| Loyal Customers | * | 4+ | 4+ | Alta frequência e valor |
| At Risk | 1-2 | * | 4+ | Alto valor, baixa recência |
| Cannot Lose Them | 1 | * | 5 | Muito valor, muito tempo sem ver |
| Lost | 1 | * | * | Não visto há muito tempo |

### Segmentos de LTV

| Segmento | Percentil | Descrição |
|----------|-----------|-----------|
| VIP | 95%+ | Top 5% clientes |
| high | 75-94% | Alta valor |
| medium | 50-74% | Médio valor |
| low | < 50% | Baixo valor |

## 📊 Views Disponíveis

### v_daily_events_summary
Resumo diário de eventos com volume, receita e trust scores.

### v_funnel_analysis
Análise de funil e-commerce: PageView → ViewContent → AddToCart → Checkout → Purchase

### v_rfm_distribution
Distribuição de usuários por segmento RFM.

### v_bot_detection_stats
Estatísticas de detecção de bots e trust scores.

### v_capi_delivery_stats
Taxa de entrega para Meta/Google/TikTok CAPI.

### v_high_value_at_risk
Usuários de alto valor com risco de churn.

### v_audience_segments_meta
Segmentos formatados para exportação ao Meta Custom Audiences.

## ⚙️ Configuração do Worker

Adicione ao `wrangler.toml`:

```toml
[vars]
ENABLE_BIGQUERY = "true"
BIGQUERY_PROJECT_ID = "your-gcp-project"
BIGQUERY_DATASET = "ssi_shadow"
BIGQUERY_TABLE = "events_raw"
```

Configure a Service Account:

```bash
# Criar Service Account
gcloud iam service-accounts create ssi-shadow-worker \
  --display-name="SSI Shadow Worker"

# Dar permissões de BigQuery
gcloud projects add-iam-policy-binding your-project \
  --member="serviceAccount:ssi-shadow-worker@your-project.iam.gserviceaccount.com" \
  --role="roles/bigquery.dataEditor"

# Criar chave JSON
gcloud iam service-accounts keys create key.json \
  --iam-account=ssi-shadow-worker@your-project.iam.gserviceaccount.com

# Adicionar como secret no Worker
wrangler secret put GCP_SERVICE_ACCOUNT_KEY < key.json
```

## 💰 Estimativa de Custos

| Recurso | Custo | Estimativa (1M eventos/mês) |
|---------|-------|----------------------------|
| Storage | $0.02/GB/mês | ~$2/mês (100GB) |
| Streaming Insert | $0.05/200MB | ~$25/mês |
| Queries | $5/TB | ~$10/mês |
| **Total** | | **~$37/mês** |

## 🔒 Segurança

1. **PII sempre hasheado** antes de armazenar (email_hash, phone_hash)
2. **IP hasheado** para privacidade
3. **Service Account** com permissões mínimas
4. **Partição de 365 dias** - dados antigos são deletados automaticamente
5. **Clustering** por ssi_id para isolamento lógico

## 📊 Queries Úteis

### Receita por dia dos últimos 30 dias

```sql
SELECT
  DATE(event_time) AS date,
  SUM(value) AS revenue,
  COUNT(DISTINCT ssi_id) AS purchasers
FROM `ssi_shadow.events_raw`
WHERE event_name = 'Purchase'
  AND event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
GROUP BY date
ORDER BY date DESC;
```

### Top 10 usuários por LTV previsto

```sql
SELECT
  canonical_id,
  predicted_ltv,
  total_revenue,
  total_purchases,
  rfm_segment
FROM `ssi_shadow.user_profiles`
ORDER BY predicted_ltv DESC
LIMIT 10;
```

### Taxa de bloqueio de bots por dia

```sql
SELECT
  DATE(event_time) AS date,
  COUNTIF(trust_action = 'block') AS blocked,
  COUNT(*) AS total,
  SAFE_DIVIDE(COUNTIF(trust_action = 'block'), COUNT(*)) * 100 AS block_rate_pct
FROM `ssi_shadow.events_raw`
WHERE event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
GROUP BY date
ORDER BY date DESC;
```

---

**S.S.I. SHADOW** - Server-Side Intelligence for Optimized Ads
