# 🔄 C1: Pub/Sub Event Decoupling

## Resumo

Esta implementação adiciona uma camada de Pub/Sub entre o Worker (Cloudflare) e o BigQuery para garantir **zero perda de dados** durante picos de tráfego (Black Friday, viral, etc).

## Arquitetura

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           ANTES (Risco)                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   User → Ghost.js → Worker → BigQuery (direto)                              │
│                              ↓                                              │
│                        Se BigQuery lento/offline:                           │
│                        ❌ Evento PERDIDO                                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                           DEPOIS (Resiliente)                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   User → Ghost.js → Worker → Pub/Sub → Cloud Function → BigQuery            │
│                       ↓         │                                           │
│                    <50ms      Auto-retry, DLQ                               │
│                       ↓         │                                           │
│                  Se Pub/Sub falhar: Fallback → BigQuery direto              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Benefícios

| Benefício | Descrição |
|-----------|-----------|
| **Zero Data Loss** | Pub/Sub garante entrega (7 dias de retenção) |
| **Latência Baixa** | Worker retorna em <50ms (vs ~200ms direto BQ) |
| **Auto-Scale** | Cloud Function escala automaticamente |
| **Retry Automático** | 5 tentativas com backoff exponencial |
| **Dead Letter Queue** | Eventos que falharam vão para DLQ para análise |
| **Batch Efficiency** | Agrupa 100 eventos por insert (menos custo BQ) |

## Arquivos Criados/Modificados

```
workers/gateway/src/
├── bigquery-v2.ts          # Novo: BigQuery client com Pub/Sub
└── bigquery.ts             # Original (mantido para compatibilidade)

functions/
└── pubsub_consumer.py      # Cloud Function consumer

monitoring/
└── metrics.py              # Métricas de Pub/Sub adicionadas

scripts/
└── setup_pubsub.sh         # Script de setup no GCP
```

## Configuração

### 1. Worker (Cloudflare)

Em `wrangler.toml`:

```toml
[vars]
USE_PUBSUB = "true"
PUBSUB_TOPIC = "raw-events"
ENABLE_BIGQUERY = "true"
BIGQUERY_PROJECT_ID = "seu-projeto"
BIGQUERY_DATASET = "ssi_shadow"
BIGQUERY_TABLE = "events_raw"
```

### 2. GCP Setup

```bash
# Executar script de setup
chmod +x scripts/setup_pubsub.sh
./scripts/setup_pubsub.sh --project=seu-projeto --region=us-central1
```

### 3. Verificar Deploy

```bash
# Testar publicação
gcloud pubsub topics publish raw-events \
  --message='{"test": true}' \
  --project=seu-projeto

# Ver logs da Cloud Function
gcloud functions logs read pubsub-consumer \
  --project=seu-projeto \
  --region=us-central1
```

## Uso no Código

### Worker (TypeScript)

```typescript
import { sendToBigQuery, getPubSubMetrics } from './bigquery-v2';

// Enviar evento (automaticamente usa Pub/Sub com fallback)
const result = await sendToBigQuery(event, request, env, trustScore);

console.log(result);
// {
//   sent: true,
//   pubsub_message_id: "123456789",
//   latency_ms: 42,
//   ingestion_method: "pubsub"
// }

// Ver métricas
const metrics = getPubSubMetrics();
console.log(metrics);
// {
//   published: 1000,
//   failed: 2,
//   fallbackToBigQuery: 2,
//   avgLatencyMs: 38.5
// }
```

### Cloud Function (Python)

A Cloud Function é ativada automaticamente pelo Pub/Sub. Para deploy manual:

```bash
gcloud functions deploy pubsub-consumer \
  --runtime python311 \
  --trigger-topic raw-events \
  --entry-point handle_pubsub_message \
  --memory 512MB \
  --timeout 60s \
  --set-env-vars GCP_PROJECT_ID=xxx,BQ_DATASET=ssi_shadow
```

## Métricas

### Prometheus

```promql
# Taxa de publicação
rate(ssi_pubsub_messages_published_total[5m])

# Lag médio
histogram_quantile(0.95, rate(ssi_pubsub_lag_seconds_bucket[5m]))

# Fallbacks (deveria ser ~0)
increase(ssi_pubsub_fallback_total[1h])

# Tamanho dos batches
histogram_quantile(0.5, rate(ssi_pubsub_batch_size_bucket[5m]))
```

### Grafana Dashboard

```json
{
  "title": "Pub/Sub Event Pipeline",
  "panels": [
    {
      "title": "Events Published/sec",
      "type": "graph",
      "targets": [{
        "expr": "rate(ssi_pubsub_messages_published_total{status='success'}[1m])"
      }]
    },
    {
      "title": "End-to-End Lag (P95)",
      "type": "singlestat",
      "targets": [{
        "expr": "histogram_quantile(0.95, rate(ssi_pubsub_lag_seconds_bucket[5m]))"
      }]
    },
    {
      "title": "Fallbacks to Direct BQ",
      "type": "graph",
      "targets": [{
        "expr": "increase(ssi_pubsub_fallback_total[1h])"
      }]
    }
  ]
}
```

## Alertas

| Alerta | Condição | Severidade |
|--------|----------|------------|
| Consumer Lag High | Unacked messages > 10k por 5min | Warning |
| DLQ Messages | Qualquer mensagem no DLQ | Critical |
| High Fallback Rate | Fallbacks > 10/min | Warning |
| Pub/Sub Unavailable | Publish failures > 50% | Critical |

## Custos Estimados

| Recurso | Volume | Custo/mês |
|---------|--------|-----------|
| Pub/Sub | 10M msgs | ~$4 |
| Cloud Function | 10M invocações | ~$2 |
| BigQuery Streaming | Mesmo de antes | - |
| **Total adicional** | | **~$6/mês** |

## Fallback Behavior

```
┌─────────────────────────────────────────────────────────────────┐
│                      DECISION FLOW                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  USE_PUBSUB = true?                                             │
│       │                                                         │
│       ├── YES → Try Pub/Sub                                     │
│       │         │                                               │
│       │         ├── Success → Return (fast path)                │
│       │         │                                               │
│       │         └── Fail → Fallback to Direct BigQuery          │
│       │                    │                                    │
│       │                    ├── Success → Return (slow path)     │
│       │                    │                                    │
│       │                    └── Fail → Return error              │
│       │                                                         │
│       └── NO → Direct BigQuery (legacy mode)                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Troubleshooting

### Pub/Sub não está recebendo mensagens

```bash
# Verificar se o tópico existe
gcloud pubsub topics describe raw-events

# Verificar permissões do Worker
gcloud iam service-accounts list

# Testar publicação manual
gcloud pubsub topics publish raw-events --message='{"test":1}'
```

### Cloud Function não está processando

```bash
# Ver logs
gcloud functions logs read pubsub-consumer --limit=100

# Verificar subscription
gcloud pubsub subscriptions describe raw-events-consumer

# Ver mensagens não processadas
gcloud pubsub subscriptions pull raw-events-consumer --limit=10
```

### DLQ tem mensagens

```bash
# Ver mensagens no DLQ
gcloud pubsub subscriptions pull raw-events-dlq --limit=10

# Reprocessar (com cuidado)
gcloud pubsub subscriptions seek raw-events-consumer \
  --time=$(date -u +%Y-%m-%dT%H:%M:%SZ)
```

## Rollback

Para desabilitar Pub/Sub e voltar ao modo direto:

```toml
# wrangler.toml
[vars]
USE_PUBSUB = "false"  # Desabilita Pub/Sub
```

O Worker automaticamente volta a inserir diretamente no BigQuery.

## Performance Esperada

| Métrica | Antes | Depois |
|---------|-------|--------|
| Latência Worker | ~200ms | ~50ms |
| Data Loss em Pico | Possível | Zero |
| Custo Black Friday | Igual | +$20 |
| Throughput Máximo | ~1k/s | ~100k/s |
