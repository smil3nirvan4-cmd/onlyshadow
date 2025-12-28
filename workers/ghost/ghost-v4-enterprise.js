/**
 * S.S.I. SHADOW — Ghost Script v4
 * ENTERPRISE EDITION
 * 
 * Integrações:
 * - FingerprintJS Pro (99.5% accuracy)
 * - Behavioral biometrics
 * - Lazy Hydration
 * - Cross-device identity
 * 
 * Upgrade de match rate: 50% → 95%+
 */

(function(window, document) {
  'use strict';
  
  // ============================================================================
  // CONFIGURAÇÃO
  // ============================================================================
  
  var CONFIG = {
    endpoint: 'https://ssi.seudominio.com.br/ingest',
    debug: false,
    
    // FingerprintJS Pro
    fingerprintjs: {
      apiKey: '',  // Configurar via init()
      endpoint: 'https://fp.seudominio.com.br',  // Subdomain para melhor accuracy
      region: 'us'
    },
    
    // Hydration triggers
    hydration: {
      scrollThreshold: 30,
      timeThreshold: 5000,
      requireInteraction: true
    },
    
    // High Intent thresholds
    highIntent: {
      minTimeOnPage: 40,
      minScrollDepth: 60,
      minInteractions: 2
    },
    
    // Behavioral biometrics
    biometrics: {
      enabled: true,
      sampleRate: 100,  // ms entre amostras
      maxSamples: 50
    }
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
    
    // FingerprintJS
    visitorId: null,
    fpConfidence: 0,
    fpLoaded: false,
    
    // Behavioral
    mouseMovements: [],
    keyStrokes: [],
    scrollPattern: [],
    
    // Interaction flags
    hasScrolled: false,
    hasClicked: false,
    hasMoved: false,
    hasTyped: false
  };
  
  // ============================================================================
  // FINGERPRINTJS PRO INTEGRATION
  // ============================================================================
  
  var fpPromise = null;
  
  /**
   * Carrega FingerprintJS Pro
   */
  function loadFingerprintJS() {
    if (!CONFIG.fingerprintjs.apiKey) {
      if (CONFIG.debug) console.log('[SSI] FingerprintJS API key not configured, using fallback');
      return Promise.resolve(null);
    }
    
    if (fpPromise) return fpPromise;
    
    fpPromise = new Promise(function(resolve, reject) {
      // Carregar script
      var script = document.createElement('script');
      script.src = 'https://fpjscdn.net/v3/' + CONFIG.fingerprintjs.apiKey + '/loader_v3.8.1.js';
      script.async = true;
      
      script.onload = function() {
        if (window.FingerprintJS) {
          window.FingerprintJS.load({
            apiKey: CONFIG.fingerprintjs.apiKey,
            endpoint: CONFIG.fingerprintjs.endpoint || undefined,
            region: CONFIG.fingerprintjs.region
          }).then(function(fp) {
            state.fpLoaded = true;
            resolve(fp);
          }).catch(reject);
        } else {
          reject(new Error('FingerprintJS not loaded'));
        }
      };
      
      script.onerror = function() {
        if (CONFIG.debug) console.log('[SSI] FingerprintJS failed to load, using fallback');
        resolve(null);
      };
      
      document.head.appendChild(script);
    });
    
    return fpPromise;
  }
  
  /**
   * Obtém visitor ID do FingerprintJS Pro
   */
  async function getVisitorIdentity() {
    try {
      var fp = await loadFingerprintJS();
      
      if (fp) {
        var result = await fp.get({
          extendedResult: true,
          linkedId: getStoredSSIId()  // Linkar com SSI ID existente
        });
        
        state.visitorId = result.visitorId;
        state.fpConfidence = result.confidence.score;
        
        return {
          visitor_id: result.visitorId,
          request_id: result.requestId,
          confidence: result.confidence.score,
          
          // Sinais de bot
          bot_probability: result.bot ? result.bot.probability : 0,
          bot_safe: result.bot ? result.bot.safe : true,
          
          // Incognito detection
          incognito: result.incognito,
          
          // Device info
          browser_name: result.browserName,
          browser_version: result.browserVersion,
          os: result.os,
          os_version: result.osVersion,
          device: result.device,
          
          // Sinais avançados
          ip_location: result.ipLocation,
          first_seen_at: result.firstSeenAt ? result.firstSeenAt.global : null,
          last_seen_at: result.lastSeenAt ? result.lastSeenAt.global : null,
          visitor_found: result.visitorFound,
          
          // Método
          method: 'fingerprintjs_pro'
        };
      }
    } catch (e) {
      if (CONFIG.debug) console.error('[SSI] FingerprintJS error:', e);
    }
    
    // Fallback para fingerprint local
    return getFallbackFingerprint();
  }
  
  /**
   * Fallback fingerprint (canvas + webgl)
   */
  function getFallbackFingerprint() {
    var canvas = getCanvasFingerprint();
    var webgl = getWebGLFingerprint();
    
    // Gerar visitor_id a partir dos hashes
    var combined = (canvas || '') + (webgl || '') + navigator.userAgent;
    var hash = hashCode(combined);
    
    return {
      visitor_id: 'ssi_' + Math.abs(hash).toString(36),
      confidence: 0.6,  // Menor confiança que FingerprintJS Pro
      canvas_hash: canvas,
      webgl_hash: webgl,
      method: 'fallback'
    };
  }
  
  function getCanvasFingerprint() {
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
      ctx.fillText('SSI_v4_2025', 2, 15);
      ctx.fillStyle = 'rgba(102, 204, 0, 0.7)';
      ctx.fillText('SSI_v4_2025', 4, 17);
      
      return hashCode(canvas.toDataURL()).toString(16);
    } catch (e) {
      return null;
    }
  }
  
  function getWebGLFingerprint() {
    try {
      var canvas = document.createElement('canvas');
      var gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
      if (!gl) return null;
      
      var debugInfo = gl.getExtension('WEBGL_debug_renderer_info');
      if (!debugInfo) return null;
      
      var vendor = gl.getParameter(debugInfo.UNMASKED_VENDOR_WEBGL);
      var renderer = gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL);
      
      return hashCode(vendor + '~' + renderer).toString(16);
    } catch (e) {
      return null;
    }
  }
  
  function hashCode(str) {
    var hash = 0;
    for (var i = 0; i < str.length; i++) {
      hash = ((hash << 5) - hash) + str.charCodeAt(i);
      hash |= 0;
    }
    return hash;
  }
  
  // ============================================================================
  // BEHAVIORAL BIOMETRICS
  // ============================================================================
  
  /**
   * Coleta padrões de movimento do mouse
   */
  function trackMouseBiometrics(e) {
    if (!CONFIG.biometrics.enabled) return;
    if (state.mouseMovements.length >= CONFIG.biometrics.maxSamples) return;
    
    state.mouseMovements.push({
      x: e.clientX,
      y: e.clientY,
      t: Date.now() - state.startTime
    });
  }
  
  /**
   * Coleta padrões de digitação
   */
  function trackKeyBiometrics(e) {
    if (!CONFIG.biometrics.enabled) return;
    if (state.keyStrokes.length >= CONFIG.biometrics.maxSamples) return;
    
    state.keyStrokes.push({
      key: e.key ? e.key.length : 0,  // Não armazenar tecla real
      t: Date.now() - state.startTime
    });
    
    if (!state.hasTyped) {
      state.hasTyped = true;
      state.interactions++;
    }
  }
  
  /**
   * Analisa padrões de scroll
   */
  function trackScrollBiometrics() {
    if (!CONFIG.biometrics.enabled) return;
    if (state.scrollPattern.length >= CONFIG.biometrics.maxSamples) return;
    
    state.scrollPattern.push({
      y: window.pageYOffset,
      t: Date.now() - state.startTime
    });
  }
  
  /**
   * Gera score de biometrics (humano vs bot)
   */
  function calculateBiometricScore() {
    var score = 0.5;  // Baseline
    
    // Mouse movements analysis
    if (state.mouseMovements.length >= 10) {
      // Calcular variância de velocidade
      var velocities = [];
      for (var i = 1; i < state.mouseMovements.length; i++) {
        var prev = state.mouseMovements[i - 1];
        var curr = state.mouseMovements[i];
        var dist = Math.sqrt(Math.pow(curr.x - prev.x, 2) + Math.pow(curr.y - prev.y, 2));
        var time = curr.t - prev.t;
        if (time > 0) velocities.push(dist / time);
      }
      
      if (velocities.length > 5) {
        var variance = calculateVariance(velocities);
        // Humanos têm variância alta, bots são consistentes
        if (variance > 0.5) score += 0.15;
        else if (variance < 0.1) score -= 0.2;  // Muito consistente = suspeito
      }
    }
    
    // Keystroke analysis
    if (state.keyStrokes.length >= 5) {
      var intervals = [];
      for (var j = 1; j < state.keyStrokes.length; j++) {
        intervals.push(state.keyStrokes[j].t - state.keyStrokes[j - 1].t);
      }
      
      var keyVariance = calculateVariance(intervals);
      // Humanos têm ritmo variável
      if (keyVariance > 100) score += 0.1;
      else if (keyVariance < 10) score -= 0.15;  // Digitação de bot
    }
    
    // Scroll analysis
    if (state.scrollPattern.length >= 5) {
      // Verificar se scroll é suave (humano) ou instantâneo (bot)
      var scrollJumps = 0;
      for (var k = 1; k < state.scrollPattern.length; k++) {
        var jump = Math.abs(state.scrollPattern[k].y - state.scrollPattern[k - 1].y);
        if (jump > 500) scrollJumps++;  // Jump grande
      }
      
      if (scrollJumps > state.scrollPattern.length * 0.5) {
        score -= 0.1;  // Muitos jumps = suspeito
      }
    }
    
    return Math.max(0, Math.min(1, score));
  }
  
  function calculateVariance(arr) {
    if (arr.length === 0) return 0;
    var mean = arr.reduce(function(a, b) { return a + b; }, 0) / arr.length;
    var squaredDiffs = arr.map(function(x) { return Math.pow(x - mean, 2); });
    return squaredDiffs.reduce(function(a, b) { return a + b; }, 0) / arr.length;
  }
  
  // ============================================================================
  // HYDRATION ENGINE
  // ============================================================================
  
  function shouldHydrate() {
    if (state.hydrated) return false;
    
    var timePassed = Date.now() - state.startTime;
    var thresholds = CONFIG.hydration;
    
    if (state.maxScroll >= thresholds.scrollThreshold) return true;
    
    if (timePassed >= thresholds.timeThreshold && 
        (state.hasScrolled || state.hasClicked || state.hasMoved)) {
      return true;
    }
    
    var interactionCount = [
      state.hasScrolled, state.hasClicked, state.hasMoved, state.hasTyped
    ].filter(Boolean).length;
    
    if (interactionCount >= 2) return true;
    
    return false;
  }
  
  function hydrate() {
    if (state.hydrated) return;
    state.hydrated = true;
    
    if (CONFIG.debug) console.log('[SSI] Hydrating page');
    
    // Revelar elementos
    var elements = document.querySelectorAll('[data-ssi-reveal]');
    elements.forEach(function(el) {
      el.classList.add('ssi-hydrated');
      el.style.display = '';
      el.style.opacity = '0';
      el.style.transform = 'translateY(10px)';
      
      requestAnimationFrame(function() {
        el.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
        el.style.opacity = '1';
        el.style.transform = 'translateY(0)';
      });
    });
    
    // Transformar CTAs
    document.querySelectorAll('[data-ssi-cta]').forEach(function(el) {
      var urgencyText = el.getAttribute('data-ssi-urgency-text');
      if (urgencyText) {
        el.innerHTML = urgencyText;
        el.classList.add('ssi-cta-enhanced');
      }
    });
    
    // Mostrar preços com desconto
    document.querySelectorAll('[data-ssi-price]').forEach(function(el) {
      var original = el.getAttribute('data-ssi-original');
      var discount = el.getAttribute('data-ssi-discount');
      if (original && discount) {
        el.innerHTML = 
          '<span class="ssi-original-price">' + original + '</span> ' +
          '<span class="ssi-discount-price">' + discount + '</span>';
      }
    });
    
    // Iniciar countdowns
    document.querySelectorAll('[data-ssi-countdown]').forEach(function(el) {
      var duration = parseInt(el.getAttribute('data-ssi-countdown')) || 900;
      var endTime = Date.now() + (duration * 1000);
      
      function update() {
        var remaining = Math.max(0, endTime - Date.now());
        var minutes = Math.floor(remaining / 60000);
        var seconds = Math.floor((remaining % 60000) / 1000);
        el.textContent = String(minutes).padStart(2, '0') + ':' + String(seconds).padStart(2, '0');
        if (remaining > 0) requestAnimationFrame(update);
      }
      update();
    });
    
    track('SSI_Hydrated', {
      time_to_hydrate: Date.now() - state.startTime,
      scroll_at_hydrate: state.maxScroll,
      interactions: state.interactions
    });
  }
  
  // ============================================================================
  // TRACKING
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
    
    trackScrollBiometrics();
    checkHydration();
    checkHighIntent();
  }
  
  function trackClick(e) {
    if (!state.hasClicked) {
      state.hasClicked = true;
      state.interactions++;
    }
    
    var interestSelectors = [
      '[data-faq]', '.faq', '.accordion',
      '[data-testimonial]', '.testimonial',
      '.product-gallery', '.carousel',
      '[data-price]', '.price',
      '.buy-button', '.add-to-cart',
      '.video-play', '[data-video]'
    ];
    
    var target = e.target;
    for (var i = 0; i < interestSelectors.length; i++) {
      if (target.closest && target.closest(interestSelectors[i])) {
        state.interactions++;
        break;
      }
    }
    
    checkHydration();
    checkHighIntent();
  }
  
  function trackMouseMove(e) {
    if (!state.hasMoved) {
      state.hasMoved = true;
    }
    trackMouseBiometrics(e);
    checkHydration();
  }
  
  function checkHydration() {
    if (shouldHydrate()) hydrate();
  }
  
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
        biometric_score: calculateBiometricScore()
      });
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
  
  function setCookie(name, value, days) {
    var expires = new Date(Date.now() + days * 864e5).toUTCString();
    document.cookie = name + '=' + value + '; expires=' + expires + '; path=/; SameSite=Lax';
  }
  
  function getStoredSSIId() {
    return getCookie('_ssi_id') || localStorage.getItem('_ssi_id');
  }
  
  function generateEventId() {
    return 'evt_' + Date.now().toString(36) + '_' + Math.random().toString(36).substr(2, 9);
  }
  
  async function collectData(eventName, customData) {
    // Obter identity
    var identity = await getVisitorIdentity();
    
    // SSI ID (persistente)
    var ssiId = getStoredSSIId();
    if (!ssiId) {
      ssiId = identity.visitor_id || ('ssi_' + Date.now().toString(36) + '_' + Math.random().toString(36).substr(2, 9));
      setCookie('_ssi_id', ssiId, 365);
      try { localStorage.setItem('_ssi_id', ssiId); } catch(e) {}
    }
    
    return {
      event_name: eventName || 'PageView',
      event_id: generateEventId(),
      timestamp: Date.now(),
      
      // URL data
      url: window.location.href,
      referrer: document.referrer || null,
      
      // Click IDs
      fbclid: getUrlParam('fbclid'),
      gclid: getUrlParam('gclid'),
      ttclid: getUrlParam('ttclid'),
      utm_source: getUrlParam('utm_source'),
      utm_medium: getUrlParam('utm_medium'),
      utm_campaign: getUrlParam('utm_campaign'),
      
      // Cookies
      fbp: getCookie('_fbp'),
      fbc: getCookie('_fbc'),
      
      // Identity (FingerprintJS Pro ou fallback)
      ssi_id: ssiId,
      visitor_id: identity.visitor_id,
      fp_confidence: identity.confidence,
      fp_method: identity.method,
      fp_request_id: identity.request_id,
      
      // Bot detection
      bot_probability: identity.bot_probability || 0,
      bot_safe: identity.bot_safe !== false,
      incognito: identity.incognito || false,
      
      // Device (from FingerprintJS)
      browser_name: identity.browser_name,
      browser_version: identity.browser_version,
      os: identity.os,
      os_version: identity.os_version,
      device_type: identity.device,
      
      // Visitor history
      first_seen_at: identity.first_seen_at,
      last_seen_at: identity.last_seen_at,
      visitor_found: identity.visitor_found,
      
      // Fallback fingerprints
      canvas_hash: identity.canvas_hash,
      webgl_hash: identity.webgl_hash,
      
      // Screen
      screen: { w: window.screen.width, h: window.screen.height },
      viewport: { w: window.innerWidth, h: window.innerHeight },
      
      // Behavioral
      session_start: state.startTime,
      scroll_depth: state.maxScroll,
      interactions: state.interactions,
      is_hydrated: state.hydrated,
      biometric_score: calculateBiometricScore(),
      
      // Biometric raw data (para análise server-side)
      biometrics: CONFIG.biometrics.enabled ? {
        mouse_samples: state.mouseMovements.length,
        key_samples: state.keyStrokes.length,
        scroll_samples: state.scrollPattern.length
      } : null,
      
      // Custom data
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
  
  async function track(eventName, customData) {
    var data = await collectData(eventName, customData);
    sendBeacon(data);
    return data;
  }
  
  // ============================================================================
  // INITIALIZATION
  // ============================================================================
  
  function init(options) {
    if (state.initialized) return;
    
    if (options) {
      if (options.endpoint) CONFIG.endpoint = options.endpoint;
      if (options.debug) CONFIG.debug = options.debug;
      if (options.fingerprintApiKey) {
        CONFIG.fingerprintjs.apiKey = options.fingerprintApiKey;
      }
      if (options.fingerprintEndpoint) {
        CONFIG.fingerprintjs.endpoint = options.fingerprintEndpoint;
      }
    }
    
    state.initialized = true;
    
    // Pré-carregar FingerprintJS
    loadFingerprintJS();
    
    // Event listeners
    window.addEventListener('scroll', trackScroll, { passive: true });
    document.addEventListener('click', trackClick, { passive: true });
    document.addEventListener('mousemove', trackMouseMove, { passive: true });
    document.addEventListener('keydown', trackKeyBiometrics, { passive: true });
    
    // Timer
    setInterval(function() {
      checkHydration();
      checkHighIntent();
    }, 1000);
    
    // Injetar CSS
    injectStyles();
    
    // PageView
    track('PageView');
    
    if (CONFIG.debug) console.log('[SSI] v4 Enterprise initialized');
  }
  
  function injectStyles() {
    var style = document.createElement('style');
    style.textContent = [
      '[data-ssi-reveal]:not(.ssi-hydrated),',
      '.ssi-countdown:not(.ssi-hydrated),',
      '.ssi-urgency:not(.ssi-hydrated),',
      '.ssi-social-proof:not(.ssi-hydrated),',
      '.ssi-discount-banner:not(.ssi-hydrated) {',
      '  display: none !important;',
      '}',
      '.ssi-cta-enhanced { animation: ssi-pulse 2s infinite; }',
      '@keyframes ssi-pulse {',
      '  0%, 100% { transform: scale(1); }',
      '  50% { transform: scale(1.02); }',
      '}',
      '.ssi-original-price { text-decoration: line-through; opacity: 0.6; margin-right: 8px; }',
      '.ssi-discount-price { font-weight: bold; color: #e53e3e; }'
    ].join('\n');
    document.head.appendChild(style);
  }
  
  // ============================================================================
  // E-COMMERCE HELPERS
  // ============================================================================
  
  function trackViewContent(id, name, value, currency) {
    return track('ViewContent', {
      content_ids: [id], content_name: name,
      value: value, currency: currency || 'BRL'
    });
  }
  
  function trackAddToCart(id, name, value, currency, qty) {
    return track('AddToCart', {
      content_ids: [id], content_name: name,
      value: value, currency: currency || 'BRL', quantity: qty || 1
    });
  }
  
  function trackInitiateCheckout(ids, value, currency, numItems) {
    return track('InitiateCheckout', {
      content_ids: ids, value: value,
      currency: currency || 'BRL', num_items: numItems
    });
  }
  
  function trackPurchase(ids, value, currency, orderId, numItems) {
    return track('Purchase', {
      content_ids: ids, value: value, currency: currency || 'BRL',
      order_id: orderId, num_items: numItems
    });
  }
  
  function trackLead(value, currency) {
    return track('Lead', { value: value || 0, currency: currency || 'BRL' });
  }
  
  // ============================================================================
  // EXPORT
  // ============================================================================
  
  window.ssi = {
    init: init,
    track: track,
    
    trackViewContent: trackViewContent,
    trackAddToCart: trackAddToCart,
    trackInitiateCheckout: trackInitiateCheckout,
    trackPurchase: trackPurchase,
    trackLead: trackLead,
    
    getState: function() { return state; },
    getVisitorId: function() { return state.visitorId; },
    isHydrated: function() { return state.hydrated; },
    getBiometricScore: calculateBiometricScore
  };
  
  // Auto-init
  var script = document.currentScript;
  if (script && script.hasAttribute('data-auto')) {
    init({
      endpoint: script.getAttribute('data-endpoint'),
      fingerprintApiKey: script.getAttribute('data-fp-key')
    });
  }
  
})(window, document);
