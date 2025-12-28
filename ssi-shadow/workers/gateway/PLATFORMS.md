# S.S.I. SHADOW - Platform Integrations

Documentação das integrações com plataformas de anúncios.

## 📊 Plataformas Suportadas

| Plataforma | Status | Módulo | Endpoint |
|------------|--------|--------|----------|
| Meta (Facebook/Instagram) | ✅ | `meta-capi.ts` | graph.facebook.com/v21.0 |
| TikTok Ads | ✅ | `tiktok-capi.ts` | business-api.tiktok.com/v1.3 |
| Google Analytics 4 | ✅ | `google-mp.ts` | google-analytics.com/mp |
| BigQuery | ✅ | `bigquery.ts` | bigquery.googleapis.com |

---

## 🔵 Meta Conversions API

### Configuração

```bash
# Configurar secrets
wrangler secret put META_PIXEL_ID
wrangler secret put META_ACCESS_TOKEN

# Opcional: Test Event Code
# Adicione no wrangler.toml:
# META_TEST_EVENT_CODE = "TEST12345"
```

### Onde encontrar as credenciais

1. **Pixel ID**: Events Manager > Data Sources > Seu Pixel
2. **Access Token**: Events Manager > Settings > Generate Access Token

### Event Match Quality (EMQ)

| Sinal | Pontos |
|-------|--------|
| Email | +3 |
| Phone | +2 |
| FBC (Click ID) | +2 |
| FBP (Browser ID) | +1 |
| External ID | +1 |
| Nome/Cidade/Estado/CEP | +0.25 cada |

**Meta recomenda EMQ ≥ 6**

### Mapeamento de Eventos

| SSI Event | Meta Event |
|-----------|------------|
| PageView | PageView |
| ViewContent | ViewContent |
| AddToCart | AddToCart |
| InitiateCheckout | InitiateCheckout |
| Purchase | Purchase |
| Lead | Lead |
| CompleteRegistration | CompleteRegistration |
| Search | Search |

---

## 🎵 TikTok Events API

### Configuração

```bash
# Configurar secrets
wrangler secret put TIKTOK_PIXEL_ID
wrangler secret put TIKTOK_ACCESS_TOKEN

# Opcional: Test Event Code
# Adicione no wrangler.toml:
# TIKTOK_TEST_EVENT_CODE = "TEST12345"
```

### Onde encontrar as credenciais

1. **Pixel ID**: TikTok Ads Manager > Events > Web Events > Pixel Code
2. **Access Token**: TikTok for Business > Settings > Business Center Access Tokens

### Mapeamento de Eventos

| SSI Event | TikTok Event |
|-----------|--------------|
| PageView | ViewContent |
| ViewContent | ViewContent |
| AddToCart | AddToCart |
| InitiateCheckout | InitiateCheckout |
| Purchase | CompletePayment |
| Lead | SubmitForm |
| CompleteRegistration | CompleteRegistration |
| Search | Search |
| AddToWishlist | AddToWishlist |

### Sinais de Matching

| Sinal | Campo TikTok |
|-------|--------------|
| Email (SHA-256) | sha256_email |
| Phone (SHA-256) | sha256_phone_number |
| TikTok Click ID | ttclid |
| TikTok Browser ID | ttp |
| External ID | external_id |
| IP | ip |
| User Agent | user_agent |

---

## 📊 Google Analytics 4 (Measurement Protocol)

### Configuração

```bash
# Configurar secrets
wrangler secret put GA4_MEASUREMENT_ID
wrangler secret put GA4_API_SECRET
```

### Onde encontrar as credenciais

1. **Measurement ID**: GA4 > Admin > Data Streams > Seu Stream (formato: G-XXXXXXXXXX)
2. **API Secret**: GA4 > Admin > Data Streams > Measurement Protocol API secrets > Create

### Mapeamento de Eventos

| SSI Event | GA4 Event |
|-----------|-----------|
| PageView | page_view |
| ViewContent | view_item |
| AddToCart | add_to_cart |
| RemoveFromCart | remove_from_cart |
| InitiateCheckout | begin_checkout |
| AddPaymentInfo | add_payment_info |
| Purchase | purchase |
| Lead | generate_lead |
| CompleteRegistration | sign_up |
| Search | search |

### Parâmetros E-commerce

```json
{
  "client_id": "1234567890.1234567890",
  "events": [{
    "name": "purchase",
    "params": {
      "transaction_id": "ORDER-123",
      "value": 299.90,
      "currency": "BRL",
      "items": [{
        "item_id": "SKU-001",
        "item_name": "Produto X",
        "price": 299.90,
        "quantity": 1
      }]
    }
  }]
}
```

---

## 🗃️ BigQuery

### Configuração

```bash
# 1. Criar Service Account no GCP
gcloud iam service-accounts create ssi-shadow-worker

# 2. Dar permissões
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:ssi-shadow-worker@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/bigquery.dataEditor"

# 3. Gerar chave JSON
gcloud iam service-accounts keys create key.json \
  --iam-account=ssi-shadow-worker@PROJECT_ID.iam.gserviceaccount.com

# 4. Configurar no Worker
wrangler secret put GCP_SERVICE_ACCOUNT_KEY < key.json
```

### Variáveis de Ambiente

```toml
# wrangler.toml
[vars]
ENABLE_BIGQUERY = "true"
BIGQUERY_PROJECT_ID = "your-project"
BIGQUERY_DATASET = "ssi_shadow"
BIGQUERY_TABLE = "events_raw"
```

---

## 🚀 Ativando Plataformas

### Habilitar no wrangler.toml

```toml
[vars]
ENABLE_META = "true"      # Meta Conversions API
ENABLE_GOOGLE = "true"    # Google Analytics 4
ENABLE_TIKTOK = "true"    # TikTok Events API
ENABLE_BIGQUERY = "true"  # BigQuery Storage
```

### Response de Exemplo

```json
{
  "success": true,
  "event_id": "550e8400-e29b-41d4-a716-446655440000",
  "ssi_id": "ssi_abc123",
  "trust_score": 0.85,
  "trust_action": "allow",
  "platforms": {
    "meta": { "sent": true, "status": 200, "events_received": 1 },
    "tiktok": { "sent": true, "status": 200, "events_received": 1 },
    "google": { "sent": true, "status": 204 },
    "bigquery": { "sent": true, "status": 200 }
  },
  "processing_time_ms": 125
}
```

---

## 🔒 Segurança

### Secrets (Nunca no código!)

```bash
# Meta
wrangler secret put META_PIXEL_ID
wrangler secret put META_ACCESS_TOKEN

# TikTok
wrangler secret put TIKTOK_PIXEL_ID
wrangler secret put TIKTOK_ACCESS_TOKEN

# Google
wrangler secret put GA4_MEASUREMENT_ID
wrangler secret put GA4_API_SECRET

# BigQuery
wrangler secret put GCP_SERVICE_ACCOUNT_KEY < key.json
```

### PII Hashing

Todos os dados de PII são hasheados (SHA-256) antes de enviar:
- Email (normalizado: lowercase, trim)
- Telefone (normalizado: E.164)
- Nome
- Cidade
- Estado
- CEP

---

## 🧪 Testando

### Teste com curl

```bash
curl -X POST https://ssi-shadow.YOUR-SUBDOMAIN.workers.dev/api/collect \
  -H "Content-Type: application/json" \
  -d '{
    "event_name": "Purchase",
    "email": "test@example.com",
    "phone": "+5511999999999",
    "value": 299.90,
    "currency": "BRL",
    "content_ids": ["SKU-001"],
    "order_id": "ORDER-123"
  }'
```

### Verificação por Plataforma

| Plataforma | Onde verificar |
|------------|----------------|
| Meta | Events Manager > Test Events |
| TikTok | Ads Manager > Events > Test Events |
| Google | GA4 > Realtime > Events |
| BigQuery | BigQuery Console > Query results |

---

## 📈 Métricas de Sucesso

| Métrica | Meta Esperada |
|---------|---------------|
| Latência média | < 200ms |
| Taxa de sucesso | > 99% |
| EMQ Meta | ≥ 6 |
| Taxa de match TikTok | > 80% |
| Events/segundo | 100+ |

---

## 🔧 Troubleshooting

### Meta: "Invalid parameter"
- Verifique se o Pixel ID está correto
- Verifique se o Access Token tem permissões

### TikTok: "Unauthorized"
- Regenere o Access Token
- Verifique se o token tem scope para Events API

### Google: "Invalid measurement_id"
- Use formato G-XXXXXXXXXX
- Verifique se o API Secret está correto

### BigQuery: "Permission denied"
- Verifique se a Service Account tem `bigquery.dataEditor`
- Verifique se o dataset/table existem

---

**S.S.I. SHADOW** - Server-Side Intelligence for Optimized Ads
