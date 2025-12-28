# S.S.I. SHADOW - Guia de Integração

Guia para desenvolvedores frontend integrarem o tracking em seus sites.

## 🚀 Quick Start

### Opção 1: Ghost Script (Recomendado)

```html
<!-- Antes do </head> -->
<script>
  window.SSI_CONFIG = {
    endpoint: 'https://ssi-shadow.YOUR-SUBDOMAIN.workers.dev/api/collect',
    debug: false
  };
</script>
<script src="ghost.min.js" defer></script>
```

O Ghost Script automaticamente:
- Rastreia PageView em todas as páginas
- Captura click IDs (fbclid, gclid, ttclid)
- Coleta cookies (_fbc, _fbp)
- Mede scroll depth e tempo na página
- Gera fingerprint para detecção de bots

### Opção 2: Integração Manual (JavaScript)

```javascript
// Função helper para enviar eventos
async function sendEvent(eventName, eventData = {}) {
  const endpoint = 'https://ssi-shadow.YOUR-SUBDOMAIN.workers.dev/api/collect';
  
  try {
    const response = await fetch(endpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        event_name: eventName,
        url: window.location.href,
        referrer: document.referrer,
        ...eventData
      })
    });
    
    return await response.json();
  } catch (error) {
    console.error('SSI Event Error:', error);
    return null;
  }
}

// Exemplos de uso
sendEvent('PageView');
sendEvent('ViewContent', { content_ids: ['SKU-123'], value: 99.90 });
sendEvent('Purchase', { order_id: 'ORDER-123', value: 299.90 });
```

### Opção 3: Integração via GTM

1. Crie uma Tag HTML Personalizada
2. Adicione o código do Ghost Script
3. Configure o Trigger para "All Pages"

```html
<script>
  window.SSI_CONFIG = {
    endpoint: 'https://ssi-shadow.YOUR-SUBDOMAIN.workers.dev/api/collect'
  };
</script>
<script src="https://seu-cdn.com/ghost.min.js"></script>
```

---

## 📊 Eventos Padrão

### PageView
Rastreado automaticamente pelo Ghost Script.

```javascript
sendEvent('PageView', {
  url: 'https://seusite.com/pagina',
  referrer: 'https://google.com',
  title: 'Título da Página'
});
```

### ViewContent (Visualização de Produto)

```javascript
sendEvent('ViewContent', {
  content_ids: ['SKU-123'],
  content_name: 'Nome do Produto',
  content_category: 'Categoria',
  content_type: 'product',
  value: 99.90,
  currency: 'BRL'
});
```

### AddToCart

```javascript
sendEvent('AddToCart', {
  content_ids: ['SKU-123'],
  content_name: 'Nome do Produto',
  value: 99.90,
  currency: 'BRL',
  num_items: 1
});
```

### InitiateCheckout

```javascript
sendEvent('InitiateCheckout', {
  content_ids: ['SKU-123', 'SKU-456'],
  value: 199.80,
  currency: 'BRL',
  num_items: 2
});
```

### Purchase (Compra)

```javascript
sendEvent('Purchase', {
  // Dados do pedido
  order_id: 'ORDER-12345',
  value: 199.80,
  currency: 'BRL',
  content_ids: ['SKU-123', 'SKU-456'],
  num_items: 2,
  
  // Dados do cliente (para matching)
  email: 'cliente@email.com',
  phone: '+5511999999999',
  first_name: 'João',
  last_name: 'Silva',
  city: 'São Paulo',
  state: 'SP',
  zip: '01310100',
  country: 'BR',
  
  // ID externo (opcional)
  external_id: 'USER-789'
});
```

### Lead (Cadastro/Formulário)

```javascript
sendEvent('Lead', {
  email: 'lead@email.com',
  phone: '+5511888888888',
  first_name: 'Maria',
  last_name: 'Santos'
});
```

### CompleteRegistration

```javascript
sendEvent('CompleteRegistration', {
  email: 'novo@email.com',
  external_id: 'USER-NEW-123'
});
```

### Search

```javascript
sendEvent('Search', {
  search_string: 'camiseta preta masculina'
});
```

---

## 🛒 Integração E-commerce

### WooCommerce

```php
// functions.php
add_action('woocommerce_thankyou', 'ssi_track_purchase');
function ssi_track_purchase($order_id) {
  $order = wc_get_order($order_id);
  
  $items = [];
  foreach ($order->get_items() as $item) {
    $items[] = $item->get_product()->get_sku();
  }
  
  ?>
  <script>
    sendEvent('Purchase', {
      order_id: '<?php echo $order_id; ?>',
      value: <?php echo $order->get_total(); ?>,
      currency: '<?php echo $order->get_currency(); ?>',
      content_ids: <?php echo json_encode($items); ?>,
      email: '<?php echo $order->get_billing_email(); ?>',
      phone: '<?php echo $order->get_billing_phone(); ?>',
      first_name: '<?php echo $order->get_billing_first_name(); ?>',
      last_name: '<?php echo $order->get_billing_last_name(); ?>',
      city: '<?php echo $order->get_billing_city(); ?>',
      state: '<?php echo $order->get_billing_state(); ?>',
      zip: '<?php echo $order->get_billing_postcode(); ?>',
      country: '<?php echo $order->get_billing_country(); ?>'
    });
  </script>
  <?php
}
```

### Shopify

```liquid
{% comment %} theme.liquid - antes do </head> {% endcomment %}
<script>
  window.SSI_CONFIG = {
    endpoint: 'https://ssi-shadow.YOUR-SUBDOMAIN.workers.dev/api/collect'
  };
</script>
<script src="https://seu-cdn.com/ghost.min.js" defer></script>

{% comment %} Em pages de produto {% endcomment %}
{% if template contains 'product' %}
<script>
  document.addEventListener('DOMContentLoaded', function() {
    sendEvent('ViewContent', {
      content_ids: ['{{ product.variants.first.sku }}'],
      content_name: '{{ product.title | escape }}',
      content_category: '{{ product.type | escape }}',
      value: {{ product.price | money_without_currency | remove: ',' }},
      currency: '{{ shop.currency }}'
    });
  });
</script>
{% endif %}

{% comment %} thank_you.liquid {% endcomment %}
<script>
  sendEvent('Purchase', {
    order_id: '{{ order.name }}',
    value: {{ order.total_price | money_without_currency | remove: ',' }},
    currency: '{{ shop.currency }}',
    content_ids: [{% for line_item in order.line_items %}'{{ line_item.sku }}'{% unless forloop.last %},{% endunless %}{% endfor %}],
    email: '{{ order.email }}',
    first_name: '{{ order.billing_address.first_name | escape }}',
    last_name: '{{ order.billing_address.last_name | escape }}',
    phone: '{{ order.billing_address.phone }}',
    city: '{{ order.billing_address.city | escape }}',
    state: '{{ order.billing_address.province_code }}',
    zip: '{{ order.billing_address.zip }}',
    country: '{{ order.billing_address.country_code }}'
  });
</script>
```

### React/Next.js

```tsx
// hooks/useSSI.ts
import { useCallback } from 'react';

const SSI_ENDPOINT = process.env.NEXT_PUBLIC_SSI_ENDPOINT;

interface EventData {
  [key: string]: any;
}

export function useSSI() {
  const sendEvent = useCallback(async (eventName: string, data: EventData = {}) => {
    if (!SSI_ENDPOINT) return;
    
    try {
      const response = await fetch(SSI_ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          event_name: eventName,
          url: window.location.href,
          referrer: document.referrer,
          ...data
        })
      });
      return response.json();
    } catch (error) {
      console.error('SSI Error:', error);
    }
  }, []);

  return { sendEvent };
}

// Uso em componente
function ProductPage({ product }) {
  const { sendEvent } = useSSI();
  
  useEffect(() => {
    sendEvent('ViewContent', {
      content_ids: [product.sku],
      content_name: product.name,
      value: product.price
    });
  }, [product]);
  
  const handleAddToCart = () => {
    sendEvent('AddToCart', {
      content_ids: [product.sku],
      value: product.price
    });
  };
  
  return (
    <button onClick={handleAddToCart}>Adicionar ao Carrinho</button>
  );
}
```

---

## 🔒 Dados de Usuário (PII)

### Campos Aceitos

| Campo | Descrição | Exemplo |
|-------|-----------|---------|
| email | Email do usuário | cliente@email.com |
| phone | Telefone (E.164) | +5511999999999 |
| first_name | Primeiro nome | João |
| last_name | Sobrenome | Silva |
| city | Cidade | São Paulo |
| state | Estado/UF | SP |
| zip | CEP | 01310100 |
| country | País (ISO) | BR |
| external_id | ID no seu sistema | USER-123 |

### Normalização Automática

O Worker normaliza automaticamente:
- **Email:** lowercase, trim
- **Phone:** remove caracteres não numéricos, adiciona código do país
- **Nomes:** lowercase, trim, remove acentos
- **CEP:** remove hífen

Todos os dados são hasheados (SHA-256) antes de enviar às plataformas.

---

## 🧪 Debug

### Ativar modo debug

```javascript
window.SSI_CONFIG = {
  endpoint: 'https://ssi-shadow.workers.dev/api/collect',
  debug: true  // Ativa logs no console
};
```

### Verificar resposta

```javascript
const result = await sendEvent('Purchase', { ... });
console.log('SSI Response:', result);

// Resposta esperada:
// {
//   success: true,
//   event_id: "550e8400-...",
//   ssi_id: "ssi_abc123...",
//   trust_score: 0.85,
//   trust_action: "allow",
//   platforms: {
//     meta: { sent: true, status: 200 },
//     tiktok: { sent: true, status: 200 },
//     google: { sent: true, status: 204 }
//   }
// }
```

### Usar endpoint de teste

```javascript
// Usa test_event_code do Meta/TikTok
const testEndpoint = 'https://ssi-shadow.workers.dev/api/test';
```

---

## ❓ FAQ

### O evento foi bloqueado, por quê?
Verifique o `trust_action` na resposta. Se for `block`, o trust_score estava abaixo do threshold (padrão: 0.3). Isso pode acontecer com:
- User-agents de bots
- IPs de datacenters
- Falta de dados comportamentais

### Como aumentar o Event Match Quality (Meta)?
Envie mais dados de usuário:
- Email (obrigatório para bom EMQ)
- Telefone
- Nome completo
- Endereço

### Posso rastrear em SPAs?
Sim! Chame `sendEvent('PageView')` a cada navegação de rota:

```javascript
// React Router
useEffect(() => {
  sendEvent('PageView', { url: location.pathname });
}, [location]);
```

### Como testar localmente?
Configure o Worker em modo dev:
```bash
cd ssi-shadow-worker
npm run dev
# Use http://localhost:8787/api/collect
```

---

**S.S.I. SHADOW** - Server-Side Intelligence for Optimized Ads
