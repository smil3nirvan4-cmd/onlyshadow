/**
 * S.S.I. SHADOW - Ghost Script v1 (Basic)
 * Lightweight client-side tracking (~1KB minified)
 * 
 * Features:
 * - Click ID capture (fbclid, gclid, ttclid)
 * - Cookie management (_fbc, _fbp, ssi_id)
 * - PageView tracking
 * - Event sending via sendBeacon
 * 
 * @version 1.0.0
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
    debug: window.SSI_DEBUG || false
  };

  // ============================================================================
  // Utility Functions
  // ============================================================================
  
  /**
   * Generate UUID v4
   */
  function uuid() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
      var r = Math.random() * 16 | 0;
      var v = c === 'x' ? r : (r & 0x3 | 0x8);
      return v.toString(16);
    });
  }

  /**
   * Get cookie value by name
   */
  function getCookie(name) {
    var match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
    return match ? decodeURIComponent(match[2]) : null;
  }

  /**
   * Set cookie with options
   */
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

  /**
   * Get URL parameter
   */
  function getParam(name) {
    var url = new URL(window.location.href);
    return url.searchParams.get(name);
  }

  /**
   * Log message (if debug enabled)
   */
  function log(msg, data) {
    if (CONFIG.debug) {
      console.log('[SSI Ghost]', msg, data || '');
    }
  }

  // ============================================================================
  // ID Management
  // ============================================================================

  /**
   * Get or create SSI ID (persistent user identifier)
   */
  function getSSIId() {
    var ssiId = getCookie('_ssi_id');
    if (!ssiId) {
      ssiId = 'ssi_' + uuid().replace(/-/g, '');
      setCookie('_ssi_id', ssiId, 365, CONFIG.cookieDomain);
      log('Created new SSI ID:', ssiId);
    }
    return ssiId;
  }

  /**
   * Get or create session ID (30 min expiry)
   */
  function getSessionId() {
    var sessionId = getCookie('_ssi_session');
    if (!sessionId) {
      sessionId = 'sess_' + uuid().replace(/-/g, '');
    }
    // Always refresh session cookie (sliding expiration)
    setCookie('_ssi_session', sessionId, 1/48, CONFIG.cookieDomain); // 30 minutes
    return sessionId;
  }

  // ============================================================================
  // Click ID Capture
  // ============================================================================

  /**
   * Capture click IDs from URL and store in cookies
   */
  function captureClickIds() {
    var clickIds = {
      fbclid: getParam('fbclid'),
      gclid: getParam('gclid'),
      ttclid: getParam('ttclid')
    };

    // Store fbclid as _fbc cookie (Meta format)
    if (clickIds.fbclid) {
      var fbc = 'fb.1.' + Date.now() + '.' + clickIds.fbclid;
      setCookie('_fbc', fbc, 90, CONFIG.cookieDomain);
      log('Captured fbclid:', clickIds.fbclid);
    }

    // Store gclid
    if (clickIds.gclid) {
      setCookie('_gcl_aw', 'GCL.' + Date.now() + '.' + clickIds.gclid, 90, CONFIG.cookieDomain);
      log('Captured gclid:', clickIds.gclid);
    }

    // Store ttclid
    if (clickIds.ttclid) {
      setCookie('_ttp', clickIds.ttclid, 90, CONFIG.cookieDomain);
      log('Captured ttclid:', clickIds.ttclid);
    }

    return clickIds;
  }

  /**
   * Get Meta cookies (_fbc, _fbp)
   */
  function getMetaCookies() {
    var fbc = getCookie('_fbc');
    var fbp = getCookie('_fbp');

    // Generate _fbp if not exists
    if (!fbp) {
      fbp = 'fb.1.' + Date.now() + '.' + Math.floor(Math.random() * 10000000000);
      setCookie('_fbp', fbp, 365, CONFIG.cookieDomain);
      log('Generated _fbp:', fbp);
    }

    return { fbc: fbc, fbp: fbp };
  }

  // ============================================================================
  // Event Sending
  // ============================================================================

  /**
   * Build base payload
   */
  function buildPayload(eventName, eventData) {
    var clickIds = captureClickIds();
    var metaCookies = getMetaCookies();

    var payload = {
      // Identifiers
      ssi_id: getSSIId(),
      session_id: getSessionId(),
      
      // Event
      event_name: eventName,
      event_id: uuid(),
      timestamp: Date.now(),
      
      // Click IDs
      fbclid: clickIds.fbclid || getParam('fbclid'),
      gclid: clickIds.gclid || getParam('gclid'),
      ttclid: clickIds.ttclid || getParam('ttclid'),
      
      // Meta Cookies
      fbc: metaCookies.fbc,
      fbp: metaCookies.fbp,
      
      // Page Info
      url: window.location.href,
      referrer: document.referrer || null,
      title: document.title,
      
      // Basic Device Info
      user_agent: navigator.userAgent,
      language: navigator.language,
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      screen_width: screen.width,
      screen_height: screen.height,
      viewport_width: window.innerWidth,
      viewport_height: window.innerHeight
    };

    // Merge custom event data
    if (eventData) {
      for (var key in eventData) {
        if (eventData.hasOwnProperty(key)) {
          payload[key] = eventData[key];
        }
      }
    }

    return payload;
  }

  /**
   * Send event to server
   */
  function sendEvent(eventName, eventData) {
    try {
      var payload = buildPayload(eventName, eventData);
      var json = JSON.stringify(payload);

      log('Sending event:', payload);

      // Use sendBeacon for reliability (fires even on page unload)
      if (navigator.sendBeacon) {
        var blob = new Blob([json], { type: 'application/json' });
        navigator.sendBeacon(CONFIG.endpoint, blob);
      } else {
        // Fallback to fetch
        fetch(CONFIG.endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: json,
          keepalive: true
        });
      }

      return payload.event_id;
    } catch (e) {
      log('Error sending event:', e);
      return null;
    }
  }

  // ============================================================================
  // Public API
  // ============================================================================

  window.SSI = {
    /**
     * Track PageView event
     */
    pageview: function() {
      return sendEvent('PageView');
    },

    /**
     * Track custom event
     * @param {string} eventName - Event name (e.g., 'Purchase', 'Lead')
     * @param {object} eventData - Custom event data
     */
    track: function(eventName, eventData) {
      return sendEvent(eventName, eventData);
    },

    /**
     * Track Purchase event
     */
    purchase: function(value, currency, orderId, contentIds) {
      return sendEvent('Purchase', {
        value: value,
        currency: currency || 'BRL',
        order_id: orderId,
        content_ids: contentIds
      });
    },

    /**
     * Track Lead event
     */
    lead: function(email, phone, value) {
      return sendEvent('Lead', {
        email: email,
        phone: phone,
        value: value
      });
    },

    /**
     * Track AddToCart event
     */
    addToCart: function(contentIds, value, currency) {
      return sendEvent('AddToCart', {
        content_ids: contentIds,
        value: value,
        currency: currency || 'BRL'
      });
    },

    /**
     * Track ViewContent event
     */
    viewContent: function(contentIds, contentName, value) {
      return sendEvent('ViewContent', {
        content_ids: contentIds,
        content_name: contentName,
        value: value
      });
    },

    /**
     * Get current SSI ID
     */
    getSSIId: getSSIId,

    /**
     * Get current Session ID
     */
    getSessionId: getSessionId,

    /**
     * Set configuration
     */
    config: function(options) {
      if (options.endpoint) CONFIG.endpoint = options.endpoint;
      if (options.cookieDomain) CONFIG.cookieDomain = options.cookieDomain;
      if (options.debug !== undefined) CONFIG.debug = options.debug;
    },

    /**
     * Version
     */
    version: '1.0.0'
  };

  // ============================================================================
  // Auto-initialization
  // ============================================================================

  // Capture click IDs on page load
  captureClickIds();
  getMetaCookies();

  // Auto-track PageView (can be disabled with SSI_NO_AUTO_PAGEVIEW)
  if (!window.SSI_NO_AUTO_PAGEVIEW) {
    if (document.readyState === 'complete') {
      SSI.pageview();
    } else {
      window.addEventListener('load', function() {
        SSI.pageview();
      });
    }
  }

  log('Ghost Script v1 initialized');

})(window, document);
