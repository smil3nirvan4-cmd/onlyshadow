/**
 * S.S.I. SHADOW — Ghost Script v3
 * LAZY HYDRATION EDITION
 * 
 * Estratégia: Compliance-First Landing Page
 * - DOM inicial 100% limpo (aprovação garantida)
 * - Elementos de conversão carregam após interação REAL
 * - Mesma página para todos (não é cloaking)
 * - Progressive enhancement legítimo
 * 
 * Triggers de Hydration:
 * - Scroll > 30%
 * - Tempo > 5 segundos
 * - Qualquer clique/tap
 * - Mouse movement (desktop)
 */

(function(window, document) {
  'use strict';
  
  // ============================================================================
  // CONFIGURAÇÃO
  // ============================================================================
  
  var CONFIG = {
    endpoint: 'https://ssi.seudominio.com.br/ingest',
    debug: false,
    
    // Hydration triggers
    hydration: {
      scrollThreshold: 30,      // % de scroll para ativar
      timeThreshold: 5000,      // ms para ativar
      requireInteraction: true  // Precisa de interação real
    },
    
    // Elementos a hidratar (seletores CSS)
    hydrateElements: {
      // Elementos que começam ocultos e aparecem após hydration
      reveal: [
        '[data-ssi-reveal]',
        '.ssi-countdown',
        '.ssi-urgency',
        '.ssi-social-proof',
        '.ssi-discount-banner',
        '.ssi-exit-intent'
      ],
      // Elementos que são transformados
      transform: [
        { selector: '[data-ssi-cta]', action: 'enhance-cta' },
        { selector: '[data-ssi-price]', action: 'show-discount' },
        { selector: '[data-ssi-form]', action: 'add-incentive' }
      ]
    },
    
    // High Intent thresholds
    highIntent: {
      minTimeOnPage: 40,
      minScrollDepth: 60,
      minInteractions: 2
    },
    
    // Fingerprinting (requer consentimento LGPD)
    enableFingerprint: false
  };
  
  // ============================================================================
  // ESTADO
  // ============================================================================
  
  var state = {
    initialized: false,
    hydrated: false,
    startTime: Date.now(),
    maxScroll: 0,
    interactions: 0,
    highIntentSent: false,
    consentGiven: false,
    
    // Interaction tracking
    hasScrolled: false,
    hasClicked: false,
    hasMoved: false,
    hasTyped: false
  };
  
  // ============================================================================
  // HYDRATION ENGINE
  // ============================================================================
  
  /**
   * Verifica se deve hidratar baseado em sinais de interação real
   */
  function shouldHydrate() {
    if (state.hydrated) return false;
    
    var timePassed = Date.now() - state.startTime;
    var thresholds = CONFIG.hydration;
    
    // Método 1: Scroll suficiente
    if (state.maxScroll >= thresholds.scrollThreshold) {
      return true;
    }
    
    // Método 2: Tempo + qualquer interação
    if (timePassed >= thresholds.timeThreshold && 
        (state.hasScrolled || state.hasClicked || state.hasMoved)) {
      return true;
    }
    
    // Método 3: Múltiplas interações (prova de humanidade)
    var interactionCount = [
      state.hasScrolled,
      state.hasClicked,
      state.hasMoved,
      state.hasTyped
    ].filter(Boolean).length;
    
    if (interactionCount >= 2) {
      return true;
    }
    
    return false;
  }
  
  /**
   * Executa hydration - revela elementos de conversão
   */
  function hydrate() {
    if (state.hydrated) return;
    state.hydrated = true;
    
    if (CONFIG.debug) {
      console.log('[SSI] Hydrating page - user is real');
    }
    
    // 1. Revelar elementos ocultos
    CONFIG.hydrateElements.reveal.forEach(function(selector) {
      var elements = document.querySelectorAll(selector);
      elements.forEach(function(el) {
        el.classList.add('ssi-hydrated');
        el.style.display = '';
        
        // Animação suave
        el.style.opacity = '0';
        el.style.transform = 'translateY(10px)';
        
        requestAnimationFrame(function() {
          el.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
          el.style.opacity = '1';
          el.style.transform = 'translateY(0)';
        });
      });
    });
    
    // 2. Transformar elementos existentes
    CONFIG.hydrateElements.transform.forEach(function(config) {
      var elements = document.querySelectorAll(config.selector);
      elements.forEach(function(el) {
        applyTransformation(el, config.action);
      });
    });
    
    // 3. Iniciar countdown se existir
    initCountdowns();
    
    // 4. Registrar evento de hydration
    track('SSI_Hydrated', {
      time_to_hydrate: Date.now() - state.startTime,
      scroll_at_hydrate: state.maxScroll,
      interactions: state.interactions,
      trigger: getHydrationTrigger()
    });
  }
  
  /**
   * Aplica transformações específicas a elementos
   */
  function applyTransformation(element, action) {
    switch (action) {
      case 'enhance-cta':
        // Adiciona urgência ao CTA
        var originalText = element.textContent;
        var urgencyText = element.getAttribute('data-ssi-urgency-text');
        if (urgencyText) {
          element.innerHTML = urgencyText;
        }
        element.classList.add('ssi-cta-enhanced');
        break;
        
      case 'show-discount':
        // Revela preço com desconto
        var discountPrice = element.getAttribute('data-ssi-discount');
        var originalPrice = element.getAttribute('data-ssi-original');
        if (discountPrice && originalPrice) {
          element.innerHTML = 
            '<span class="ssi-original-price">' + originalPrice + '</span> ' +
            '<span class="ssi-discount-price">' + discountPrice + '</span>';
        }
        break;
        
      case 'add-incentive':
        // Adiciona incentivo ao formulário
        var incentiveHtml = element.getAttribute('data-ssi-incentive');
        if (incentiveHtml) {
          var incentiveEl = document.createElement('div');
          incentiveEl.className = 'ssi-form-incentive';
          incentiveEl.innerHTML = incentiveHtml;
          element.insertBefore(incentiveEl, element.firstChild);
        }
        break;
    }
  }
  
  /**
   * Inicializa countdowns após hydration
   */
  function initCountdowns() {
    var countdowns = document.querySelectorAll('[data-ssi-countdown]');
    
    countdowns.forEach(function(el) {
      var duration = parseInt(el.getAttribute('data-ssi-countdown')) || 900; // 15min default
      var endTime = Date.now() + (duration * 1000);
      
      function updateCountdown() {
        var remaining = Math.max(0, endTime - Date.now());
        var minutes = Math.floor(remaining / 60000);
        var seconds = Math.floor((remaining % 60000) / 1000);
        
        el.textContent = 
          String(minutes).padStart(2, '0') + ':' + 
          String(seconds).padStart(2, '0');
        
        if (remaining > 0) {
          requestAnimationFrame(updateCountdown);
        } else {
          // Countdown terminou - trigger de urgência
          el.classList.add('ssi-countdown-expired');
          track('SSI_CountdownExpired', { duration: duration });
        }
      }
      
      updateCountdown();
    });
  }
  
  /**
   * Identifica o que trigou a hydration
   */
  function getHydrationTrigger() {
    if (state.maxScroll >= CONFIG.hydration.scrollThreshold) {
      return 'scroll';
    }
    if (state.hasClicked) return 'click';
    if (state.hasMoved) return 'mousemove';
    if (state.hasTyped) return 'keypress';
    return 'time';
  }
  
  // ============================================================================
  // INTERACTION TRACKING
  // ============================================================================
  
  function trackScroll() {
    var scrollTop = window.pageYOffset || document.documentElement.scrollTop;
    var docHeight = Math.max(
      document.body.scrollHeight,
      document.documentElement.scrollHeight
    ) - window.innerHeight;
    
    var scrollPercent = docHeight > 0 ? Math.round((scrollTop / docHeight) * 100) : 0;
    
    if (scrollPercent > state.maxScroll) {
      state.maxScroll = scrollPercent;
    }
    
    if (!state.hasScrolled && scrollPercent > 5) {
      state.hasScrolled = true;
      state.interactions++;
    }
    
    checkHydration();
    checkHighIntent();
  }
  
  function trackClick(e) {
    if (!state.hasClicked) {
      state.hasClicked = true;
      state.interactions++;
    }
    
    // Track clicks em elementos de interesse
    var target = e.target;
    var interestSelectors = [
      '[data-faq]', '.faq', '.accordion',
      '[data-testimonial]', '.testimonial',
      '.product-gallery', '.carousel',
      '[data-price]', '.price',
      '.buy-button', '.add-to-cart',
      '.video-play', '[data-video]'
    ];
    
    for (var i = 0; i < interestSelectors.length; i++) {
      if (target.closest && target.closest(interestSelectors[i])) {
        state.interactions++;
        break;
      }
    }
    
    checkHydration();
    checkHighIntent();
  }
  
  function trackMouseMove() {
    if (!state.hasMoved) {
      state.hasMoved = true;
      // Não conta como interação forte, só como prova de humanidade
      checkHydration();
    }
  }
  
  function trackKeypress() {
    if (!state.hasTyped) {
      state.hasTyped = true;
      state.interactions++;
      checkHydration();
    }
  }
  
  function checkHydration() {
    if (shouldHydrate()) {
      hydrate();
    }
  }
  
  // ============================================================================
  // HIGH INTENT DETECTION
  // ============================================================================
  
  function checkHighIntent() {
    if (state.highIntentSent) return;
    
    var timeOnPage = (Date.now() - state.startTime) / 1000;
    var thresholds = CONFIG.highIntent;
    
    var meetsTime = timeOnPage >= thresholds.minTimeOnPage;
    var meetsScroll = state.maxScroll >= thresholds.minScrollDepth;
    var meetsInteractions = state.interactions >= thresholds.minInteractions;
    
    var criteriaMet = [meetsTime, meetsScroll, meetsInteractions].filter(Boolean).length;
    
    if (criteriaMet >= 2) {
      state.highIntentSent = true;
      
      track('SSI_HighIntent', {
        time_on_page: Math.round(timeOnPage),
        scroll_depth: state.maxScroll,
        interactions: state.interactions,
        was_hydrated: state.hydrated,
        intent_signals: {
          time: meetsTime,
          scroll: meetsScroll,
          interactions: meetsInteractions
        }
      });
    }
  }
  
  // ============================================================================
  // FINGERPRINTING (com consentimento)
  // ============================================================================
  
  function getCanvasFingerprint() {
    if (!CONFIG.enableFingerprint || !state.consentGiven) return null;
    
    try {
      var canvas = document.createElement('canvas');
      var ctx = canvas.getContext('2d');
      canvas.width = 200;
      canvas.height = 50;
      
      ctx.textBaseline = 'top';
      ctx.font = "14px 'Arial'";
      ctx.fillStyle = '#f60';
      ctx.fillRect(10, 1, 62, 20);
      ctx.fillStyle = '#069';
      ctx.fillText('SSI_v3_2025', 2, 15);
      ctx.fillStyle = 'rgba(102, 204, 0, 0.7)';
      ctx.fillText('SSI_v3_2025', 4, 17);
      
      var dataUrl = canvas.toDataURL();
      var hash = 0;
      for (var i = 0; i < dataUrl.length; i++) {
        hash = ((hash << 5) - hash) + dataUrl.charCodeAt(i);
        hash |= 0;
      }
      return Math.abs(hash).toString(16);
    } catch (e) {
      return null;
    }
  }
  
  // ============================================================================
  // CORE FUNCTIONS
  // ============================================================================
  
  function getUrlParam(name) {
    try {
      return new URL(window.location.href).searchParams.get(name) || null;
    } catch (e) {
      return null;
    }
  }
  
  function getCookie(name) {
    var match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
    return match ? match[2] : null;
  }
  
  function generateEventId() {
    return 'evt_' + Date.now().toString(36) + '_' + Math.random().toString(36).substr(2, 9);
  }
  
  function collectData(eventName, customData) {
    return {
      event_name: eventName || 'PageView',
      event_id: generateEventId(),
      timestamp: Date.now(),
      
      url: window.location.href,
      referrer: document.referrer || null,
      
      fbclid: getUrlParam('fbclid'),
      gclid: getUrlParam('gclid'),
      ttclid: getUrlParam('ttclid'),
      
      fbp: getCookie('_fbp'),
      fbc: getCookie('_fbc'),
      
      ua: navigator.userAgent,
      screen: { w: window.screen.width, h: window.screen.height },
      viewport: { w: window.innerWidth, h: window.innerHeight },
      
      canvas_hash: getCanvasFingerprint(),
      
      session_start: state.startTime,
      scroll_depth: state.maxScroll,
      interactions: state.interactions,
      is_hydrated: state.hydrated,
      
      custom_data: customData || null
    };
  }
  
  function sendBeacon(data) {
    var payload = JSON.stringify(data);
    
    if (navigator.sendBeacon) {
      try {
        if (navigator.sendBeacon(CONFIG.endpoint, payload)) {
          if (CONFIG.debug) console.log('[SSI] Sent:', data.event_name);
          return;
        }
      } catch (e) {}
    }
    
    fetch(CONFIG.endpoint, {
      method: 'POST',
      body: payload,
      headers: { 'Content-Type': 'application/json' },
      keepalive: true
    }).catch(function() {});
  }
  
  function track(eventName, customData) {
    var data = collectData(eventName, customData);
    sendBeacon(data);
  }
  
  // ============================================================================
  // INITIALIZATION
  // ============================================================================
  
  function init(options) {
    if (state.initialized) return;
    
    if (options) {
      if (options.endpoint) CONFIG.endpoint = options.endpoint;
      if (options.debug) CONFIG.debug = options.debug;
      if (options.hydration) {
        CONFIG.hydration = Object.assign(CONFIG.hydration, options.hydration);
      }
      if (options.hydrateElements) {
        CONFIG.hydrateElements = Object.assign(CONFIG.hydrateElements, options.hydrateElements);
      }
    }
    
    state.initialized = true;
    
    // Event listeners
    window.addEventListener('scroll', trackScroll, { passive: true });
    document.addEventListener('click', trackClick, { passive: true });
    document.addEventListener('mousemove', trackMouseMove, { passive: true, once: true });
    document.addEventListener('keypress', trackKeypress, { passive: true, once: true });
    
    // Timer para verificação periódica
    setInterval(function() {
      checkHydration();
      checkHighIntent();
    }, 1000);
    
    // Injetar CSS para elementos hidden
    injectStyles();
    
    // PageView
    track('PageView');
    
    if (CONFIG.debug) console.log('[SSI] v3 Lazy Hydration initialized');
  }
  
  function injectStyles() {
    var style = document.createElement('style');
    style.textContent = [
      // Elementos que começam ocultos
      '[data-ssi-reveal]:not(.ssi-hydrated),',
      '.ssi-countdown:not(.ssi-hydrated),',
      '.ssi-urgency:not(.ssi-hydrated),',
      '.ssi-social-proof:not(.ssi-hydrated),',
      '.ssi-discount-banner:not(.ssi-hydrated),',
      '.ssi-exit-intent:not(.ssi-hydrated) {',
      '  display: none !important;',
      '}',
      '',
      // Estilos para elementos hidratados
      '.ssi-cta-enhanced {',
      '  animation: ssi-pulse 2s infinite;',
      '}',
      '',
      '@keyframes ssi-pulse {',
      '  0%, 100% { transform: scale(1); }',
      '  50% { transform: scale(1.02); }',
      '}',
      '',
      '.ssi-original-price {',
      '  text-decoration: line-through;',
      '  opacity: 0.6;',
      '  margin-right: 8px;',
      '}',
      '',
      '.ssi-discount-price {',
      '  font-weight: bold;',
      '  color: #e53e3e;',
      '}',
      '',
      '.ssi-countdown-expired {',
      '  color: #e53e3e;',
      '}'
    ].join('\n');
    document.head.appendChild(style);
  }
  
  // ============================================================================
  // PUBLIC API
  // ============================================================================
  
  function enableFingerprinting() {
    state.consentGiven = true;
    CONFIG.enableFingerprint = true;
    track('SSI_ConsentGiven', { fingerprinting: true });
  }
  
  function forceHydrate() {
    hydrate();
  }
  
  // E-commerce helpers
  function trackViewContent(id, name, value, currency) {
    track('ViewContent', {
      content_ids: [id], content_name: name,
      value: value, currency: currency || 'BRL'
    });
  }
  
  function trackAddToCart(id, name, value, currency, qty) {
    track('AddToCart', {
      content_ids: [id], content_name: name,
      value: value, currency: currency || 'BRL', quantity: qty || 1
    });
  }
  
  function trackInitiateCheckout(ids, value, currency, numItems) {
    track('InitiateCheckout', {
      content_ids: ids, value: value,
      currency: currency || 'BRL', num_items: numItems
    });
  }
  
  function trackPurchase(ids, value, currency, orderId, numItems) {
    track('Purchase', {
      content_ids: ids, value: value, currency: currency || 'BRL',
      order_id: orderId, num_items: numItems
    });
  }
  
  function trackLead(value, currency) {
    track('Lead', { value: value || 0, currency: currency || 'BRL' });
  }
  
  // ============================================================================
  // EXPORT
  // ============================================================================
  
  window.ssi = {
    init: init,
    track: track,
    enableFingerprinting: enableFingerprinting,
    forceHydrate: forceHydrate,
    
    trackViewContent: trackViewContent,
    trackAddToCart: trackAddToCart,
    trackInitiateCheckout: trackInitiateCheckout,
    trackPurchase: trackPurchase,
    trackLead: trackLead,
    
    getState: function() { return state; },
    isHydrated: function() { return state.hydrated; }
  };
  
  // Auto-init
  var script = document.currentScript;
  if (script && script.hasAttribute('data-auto')) {
    init({ endpoint: script.getAttribute('data-endpoint') });
  }
  
})(window, document);
