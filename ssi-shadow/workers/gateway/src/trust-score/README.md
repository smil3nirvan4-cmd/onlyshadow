# S.S.I. SHADOW - Trust Score Module

Módulo de detecção de bots e scoring de confiança heurístico.

## 🎯 Objetivo

Filtrar tráfego inválido (IVT - Invalid Traffic) antes de enviar para CAPIs, economizando budget de ads e melhorando a qualidade dos dados.

## 📊 Como Funciona

O módulo analisa múltiplos sinais do request e do Ghost Script para calcular um score de 0.0 (bot) a 1.0 (humano).

### Sinais Analisados

| Categoria | Sinais | Peso |
|-----------|--------|------|
| **User-Agent** | Bot keywords, headless browser, automation tools | Alto |
| **IP/ASN** | Datacenter IPs (AWS, GCP, Azure, etc) | Médio |
| **Headers** | Accept-Language, Accept-Encoding, Client Hints | Baixo-Médio |
| **TLS** | Versão TLS (1.0/1.1 = suspeito) | Médio |
| **Fingerprint** | Canvas, WebGL (SwiftShader = headless) | Alto |
| **Behavioral** | Scroll, clicks, tempo na página | Médio |
| **Rate Limit** | Requests por IP/fingerprint | Crítico |

### Thresholds

| Score | Ação | Descrição |
|-------|------|-----------|
| < 0.3 | `block` | Não envia para CAPI |
| 0.3 - 0.6 | `challenge` | Envia com flag de suspeito |
| > 0.6 | `allow` | Envia normalmente |

## 🔧 Configuração

### Environment Variables

```toml
# wrangler.toml
[vars]
TRUST_SCORE_THRESHOLD = "0.3"  # Threshold para bloquear

# KV Namespace para rate limiting
[[kv_namespaces]]
binding = "RATE_LIMIT"
id = "your-kv-namespace-id"
```

### Criar KV Namespace

```bash
wrangler kv:namespace create "RATE_LIMIT"
```

## 📤 Response

```json
{
  "success": true,
  "event_id": "uuid",
  "ssi_id": "ssi_uuid",
  "trust_score": 0.85,
  "trust_action": "allow",
  "platforms": {
    "meta": { "sent": true }
  },
  "processing_time_ms": 45
}
```

## 🚫 Penalizações

| Código | Penalização | Descrição |
|--------|-------------|-----------|
| `BOT_USER_AGENT` | -0.8 | Bot keyword no UA |
| `HEADLESS_BROWSER` | -0.7 | HeadlessChrome, PhantomJS |
| `AUTOMATION_TOOL` | -0.8 | Selenium, Puppeteer |
| `RATE_LIMIT_EXCEEDED` | -0.9 | Limite de requests excedido |
| `DATACENTER_IP` | -0.5 | IP de datacenter (AWS, GCP, etc) |
| `SEC_CH_UA_MISMATCH` | -0.4 | Inconsistência Client Hints |
| `OLD_TLS_VERSION` | -0.3 | TLS 1.0/1.1 |
| `SUSPICIOUS_WEBGL` | -0.5 | SwiftShader, LLVMpipe |
| `MISSING_ACCEPT_LANGUAGE` | -0.2 | Header ausente |
| `ZERO_SCROLL_30S` | -0.3 | Sem scroll após 30s |
| `ZERO_CLICKS_30S` | -0.2 | Sem clicks após 30s |

## ✅ Bônus

| Código | Bônus | Descrição |
|--------|-------|-----------|
| `RESIDENTIAL_IP` | +0.15 | IP residencial/ISP |
| `VALID_CLIENT_HINTS` | +0.1 | Client Hints consistentes |
| `HAS_BEHAVIORAL_DATA` | +0.1 | Dados comportamentais presentes |
| `NATURAL_SCROLL_PATTERN` | +0.1 | Scroll natural (25-99%) |
| `MULTIPLE_CLICKS` | +0.1 | 2+ clicks |
| `CONSISTENT_FINGERPRINT` | +0.1 | Fingerprint consistente |

## 📁 Estrutura

```
trust-score/
├── index.ts        # Módulo principal
├── signals.ts      # Extração de sinais
├── rules.ts        # Regras de scoring
└── rate-limit.ts   # Rate limiting com KV
```

## 🔌 Uso

```typescript
import {
  calculateTrustScore,
  quickBotCheck,
  shouldSendToCAPI,
} from './trust-score';

// Quick check (fast rejection)
const quickCheck = quickBotCheck(request);
if (quickCheck.isBot) {
  return blocked();
}

// Full trust score
const trustScore = await calculateTrustScore(request, event, env);

// Check if should send to CAPI
const decision = shouldSendToCAPI(trustScore, env);
if (!decision.send) {
  console.log('Blocked:', decision.reason);
}
```

## 📊 Rate Limiting

### Configurações

| Tipo | Janela | Limite | Bloqueio |
|------|--------|--------|----------|
| IP | 1 min | 100 req | 5 min |
| Fingerprint | 1 min | 60 req | 10 min |
| Burst | 1 seg | 10 req | 1 min |

### Como funciona

1. Cada request incrementa contador no KV
2. Se limite excedido, IP/fingerprint é bloqueado temporariamente
3. Contador reseta após janela expirar

## 🧪 Testando

### Simular bot

```bash
curl -X POST https://ssi-shadow.workers.dev/api/collect \
  -H "Content-Type: application/json" \
  -H "User-Agent: python-requests/2.28.0" \
  -d '{"event_name":"PageView"}'
```

**Esperado:** `trust_score: 0.1`, `trust_action: block`

### Simular humano

```bash
curl -X POST https://ssi-shadow.workers.dev/api/collect \
  -H "Content-Type: application/json" \
  -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0" \
  -H "Accept-Language: pt-BR,pt;q=0.9" \
  -H "Accept-Encoding: gzip, deflate, br" \
  -d '{
    "event_name":"PageView",
    "scroll_depth": 45,
    "time_on_page": 30000,
    "clicks": 3,
    "canvas_hash": "abc123",
    "webgl_renderer": "ANGLE (Intel, Mesa Intel UHD Graphics 620)"
  }'
```

**Esperado:** `trust_score: 0.85+`, `trust_action: allow`

## 📈 Métricas Esperadas

- **Bot detection rate:** 15-25% do tráfego
- **False positive rate:** < 1%
- **Processing time:** < 10ms

## 🔒 Privacidade

- IPs são hasheados antes de logar
- Nenhum PII é armazenado no KV
- Dados comportamentais são agregados

## 🚀 Próximos Passos

1. **FingerprintJS Pro** - Se IVT > 15%, adicionar para accuracy 99.5%
2. **Machine Learning** - Treinar modelo com dados coletados
3. **IP Reputation API** - Integrar com MaxMind/IPQualityScore

---

**S.S.I. SHADOW** - Server-Side Intelligence for Optimized Ads
