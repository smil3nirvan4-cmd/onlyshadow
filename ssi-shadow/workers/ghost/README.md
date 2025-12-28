# S.S.I. SHADOW - Ghost Script

Client-side JavaScript para coleta de dados de tracking.

## 📊 Versões Disponíveis

| Versão | Tamanho | Features |
|--------|---------|----------|
| **v1** | ~1.2KB | Click IDs, Cookies, PageView |
| **v2** | ~2.1KB | v1 + Canvas/WebGL Fingerprint |
| **v3** | ~2.9KB | v2 + Lazy Hydration, Behavioral, SPA |
| **min** | ~2.8KB | v3 minificado (produção) |

## 🚀 Instalação Rápida

### Opção 1: CDN (Recomendado)

```html
<!-- Antes de </body> -->
<script>
  window.SSI_ENDPOINT = 'https://ssi-shadow.seu-dominio.workers.dev/api/collect';
</script>
<script src="https://seu-cdn.com/ghost.min.js" defer></script>
```

### Opção 2: Self-hosted

```html
<script>
  window.SSI_ENDPOINT = 'https://ssi-shadow.workers.dev/api/collect';
</script>
<script src="/js/ghost.min.js" defer></script>
```

### Opção 3: Inline (menor latência)

```html
<script>
  window.SSI_ENDPOINT = 'https://ssi-shadow.workers.dev/api/collect';
</script>
<script>
  // Cole aqui o conteúdo de ghost.min.js
</script>
```

## ⚙️ Configuração

### Variáveis Globais (antes do script)

```javascript
// Obrigatório - URL do seu Worker
window.SSI_ENDPOINT = 'https://ssi-shadow.workers.dev/api/collect';

// Opcional - Domínio para cookies (cross-subdomain)
window.SSI_COOKIE_DOMAIN = '.seusite.com';

// Opcional - Debug mode
window.SSI_DEBUG = true;

// Opcional - Desabilitar auto PageView
window.SSI_NO_AUTO_PAGEVIEW = true;

// Opcional - Desabilitar fingerprint (privacidade)
window.SSI_ENABLE_FINGERPRINT = false;

// Opcional - Desabilitar lazy hydration
window.SSI_LAZY_HYDRATION = false;

// Opcional - Habilitar modo SPA
window.SSI_SPA_MODE = true;

// Opcional - Desabilitar tracking comportamental
window.SSI_TRACK_BEHAVIOR = false;
```

### Configuração via API

```javascript
SSI.config({
  endpoint: 'https://ssi-shadow.workers.dev/api/collect',
  cookieDomain: '.seusite.com',
  debug: true,
  enableFingerprint: true,
  lazyHydration: true,
  trackBehavior: true,
  spaMode: false
});
```

## 📤 Rastreamento de Eventos

### PageView (automático)

O PageView é enviado automaticamente no carregamento da página.

```javascript
// Manual (se SSI_NO_AUTO_PAGEVIEW = true)
SSI.pageview();
```

### ViewContent

```javascript
// Quando usuário visualiza um produto
SSI.viewContent(
  ['SKU-001'],           // content_ids
  'Tênis Nike Air Max',  // content_name
  299.90,                // value
  'Calçados'             // content_category (opcional)
);
```

### AddToCart

```javascript
// Quando usuário adiciona ao carrinho
SSI.addToCart(
  ['SKU-001', 'SKU-002'], // content_ids
  549.90,                  // value
  'BRL',                   // currency
  'Kit Tênis + Meia'       // content_name (opcional)
);
```

### InitiateCheckout

```javascript
// Quando usuário inicia checkout
SSI.initiateCheckout(
  ['SKU-001', 'SKU-002'], // content_ids
  549.90,                  // value
  'BRL',                   // currency
  2                        // num_items
);
```

### Purchase

```javascript
// Quando compra é concluída
SSI.purchase(
  549.90,                  // value
  'BRL',                   // currency
  'PED-12345',             // order_id
  ['SKU-001', 'SKU-002'],  // content_ids
  {                        // extra data (opcional)
    coupon: 'DESCONTO10',
    shipping: 29.90
  }
);
```

### Lead

```javascript
// Quando usuário se cadastra como lead
SSI.lead(
  'cliente@email.com',     // email
  '+5511999999999',        // phone
  0,                       // value (opcional)
  {                        // extra data (opcional)
    source: 'landing_page',
    campaign: 'black_friday'
  }
);
```

### CompleteRegistration

```javascript
// Quando usuário completa cadastro
SSI.completeRegistration(
  'cliente@email.com',     // email
  '+5511999999999',        // phone
  'email'                  // method (opcional)
);
```

### Search

```javascript
// Quando usuário faz busca
SSI.search(
  'tênis nike',            // search_string
  ['SKU-001', 'SKU-002']   // content_ids encontrados (opcional)
);
```

### Identify (Identificação de Usuário)

```javascript
// Quando usuário faz login ou fornece dados
SSI.identify(
  'cliente@email.com',     // email
  '+5511999999999',        // phone
  'USR-12345',             // external_id (seu sistema)
  {                        // extra data (opcional)
    name: 'João Silva',
    customer_since: '2023-01-15'
  }
);
```

### Evento Customizado

```javascript
// Qualquer evento customizado
SSI.track('CustomEvent', {
  custom_param: 'valor',
  another_param: 123
});
```

## 🔄 Suporte a SPAs

### React / Next.js

```javascript
// Em _app.js ou layout principal
import { useEffect } from 'react';
import { useRouter } from 'next/router';

function MyApp({ Component, pageProps }) {
  const router = useRouter();

  useEffect(() => {
    // Habilitar modo SPA
    if (window.SSI) {
      SSI.config({ spaMode: true });
    }

    // Ou usar trackNavigation manual
    const handleRouteChange = () => {
      if (window.SSI) {
        SSI.trackNavigation();
      }
    };

    router.events.on('routeChangeComplete', handleRouteChange);
    return () => {
      router.events.off('routeChangeComplete', handleRouteChange);
    };
  }, []);

  return <Component {...pageProps} />;
}
```

### Vue.js / Nuxt

```javascript
// Em router/index.js ou plugin
router.afterEach(() => {
  if (window.SSI) {
    SSI.trackNavigation();
  }
});
```

### Modo Automático

```javascript
// Habilita detecção automática de navegação
window.SSI_SPA_MODE = true;
```

## 📊 Lazy Hydration

O Ghost Script v3 usa **Lazy Hydration** para melhor performance:

1. **Carga inicial leve**: Apenas captura click IDs e envia PageView básico
2. **Hydration completa após interação**:
   - Scroll > 10%
   - Click em qualquer elemento
   - 5 segundos de permanência
3. **Após hydration**: Fingerprint e behavioral tracking ativados

### Forçar Hydration Manual

```javascript
// Forçar hydration imediata
SSI.hydrate();

// Verificar se está hydrated
if (SSI.isHydrated()) {
  console.log('Full tracking ativo');
}
```

## 🔧 API Completa

### Métodos de Tracking

| Método | Descrição |
|--------|-----------|
| `SSI.pageview()` | Rastreia visualização de página |
| `SSI.track(name, data)` | Evento customizado |
| `SSI.purchase(value, currency, orderId, contentIds, extra)` | Compra |
| `SSI.lead(email, phone, value, extra)` | Lead/cadastro |
| `SSI.addToCart(contentIds, value, currency, name)` | Adicionar ao carrinho |
| `SSI.viewContent(contentIds, name, value, category)` | Visualizar conteúdo |
| `SSI.initiateCheckout(contentIds, value, currency, numItems)` | Iniciar checkout |
| `SSI.completeRegistration(email, phone, method)` | Completar cadastro |
| `SSI.search(query, contentIds)` | Busca |
| `SSI.identify(email, phone, externalId, extra)` | Identificar usuário |

### Métodos Utilitários

| Método | Descrição |
|--------|-----------|
| `SSI.getSSIId()` | Retorna SSI ID do usuário |
| `SSI.getSessionId()` | Retorna ID da sessão |
| `SSI.getFingerprint()` | Retorna dados de fingerprint |
| `SSI.getBehavior()` | Retorna dados comportamentais |
| `SSI.isHydrated()` | Verifica se hydration completa |
| `SSI.hydrate()` | Força hydration |
| `SSI.config(options)` | Configura opções |
| `SSI.debug(enable)` | Ativa/desativa debug |
| `SSI.trackNavigation()` | Força tracking de navegação SPA |
| `SSI.version` | Retorna versão do script |

## 🍪 Cookies Criados

| Cookie | Duração | Descrição |
|--------|---------|-----------|
| `_ssi_id` | 1 ano | Identificador único do usuário |
| `_ssi_session` | 30 min | Identificador da sessão |
| `_ssi_session_start` | 30 min | Timestamp início da sessão |
| `_fbc` | 90 dias | Meta Click ID (fbclid) |
| `_fbp` | 1 ano | Meta Browser ID |
| `_gcl_aw` | 90 dias | Google Click ID |
| `_ttp` | 90 dias | TikTok Click ID |

## 🔒 Privacidade

### Desabilitar Fingerprint

```javascript
window.SSI_ENABLE_FINGERPRINT = false;
```

### Respeitar Do Not Track

O script detecta automaticamente `navigator.doNotTrack` e inclui essa informação no payload.

### LGPD/GDPR Compliance

```javascript
// Carrega script apenas após consentimento
if (userHasConsent()) {
  var script = document.createElement('script');
  script.src = '/js/ghost.min.js';
  document.body.appendChild(script);
}
```

## 🐛 Debug

```javascript
// Ativar debug
SSI.debug(true);

// Ver dados coletados
console.log('SSI ID:', SSI.getSSIId());
console.log('Session:', SSI.getSessionId());
console.log('Fingerprint:', SSI.getFingerprint());
console.log('Behavior:', SSI.getBehavior());
console.log('Hydrated:', SSI.isHydrated());
```

## 📋 Exemplo Completo

```html
<!DOCTYPE html>
<html>
<head>
  <title>Minha Loja</title>
</head>
<body>
  <!-- Conteúdo da página -->
  
  <button onclick="addToCart()">Adicionar ao Carrinho</button>
  
  <!-- Configuração do Ghost Script -->
  <script>
    window.SSI_ENDPOINT = 'https://ssi-shadow.minhaloja.workers.dev/api/collect';
    window.SSI_COOKIE_DOMAIN = '.minhaloja.com';
    window.SSI_DEBUG = false;
  </script>
  
  <!-- Ghost Script -->
  <script src="/js/ghost.min.js" defer></script>
  
  <!-- Eventos customizados -->
  <script>
    function addToCart() {
      SSI.addToCart(['SKU-001'], 299.90, 'BRL', 'Tênis Nike');
      alert('Produto adicionado!');
    }
    
    // Identificar usuário após login
    function onLogin(user) {
      SSI.identify(user.email, user.phone, user.id);
    }
    
    // Purchase após confirmação do pagamento
    function onPaymentConfirmed(order) {
      SSI.purchase(
        order.total,
        'BRL',
        order.id,
        order.items.map(i => i.sku)
      );
    }
  </script>
</body>
</html>
```

## 📈 Integração com E-commerce

### WooCommerce

```php
// functions.php
add_action('woocommerce_thankyou', function($order_id) {
    $order = wc_get_order($order_id);
    $items = array();
    foreach ($order->get_items() as $item) {
        $items[] = $item->get_product()->get_sku();
    }
    ?>
    <script>
        SSI.purchase(
            <?php echo $order->get_total(); ?>,
            '<?php echo $order->get_currency(); ?>',
            '<?php echo $order_id; ?>',
            <?php echo json_encode($items); ?>
        );
    </script>
    <?php
});
```

### Shopify

```liquid
{% if first_time_accessed %}
<script>
  SSI.purchase(
    {{ total_price | money_without_currency | remove: ',' }},
    '{{ shop.currency }}',
    '{{ order.order_number }}',
    [{% for item in line_items %}'{{ item.sku }}'{% unless forloop.last %},{% endunless %}{% endfor %}]
  );
</script>
{% endif %}
```

## 🔄 Changelog

### v3.0.0
- Lazy Hydration para melhor performance
- Behavioral tracking (scroll, time, clicks)
- Suporte completo a SPAs
- MutationObserver para detecção de navegação
- Engagement ping on page unload

### v2.0.0
- Canvas fingerprinting
- WebGL fingerprinting
- Plugin detection
- Touch support detection

### v1.0.0
- Click ID capture (fbclid, gclid, ttclid)
- Cookie management (_fbc, _fbp)
- Basic PageView tracking
- sendBeacon for reliable delivery

---

**S.S.I. SHADOW** - Server-Side Intelligence for Optimized Ads
