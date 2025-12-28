/**
 * S.S.I. SHADOW — Ghost Script
 * Client-side tracking mínimo (~1KB minificado)
 * 
 * Responsabilidades:
 * - Capturar click IDs (fbclid, gclid, ttclid)
 * - Ler cookies existentes (_fbp, _fbc)
 * - Coletar sinais do dispositivo
 * - Enviar beacon para Worker
 * - Expor API para eventos customizados
 */

(function(window, document) {
  'use strict';
  
  // Configuração - AJUSTAR PARA SEU ENDPOINT
  var CONFIG = {
    endpoint: 'https://ssi.seudominio.com.br/ingest', // Seu Worker URL
    debug: false
  };
  
  // Estado
  var initialized = false;
  var queue = [];
  
  // ============================================================================
  // UTILITÁRIOS
  // ============================================================================
  
  function getUrlParam(name) {
    try {
      var url = new URL(window.location.href);
      return url.searchParams.get(name) || null;
    } catch (e) {
      return null;
    }
  }
  
  function getCookie(name) {
    var match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
    return match ? match[2] : null;
  }
  
  function getDeviceInfo() {
    return {
      screen: {
        w: window.screen.width,
        h: window.screen.height
      },
      viewport: {
        w: window.innerWidth,
        h: window.innerHeight
      }
    };
  }
  
  // ============================================================================
  // BEACON SENDER
  // ============================================================================
  
  function sendBeacon(data) {
    var payload = JSON.stringify(data);
    
    // Tentar sendBeacon (não bloqueia)
    if (navigator.sendBeacon) {
      try {
        var sent = navigator.sendBeacon(CONFIG.endpoint, payload);
        if (sent) {
          if (CONFIG.debug) console.log('[SSI] Beacon sent:', data.event_name);
          return;
        }
      } catch (e) {}
    }
    
    // Fallback para fetch com keepalive
    try {
      fetch(CONFIG.endpoint, {
        method: 'POST',
        body: payload,
        headers: { 'Content-Type': 'application/json' },
        keepalive: true,
        mode: 'cors'
      }).catch(function() {});
    } catch (e) {
      if (CONFIG.debug) console.error('[SSI] Send failed:', e);
    }
  }
  
  // ============================================================================
  // DATA COLLECTION
  // ============================================================================
  
  function collectData(eventName, customData) {
    var device = getDeviceInfo();
    
    return {
      // Evento
      event_name: eventName || 'PageView',
      timestamp: Date.now(),
      
      // URL e referrer
      url: window.location.href,
      referrer: document.referrer || null,
      
      // Click IDs
      fbclid: getUrlParam('fbclid'),
      gclid: getUrlParam('gclid'),
      ttclid: getUrlParam('ttclid'),
      
      // Cookies Meta
      fbp: getCookie('_fbp'),
      fbc: getCookie('_fbc'),
      
      // Device
      ua: navigator.userAgent,
      screen: device.screen,
      viewport: device.viewport,
      
      // Custom data
      custom_data: customData || null
    };
  }
  
  // ============================================================================
  // PUBLIC API
  // ============================================================================
  
  function track(eventName, customData) {
    if (!initialized) {
      queue.push({ event: eventName, data: customData });
      return;
    }
    
    var data = collectData(eventName, customData);
    sendBeacon(data);
  }
  
  function init(options) {
    if (initialized) return;
    
    // Merge config
    if (options) {
      if (options.endpoint) CONFIG.endpoint = options.endpoint;
      if (options.debug) CONFIG.debug = options.debug;
    }
    
    initialized = true;
    
    // Enviar PageView automático
    track('PageView');
    
    // Processar queue
    while (queue.length > 0) {
      var item = queue.shift();
      track(item.event, item.data);
    }
    
    if (CONFIG.debug) console.log('[SSI] Initialized');
  }
  
  // ============================================================================
  // E-COMMERCE HELPERS
  // ============================================================================
  
  function trackViewContent(contentId, contentName, value, currency) {
    track('ViewContent', {
      content_ids: [contentId],
      content_name: contentName,
      content_type: 'product',
      value: value,
      currency: currency || 'BRL'
    });
  }
  
  function trackAddToCart(contentId, contentName, value, currency, quantity) {
    track('AddToCart', {
      content_ids: [contentId],
      content_name: contentName,
      content_type: 'product',
      value: value,
      currency: currency || 'BRL',
      quantity: quantity || 1
    });
  }
  
  function trackInitiateCheckout(contentIds, value, currency, numItems) {
    track('InitiateCheckout', {
      content_ids: contentIds,
      value: value,
      currency: currency || 'BRL',
      num_items: numItems
    });
  }
  
  function trackPurchase(contentIds, value, currency, orderId, numItems) {
    track('Purchase', {
      content_ids: contentIds,
      value: value,
      currency: currency || 'BRL',
      order_id: orderId,
      num_items: numItems
    });
  }
  
  function trackLead(leadValue, currency) {
    track('Lead', {
      value: leadValue || 0,
      currency: currency || 'BRL'
    });
  }
  
  // ============================================================================
  // FORM CAPTURE (opcional)
  // ============================================================================
  
  function captureForm(formSelector, eventName) {
    try {
      var form = document.querySelector(formSelector);
      if (!form) return;
      
      form.addEventListener('submit', function(e) {
        var data = {};
        var formData = new FormData(form);
        formData.forEach(function(value, key) {
          // Não capturar senhas
          if (key.toLowerCase().includes('password')) return;
          data[key] = value;
        });
        
        track(eventName || 'Lead', { form_data: data });
      });
    } catch (e) {
      if (CONFIG.debug) console.error('[SSI] Form capture error:', e);
    }
  }
  
  // ============================================================================
  // SCROLL TRACKING (opcional)
  // ============================================================================
  
  var scrollMilestones = [25, 50, 75, 90];
  var scrollReached = {};
  
  function initScrollTracking() {
    window.addEventListener('scroll', function() {
      var scrollPercent = Math.round(
        (window.scrollY / (document.body.scrollHeight - window.innerHeight)) * 100
      );
      
      scrollMilestones.forEach(function(milestone) {
        if (scrollPercent >= milestone && !scrollReached[milestone]) {
          scrollReached[milestone] = true;
          track('ScrollDepth', { depth: milestone });
        }
      });
    }, { passive: true });
  }
  
  // ============================================================================
  // EXPORT
  // ============================================================================
  
  // API global
  window.ssi = {
    init: init,
    track: track,
    trackViewContent: trackViewContent,
    trackAddToCart: trackAddToCart,
    trackInitiateCheckout: trackInitiateCheckout,
    trackPurchase: trackPurchase,
    trackLead: trackLead,
    captureForm: captureForm,
    initScrollTracking: initScrollTracking
  };
  
  // Auto-init se atributo presente
  var script = document.currentScript;
  if (script && script.hasAttribute('data-auto')) {
    var endpoint = script.getAttribute('data-endpoint');
    init({ endpoint: endpoint });
  }
  
})(window, document);
