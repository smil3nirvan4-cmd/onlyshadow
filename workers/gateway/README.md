# S.S.I. SHADOW

**Server-Side Intelligence for Optimized Ads**

Sistema completo de server-side tracking para Meta, TikTok, Google e BigQuery com detecção de bots, identity resolution e predição de LTV.

## 🎯 O que é?

O S.S.I. SHADOW é um gateway de tracking server-side que:

- ✅ Recebe eventos do client-side (Ghost Script)
- ✅ Detecta e filtra bots/tráfego inválido
- ✅ Envia para Meta CAPI, TikTok Events API e GA4
- ✅ Armazena no BigQuery para análise
- ✅ Resolve identidades cross-device
- ✅ Calcula RFM e prediz LTV

## 🏗️ Arquitetura

```
┌─────────────────┐      ┌───────────────────────────────────────┐
│   Ghost Script  │─────▶│         Cloudflare Worker             │
│   (Client-side) │      │  ┌─────────────────────────────────┐  │
└─────────────────┘      │  │      Trust Score Engine         │  │
                         │  │   (Bot Detection + Rate Limit)  │  │
                         │  └────────────┬────────────────────┘  │
                         │               │                       │
                         │  ┌────────────▼────────────────────┐  │
                         │  │      Platform Router            │  │
                         │  └─┬──────┬──────┬──────┬─────────┘  │
                         └───┼──────┼──────┼──────┼─────────────┘
                             │      │      │      │
                    ┌────────▼┐ ┌───▼───┐ ┌▼────┐ ┌▼────────┐
                    │  Meta   │ │TikTok │ │ GA4 │ │BigQuery │
                    │  CAPI   │ │Events │ │ MP  │ │         │
                    └─────────┘ └───────┘ └─────┘ └─────────┘
```

## 🚀 Quick Start

### 1. Clone e Instale

```bash
# Extrair o ZIP
unzip ssi-shadow-worker-complete.zip
cd ssi-shadow-worker

# Instalar dependências
npm install
```

### 2. Configure os Secrets

```bash
# Meta CAPI (obrigatório)
wrangler secret put META_PIXEL_ID
wrangler secret put META_ACCESS_TOKEN

# TikTok Events API (opcional)
wrangler secret put TIKTOK_PIXEL_ID
wrangler secret put TIKTOK_ACCESS_TOKEN

# Google GA4 (opcional)
wrangler secret put GA4_MEASUREMENT_ID
wrangler secret put GA4_API_SECRET

# BigQuery (opcional)
wrangler secret put GCP_SERVICE_ACCOUNT_KEY < service-account.json
```

### 3. Configure o wrangler.toml

```toml
[vars]
ENABLE_META = "true"
ENABLE_TIKTOK = "true"
ENABLE_GOOGLE = "true"
ENABLE_BIGQUERY = "true"
TRUST_SCORE_THRESHOLD = "0.3"

# BigQuery
BIGQUERY_PROJECT_ID = "your-project"
BIGQUERY_DATASET = "ssi_shadow"
BIGQUERY_TABLE = "events_raw"
```

### 4. Deploy

```bash
# Desenvolvimento
npm run dev

# Staging
npm run deploy:staging

# Produção
npm run deploy:production
```

### 5. Instale o Ghost Script

```html
<script>
  window.SSI_ENDPOINT = 'https://ssi-shadow.YOUR-SUBDOMAIN.workers.dev/api/collect';
</script>
<script src="ghost.min.js" defer></script>
```

## 📡 API Endpoints

### Health Check
```
GET /api/health
```

### Config (Debug)
```
GET /api/config
```

### Collect Event
```
POST /api/collect
Content-Type: application/json
```

### Test Event
```
POST /api/test
```

## 📊 Trust Score (Bot Detection)

Score de 0.0 (bot) a 1.0 (humano):

- Score < 0.3 → `block`
- Score 0.3-0.6 → `challenge`
- Score > 0.6 → `allow`

## 📁 Estrutura

```
src/
├── index.ts           # Entry point
├── types.ts           # TypeScript interfaces
├── meta-capi.ts       # Meta Conversions API
├── tiktok-capi.ts     # TikTok Events API
├── google-mp.ts       # GA4 Measurement Protocol
├── bigquery.ts        # BigQuery Streaming
├── trust-score/       # Bot detection
└── utils/             # Utilities
```

## 🔧 Scripts

```bash
npm run dev              # Desenvolvimento
npm run deploy:staging   # Deploy staging
npm run deploy:production # Deploy produção
npm run tail             # Ver logs
```

---

**S.S.I. SHADOW v1.0.0**
