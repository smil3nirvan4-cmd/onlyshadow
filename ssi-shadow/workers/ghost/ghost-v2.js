/**
 * S.S.I. SHADOW - Ghost Script v2 (Fingerprint)
 * Client-side tracking with device fingerprinting (~2KB minified)
 * 
 * Features (v1 +):
 * - Canvas fingerprint (hashed)
 * - WebGL vendor/renderer
 * - Screen/viewport dimensions
 * - Timezone, language
 * - Plugin detection
 * - Touch support detection
 * 
 * @version 2.0.0
 * @license MIT
 */
(function(window, document) {
  'use strict';

  // ============================================================================
  // Configuration
  // ============================================================================
  var CONFIG = {
    endpoint: window.SSI_ENDPOINT || 'https://ssi-shadow.workers.dev/api/collect',
    cookieDomain: window.SSI_COOKIE_DOMAIN || '',
    debug: window.SSI_DEBUG || false,
    enableFingerprint: window.SSI_ENABLE_FINGERPRINT !== false
  };

  // ============================================================================
  // Utility Functions
  // ============================================================================
  
  function uuid() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
      var r = Math.random() * 16 | 0;
      var v = c === 'x' ? r : (r & 0x3 | 0x8);
      return v.toString(16);
    });
  }

  function getCookie(name) {
    var match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
    return match ? decodeURIComponent(match[2]) : null;
  }

  function setCookie(name, value, days, domain) {
    var expires = '';
    if (days) {
      var date = new Date();
      date.setTime(date.getTime() + (days * 24 * 60 * 60 * 1000));
      expires = '; expires=' + date.toUTCString();
    }
    var domainStr = domain ? '; domain=' + domain : '';
    document.cookie = name + '=' + encodeURIComponent(value) + expires + domainStr + '; path=/; SameSite=Lax';
  }

  function getParam(name) {
    try {
      var url = new URL(window.location.href);
      return url.searchParams.get(name);
    } catch (e) {
      return null;
    }
  }

  function log(msg, data) {
    if (CONFIG.debug) {
      console.log('[SSI Ghost v2]', msg, data || '');
    }
  }

  function hash(str) {
    var hash = 5381;
    for (var i = 0; i < str.length; i++) {
      hash = ((hash << 5) + hash) + str.charCodeAt(i);
    }
    return (hash >>> 0).toString(16);
  }

  // ============================================================================
  // ID Management
  // ============================================================================

  function getSSIId() {
    var ssiId = getCookie('_ssi_id');
    if (!ssiId) {
      ssiId = 'ssi_' + uuid().replace(/-/g, '');
      setCookie('_ssi_id', ssiId, 365, CONFIG.cookieDomain);
    }
    return ssiId;
  }

  function getSessionId() {
    var sessionId = getCookie('_ssi_session');
    if (!sessionId) {
      sessionId = 'sess_' + uuid().replace(/-/g, '');
    }
    setCookie('_ssi_session', sessionId, 1/48, CONFIG.cookieDomain);
    return sessionId;
  }

  // ============================================================================
  // Click ID Capture
  // ============================================================================

  function captureClickIds() {
    var clickIds = {
      fbclid: getParam('fbclid'),
      gclid: getParam('gclid'),
      ttclid: getParam('ttclid')
    };

    if (clickIds.fbclid) {
      var fbc = 'fb.1.' + Date.now() + '.' + clickIds.fbclid;
      setCookie('_fbc', fbc, 90, CONFIG.cookieDomain);
    }
    if (clickIds.gclid) {
      setCookie('_gcl_aw', 'GCL.' + Date.now() + '.' + clickIds.gclid, 90, CONFIG.cookieDomain);
    }
    if (clickIds.ttclid) {
      setCookie('_ttp', clickIds.ttclid, 90, CONFIG.cookieDomain);
    }

    return clickIds;
  }

  function getMetaCookies() {
    var fbc = getCookie('_fbc');
    var fbp = getCookie('_fbp');

    if (!fbp) {
      fbp = 'fb.1.' + Date.now() + '.' + Math.floor(Math.random() * 10000000000);
      setCookie('_fbp', fbp, 365, CONFIG.cookieDomain);
    }

    return { fbc: fbc, fbp: fbp };
  }

  // ============================================================================
  // Fingerprinting
  // ============================================================================

  function getCanvasFingerprint() {
    try {
      var canvas = document.createElement('canvas');
      var ctx = canvas.getContext('2d');
      canvas.width = 200;
      canvas.height = 50;
      ctx.textBaseline = 'top';
      ctx.font = '14px Arial';
      ctx.fillStyle = '#f60';
      ctx.fillRect(0, 0, 100, 50);
      ctx.fillStyle = '#069';
      ctx.fillText('SSI.Shadow.v2', 2, 15);
      ctx.fillStyle = 'rgba(102, 204, 0, 0.7)';
      ctx.fillText('Canvas FP', 4, 35);
      return hash(canvas.toDataURL());
    } catch (e) {
      return null;
    }
  }

  function getWebGLInfo() {
    try {
      var canvas = document.createElement('canvas');
      var gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
      if (!gl) return { vendor: null, renderer: null };
      var debugInfo = gl.getExtension('WEBGL_debug_renderer_info');
      if (debugInfo) {
        return {
          vendor: gl.getParameter(debugInfo.UNMASKED_VENDOR_WEBGL),
          renderer: gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL)
        };
      }
      return { vendor: gl.getParameter(gl.VENDOR), renderer: gl.getParameter(gl.RENDERER) };
    } catch (e) {
      return { vendor: null, renderer: null };
    }
  }

  function getPluginsHash() {
    try {
      var plugins = [];
      for (var i = 0; i < navigator.plugins.length; i++) {
        plugins.push(navigator.plugins[i].name);
      }
      return plugins.length > 0 ? hash(plugins.sort().join(',')) : null;
    } catch (e) {
      return null;
    }
  }

  function hasTouchSupport() {
    return 'ontouchstart' in window || navigator.maxTouchPoints > 0;
  }

  function collectFingerprint() {
    if (!CONFIG.enableFingerprint) return {};
    var webgl = getWebGLInfo();
    return {
      canvas_hash: getCanvasFingerprint(),
      webgl_vendor: webgl.vendor,
      webgl_renderer: webgl.renderer,
      plugins_hash: getPluginsHash(),
      touch_support: hasTouchSupport(),
      device_pixel_ratio: window.devicePixelRatio || 1,
      color_depth: screen.colorDepth || 24,
      hardware_concurrency: navigator.hardwareConcurrency || null,
      device_memory: navigator.deviceMemory || null,
      do_not_track: navigator.doNotTrack === '1'
    };
  }

  // ============================================================================
  // Event Sending
  // ============================================================================

  var cachedFingerprint = null;

  function buildPayload(eventName, eventData) {
    var clickIds = captureClickIds();
    var metaCookies = getMetaCookies();
    if (cachedFingerprint === null) cachedFingerprint = collectFingerprint();

    var payload = {
      ssi_id: getSSIId(),
      session_id: getSessionId(),
      event_name: eventName,
      event_id: uuid(),
      timestamp: Date.now(),
      fbclid: clickIds.fbclid || getParam('fbclid'),
      gclid: clickIds.gclid || getParam('gclid'),
      ttclid: clickIds.ttclid || getParam('ttclid'),
      fbc: metaCookies.fbc,
      fbp: metaCookies.fbp,
      url: window.location.href,
      referrer: document.referrer || null,
      title: document.title,
      user_agent: navigator.userAgent,
      language: navigator.language,
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      screen_width: screen.width,
      screen_height: screen.height,
      viewport_width: window.innerWidth,
      viewport_height: window.innerHeight,
      canvas_hash: cachedFingerprint.canvas_hash,
      webgl_vendor: cachedFingerprint.webgl_vendor,
      webgl_renderer: cachedFingerprint.webgl_renderer,
      plugins_hash: cachedFingerprint.plugins_hash,
      touch_support: cachedFingerprint.touch_support
    };

    if (eventData) {
      for (var key in eventData) {
        if (eventData.hasOwnProperty(key)) payload[key] = eventData[key];
      }
    }
    return payload;
  }

  function sendEvent(eventName, eventData) {
    try {
      var payload = buildPayload(eventName, eventData);
      var json = JSON.stringify(payload);
      log('Sending:', payload);
      if (navigator.sendBeacon) {
        navigator.sendBeacon(CONFIG.endpoint, new Blob([json], { type: 'application/json' }));
      } else {
        fetch(CONFIG.endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: json, keepalive: true });
      }
      return payload.event_id;
    } catch (e) {
      log('Error:', e);
      return null;
    }
  }

  // ============================================================================
  // Public API
  // ============================================================================

  window.SSI = {
    pageview: function() { return sendEvent('PageView'); },
    track: function(eventName, eventData) { return sendEvent(eventName, eventData); },
    purchase: function(value, currency, orderId, contentIds) {
      return sendEvent('Purchase', { value: value, currency: currency || 'BRL', order_id: orderId, content_ids: contentIds });
    },
    lead: function(email, phone, value) {
      return sendEvent('Lead', { email: email, phone: phone, value: value });
    },
    addToCart: function(contentIds, value, currency) {
      return sendEvent('AddToCart', { content_ids: contentIds, value: value, currency: currency || 'BRL' });
    },
    viewContent: function(contentIds, contentName, value) {
      return sendEvent('ViewContent', { content_ids: contentIds, content_name: contentName, value: value });
    },
    initiateCheckout: function(contentIds, value, currency, numItems) {
      return sendEvent('InitiateCheckout', { content_ids: contentIds, value: value, currency: currency || 'BRL', num_items: numItems });
    },
    completeRegistration: function(email, phone) {
      return sendEvent('CompleteRegistration', { email: email, phone: phone });
    },
    getSSIId: getSSIId,
    getSessionId: getSessionId,
    getFingerprint: function() {
      if (cachedFingerprint === null) cachedFingerprint = collectFingerprint();
      return cachedFingerprint;
    },
    config: function(options) {
      if (options.endpoint) CONFIG.endpoint = options.endpoint;
      if (options.cookieDomain) CONFIG.cookieDomain = options.cookieDomain;
      if (options.debug !== undefined) CONFIG.debug = options.debug;
      if (options.enableFingerprint !== undefined) CONFIG.enableFingerprint = options.enableFingerprint;
    },
    version: '2.0.0'
  };

  // ============================================================================
  // Auto-initialization
  // ============================================================================

  captureClickIds();
  getMetaCookies();
  cachedFingerprint = collectFingerprint();

  if (!window.SSI_NO_AUTO_PAGEVIEW) {
    if (document.readyState === 'complete') {
      SSI.pageview();
    } else {
      window.addEventListener('load', function() { SSI.pageview(); });
    }
  }

  log('Ghost Script v2 initialized');

})(window, document);
