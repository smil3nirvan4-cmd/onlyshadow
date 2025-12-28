# 🔮 C2: Prophet Anomaly Detection

## Resumo

Sistema de detecção de anomalias em tempo real usando Facebook Prophet.
Detecta automaticamente quedas bruscas (site fora do ar) e picos anormais (ataque bot),
ativando modo de defesa quando necessário.

## Arquitetura

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           ANOMALY DETECTION FLOW                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  BigQuery ──────────────────────────────────────────────────────────────┐   │
│     │                                                                   │   │
│     │ Dados históricos (30 dias)                                        │   │
│     ▼                                                                   │   │
│  ┌─────────────────┐                                                    │   │
│  │  Prophet Model  │ ◄─── Treina diariamente                            │   │
│  │  (Sazonalidade) │      - Diária (hora do dia)                        │   │
│  └────────┬────────┘      - Semanal (dia da semana)                     │   │
│           │                                                             │   │
│           │ Previsão + Intervalo de Confiança (95%)                     │   │
│           ▼                                                             │   │
│  ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐   │   │
│  │  Z-Score Calc   │────▶│  Anomaly Type   │────▶│    Response     │   │   │
│  │                 │     │                 │     │                 │   │   │
│  │ (actual-pred)/σ │     │ SPIKE: >3σ      │     │ • Alert Slack   │   │   │
│  └─────────────────┘     │ DROP: <-3σ      │     │ • Defense Mode  │   │   │
│                          │ NORMAL: ±2σ    │     │ • PagerDuty     │   │   │
│                          └─────────────────┘     └─────────────────┘   │   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Tipos de Anomalia

| Tipo | Descrição | Z-Score | Ação Automática |
|------|-----------|---------|-----------------|
| **SPIKE** | Pico anormal de tráfego | > +3σ | Ativa Defense Mode |
| **DROP** | Queda brusca de tráfego | < -3σ | Alerta crítico |
| **DRIFT** | Desvio gradual | ±2σ a ±3σ | Alerta warning |
| **NORMAL** | Dentro do esperado | ±2σ | Nenhuma |

## Severidades

| Severidade | Condição | Canais |
|------------|----------|--------|
| **INFO** | \|Z-Score\| < 2 | Log only |
| **WARNING** | 2 ≤ \|Z-Score\| < 3 | Slack |
| **CRITICAL** | \|Z-Score\| ≥ 3 | Slack + PagerDuty + Defense Mode |

## Arquivos Criados

```
monitoring/
└── anomaly_detector.py   # 850 linhas - Detector principal

monitoring/
└── metrics.py            # +80 linhas de métricas
```

## Configuração

### Environment Variables

```bash
# BigQuery
GCP_PROJECT_ID=seu-projeto
BQ_DATASET=ssi_shadow
BQ_EVENTS_TABLE=events_raw

# Detection
ANOMALY_CHECK_INTERVAL_MINUTES=10    # Intervalo entre checks
ANOMALY_TRAINING_DAYS=30             # Dias de histórico para treinar
ANOMALY_ZSCORE_THRESHOLD=3.0         # Threshold para anomalia
ANOMALY_WARNING_ZSCORE=2.0           # Threshold para warning
ANOMALY_CRITICAL_ZSCORE=3.0          # Threshold para critical

# Granularity
ANOMALY_AGGREGATION_MINUTES=10       # Janela de agregação

# Defense Mode
DEFENSE_MODE_API_URL=https://api.seusite.com
DEFENSE_MODE_API_KEY=xxx
AUTO_DEFENSE_ON_SPIKE=true           # Ativa automaticamente em spike

# Notifications
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/xxx
PAGERDUTY_ROUTING_KEY=xxx
```

## Uso

### Como Serviço Standalone

```bash
# Monitoramento contínuo
python -m monitoring.anomaly_detector

# Check único
python -m monitoring.anomaly_detector --once

# Treinar modelo
python -m monitoring.anomaly_detector --train

# Ver status
python -m monitoring.anomaly_detector --status
```

### Integrado ao FastAPI

```python
from monitoring.anomaly_detector import anomaly_router

app = FastAPI()
app.include_router(anomaly_router)
```

Endpoints disponíveis:
- `GET /api/anomaly/status` - Status do detector
- `POST /api/anomaly/check` - Trigger manual
- `POST /api/anomaly/train` - Retreinar modelo
- `POST /api/anomaly/defense-mode` - Controlar defense mode

### Integrado ao Código

```python
from monitoring.anomaly_detector import AnomalyDetector

detector = AnomalyDetector()

# Treinar modelo
await detector.train_model()

# Executar check
result = await detector.run_check()

if result and result.is_anomaly:
    print(f"ANOMALY: {result.anomaly_type.value}")
    print(f"Z-Score: {result.zscore:.2f}")
    print(f"Actual: {result.actual_value:.0f}")
    print(f"Expected: {result.predicted_value:.0f}")
```

## Prophet Model

### Features do Modelo

- **Sazonalidade Diária**: Captura padrões por hora do dia
- **Sazonalidade Semanal**: Captura padrões por dia da semana
- **Sazonalidade Horária**: Custom seasonality para variações dentro da hora
- **Intervalo de Confiança**: 95% para detecção precisa
- **Mode Multiplicativo**: Melhor para dados de tráfego web

### Training

```python
# O modelo treina automaticamente com 30 dias de dados
# Retrain automático a cada 24 horas

# Manual retrain
await detector.train_model()
```

### Previsão

```python
# Prophet retorna:
# - yhat: Valor previsto
# - yhat_lower: Limite inferior (2.5%)
# - yhat_upper: Limite superior (97.5%)

predicted, lower, upper = model.get_expected_value(timestamp)
```

## Defense Mode

Quando um SPIKE é detectado, o sistema pode ativar automaticamente o Defense Mode:

```
┌─────────────────────────────────────────────────────────────────┐
│                     DEFENSE MODE FLOW                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  SPIKE Detected (Z > 3σ)                                        │
│        │                                                        │
│        ▼                                                        │
│  ┌─────────────────┐                                            │
│  │ AUTO_DEFENSE=   │                                            │
│  │     true?       │                                            │
│  └────────┬────────┘                                            │
│           │                                                     │
│       YES │                                                     │
│           ▼                                                     │
│  ┌─────────────────┐         ┌─────────────────┐               │
│  │ API Call to     │────────▶│ Worker increases│               │
│  │ Worker          │         │ Trust Score     │               │
│  │                 │         │ threshold 1.5x  │               │
│  └─────────────────┘         └─────────────────┘               │
│           │                          │                          │
│           │                          ▼                          │
│           │                  Mais tráfego suspeito              │
│           │                  é bloqueado automaticamente        │
│           │                                                     │
│           │◄──── Auto-desativa após 30 minutos ────────────────│
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Configuração do Defense Mode

```python
# Ativar manualmente
await detector.defense_controller.activate(
    reason="Ataque bot detectado",
    duration_minutes=30
)

# Desativar
await detector.defense_controller.deactivate()
```

## Métricas Prometheus

```promql
# Checks realizados
ssi_anomaly_checks_total{metric="event_count", result="spike"}

# Anomalias detectadas
ssi_anomaly_detected_total{anomaly_type="spike", severity="critical"}

# Z-Score atual
ssi_anomaly_zscore{metric="event_count"}

# Valores atuais vs previstos
ssi_anomaly_actual_value{metric="event_count"}
ssi_anomaly_predicted_value{metric="event_count"}

# Bounds
ssi_anomaly_prediction_bounds{metric="event_count", bound="lower"}
ssi_anomaly_prediction_bounds{metric="event_count", bound="upper"}

# Duração do training
histogram_quantile(0.95, ssi_anomaly_model_training_duration_seconds_bucket)

# Defense mode
ssi_defense_mode_active
ssi_defense_mode_activations_total{reason="spike"}
```

## Grafana Dashboard

```json
{
  "title": "Anomaly Detection",
  "panels": [
    {
      "title": "Event Volume vs Prediction",
      "type": "timeseries",
      "targets": [
        {"expr": "ssi_anomaly_actual_value{metric='event_count'}", "legendFormat": "Actual"},
        {"expr": "ssi_anomaly_predicted_value{metric='event_count'}", "legendFormat": "Predicted"},
        {"expr": "ssi_anomaly_prediction_bounds{metric='event_count', bound='upper'}", "legendFormat": "Upper Bound"},
        {"expr": "ssi_anomaly_prediction_bounds{metric='event_count', bound='lower'}", "legendFormat": "Lower Bound"}
      ]
    },
    {
      "title": "Z-Score",
      "type": "gauge",
      "targets": [{"expr": "ssi_anomaly_zscore{metric='event_count'}"}],
      "thresholds": [
        {"value": -3, "color": "red"},
        {"value": -2, "color": "orange"},
        {"value": 2, "color": "green"},
        {"value": 3, "color": "orange"}
      ]
    },
    {
      "title": "Anomalies Detected (24h)",
      "type": "stat",
      "targets": [{"expr": "increase(ssi_anomaly_detected_total[24h])"}]
    },
    {
      "title": "Defense Mode Status",
      "type": "stat",
      "targets": [{"expr": "ssi_defense_mode_active"}],
      "mappings": [
        {"value": 0, "text": "INACTIVE", "color": "green"},
        {"value": 1, "text": "ACTIVE", "color": "red"}
      ]
    }
  ]
}
```

## Alertas

### Alertmanager

```yaml
groups:
  - name: anomaly_detection
    rules:
      - alert: TrafficSpikeDetected
        expr: ssi_anomaly_zscore{metric="event_count"} > 3
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Traffic spike detected"
          description: "Z-Score: {{ $value }}"
      
      - alert: TrafficDropDetected
        expr: ssi_anomaly_zscore{metric="event_count"} < -3
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Traffic drop detected - possible site outage"
          description: "Z-Score: {{ $value }}"
      
      - alert: DefenseModeActive
        expr: ssi_defense_mode_active == 1
        for: 1m
        labels:
          severity: warning
        annotations:
          summary: "Defense mode is active"
```

## Exemplo de Alerta Slack

```
┌────────────────────────────────────────────────────────────────┐
│ 📈 SSI Shadow: SPIKE Detected                                  │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│ 🚨 SPIKE DETECTED: Event volume 15847 is 4.2σ above           │
│ expected (3521)                                                │
│                                                                │
│ ────────────────────────────────────                           │
│ Current:   15,847                                              │
│ Expected:   3,521                                              │
│ Z-Score:    4.2σ                                               │
│ Severity:   CRITICAL                                           │
│ ────────────────────────────────────                           │
│                                                                │
│ Defense Mode: ACTIVATED                                        │
│                                                                │
│ 🕐 2024-01-15 14:30 UTC                                        │
│ SSI Shadow Anomaly Detection                                   │
└────────────────────────────────────────────────────────────────┘
```

## Deploy

### Kubernetes CronJob

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: anomaly-detector
spec:
  schedule: "*/10 * * * *"  # A cada 10 minutos
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: detector
            image: ssi-shadow/anomaly-detector:latest
            command: ["python", "-m", "monitoring.anomaly_detector", "--once"]
            env:
            - name: GCP_PROJECT_ID
              valueFrom:
                secretKeyRef:
                  name: gcp-credentials
                  key: project_id
            - name: SLACK_WEBHOOK_URL
              valueFrom:
                secretKeyRef:
                  name: slack-credentials
                  key: webhook_url
          restartPolicy: OnFailure
```

### Cloud Scheduler + Cloud Run

```bash
# Deploy Cloud Run
gcloud run deploy anomaly-detector \
  --image=ssi-shadow/anomaly-detector:latest \
  --region=us-central1 \
  --set-env-vars=GCP_PROJECT_ID=xxx

# Create scheduler
gcloud scheduler jobs create http anomaly-check \
  --schedule="*/10 * * * *" \
  --uri="https://anomaly-detector-xxx.run.app/api/anomaly/check" \
  --http-method=POST
```

## Troubleshooting

### Modelo não está treinando

```bash
# Verificar se há dados suficientes
bq query "SELECT COUNT(*) FROM ssi_shadow.events_raw WHERE event_time > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)"

# Treinar manualmente
python -m monitoring.anomaly_detector --train
```

### Muitos falsos positivos

```bash
# Aumentar threshold
export ANOMALY_ZSCORE_THRESHOLD=4.0
export ANOMALY_WARNING_ZSCORE=3.0

# Ou ajustar intervalo de confiança no código
model = ProphetAnomalyModel(interval_width=0.99)  # 99% CI
```

### Defense Mode não está ativando

```bash
# Verificar URL da API
curl -X POST https://api.seusite.com/api/defense-mode \
  -H "Authorization: Bearer $DEFENSE_MODE_API_KEY" \
  -d '{"enabled": true, "reason": "test"}'
```

## Performance

| Operação | Tempo Típico |
|----------|--------------|
| Training (30 dias) | 10-30 segundos |
| Single check | 1-3 segundos |
| BigQuery query | 0.5-2 segundos |
| Prophet prediction | 0.1-0.5 segundos |

## Custos

| Recurso | Volume | Custo/mês |
|---------|--------|-----------|
| BigQuery (queries) | 144/dia × 30 = 4320 queries | ~$5 |
| Cloud Run (checks) | 4320 invocações | ~$2 |
| **Total** | | **~$7/mês** |
