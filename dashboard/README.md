# S.S.I. SHADOW Dashboard

Dashboard de administração para monitoramento do sistema S.S.I. SHADOW.

## 🚀 Features

- **Visão Geral**: Métricas em tempo real de eventos, usuários e receita
- **Plataformas**: Status de Meta, TikTok, Google e BigQuery
- **Trust Score**: Distribuição e análise de bot detection
- **ML Predictions**: LTV, Churn e Propensity segments
- **Funil**: Análise de conversão e-commerce

## 📦 Tech Stack

- **React 18** - UI Framework
- **TypeScript** - Type safety
- **Vite** - Build tool
- **Tailwind CSS** - Styling
- **Recharts** - Charts

## 🛠️ Setup

```bash
# Instalar dependências
npm install

# Rodar em desenvolvimento
npm run dev

# Build para produção
npm run build

# Preview do build
npm run preview
```

## 📁 Estrutura

```
dashboard/
├── public/
│   └── favicon.svg
├── src/
│   ├── components/
│   │   ├── ui.tsx          # Componentes base
│   │   ├── Charts.tsx      # Gráficos Recharts
│   │   └── Dashboard.tsx   # Dashboard principal
│   ├── hooks/
│   │   └── useData.ts      # Data fetching hooks
│   ├── types/
│   │   └── index.ts        # TypeScript types
│   ├── App.tsx
│   ├── main.tsx
│   └── index.css
├── index.html
├── package.json
├── tailwind.config.js
├── tsconfig.json
└── vite.config.ts
```

## 🔧 Configuração

### Variáveis de Ambiente

Crie um arquivo `.env`:

```env
VITE_API_URL=https://ssi-shadow.YOUR-SUBDOMAIN.workers.dev
```

### API Endpoints Esperados

O dashboard espera os seguintes endpoints:

| Endpoint | Descrição |
|----------|-----------|
| `GET /api/dashboard/overview` | Métricas gerais |
| `GET /api/dashboard/platforms` | Status das plataformas |
| `GET /api/dashboard/trust-score` | Métricas de trust score |
| `GET /api/dashboard/ml-predictions` | Predições ML |
| `GET /api/dashboard/bid-metrics` | Métricas de bid |
| `GET /api/dashboard/recent-events` | Eventos recentes |
| `GET /api/dashboard/funnel` | Métricas de funil |

## 🎨 Customização

### Cores

Edite `tailwind.config.js` para customizar cores:

```js
theme: {
  extend: {
    colors: {
      brand: {
        500: '#3b82f6', // Sua cor primária
      },
    },
  },
},
```

### Gráficos

Os gráficos usam Recharts. Personalize cores em `src/components/Charts.tsx`:

```tsx
const COLORS = {
  primary: '#3B82F6',
  secondary: '#8B5CF6',
  success: '#10B981',
  // ...
};
```

## 📊 Screenshots

### Visão Geral
- Cards de métricas (Eventos, Usuários, Receita, Conversão)
- Status das plataformas
- Gráfico de eventos por hora
- Tabela de eventos recentes

### Trust Score
- Distribuição por faixa
- Ações (allow/challenge/block)
- Top motivos de bloqueio

### ML Predictions
- Segmentos LTV (VIP, High, Medium, Low)
- Risco de Churn
- Distribuição de estratégias de bid

### Funil
- Funil de conversão visual
- Taxas de conversão por etapa

## 🔌 Integração com Worker

Adicione endpoints de dashboard ao Worker:

```typescript
// workers/gateway/src/index.ts
router.get('/api/dashboard/overview', handleDashboardOverview);
router.get('/api/dashboard/platforms', handleDashboardPlatforms);
// ...
```

## 📝 License

MIT

---

**S.S.I. SHADOW** - Server-Side Intelligence for Optimized Ads
