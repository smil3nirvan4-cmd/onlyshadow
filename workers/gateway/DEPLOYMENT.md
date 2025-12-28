# S.S.I. SHADOW - Guia de Deployment

Guia completo para deploy do sistema S.S.I. SHADOW em produção.

## 📋 Pré-requisitos

- Node.js 18+ instalado
- Conta Cloudflare (Free tier funciona)
- Wrangler CLI: `npm install -g wrangler`
- Credenciais das plataformas (Meta, TikTok, Google)

## 🚀 Passo a Passo

### Passo 1: Preparar Ambiente

```bash
# 1. Extrair arquivos
unzip ssi-shadow-worker-complete.zip
cd ssi-shadow-worker

# 2. Instalar dependências
npm install

# 3. Login no Cloudflare
wrangler login
```

### Passo 2: Configurar Meta CAPI

```bash
# Obter credenciais em:
# https://business.facebook.com/events_manager

# Configurar secrets
wrangler secret put META_PIXEL_ID
# Digite: seu_pixel_id (ex: 1234567890123456)

wrangler secret put META_ACCESS_TOKEN
# Digite: seu_access_token (começa com EAA...)

# Opcional: Test Event Code para testar
# Adicione no wrangler.toml:
# META_TEST_EVENT_CODE = "TEST12345"
```

### Passo 3: Configurar TikTok (Opcional)

```bash
# Obter credenciais em:
# https://ads.tiktok.com/marketing_api/

wrangler secret put TIKTOK_PIXEL_ID
# Digite: seu_pixel_code

wrangler secret put TIKTOK_ACCESS_TOKEN
# Digite: seu_access_token

# Habilitar no wrangler.toml:
# ENABLE_TIKTOK = "true"
```

### Passo 4: Configurar Google GA4 (Opcional)

```bash
# Obter credenciais em:
# GA4 > Admin > Data Streams > Measurement Protocol

wrangler secret put GA4_MEASUREMENT_ID
# Digite: G-XXXXXXXXXX

wrangler secret put GA4_API_SECRET
# Digite: seu_api_secret

# Habilitar no wrangler.toml:
# ENABLE_GOOGLE = "true"
```

### Passo 5: Configurar BigQuery (Opcional)

```bash
# 1. Criar Service Account no GCP
gcloud iam service-accounts create ssi-shadow \
  --display-name="SSI Shadow Worker"

# 2. Dar permissões
gcloud projects add-iam-policy-binding YOUR_PROJECT \
  --member="serviceAccount:ssi-shadow@YOUR_PROJECT.iam.gserviceaccount.com" \
  --role="roles/bigquery.dataEditor"

# 3. Gerar chave JSON
gcloud iam service-accounts keys create key.json \
  --iam-account=ssi-shadow@YOUR_PROJECT.iam.gserviceaccount.com

# 4. Configurar secret
wrangler secret put GCP_SERVICE_ACCOUNT_KEY < key.json

# 5. Configurar no wrangler.toml:
# ENABLE_BIGQUERY = "true"
# BIGQUERY_PROJECT_ID = "your-project"
# BIGQUERY_DATASET = "ssi_shadow"
# BIGQUERY_TABLE = "events_raw"

# 6. Criar tabelas no BigQuery
cd ../bigquery
bq query --use_legacy_sql=false < schemas/events_raw.sql
bq query --use_legacy_sql=false < schemas/identity_graph.sql
bq query --use_legacy_sql=false < schemas/user_profiles.sql
```

### Passo 6: Configurar Rate Limiting (Recomendado)

```bash
# 1. Criar KV namespace
wrangler kv:namespace create "RATE_LIMIT"
# Anote o ID retornado

# 2. Adicionar no wrangler.toml:
# [[kv_namespaces]]
# binding = "RATE_LIMIT"
# id = "seu-kv-id"
```

### Passo 7: Deploy

```bash
# Testar localmente primeiro
npm run dev

# Deploy para staging
wrangler deploy --env staging

# Testar staging
curl https://ssi-shadow-staging.YOUR-SUBDOMAIN.workers.dev/api/health

# Deploy para produção
wrangler deploy --env production
```

### Passo 8: Instalar Ghost Script

```html
<!-- No seu site, antes do </head> -->
<script>
  window.SSI_CONFIG = {
    endpoint: 'https://ssi-shadow.YOUR-SUBDOMAIN.workers.dev/api/collect',
    pixelId: 'SEU_PIXEL_ID',
    debug: false
  };
</script>
<script src="https://seu-cdn.com/ghost.min.js" defer></script>
```

Ou hospede o ghost.js no seu próprio servidor/CDN.

### Passo 9: Verificar Funcionamento

```bash
# 1. Testar endpoint de health
curl https://ssi-shadow.YOUR-SUBDOMAIN.workers.dev/api/health

# 2. Testar configuração
curl https://ssi-shadow.YOUR-SUBDOMAIN.workers.dev/api/config

# 3. Enviar evento de teste
curl -X POST https://ssi-shadow.YOUR-SUBDOMAIN.workers.dev/api/test \
  -H "Content-Type: application/json" \
  -d '{
    "event_name": "PageView",
    "url": "https://seusite.com/teste"
  }'

# 4. Ver logs em tempo real
wrangler tail --env production
```

### Passo 10: Verificar nas Plataformas

| Plataforma | Onde verificar |
|------------|----------------|
| Meta | Events Manager > Test Events |
| TikTok | Ads Manager > Events > Test Events |
| Google | GA4 > Realtime > Events |
| BigQuery | BigQuery Console > Query |

---

## 🔧 Configuração Completa do wrangler.toml

```toml
name = "ssi-shadow"
main = "src/index.ts"
compatibility_date = "2024-01-01"
compatibility_flags = ["nodejs_compat"]

[vars]
# Feature Flags
ENABLE_META = "true"
ENABLE_TIKTOK = "true"
ENABLE_GOOGLE = "true"
ENABLE_BIGQUERY = "true"

# Trust Score
TRUST_SCORE_THRESHOLD = "0.3"

# BigQuery
BIGQUERY_PROJECT_ID = "your-project"
BIGQUERY_DATASET = "ssi_shadow"
BIGQUERY_TABLE = "events_raw"

# Test Event Codes (opcional)
# META_TEST_EVENT_CODE = "TEST12345"
# TIKTOK_TEST_EVENT_CODE = "TEST12345"

# KV para Rate Limiting
[[kv_namespaces]]
binding = "RATE_LIMIT"
id = "your-kv-namespace-id"

# Ambientes
[env.staging]
name = "ssi-shadow-staging"

[env.production]
name = "ssi-shadow"

# Observability
[observability]
enabled = true
```

---

## 📊 Checklist de Produção

### Segurança
- [ ] Todos os secrets configurados via `wrangler secret`
- [ ] Nenhuma credencial no código ou wrangler.toml
- [ ] CORS configurado corretamente
- [ ] Rate limiting habilitado

### Performance
- [ ] Trust Score threshold ajustado
- [ ] KV namespace criado para rate limiting
- [ ] BigQuery com particionamento por data

### Monitoramento
- [ ] Observability habilitado no wrangler.toml
- [ ] Alertas configurados no Cloudflare Dashboard
- [ ] Logs sendo coletados

### Validação
- [ ] Events aparecendo no Meta Events Manager
- [ ] Events aparecendo no TikTok Events
- [ ] Events aparecendo no GA4 Realtime
- [ ] Dados chegando no BigQuery

---

## 🔄 Atualizações

Para atualizar o Worker:

```bash
# 1. Fazer alterações no código

# 2. Testar localmente
npm run dev

# 3. Deploy para staging
wrangler deploy --env staging

# 4. Testar staging
curl https://ssi-shadow-staging.workers.dev/api/health

# 5. Deploy para produção
wrangler deploy --env production

# 6. Verificar logs
wrangler tail --env production
```

---

## 🆘 Troubleshooting

### Worker não responde
```bash
# Verificar status
wrangler deployments list

# Ver logs
wrangler tail --env production
```

### Secrets não funcionam
```bash
# Listar secrets
wrangler secret list

# Re-configurar
wrangler secret put META_PIXEL_ID
```

### BigQuery permission denied
```bash
# Verificar permissões da Service Account
gcloud projects get-iam-policy YOUR_PROJECT \
  --flatten="bindings[].members" \
  --filter="bindings.members:ssi-shadow@"
```

### Rate limiting não funciona
```bash
# Verificar KV namespace
wrangler kv:namespace list

# Verificar binding no wrangler.toml
```

---

## 📈 Monitoramento Recomendado

### Cloudflare Dashboard
- Workers > Analytics
- Workers > Logs

### Métricas para acompanhar
- Requests/segundo
- Latência P50/P95
- Taxa de erro
- Taxa de bloqueio (trust_action = block)

### Alertas sugeridos
- Latência P95 > 500ms
- Taxa de erro > 1%
- Zero requests por 5 minutos

---

## 💰 Custos Estimados

| Serviço | Free Tier | Pago |
|---------|-----------|------|
| Cloudflare Workers | 100K req/dia | $5/mês (10M req) |
| Cloudflare KV | 100K reads/dia | Incluído |
| BigQuery Storage | 10GB | $0.02/GB/mês |
| BigQuery Streaming | - | $0.05/200MB |

**Estimativa para 1M eventos/mês: ~$40/mês**

---

**S.S.I. SHADOW** - Server-Side Intelligence for Optimized Ads
