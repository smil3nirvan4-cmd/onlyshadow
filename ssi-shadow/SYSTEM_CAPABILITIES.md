# 🔮 S.S.I. SHADOW - Server-Side Intelligence Shadow
## Documentação Completa de Funcionalidades

```
███████╗███████╗██╗     ██████╗ ██████╗  █████╗  ██████╗██╗     ███████╗
██╔════╝██╔════╝██║    ██╔═══██╗██╔══██╗██╔══██╗██╔════╝██║     ██╔════╝
███████╗███████╗██║    ██║   ██║██████╔╝███████║██║     ██║     █████╗  
╚════██║╚════██║██║    ██║   ██║██╔══██╗██╔══██║██║     ██║     ██╔══╝  
███████║███████║██║    ╚██████╔╝██║  ██║██║  ██║╚██████╗███████╗███████╗
╚══════╝╚══════╝╚═╝     ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝╚══════╝╚══════╝
                                                                         
        Server-Side Intelligence Shadow - Marketing Intelligence Platform
```

---

## 📊 ARQUITETURA DO SISTEMA

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CAMADA DE ENTRADA                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │   Website   │  │  Mobile App │  │   CRM/ERP   │  │  Webhooks   │        │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘        │
└─────────┼────────────────┼────────────────┼────────────────┼────────────────┘
          │                │                │                │
          ▼                ▼                ▼                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      CLOUDFLARE EDGE WORKERS                                 │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  • Event Validation & Enrichment    • Trust Score Calculation        │   │
│  │  • PII Hashing (SHA256)             • Bot/IVT Detection              │   │
│  │  • Rate Limiting                    • Geographic Routing             │   │
│  │  • Cookie Management                • Real-time Bid Optimization     │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FASTAPI BACKEND (Python)                             │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐                    │
│  │  Auth & RBAC  │  │  Rate Limiter │  │ Error Handler │                    │
│  └───────┬───────┘  └───────┬───────┘  └───────┬───────┘                    │
│          └──────────────────┴──────────────────┘                            │
│                              │                                               │
│  ┌───────────────────────────┼───────────────────────────┐                  │
│  │                    CORE SERVICES                       │                  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐   │                  │
│  │  │   gROAS     │  │   Budget    │  │   Weather   │   │                  │
│  │  │ Orchestrator│  │  Optimizer  │  │   Bidder    │   │                  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘   │                  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐   │                  │
│  │  │ Attribution │  │     CDP     │  │  ML Engine  │   │                  │
│  │  │   Engine    │  │   Profiles  │  │             │   │                  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘   │                  │
│  └───────────────────────────────────────────────────────┘                  │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
          ┌─────────────────────────┼─────────────────────────┐
          ▼                         ▼                         ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  AD PLATFORMS   │    │   DATA LAYER    │    │   INTELLIGENCE  │
│  ┌───────────┐  │    │  ┌───────────┐  │    │  ┌───────────┐  │
│  │  Google   │  │    │  │ BigQuery  │  │    │  │ Competitor│  │
│  │   Ads     │  │    │  │  (Data)   │  │    │  │  Scraper  │  │
│  ├───────────┤  │    │  ├───────────┤  │    │  ├───────────┤  │
│  │   Meta    │  │    │  │   Redis   │  │    │  │   Copy    │  │
│  │  (CAPI)   │  │    │  │  (Cache)  │  │    │  │ Architect │  │
│  ├───────────┤  │    │  ├───────────┤  │    │  ├───────────┤  │
│  │  TikTok   │  │    │  │  Pub/Sub  │  │    │  │  Vision   │  │
│  │   Ads     │  │    │  │  (Queue)  │  │    │  │    API    │  │
│  ├───────────┤  │    │  └───────────┘  │    │  └───────────┘  │
│  │ LinkedIn  │  │    └─────────────────┘    └─────────────────┘
│  ├───────────┤  │
│  │ Pinterest │  │
│  ├───────────┤  │
│  │ Snapchat  │  │
│  └───────────┘  │
└─────────────────┘
```

---

## 🎯 FUNCIONALIDADES DETALHADAS

### 1. 📡 SERVER-SIDE TRACKING (Rastreamento Server-Side)

```
┌─────────────────────────────────────────────────────────────┐
│                  SERVER-SIDE TRACKING                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ✅ Coleta de Eventos Server-Side                           │
│     • Bypass de ad blockers (95%+ de eventos capturados)    │
│     • Não depende de cookies de terceiros                   │
│     • Compatível com iOS 14.5+ e políticas de privacidade   │
│                                                              │
│  ✅ Eventos Suportados                                       │
│     • page_view, view_content, add_to_cart                  │
│     • initiate_checkout, add_payment_info                   │
│     • purchase, lead, complete_registration                 │
│     • search, subscribe, custom events                      │
│                                                              │
│  ✅ Enriquecimento de Dados                                  │
│     • IP → Geolocalização (país, região, cidade)            │
│     • User-Agent → Device info (OS, browser, device type)   │
│     • Referrer parsing → Source/Medium/Campaign             │
│     • UTM parameters extraction                             │
│                                                              │
│  ✅ Hashing de PII (SHA256)                                  │
│     • Email normalization + hashing                         │
│     • Phone normalization (E.164) + hashing                 │
│     • First/Last name hashing                               │
│     • Conforme LGPD, GDPR, CCPA                             │
│                                                              │
│  ✅ Deduplicação de Eventos                                  │
│     • Event ID tracking                                     │
│     • Prevenção de duplicatas cross-platform                │
│     • Idempotency keys                                      │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 2. 🔗 CONVERSIONS API (CAPI) - Multi-Platform

```
┌─────────────────────────────────────────────────────────────┐
│               CONVERSIONS API INTEGRATIONS                   │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ✅ META (Facebook/Instagram) CAPI                          │
│     • Real-time event dispatch                              │
│     • Event Match Quality scoring                           │
│     • Automatic hashing (em, ph, fn, ln, ct, st, zp, country)│
│     • Test events support                                   │
│     • fbp/fbc cookie handling                               │
│     • Deduplication with pixel                              │
│                                                              │
│  ✅ GOOGLE ADS                                               │
│     • Offline Conversion Import                             │
│     • Enhanced Conversions                                  │
│     • GCLID tracking & storage                              │
│     • Conversion value optimization                         │
│     • Store Sales Direct                                    │
│                                                              │
│  ✅ GOOGLE ANALYTICS 4 (GA4)                                 │
│     • Measurement Protocol                                  │
│     • User-ID tracking                                      │
│     • Custom dimensions/metrics                             │
│     • E-commerce tracking                                   │
│                                                              │
│  ✅ TIKTOK EVENTS API                                        │
│     • Web events (ViewContent, AddToCart, Purchase)         │
│     • ttclid tracking                                       │
│     • Match quality optimization                            │
│     • Test mode support                                     │
│                                                              │
│  ✅ LINKEDIN CAPI                                            │
│     • Conversion tracking                                   │
│     • Lead gen events                                       │
│     • li_fat_id handling                                    │
│                                                              │
│  ✅ PINTEREST CAPI                                           │
│     • Conversion events                                     │
│     • epik/pin tracking                                     │
│                                                              │
│  ✅ SNAPCHAT CAPI                                            │
│     • Snap Pixel server events                              │
│     • sccid/scid tracking                                   │
│                                                              │
│  ✅ MICROSOFT/BING                                           │
│     • UET tag events                                        │
│     • msclkid tracking                                      │
│                                                              │
│  ✅ TWITTER/X                                                │
│     • Conversion API                                        │
│     • twclid handling                                       │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 3. 🎯 MULTI-TOUCH ATTRIBUTION (MTA)

```
┌─────────────────────────────────────────────────────────────┐
│                 MULTI-TOUCH ATTRIBUTION                      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ✅ Modelos de Atribuição Suportados                        │
│                                                              │
│     FIRST TOUCH (100% → primeiro touchpoint)                │
│     ════════════════════════════════════════                │
│     [100%]────[0%]────[0%]────[0%]────[CONV]               │
│                                                              │
│     LAST TOUCH (100% → último touchpoint)                   │
│     ════════════════════════════════════════                │
│     [0%]────[0%]────[0%]────[100%]────[CONV]               │
│                                                              │
│     LINEAR (divisão igual)                                  │
│     ════════════════════════════════════════                │
│     [25%]────[25%]────[25%]────[25%]────[CONV]             │
│                                                              │
│     TIME DECAY (mais peso para recentes)                    │
│     ════════════════════════════════════════                │
│     [10%]────[15%]────[25%]────[50%]────[CONV]             │
│                                                              │
│     POSITION-BASED (U-Shape: 40/20/40)                      │
│     ════════════════════════════════════════                │
│     [40%]────[10%]────[10%]────[40%]────[CONV]             │
│                                                              │
│     DATA-DRIVEN (ML-based)                                  │
│     ════════════════════════════════════════                │
│     [23%]────[31%]────[18%]────[28%]────[CONV]             │
│     (baseado em Shapley Values)                             │
│                                                              │
│  ✅ Funcionalidades                                          │
│     • Tracking de touchpoints cross-device                  │
│     • Janela de conversão configurável (1-90 dias)          │
│     • Attribution path visualization                        │
│     • Channel performance by model                          │
│     • ROAS por modelo de atribuição                         │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 4. 🧠 gROAS - Granular ROAS Optimization

```
┌─────────────────────────────────────────────────────────────┐
│            gROAS - GRANULAR ROAS OPTIMIZATION                │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ✅ SEARCH INTENT ANALYSIS (Análise de Intenção)            │
│                                                              │
│     Exemplo de Classificação:                               │
│     ┌─────────────────────────────────────────────────────┐ │
│     │ Search Term           │ Intent │ Score │ Action     │ │
│     ├───────────────────────┼────────┼───────┼────────────┤ │
│     │ "buy running shoes"   │ HIGH   │ 0.92  │ +Keyword   │ │
│     │ "nike air max price"  │ HIGH   │ 0.85  │ +Keyword   │ │
│     │ "best sneakers 2024"  │ MEDIUM │ 0.58  │ Monitor    │ │
│     │ "how to clean shoes"  │ LOW    │ 0.15  │ +Negative  │ │
│     │ "diy shoe repair"     │ LOW    │ 0.08  │ +Negative  │ │
│     └─────────────────────────────────────────────────────┘ │
│                                                              │
│  ✅ SINAIS DE ALTA INTENÇÃO                                  │
│     • "buy", "comprar", "order", "shop"                     │
│     • "price", "preço", "cost", "quanto custa"              │
│     • "discount", "coupon", "promo", "sale"                 │
│     • "store near me", "where to buy"                       │
│     • "best [product] for [need]"                           │
│                                                              │
│  ✅ SINAIS DE BAIXA INTENÇÃO (Negativar)                    │
│     • "free", "grátis", "download"                          │
│     • "how to make", "diy", "tutorial"                      │
│     • "recipe", "homemade"                                  │
│     • "[competitor] careers/jobs"                           │
│                                                              │
│  ✅ AÇÕES AUTOMÁTICAS                                        │
│     • Auto-add high-intent keywords                         │
│     • Auto-add negative keywords                            │
│     • Bid adjustments based on intent score                 │
│     • Ad copy suggestions based on intent                   │
│                                                              │
│  ✅ CONFIGURAÇÕES DE SEGURANÇA                               │
│     • max_keywords_per_cycle: 50                            │
│     • max_negatives_per_cycle: 30                           │
│     • max_bid_increase: 30%                                 │
│     • max_bid_decrease: 20%                                 │
│     • require_approval_for_large_changes: true              │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 5. 💰 BUDGET OPTIMIZATION (Bayesian/Ax)

```
┌─────────────────────────────────────────────────────────────┐
│              BUDGET OPTIMIZATION (Ax/Bayesian)               │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ✅ OTIMIZAÇÃO BAYESIANA                                     │
│                                                              │
│     Algoritmo: Ax (Meta's Adaptive Experimentation)         │
│     ══════════════════════════════════════════════          │
│                                                              │
│     ┌──────────────────────────────────────────────────┐    │
│     │  Entrada:                                         │    │
│     │  • Budget total: R$ 50.000/mês                   │    │
│     │  • Campanhas: 5 (Google, Meta, TikTok x2, Pinterest)│  │
│     │  • Histórico: 90 dias de performance             │    │
│     │  • Objetivo: Maximizar ROAS                      │    │
│     └──────────────────────────────────────────────────┘    │
│                         │                                    │
│                         ▼                                    │
│     ┌──────────────────────────────────────────────────┐    │
│     │  Processo:                                        │    │
│     │  1. Gaussian Process modeling                    │    │
│     │  2. Expected Improvement acquisition             │    │
│     │  3. Multi-objective optimization (ROAS + Volume) │    │
│     │  4. Constraints (min/max per platform)           │    │
│     └──────────────────────────────────────────────────┘    │
│                         │                                    │
│                         ▼                                    │
│     ┌──────────────────────────────────────────────────┐    │
│     │  Saída (Alocação Otimizada):                     │    │
│     │  • Google Ads:    R$ 18.000 (36%) ↑ 12%         │    │
│     │  • Meta Ads:      R$ 15.000 (30%) ↓ 5%          │    │
│     │  • TikTok #1:     R$ 8.000  (16%) ↑ 8%          │    │
│     │  • TikTok #2:     R$ 6.000  (12%) ↓ 3%          │    │
│     │  • Pinterest:     R$ 3.000  (6%)  ═ 0%          │    │
│     └──────────────────────────────────────────────────┘    │
│                                                              │
│  ✅ FUNCIONALIDADES                                          │
│     • Auto-rebalancing (diário/semanal)                     │
│     • Safety limits (max change per cycle)                  │
│     • Performance monitoring post-change                    │
│     • Auto-rollback se performance cair > 20%               │
│     • Multi-objective: ROAS + CPA + Volume                  │
│                                                              │
│  ✅ SAFETY CONTROLS                                          │
│     • max_increase_pct: 100% (dobrar)                       │
│     • max_decrease_pct: 50% (cortar pela metade)            │
│     • min_budget: R$ 5,00                                   │
│     • dry_run mode para preview                             │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 6. 🌤️ WEATHER-BASED BIDDING

```
┌─────────────────────────────────────────────────────────────┐
│                  WEATHER-BASED BIDDING                       │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ✅ COMO FUNCIONA                                            │
│                                                              │
│     ┌─────────────────────────────────────────────────────┐ │
│     │  Condição        │ Produto       │ Bid Mult │ Budget│ │
│     ├──────────────────┼───────────────┼──────────┼───────┤ │
│     │ 🌧️ Chuva         │ Guarda-chuvas │   1.5x   │ +30%  │ │
│     │ 🌧️ Chuva         │ Delivery food │   1.3x   │ +20%  │ │
│     │ ☀️ Sol (>30°C)   │ Protetor solar│   1.4x   │ +20%  │ │
│     │ ☀️ Sol (>30°C)   │ Ar condicion. │   1.6x   │ +40%  │ │
│     │ ❄️ Frio (<10°C)  │ Casacos       │   1.5x   │ +30%  │ │
│     │ ❄️ Neve          │ Botas inverno │   1.5x   │ +30%  │ │
│     │ 🌧️ Chuva         │ Academia/Gym  │   1.2x   │ +10%  │ │
│     │ ☀️ Sol claro     │ Móveis jardim │   1.3x   │ +10%  │ │
│     └─────────────────────────────────────────────────────┘ │
│                                                              │
│  ✅ INTEGRAÇÃO                                               │
│     • OpenWeatherMap API                                    │
│     • Forecast de até 5 dias                                │
│     • Múltiplas cidades por campanha                        │
│     • Ajustes em tempo real                                 │
│                                                              │
│  ✅ WORKFLOW                                                 │
│     1. Monitor weather every 30 min                         │
│     2. Match conditions with product rules                  │
│     3. Calculate bid/budget multipliers                     │
│     4. Apply via Google Ads/Meta location bid modifiers     │
│     5. Log changes for analysis                             │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 7. 🤖 MACHINE LEARNING & AI

```
┌─────────────────────────────────────────────────────────────┐
│                   MACHINE LEARNING & AI                      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ✅ FRAUD DETECTION (Detecção de Fraude/IVT)                │
│                                                              │
│     Modelo: Random Forest + Rule-based                      │
│     ══════════════════════════════════════                  │
│     Features:                                               │
│     • Session duration / page views ratio                   │
│     • Click patterns (time between clicks)                  │
│     • Mouse movement entropy                                │
│     • Known bot User-Agent patterns                         │
│     • IP reputation (datacenter, proxy, VPN)                │
│     • Geographic anomalies                                  │
│     • Device fingerprint consistency                        │
│                                                              │
│     Output: Trust Score (0.0 - 1.0)                         │
│     • < 0.3: Bot/Invalid → Block                            │
│     • 0.3-0.7: Suspicious → Flag for review                 │
│     • > 0.7: Valid → Process normally                       │
│                                                              │
│  ✅ LTV PREDICTION (Lifetime Value)                         │
│                                                              │
│     Modelo: XGBoost / BigQuery ML                           │
│     ══════════════════════════════════════                  │
│     Features:                                               │
│     • First purchase value                                  │
│     • Days since first purchase                             │
│     • Purchase frequency                                    │
│     • Average order value                                   │
│     • Product categories purchased                          │
│     • Engagement metrics (email opens, site visits)         │
│                                                              │
│  ✅ CHURN PREDICTION (Previsão de Churn)                    │
│                                                              │
│     Modelo: Logistic Regression / Neural Network            │
│     ══════════════════════════════════════                  │
│     Features:                                               │
│     • Days since last purchase                              │
│     • Decrease in purchase frequency                        │
│     • Support ticket count                                  │
│     • Email unsubscribe events                              │
│     • Cart abandonment rate increase                        │
│                                                              │
│  ✅ PROPENSITY SCORING (Propensão à Compra)                 │
│                                                              │
│     • Real-time scoring                                     │
│     • Segment: High/Medium/Low propensity                   │
│     • Use for: Personalization, Retargeting audiences       │
│                                                              │
│  ✅ ANOMALY DETECTION                                        │
│                                                              │
│     Modelo: Prophet + Statistical                           │
│     ══════════════════════════════════════                  │
│     Detecta:                                                │
│     • Spending spikes/drops                                 │
│     • CTR anomalies                                         │
│     • Conversion rate changes                               │
│     • Traffic pattern shifts                                │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 8. 👥 CUSTOMER DATA PLATFORM (CDP)

```
┌─────────────────────────────────────────────────────────────┐
│               CUSTOMER DATA PLATFORM (CDP)                   │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ✅ IDENTITY RESOLUTION (Unificação de Identidade)          │
│                                                              │
│     ┌─────────────────────────────────────────────────────┐ │
│     │  Inputs:                                             │ │
│     │  • anonymous_id (cookie/device)                     │ │
│     │  • user_id (após login)                             │ │
│     │  • email                                            │ │
│     │  • phone                                            │ │
│     │  • device_id                                        │ │
│     │  • browser fingerprint                              │ │
│     └─────────────────────────────────────────────────────┘ │
│                         │                                    │
│                         ▼                                    │
│     ┌─────────────────────────────────────────────────────┐ │
│     │  Identity Graph:                                     │ │
│     │                                                      │ │
│     │    [cookie_A]──┐                                    │ │
│     │    [cookie_B]──┼──→ [UNIFIED_PROFILE_123]          │ │
│     │    [email]─────┤         │                          │ │
│     │    [phone]─────┘         ▼                          │ │
│     │                    ┌───────────┐                    │ │
│     │                    │ 360° View │                    │ │
│     │                    └───────────┘                    │ │
│     └─────────────────────────────────────────────────────┘ │
│                                                              │
│  ✅ UNIFIED PROFILE                                          │
│     • Total lifetime value                                  │
│     • All touchpoints history                               │
│     • Product preferences                                   │
│     • Channel preferences                                   │
│     • Predicted segments (LTV, Churn risk)                  │
│     • Attribution path                                      │
│                                                              │
│  ✅ AUDIENCE SEGMENTS                                        │
│     • High-value customers (LTV > R$1000)                   │
│     • At-risk churners (probability > 0.7)                  │
│     • Recent purchasers (last 7 days)                       │
│     • Cart abandoners (last 24h)                            │
│     • Newsletter engaged                                    │
│     • Custom segments (rules-based)                         │
│                                                              │
│  ✅ AUDIENCE SYNC                                            │
│     • Meta Custom Audiences                                 │
│     • Google Ads Customer Match                             │
│     • TikTok Custom Audiences                               │
│     • Real-time sync                                        │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 9. 🔍 COMPETITIVE INTELLIGENCE

```
┌─────────────────────────────────────────────────────────────┐
│               COMPETITIVE INTELLIGENCE                       │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ✅ COMPETITOR PRICE MONITORING                              │
│                                                              │
│     ┌─────────────────────────────────────────────────────┐ │
│     │  Stealth Scraper Features:                           │ │
│     │  • Rotating residential proxies                     │ │
│     │  • Random user-agent rotation                       │ │
│     │  • Adaptive rate limiting                           │ │
│     │  • CAPTCHA solving (2Captcha/Anti-Captcha)         │ │
│     │  • Headless browser fallback                        │ │
│     └─────────────────────────────────────────────────────┘ │
│                                                              │
│     Price Data Collected:                                   │
│     • Product name & URL                                    │
│     • Current price                                         │
│     • Stock status                                          │
│     • Price history                                         │
│                                                              │
│  ✅ AD CREATIVE ANALYSIS                                     │
│                                                              │
│     Via Meta Ad Library API:                                │
│     • Competitor ad creatives                               │
│     • Ad copy analysis                                      │
│     • Active/Inactive status                                │
│     • Spend estimates (where available)                     │
│                                                              │
│  ✅ VISION API ANALYSIS                                      │
│                                                              │
│     • Extract text from ad images                           │
│     • Detect objects/products                               │
│     • Analyze visual style/colors                           │
│     • Compare with your creatives                           │
│                                                              │
│  ✅ COPY ARCHITECT (AI Ad Copy)                              │
│                                                              │
│     Powered by: Claude/GPT-4                                │
│     • Generate ad headlines (multiple variants)             │
│     • Generate descriptions                                 │
│     • A/B test suggestions                                  │
│     • Tone matching (formal/casual/urgent)                  │
│     • Multi-language support                                │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 10. 📊 DASHBOARDS & REPORTING

```
┌─────────────────────────────────────────────────────────────┐
│                 DASHBOARDS & REPORTING                       │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ✅ REAL-TIME DASHBOARD                                      │
│                                                              │
│     ┌─────────────────────────────────────────────────────┐ │
│     │  ╔════════════════════════════════════════════════╗ │ │
│     │  ║  TODAY'S PERFORMANCE                           ║ │ │
│     │  ╠════════════════════════════════════════════════╣ │ │
│     │  ║  Spend: R$12,450  │  Revenue: R$89,230        ║ │ │
│     │  ║  ROAS: 7.17x      │  Conversions: 234         ║ │ │
│     │  ║  CPA: R$53.21     │  CTR: 2.8%                ║ │ │
│     │  ╚════════════════════════════════════════════════╝ │ │
│     │                                                      │ │
│     │  [ROAS by Platform - Bar Chart]                     │ │
│     │  [Conversions Timeline - Line Chart]                │ │
│     │  [Attribution Funnel - Sankey Diagram]              │ │
│     │  [Geographic Heatmap]                               │ │
│     └─────────────────────────────────────────────────────┘ │
│                                                              │
│  ✅ MÉTRICAS DISPONÍVEIS                                     │
│     • Impressions, Clicks, CTR                              │
│     • Cost, CPC, CPM                                        │
│     • Conversions, Conversion Rate                          │
│     • Revenue, ROAS, CPA                                    │
│     • LTV, CAC, LTV:CAC ratio                               │
│     • Attribution by model                                  │
│     • Cohort analysis                                       │
│                                                              │
│  ✅ ALERTAS & NOTIFICAÇÕES                                   │
│     • Slack integration                                     │
│     • Email notifications                                   │
│     • Telegram bot                                          │
│     • Webhooks customizados                                 │
│                                                              │
│     Alert Types:                                            │
│     • Spending above/below threshold                        │
│     • ROAS drop > X%                                        │
│     • Conversion rate anomaly                               │
│     • Campaign paused/error                                 │
│     • Budget exhausted                                      │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 11. 🏢 ENTERPRISE FEATURES

```
┌─────────────────────────────────────────────────────────────┐
│                   ENTERPRISE FEATURES                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ✅ MULTI-TENANCY                                            │
│                                                              │
│     ┌─────────────────────────────────────────────────────┐ │
│     │  Plan      │ Events/day │ API/min │ Campaigns │ Users│ │
│     ├────────────┼────────────┼─────────┼───────────┼──────┤ │
│     │  FREE      │   10,000   │    60   │     5     │   2  │ │
│     │  STARTER   │  100,000   │   300   │    20     │   5  │ │
│     │  PRO       │ 1,000,000  │  1,000  │   100     │  20  │ │
│     │  ENTERPRISE│ Unlimited  │ 10,000  │ Unlimited │ ∞    │ │
│     └─────────────────────────────────────────────────────┘ │
│                                                              │
│  ✅ AUTHENTICATION & SECURITY                                │
│     • JWT authentication                                    │
│     • OAuth2 / OpenID Connect                               │
│     • SAML 2.0 SSO                                          │
│     • RBAC (Role-Based Access Control)                      │
│     • Team API Keys                                         │
│     • 2FA support                                           │
│                                                              │
│  ✅ AUDIT & COMPLIANCE                                       │
│     • Full audit logging                                    │
│     • Data retention policies                               │
│     • GDPR compliance tools                                 │
│     • LGPD compliance tools                                 │
│     • Data export/deletion                                  │
│     • Privacy clean rooms                                   │
│                                                              │
│  ✅ HIGH AVAILABILITY                                        │
│     • Multi-region deployment                               │
│     • Auto-scaling (HPA)                                    │
│     • Circuit breaker patterns                              │
│     • Retry with exponential backoff                        │
│     • Graceful degradation                                  │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 🛠️ TECHNOLOGY STACK

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              TECHNOLOGY STACK                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                           EDGE LAYER                                    │ │
│  │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐     │ │
│  │  │   Cloudflare     │  │   TypeScript     │  │    Wrangler      │     │ │
│  │  │    Workers       │  │     (ES2022)     │  │      CLI         │     │ │
│  │  └──────────────────┘  └──────────────────┘  └──────────────────┘     │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                         BACKEND LAYER                                   │ │
│  │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐     │ │
│  │  │     Python       │  │     FastAPI      │  │     Uvicorn      │     │ │
│  │  │      3.11+       │  │    (async)       │  │   (ASGI server)  │     │ │
│  │  └──────────────────┘  └──────────────────┘  └──────────────────┘     │ │
│  │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐     │ │
│  │  │     Pydantic     │  │      SQLAlchemy  │  │     Alembic      │     │ │
│  │  │   (validation)   │  │       (ORM)      │  │  (migrations)    │     │ │
│  │  └──────────────────┘  └──────────────────┘  └──────────────────┘     │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                          DATA LAYER                                     │ │
│  │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐     │ │
│  │  │    BigQuery      │  │      Redis       │  │   Cloud Pub/Sub  │     │ │
│  │  │ (data warehouse) │  │     (cache)      │  │     (queue)      │     │ │
│  │  └──────────────────┘  └──────────────────┘  └──────────────────┘     │ │
│  │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐     │ │
│  │  │       dbt        │  │    BigQuery ML   │  │   Cloud Storage  │     │ │
│  │  │ (transformations)│  │   (ML models)    │  │     (files)      │     │ │
│  │  └──────────────────┘  └──────────────────┘  └──────────────────┘     │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                        ML/AI LAYER                                      │ │
│  │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐     │ │
│  │  │   scikit-learn   │  │      XGBoost     │  │     Prophet      │     │ │
│  │  │   (ML models)    │  │   (boosting)     │  │    (forecast)    │     │ │
│  │  └──────────────────┘  └──────────────────┘  └──────────────────┘     │ │
│  │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐     │ │
│  │  │   Ax (Meta)      │  │    Vertex AI     │  │  Claude/GPT-4    │     │ │
│  │  │   (Bayesian)     │  │   (ML Ops)       │  │   (LLM/Copy)     │     │ │
│  │  └──────────────────┘  └──────────────────┘  └──────────────────┘     │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                       FRONTEND LAYER                                    │ │
│  │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐     │ │
│  │  │      React       │  │    TypeScript    │  │    Tailwind      │     │ │
│  │  │       18+        │  │                  │  │       CSS        │     │ │
│  │  └──────────────────┘  └──────────────────┘  └──────────────────┘     │ │
│  │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐     │ │
│  │  │      Vite        │  │     Recharts     │  │   React Query    │     │ │
│  │  │    (bundler)     │  │    (charts)      │  │  (data fetching) │     │ │
│  │  └──────────────────┘  └──────────────────┘  └──────────────────┘     │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                       INFRA & DEVOPS                                    │ │
│  │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐     │ │
│  │  │     Docker       │  │   Kubernetes     │  │      Helm        │     │ │
│  │  │                  │  │     (GKE)        │  │    (charts)      │     │ │
│  │  └──────────────────┘  └──────────────────┘  └──────────────────┘     │ │
│  │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐     │ │
│  │  │    Terraform     │  │  GitHub Actions  │  │   Cloud Run      │     │ │
│  │  │     (IaC)        │  │    (CI/CD)       │  │  (serverless)    │     │ │
│  │  └──────────────────┘  └──────────────────┘  └──────────────────┘     │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                       MONITORING                                        │ │
│  │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐     │ │
│  │  │    Prometheus    │  │     Grafana      │  │      Loki        │     │ │
│  │  │    (metrics)     │  │   (dashboards)   │  │     (logs)       │     │ │
│  │  └──────────────────┘  └──────────────────┘  └──────────────────┘     │ │
│  │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐     │ │
│  │  │   AlertManager   │  │   OpenTelemetry  │  │      Jaeger      │     │ │
│  │  │    (alerts)      │  │    (tracing)     │  │   (distributed)  │     │ │
│  │  └──────────────────┘  └──────────────────┘  └──────────────────┘     │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 📈 FLUXO DE DADOS COMPLETO

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         COMPLETE DATA FLOW                                   │
└─────────────────────────────────────────────────────────────────────────────┘

     WEBSITE/APP                    EDGE                         BACKEND
    ┌─────────┐               ┌─────────────┐              ┌─────────────────┐
    │  Event  │──────────────▶│  Cloudflare │─────────────▶│    FastAPI      │
    │ (click, │               │   Worker    │              │                 │
    │purchase)│               │             │              │ • Validate      │
    └─────────┘               │ • Validate  │              │ • Enrich        │
                              │ • Hash PII  │              │ • Store BQ      │
                              │ • Enrich    │              │ • Queue Pub/Sub │
                              │ • Score     │              │                 │
                              └─────────────┘              └────────┬────────┘
                                                                    │
                    ┌───────────────────────────────────────────────┘
                    │
                    ▼
    ┌─────────────────────────────────────────────────────────────────────────┐
    │                         PARALLEL PROCESSING                              │
    ├─────────────────┬─────────────────┬─────────────────┬───────────────────┤
    │   CAPI Dispatch │   Attribution   │   ML Scoring    │   Real-time       │
    │                 │                 │                 │   Dashboard       │
    │  ┌───────────┐  │  ┌───────────┐  │  ┌───────────┐  │  ┌───────────┐   │
    │  │   Meta    │  │  │ Calculate │  │  │   LTV     │  │  │  WebSocket│   │
    │  │  Google   │  │  │ Touchpoint│  │  │  Churn    │  │  │   Push    │   │
    │  │  TikTok   │  │  │  Weights  │  │  │ Propensity│  │  │           │   │
    │  │ LinkedIn  │  │  │           │  │  │  Fraud    │  │  │           │   │
    │  └───────────┘  │  └───────────┘  │  └───────────┘  │  └───────────┘   │
    └─────────────────┴─────────────────┴─────────────────┴───────────────────┘
                                        │
                                        ▼
    ┌─────────────────────────────────────────────────────────────────────────┐
    │                            DATA WAREHOUSE                                │
    │                                                                          │
    │    ┌────────────────┐    ┌────────────────┐    ┌────────────────┐       │
    │    │   events_raw   │    │ user_profiles  │    │  conversions   │       │
    │    │                │    │                │    │                │       │
    │    │ • event_name   │    │ • unified_id   │    │ • conversion_id│       │
    │    │ • user_id      │    │ • ltv_predicted│    │ • value        │       │
    │    │ • properties   │    │ • churn_prob   │    │ • attribution  │       │
    │    │ • trust_score  │    │ • segments     │    │ • touchpoints  │       │
    │    └────────────────┘    └────────────────┘    └────────────────┘       │
    │                                                                          │
    └─────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
    ┌─────────────────────────────────────────────────────────────────────────┐
    │                           AUTOMATION LAYER                               │
    │                                                                          │
    │    ┌───────────────────┐    ┌───────────────────┐    ┌────────────────┐ │
    │    │      gROAS        │    │  Budget Optimizer │    │ Weather Bidder │ │
    │    │                   │    │                   │    │                │ │
    │    │ • Analyze intent  │    │ • Bayesian opt    │    │ • Weather API  │ │
    │    │ • +/- keywords    │    │ • Reallocate $    │    │ • Bid adjust   │ │
    │    │ • Bid adjustments │    │ • Safety limits   │    │ • Geo targeting│ │
    │    └─────────┬─────────┘    └─────────┬─────────┘    └───────┬────────┘ │
    │              │                        │                      │          │
    └──────────────┼────────────────────────┼──────────────────────┼──────────┘
                   │                        │                      │
                   ▼                        ▼                      ▼
    ┌─────────────────────────────────────────────────────────────────────────┐
    │                         AD PLATFORMS (APIs)                              │
    │                                                                          │
    │    ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐│
    │    │  Google  │  │   Meta   │  │  TikTok  │  │ LinkedIn │  │Pinterest ││
    │    │   Ads    │  │   Ads    │  │   Ads    │  │   Ads    │  │   Ads    ││
    │    │          │  │          │  │          │  │          │  │          ││
    │    │• Campaigns│  │• Campaigns│  │• Campaigns│  │• Campaigns│  │• Campaigns│
    │    │• Keywords │  │• Ad Sets │  │• Ad Groups│  │• Audiences│  │• Pins    ││
    │    │• Bids    │  │• Creatives│  │• Creatives│  │• Creatives│  │• Boards  ││
    │    └──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────┘│
    │                                                                          │
    └─────────────────────────────────────────────────────────────────────────┘
```

---

## 💰 CASOS DE USO E ROI ESPERADO

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         CASOS DE USO & ROI                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ✅ E-COMMERCE                                                               │
│     ───────────────────────────────────────────────────────                 │
│     Problema: iOS 14.5+ quebrou tracking, ROAS caiu 40%                     │
│     Solução: Server-side tracking + Enhanced Conversions                    │
│     ROI: +95% de eventos recuperados, ROAS subiu 35%                        │
│                                                                              │
│  ✅ LEAD GENERATION                                                          │
│     ───────────────────────────────────────────────────────                 │
│     Problema: Leads não estavam sendo atribuídos corretamente               │
│     Solução: Offline conversion upload + MTA                                │
│     ROI: Identificou que 40% das conversões vinham de Google                │
│          (antes achava que era 60% Facebook)                                │
│                                                                              │
│  ✅ SaaS / SUBSCRIPTION                                                      │
│     ───────────────────────────────────────────────────────                 │
│     Problema: CAC alto, não sabia quais canais traziam LTV alto             │
│     Solução: LTV prediction + Budget allocation                             │
│     ROI: Reduziu CAC em 28% realocando budget para canais                   │
│          que traziam usuários com maior LTV                                 │
│                                                                              │
│  ✅ VAREJO / MULTI-STORE                                                     │
│     ───────────────────────────────────────────────────────                 │
│     Problema: Campanhas nacionais sem otimização local                      │
│     Solução: Weather bidding + Geo performance                              │
│     ROI: +22% ROAS em dias de chuva para delivery                           │
│          +18% ROAS em dias quentes para sorveterias                         │
│                                                                              │
│  ✅ AGÊNCIA / MULTI-TENANT                                                   │
│     ───────────────────────────────────────────────────────                 │
│     Problema: Gerenciar 50+ clientes manualmente                            │
│     Solução: Multi-tenancy + Automated alerts                               │
│     ROI: 70% menos tempo em otimização manual                               │
│          Escala de 50 para 200 clientes com mesma equipe                    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 📊 MÉTRICAS DO SISTEMA

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          SYSTEM METRICS                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  CÓDIGO                                                                      │
│  ═══════════════════════════════════════════════════════════                │
│  │ Linguagem     │ Arquivos │ Linhas   │ Propósito                │        │
│  ├───────────────┼──────────┼──────────┼─────────────────────────┤        │
│  │ Python        │    142   │  75,367  │ Backend, ML, Automation │        │
│  │ TypeScript    │     50   │  15,000+ │ Edge Workers, Frontend  │        │
│  │ SQL           │     28   │   3,000+ │ BigQuery, Migrations    │        │
│  │ YAML          │     26   │   2,500+ │ Config, CI/CD, K8s      │        │
│  ├───────────────┼──────────┼──────────┼─────────────────────────┤        │
│  │ TOTAL         │   246+   │  95,000+ │                         │        │
│  └───────────────┴──────────┴──────────┴─────────────────────────┘        │
│                                                                              │
│  PERFORMANCE TARGETS                                                         │
│  ═══════════════════════════════════════════════════════════                │
│  • Event processing latency: < 50ms (Edge)                                  │
│  • API response time: < 200ms (p95)                                         │
│  • Throughput: 100,000+ events/second                                       │
│  • Uptime SLA: 99.9%                                                        │
│  • Data freshness: Real-time (< 1 second)                                   │
│                                                                              │
│  SCALABILITY                                                                 │
│  ═══════════════════════════════════════════════════════════                │
│  • Horizontal auto-scaling (HPA)                                            │
│  • Multi-region deployment ready                                            │
│  • BigQuery: Petabyte-scale storage                                         │
│  • Edge: 300+ Cloudflare data centers                                       │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

**S.S.I. SHADOW** - Transformando dados em decisões inteligentes de marketing 🚀
