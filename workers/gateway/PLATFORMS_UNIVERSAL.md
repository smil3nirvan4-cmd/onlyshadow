# S.S.I. SHADOW UNIVERSAL

## 50 Fontes de Tráfego | 20 Plataformas de Ads

---

## 📊 Resumo

| Categoria | Quantidade | Status |
|-----------|------------|--------|
| Plataformas de Ads (Tier 1) | 5 | ✅ Implementado |
| Plataformas de Ads (Tier 2) | 5 | 🔧 Em desenvolvimento |
| Plataformas de Ads (Tier 3) | 5 | 📋 Planejado |
| Plataformas de Ads (Tier 4) | 5 | 📋 Planejado |
| Outras Fontes de Tráfego | 30 | ✅ Rastreamento via UTM/Referrer |
| **TOTAL** | **50** | |

---

## 🎯 20 PLATAFORMAS DE ADS

### Tier 1 - Big Tech (80% do mercado)

| # | Plataforma | API | Click ID | Arquivo | Status |
|---|------------|-----|----------|---------|--------|
| 1 | Meta (Facebook/Instagram) | Conversions API v18 | `fbclid` | `meta-capi.ts` | ✅ |
| 2 | Google Ads | Enhanced Conversions | `gclid` / `gbraid` / `wbraid` | `google-mp.ts` | ✅ |
| 3 | TikTok Ads | Events API v1.3 | `ttclid` | `tiktok-capi.ts` | ✅ |
| 4 | Microsoft/Bing Ads | UET API | `msclkid` | `microsoft-capi.ts` | ✅ |
| 5 | Amazon Ads | Conversions API | `amzn_cid` | `amazon-capi.ts` | 🔧 |

### Tier 2 - Major Platforms

| # | Plataforma | API | Click ID | Arquivo | Status |
|---|------------|-----|----------|---------|--------|
| 6 | Snapchat Ads | Conversions API | `ScCid` | `snapchat-capi.ts` | ✅ |
| 7 | Pinterest Ads | Conversions API v5 | `epik` | `pinterest-capi.ts` | ✅ |
| 8 | LinkedIn Ads | Conversions API | `li_fat_id` | `linkedin-capi.ts` | ✅ |
| 9 | Twitter/X Ads | Conversions API v12 | `twclid` | `twitter-capi.ts` | ✅ |
| 10 | Reddit Ads | Conversions API | `rdt_cid` | `reddit-capi.ts` | 🔧 |

### Tier 3 - Programmatic/DSP

| # | Plataforma | API | Click ID | Arquivo | Status |
|---|------------|-----|----------|---------|--------|
| 11 | Google DV360 | Floodlight | `dclid` | `dv360-capi.ts` | 📋 |
| 12 | The Trade Desk | Real-Time API | `ttd_id` | `thetradedesk-capi.ts` | 📋 |
| 13 | Criteo | Events API | `cto_bundle` | `criteo-capi.ts` | 📋 |
| 14 | Taboola | Conversions API | `tblci` | `taboola-capi.ts` | 📋 |
| 15 | Outbrain | Pixel API | `obOrigUrl` | `outbrain-capi.ts` | 📋 |

### Tier 4 - Regional/Mobile

| # | Plataforma | API | Click ID | Arquivo | Status |
|---|------------|-----|----------|---------|--------|
| 16 | Kwai Ads | Events API | `kwai_click_id` | `kwai-capi.ts` | 📋 |
| 17 | AppLovin | Postback API | `idfa/gaid` | `applovin-capi.ts` | 📋 |
| 18 | Unity Ads | Server Events | `unity_click_id` | `unity-capi.ts` | 📋 |
| 19 | IronSource | Postback API | `is_click_id` | `ironsource-capi.ts` | 📋 |
| 20 | AdRoll | Conversions API | `adroll_click_id` | `adroll-capi.ts` | 📋 |

---

## 🌐 30 OUTRAS FONTES DE TRÁFEGO

### Search Engines (Orgânico)

| # | Fonte | Detecção | Medium |
|---|-------|----------|--------|
| 21 | Google Organic | Referrer | `organic` |
| 22 | Bing Organic | Referrer | `organic` |
| 23 | Yahoo | Referrer | `organic` |
| 24 | DuckDuckGo | Referrer | `organic` |
| 25 | Baidu | Referrer | `organic` |

### Social Organic

| # | Fonte | Detecção | Medium |
|---|-------|----------|--------|
| 26 | Facebook Organic | Referrer | `social` |
| 27 | Instagram Organic | Referrer | `social` |
| 28 | TikTok Organic | Referrer | `social` |
| 29 | YouTube | Referrer | `social` |
| 30 | Twitter/X Organic | Referrer | `social` |

### Referral/Content

| # | Fonte | Detecção | Medium |
|---|-------|----------|--------|
| 31 | Blogs/Sites Parceiros | Referrer | `referral` |
| 32 | Portais de Notícias | Referrer | `referral` |
| 33 | Fóruns | Referrer | `referral` |
| 34 | Agregadores | Referrer | `referral` |
| 35 | Diretórios | Referrer | `referral` |

### Direct/Email

| # | Fonte | Detecção | Medium |
|---|-------|----------|--------|
| 36 | Tráfego Direto | No referrer | `none` |
| 37 | Email Marketing | UTM | `email` |
| 38 | Newsletter | UTM | `email` |
| 39 | Automação (n8n/Zapier) | UTM | `automation` |
| 40 | WhatsApp Business | UTM/Referrer | `social` |

### Affiliates/Partners

| # | Fonte | Detecção | Medium |
|---|-------|----------|--------|
| 41 | Hotmart | UTM/Referrer | `affiliate` |
| 42 | Eduzz | UTM/Referrer | `affiliate` |
| 43 | Monetizze | UTM/Referrer | `affiliate` |
| 44 | Amazon Associates | UTM/Referrer | `affiliate` |
| 45 | Afiliados Próprios | UTM | `affiliate` |

### Messaging/Chat

| # | Fonte | Detecção | Medium |
|---|-------|----------|--------|
| 46 | Telegram | Referrer | `social` |
| 47 | Discord | Referrer | `social` |
| 48 | Slack | Referrer | `social` |
| 49 | Messenger | Referrer | `social` |
| 50 | SMS | UTM | `sms` |

---

## 🔧 CONFIGURAÇÃO

### Variáveis de Ambiente (wrangler.toml)

```toml
[vars]
# Tier 1
ENABLE_META = "true"
ENABLE_GOOGLE = "true"
ENABLE_TIKTOK = "true"
ENABLE_MICROSOFT = "true"
ENABLE_AMAZON = "false"

# Tier 2
ENABLE_SNAPCHAT = "true"
ENABLE_PINTEREST = "true"
ENABLE_LINKEDIN = "true"
ENABLE_TWITTER = "true"
ENABLE_REDDIT = "false"

# Tier 3 (quando implementados)
ENABLE_DV360 = "false"
ENABLE_THETRADEDESK = "false"
ENABLE_CRITEO = "false"
ENABLE_TABOOLA = "false"
ENABLE_OUTBRAIN = "false"

# Storage
ENABLE_BIGQUERY = "true"
```

### Secrets

```bash
# Meta
wrangler secret put META_PIXEL_ID
wrangler secret put META_ACCESS_TOKEN

# Google
wrangler secret put GA4_MEASUREMENT_ID
wrangler secret put GA4_API_SECRET

# TikTok
wrangler secret put TIKTOK_PIXEL_ID
wrangler secret put TIKTOK_ACCESS_TOKEN

# Microsoft/Bing
wrangler secret put BING_TAG_ID
wrangler secret put BING_ACCESS_TOKEN

# Snapchat
wrangler secret put SNAPCHAT_PIXEL_ID
wrangler secret put SNAPCHAT_ACCESS_TOKEN

# Pinterest
wrangler secret put PINTEREST_AD_ACCOUNT_ID
wrangler secret put PINTEREST_ACCESS_TOKEN

# LinkedIn
wrangler secret put LINKEDIN_CONVERSION_ID
wrangler secret put LINKEDIN_ACCESS_TOKEN

# Twitter
wrangler secret put TWITTER_PIXEL_ID
wrangler secret put TWITTER_ACCESS_TOKEN
wrangler secret put TWITTER_CONVERSION_ID

# BigQuery
wrangler secret put GCP_SERVICE_ACCOUNT_KEY < key.json
```

---

## 📡 API

### POST /api/collect

Envia evento para TODAS as plataformas habilitadas.

```bash
curl -X POST https://ssi-shadow.seu-dominio.workers.dev/api/collect \
  -H "Content-Type: application/json" \
  -d '{
    "event_name": "Purchase",
    "email": "cliente@email.com",
    "phone": "+5511999999999",
    "value": 299.90,
    "currency": "BRL",
    "content_ids": ["PROD-001"],
    "order_id": "ORDER-123",
    "url": "https://seusite.com/checkout?fbclid=abc123&gclid=xyz789"
  }'
```

### Response

```json
{
  "success": true,
  "event_id": "ssi_1703708400000_abc123def",
  "ssi_id": "550e8400-e29b-41d4-a716-446655440000",
  "trust_score": 0.85,
  "trust_action": "allow",
  "traffic_source": "facebook",
  "traffic_medium": "paid",
  "platforms": {
    "meta": { "sent": true, "status": 200, "events_received": 1 },
    "google": { "sent": true, "status": 204 },
    "tiktok": { "sent": true, "status": 200, "events_received": 1 },
    "microsoft": { "sent": true, "status": 200 },
    "snapchat": { "sent": true, "status": 200 },
    "pinterest": { "sent": true, "status": 200 },
    "linkedin": { "sent": true, "status": 200 },
    "twitter": { "sent": true, "status": 200 },
    "bigquery": { "sent": true, "status": 200 }
  },
  "processing_time_ms": 187
}
```

---

## 🚀 DEPLOY

```bash
# 1. Instalar dependências
cd workers/gateway
npm install

# 2. Configurar secrets
wrangler secret put META_PIXEL_ID
# ... (todos os outros)

# 3. Deploy
wrangler deploy

# 4. Testar
curl https://ssi-shadow.seu-dominio.workers.dev/api/health
```

---

## 📈 MÉTRICAS

| Métrica | Target |
|---------|--------|
| Latência média | < 200ms |
| Taxa de sucesso | > 99% |
| Platforms/request | 8+ |
| Events/segundo | 100+ |
| EMQ Meta | ≥ 6 |
| Match rate TikTok | > 80% |

---

**S.S.I. SHADOW UNIVERSAL** - Server-Side Intelligence for 50 Traffic Sources
