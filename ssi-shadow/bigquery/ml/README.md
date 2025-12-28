# S.S.I. SHADOW - Machine Learning Module

Modelos de ML no BigQuery para predição de LTV, Churn e Propensão de Compra.

## 📊 Modelos Disponíveis

| Modelo | Tipo | Target | Atualização |
|--------|------|--------|-------------|
| model_ltv_90d | Boosted Tree Regressor | Revenue 90 dias | Mensal |
| model_ltv_tier | Boosted Tree Classifier | Tier (VIP/High/Med/Low) | Mensal |
| model_will_purchase | Boosted Tree Classifier | Vai comprar? (0/1) | Mensal |
| model_churn_30d | Boosted Tree Classifier | Vai churnar? (0/1) | Semanal |
| model_churn_score | Boosted Tree Regressor | Score de risco | Semanal |
| model_propensity_7d | Boosted Tree Classifier | Compra em 7d? (0/1) | Diário |
| model_propensity_score | Boosted Tree Regressor | Score de propensão | Horário |

## 🏗️ Arquitetura

```
┌─────────────────────────────────────────────────────────────────┐
│                      Feature Engineering                         │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │ml_features_ltv  │  │ml_features_churn│  │ml_features_prop │ │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘ │
└───────────┼─────────────────────┼─────────────────────┼─────────┘
            │                     │                     │
            ▼                     ▼                     ▼
┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐
│   LTV Models    │   │  Churn Models   │   │Propensity Models│
│  ┌───────────┐  │   │  ┌───────────┐  │   │  ┌───────────┐  │
│  │ Regressor │  │   │  │ Classifier│  │   │  │ Classifier│  │
│  └───────────┘  │   │  └───────────┘  │   │  └───────────┘  │
│  ┌───────────┐  │   │  ┌───────────┐  │   │  ┌───────────┐  │
│  │ Classifier│  │   │  │  Scorer   │  │   │  │  Scorer   │  │
│  └───────────┘  │   │  └───────────┘  │   │  └───────────┘  │
└────────┬────────┘   └────────┬────────┘   └────────┬────────┘
         │                     │                     │
         ▼                     ▼                     ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Prediction Tables                             │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────────┐   │
│  │predictions_ltv│  │predictions_   │  │predictions_       │   │
│  │               │  │churn          │  │propensity         │   │
│  └───────────────┘  └───────────────┘  └───────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                 ┌────────────────────────┐
                 │  v_realtime_bid_signals│
                 │   (Worker queries this)│
                 └────────────────────────┘
```

## 🚀 Setup Inicial

### 1. Criar Feature Tables

```bash
bq query --use_legacy_sql=false < ml/features/feature_engineering.sql
```

### 2. Preparar Training Data

```sql
-- No BigQuery Console
CALL `ssi_shadow.prepare_training_data`(DATE_SUB(CURRENT_DATE(), INTERVAL 60 DAY));
```

### 3. Treinar Modelos

```bash
# LTV
bq query --use_legacy_sql=false < ml/models/ltv_model.sql

# Churn
bq query --use_legacy_sql=false < ml/models/churn_model.sql

# Propensity
bq query --use_legacy_sql=false < ml/models/propensity_model.sql
```

### 4. Verificar Modelos

```sql
-- Listar modelos
SELECT * FROM `ssi_shadow.INFORMATION_SCHEMA.MODELS`;

-- Avaliar LTV model
SELECT * FROM ML.EVALUATE(MODEL `ssi_shadow.model_ltv_90d`);
```

## 📈 Features Utilizadas

### LTV Features

| Feature | Descrição | Importância |
|---------|-----------|-------------|
| purchase_frequency_monthly | Compras por mês | Alta |
| avg_order_value | Ticket médio | Alta |
| recency_score | Decaimento exponencial | Alta |
| log_total_revenue | Log da receita total | Média |
| is_repeat_buyer | Comprou mais de 1x | Média |
| checkout_to_purchase_rate | Taxa de conversão | Média |

### Churn Features

| Feature | Descrição | Importância |
|---------|-----------|-------------|
| days_since_last_activity | Recência | Muito Alta |
| activity_trend_30d | Tendência de atividade | Alta |
| session_trend | Tendência de sessões | Alta |
| declining_activity | Flag de declínio | Média |
| has_purchased | É cliente? | Média |

### Propensity Features

| Feature | Descrição | Importância |
|---------|-----------|-------------|
| add_to_cart_7d | Adições ao carrinho | Muito Alta |
| checkout_7d | Checkouts iniciados | Muito Alta |
| has_cart_activity | Tem carrinho ativo? | Alta |
| product_views_7d | Views de produto | Média |
| is_customer | Já comprou antes? | Média |

## 📊 Métricas de Avaliação

### LTV Model

| Métrica | Valor Esperado |
|---------|----------------|
| MAE (Mean Absolute Error) | < R$50 |
| RMSE | < R$100 |
| R² | > 0.6 |

### Churn Model

| Métrica | Valor Esperado |
|---------|----------------|
| AUC-ROC | > 0.8 |
| Precision (churn) | > 0.6 |
| Recall (churn) | > 0.7 |

### Propensity Model

| Métrica | Valor Esperado |
|---------|----------------|
| AUC-ROC | > 0.75 |
| Precision (purchase) | > 0.4 |
| Recall (purchase) | > 0.6 |

## 🔄 Agendamento

### Scheduled Queries no BigQuery

```sql
-- Diário: Features + Propensity
CALL `ssi_shadow.predict_propensity_hourly`();

-- Diário: Churn
CALL `ssi_shadow.predict_churn_daily`();

-- Semanal: LTV (mais pesado)
-- (Re-treinar manualmente ou via Cloud Scheduler)
```

### Cloud Scheduler

```bash
# Criar job para predições diárias
gcloud scheduler jobs create http predict-daily \
  --schedule="0 2 * * *" \
  --uri="https://bigquery.googleapis.com/bigquery/v2/projects/PROJECT/queries" \
  --http-method=POST \
  --message-body='{"query":"CALL ssi_shadow.predict_churn_daily();"}'
```

## 🔗 Integração com Worker

### ml-integration.ts

```typescript
import { getMLPredictions, getBidSignal } from './ml-integration';

// No handleCollect
const predictions = await getMLPredictions(ssiId, env);
const bidSignal = await getBidSignal(event, env);

// Enriquecer evento
event.predicted_ltv = predictions.ltv.predicted_ltv_90d;
event.predicted_intent = predictions.propensity.propensity_tier;
```

### Response enriquecido

```json
{
  "success": true,
  "event_id": "...",
  "ml_signals": {
    "ltv_tier": "high",
    "propensity": 0.72,
    "bid_multiplier": 1.3,
    "segment": "high_value_hot"
  }
}
```

## 📦 Estrutura de Arquivos

```
bigquery/ml/
├── features/
│   └── feature_engineering.sql   # Feature tables
├── models/
│   ├── ltv_model.sql             # LTV prediction
│   ├── churn_model.sql           # Churn prediction
│   └── propensity_model.sql      # Propensity prediction
├── predictions/
│   └── (generated tables)
└── README.md
```

## 💰 Custos BigQuery ML

| Operação | Custo |
|----------|-------|
| Training | $250/TB processado |
| Prediction | $5/TB processado |
| Storage | $0.02/GB/mês |

**Estimativa mensal (1M usuários):**
- Feature tables: ~1GB = $0.02/mês
- Training (mensal): ~10GB = $2.50/mês
- Predictions (diário): ~1GB/dia = $5/mês
- **Total: ~$10/mês**

## 🎯 Use Cases

### 1. Bid Optimization

```sql
-- Usuários high-value com alta propensão
SELECT * FROM `ssi_shadow.v_high_propensity_users`
WHERE ltv_tier = 'high'
  AND propensity_tier = 'very_high';
```

### 2. Churn Prevention

```sql
-- VIPs em risco
SELECT * FROM `ssi_shadow.v_churn_alerts`
WHERE recommended_action = 'immediate_outreach';
```

### 3. Audience Export

```sql
-- Para Meta Custom Audiences
SELECT user_id, segment
FROM `ssi_shadow.v_realtime_bid_signals`
WHERE segment = 'high_value_hot';
```

## 🔒 Boas Práticas

1. **Retrain regularmente**: LTV mensal, Churn semanal
2. **Monitor model drift**: Compare predições vs resultados
3. **Feature importance**: Revise quais features são úteis
4. **A/B test**: Valide bid multipliers antes de escalar
5. **Cache predictions**: Use TTL de 5-15 minutos

---

**S.S.I. SHADOW** - Machine Learning for Optimized Ads
