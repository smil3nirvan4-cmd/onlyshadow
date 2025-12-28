/**
 * S.S.I. SHADOW - Ghost Script v3 (Full)
 * Complete client-side tracking with lazy hydration (~3KB minified)
 * 
 * Features (v2 +):
 * - Lazy Hydration (loads full tracking after user interaction)
 * - Behavioral tracking (scroll, time on page, clicks)
 * - SPA support (MutationObserver + History API)
 * - Session tracking with persistence
 * - Engagement scoring
 * 
 * @version 3.0.0
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
    enableFingerprint: window.SSI_ENABLE_FINGERPRINT !== false,
    lazyHydration: window.SSI_LAZY_HYDRATION !== false,
    trackBehavior: window.SSI_TRACK_BEHAVIOR !== false,
    hydrationDelay: 5000, // 5 seconds before full hydration
    scrollThreshold: 10,  // 10% scroll to trigger hydration
    spaMode: window.SSI_SPA_MODE || false
  };

  // ============================================================================
  // State
  // ============================================================================
  var STATE = {
    hydrated: false,
    pageLoadTime: Date.now(),
    scrollDepth: 0,
    maxScrollDepth: 0,
    clickCount: 0,
    lastActivity: Date.now(),
    currentUrl: window.location.href,
    pageviews: 0
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
      return new URL(window.location.href).searchParams.get(name);
    } catch (e) {
      return null;
    }
  }

  function log(msg, data) {
    if (CONFIG.debug) {
      console.log('[SSI Ghost v3]', msg, data || '');
    }
  }

  function hash(str) {
    var h = 5381;
    for (var i = 0; i < str.length; i++) {
      h = ((h << 5) + h) + str.charCodeAt(i);
    }
    return (h >>> 0).toString(16);
  }

  function throttle(fn, wait) {
    var time = Date.now();
    return function() {
      if ((time + wait - Date.now()) < 0) {
        fn.apply(this, arguments);
        time = Date.now();
      }
    };
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
    var sessionStart = getCookie('_ssi_session_start');
    
    if (!sessionId || !sessionStart) {
      sessionId = 'sess_' + uuid().replace(/-/g, '');
      sessionStart = Date.now().toString();
      setCookie('_ssi_session_start', sessionStart, 1/48, CONFIG.cookieDomain);
    }
    
    setCookie('_ssi_session', sessionId, 1/48, CONFIG.cookieDomain);
    return sessionId;
  }

  function getSessionDuration() {
    var sessionStart = getCookie('_ssi_session_start');
    if (sessionStart) {
      return Date.now() - parseInt(sessionStart, 10);
    }
    return 0;
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
      setCookie('_fbc', 'fb.1.' + Date.now() + '.' + clickIds.fbclid, 90, CONFIG.cookieDomain);
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
      ctx.fillText('SSI.Shadow.v3', 2, 15);
      ctx.fillStyle = 'rgba(102, 204, 0, 0.7)';
      ctx.fillText('FP Test', 4, 35);
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

  var cachedFingerprint = null;

  function collectFingerprint() {
    if (!CONFIG.enableFingerprint) return {};
    if (cachedFingerprint) return cachedFingerprint;
    
    var webgl = getWebGLInfo();
    cachedFingerprint = {
      canvas_hash: getCanvasFingerprint(),
      webgl_vendor: webgl.vendor,
      webgl_renderer: webgl.renderer,
      plugins_hash: getPluginsHash(),
      touch_support: 'ontouchstart' in window || navigator.maxTouchPoints > 0,
      device_pixel_ratio: window.devicePixelRatio || 1,
      color_depth: screen.colorDepth || 24,
      hardware_concurrency: navigator.hardwareConcurrency || null,
      device_memory: navigator.deviceMemory || null
    };
    return cachedFingerprint;
  }

  // ============================================================================
  // Behavioral Tracking
  // ============================================================================

  function calculateScrollDepth() {
    var windowHeight = window.innerHeight;
    var documentHeight = Math.max(
      document.body.scrollHeight,
      document.body.offsetHeight,
      document.documentElement.scrollHeight,
      document.documentElement.offsetHeight
    );
    var scrollTop = window.pageYOffset || document.documentElement.scrollTop;
    
    if (documentHeight <= windowHeight) return 100;
    
    var scrolled = (scrollTop + windowHeight) / documentHeight;
    return Math.min(Math.round(scrolled * 100), 100);
  }

  function getTimeOnPage() {
    return Date.now() - STATE.pageLoadTime;
  }

  function getBehavioralData() {
    if (!CONFIG.trackBehavior) return {};
    
    return {
      scroll_depth: STATE.maxScrollDepth,
      time_on_page: getTimeOnPage(),
      clicks: STATE.clickCount,
      session_duration: getSessionDuration(),
      session_pageviews: STATE.pageviews
    };
  }

  // ============================================================================
  // Event Sending
  // ============================================================================

  function buildPayload(eventName, eventData, includeAll) {
    var clickIds = captureClickIds();
    var metaCookies = getMetaCookies();
    
    var payload = {
      // Core identifiers
      ssi_id: getSSIId(),
      session_id: getSessionId(),
      
      // Event info
      event_name: eventName,
      event_id: uuid(),
      timestamp: Date.now(),
      
      // Click IDs
      fbclid: clickIds.fbclid || getParam('fbclid'),
      gclid: clickIds.gclid || getParam('gclid'),
      ttclid: clickIds.ttclid || getParam('ttclid'),
      
      // Meta cookies
      fbc: metaCookies.fbc,
      fbp: metaCookies.fbp,
      
      // Page info
      url: window.location.href,
      referrer: document.referrer || null,
      title: document.title,
      
      // Basic device info
      user_agent: navigator.userAgent,
      language: navigator.language,
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      screen_width: screen.width,
      screen_height: screen.height,
      viewport_width: window.innerWidth,
      viewport_height: window.innerHeight
    };

    // Include full data only if hydrated or explicitly requested
    if (includeAll || STATE.hydrated) {
      var fingerprint = collectFingerprint();
      var behavioral = getBehavioralData();
      
      // Add fingerprint
      payload.canvas_hash = fingerprint.canvas_hash;
      payload.webgl_vendor = fingerprint.webgl_vendor;
      payload.webgl_renderer = fingerprint.webgl_renderer;
      payload.plugins_hash = fingerprint.plugins_hash;
      payload.touch_support = fingerprint.touch_support;
      
      // Add behavioral
      payload.scroll_depth = behavioral.scroll_depth;
      payload.time_on_page = behavioral.time_on_page;
      payload.clicks = behavioral.clicks;
      payload.session_duration = behavioral.session_duration;
      payload.session_pageviews = behavioral.session_pageviews;
    }

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

  function sendEvent(eventName, eventData, includeAll) {
    try {
      var payload = buildPayload(eventName, eventData, includeAll);
      var json = JSON.stringify(payload);
      
      log('Sending:', eventName, payload);

      if (navigator.sendBeacon) {
        navigator.sendBeacon(CONFIG.endpoint, new Blob([json], { type: 'application/json' }));
      } else {
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
  // Lazy Hydration
  // ============================================================================

  function hydrate() {
    if (STATE.hydrated) return;
    STATE.hydrated = true;
    
    log('Hydrating full tracking...');
    
    // Compute fingerprint
    collectFingerprint();
    
    // Start behavioral tracking
    if (CONFIG.trackBehavior) {
      startBehavioralTracking();
    }
    
    log('Hydration complete');
  }

  function checkHydrationTriggers() {
    // Already hydrated
    if (STATE.hydrated) return;
    
    // Check scroll threshold
    if (STATE.scrollDepth >= CONFIG.scrollThreshold) {
      log('Hydration trigger: scroll');
      hydrate();
      return;
    }
    
    // Check click
    if (STATE.clickCount > 0) {
      log('Hydration trigger: click');
      hydrate();
      return;
    }
  }

  function setupLazyHydration() {
    if (!CONFIG.lazyHydration) {
      hydrate();
      return;
    }

    // Timer-based hydration
    setTimeout(function() {
      if (!STATE.hydrated) {
        log('Hydration trigger: timeout');
        hydrate();
      }
    }, CONFIG.hydrationDelay);

    // Scroll-based hydration
    var handleScroll = throttle(function() {
      STATE.scrollDepth = calculateScrollDepth();
      if (STATE.scrollDepth > STATE.maxScrollDepth) {
        STATE.maxScrollDepth = STATE.scrollDepth;
      }
      checkHydrationTriggers();
    }, 100);

    window.addEventListener('scroll', handleScroll, { passive: true });

    // Click-based hydration
    document.addEventListener('click', function() {
      STATE.clickCount++;
      STATE.lastActivity = Date.now();
      checkHydrationTriggers();
    }, { passive: true });

    // Touch-based hydration (mobile)
    document.addEventListener('touchstart', function() {
      checkHydrationTriggers();
    }, { passive: true, once: true });
  }

  // ============================================================================
  // Behavioral Tracking (after hydration)
  // ============================================================================

  function startBehavioralTracking() {
    // Track scroll depth
    var trackScroll = throttle(function() {
      STATE.scrollDepth = calculateScrollDepth();
      if (STATE.scrollDepth > STATE.maxScrollDepth) {
        STATE.maxScrollDepth = STATE.scrollDepth;
      }
    }, 250);

    window.addEventListener('scroll', trackScroll, { passive: true });

    // Track visibility changes
    document.addEventListener('visibilitychange', function() {
      if (document.visibilityState === 'hidden') {
        // Send engagement data when user leaves
        sendEngagementPing();
      }
    });

    // Send engagement on page unload
    window.addEventListener('beforeunload', function() {
      sendEngagementPing();
    });
  }

  function sendEngagementPing() {
    if (getTimeOnPage() < 1000) return; // Skip very short visits
    
    sendEvent('Engagement', {
      scroll_depth: STATE.maxScrollDepth,
      time_on_page: getTimeOnPage(),
      clicks: STATE.clickCount
    }, true);
  }

  // ============================================================================
  // SPA Support
  // ============================================================================

  function setupSPATracking() {
    if (!CONFIG.spaMode) return;

    // Track History API navigation
    var originalPushState = history.pushState;
    var originalReplaceState = history.replaceState;

    history.pushState = function() {
      originalPushState.apply(this, arguments);
      handleNavigation();
    };

    history.replaceState = function() {
      originalReplaceState.apply(this, arguments);
      handleNavigation();
    };

    window.addEventListener('popstate', handleNavigation);

    // MutationObserver for detecting route changes
    var observer = new MutationObserver(throttle(function() {
      if (window.location.href !== STATE.currentUrl) {
        handleNavigation();
      }
    }, 500));

    observer.observe(document.body, {
      childList: true,
      subtree: true
    });
  }

  function handleNavigation() {
    if (window.location.href === STATE.currentUrl) return;
    
    log('SPA Navigation detected:', window.location.href);
    
    // Send engagement for previous page
    sendEngagementPing();
    
    // Reset state for new page
    STATE.currentUrl = window.location.href;
    STATE.pageLoadTime = Date.now();
    STATE.scrollDepth = 0;
    STATE.maxScrollDepth = 0;
    STATE.clickCount = 0;
    STATE.pageviews++;
    
    // Track new pageview
    sendEvent('PageView');
  }

  // ============================================================================
  // Public API
  // ============================================================================

  window.SSI = {
    // Core tracking methods
    pageview: function() {
      STATE.pageviews++;
      return sendEvent('PageView');
    },

    track: function(eventName, eventData) {
      return sendEvent(eventName, eventData, true);
    },

    // E-commerce events
    purchase: function(value, currency, orderId, contentIds, extra) {
      var data = {
        value: value,
        currency: currency || 'BRL',
        order_id: orderId,
        content_ids: contentIds
      };
      if (extra) {
        for (var k in extra) {
          if (extra.hasOwnProperty(k)) data[k] = extra[k];
        }
      }
      return sendEvent('Purchase', data, true);
    },

    lead: function(email, phone, value, extra) {
      var data = { email: email, phone: phone, value: value };
      if (extra) {
        for (var k in extra) {
          if (extra.hasOwnProperty(k)) data[k] = extra[k];
        }
      }
      return sendEvent('Lead', data, true);
    },

    addToCart: function(contentIds, value, currency, contentName) {
      return sendEvent('AddToCart', {
        content_ids: contentIds,
        value: value,
        currency: currency || 'BRL',
        content_name: contentName
      }, true);
    },

    viewContent: function(contentIds, contentName, value, contentCategory) {
      return sendEvent('ViewContent', {
        content_ids: contentIds,
        content_name: contentName,
        value: value,
        content_category: contentCategory
      }, true);
    },

    initiateCheckout: function(contentIds, value, currency, numItems) {
      return sendEvent('InitiateCheckout', {
        content_ids: contentIds,
        value: value,
        currency: currency || 'BRL',
        num_items: numItems
      }, true);
    },

    completeRegistration: function(email, phone, method) {
      return sendEvent('CompleteRegistration', {
        email: email,
        phone: phone,
        registration_method: method
      }, true);
    },

    search: function(searchString, contentIds) {
      return sendEvent('Search', {
        search_string: searchString,
        content_ids: contentIds
      }, true);
    },

    // User identification
    identify: function(email, phone, externalId, extra) {
      var data = {
        email: email,
        phone: phone,
        external_id: externalId
      };
      if (extra) {
        for (var k in extra) {
          if (extra.hasOwnProperty(k)) data[k] = extra[k];
        }
      }
      return sendEvent('Identify', data, true);
    },

    // Getters
    getSSIId: getSSIId,
    getSessionId: getSessionId,
    
    getFingerprint: function() {
      return collectFingerprint();
    },

    getBehavior: function() {
      return {
        scroll_depth: STATE.maxScrollDepth,
        time_on_page: getTimeOnPage(),
        clicks: STATE.clickCount,
        hydrated: STATE.hydrated
      };
    },

    isHydrated: function() {
      return STATE.hydrated;
    },

    // Manual hydration
    hydrate: hydrate,

    // Configuration
    config: function(options) {
      for (var key in options) {
        if (options.hasOwnProperty(key) && CONFIG.hasOwnProperty(key)) {
          CONFIG[key] = options[key];
        }
      }
    },

    // SPA navigation helper
    trackNavigation: handleNavigation,

    // Debug
    debug: function(enable) {
      CONFIG.debug = enable !== false;
      return CONFIG.debug;
    },

    // Version
    version: '3.0.0'
  };

  // ============================================================================
  // Auto-initialization
  // ============================================================================

  // Capture click IDs immediately
  captureClickIds();
  getMetaCookies();

  // Setup lazy hydration
  setupLazyHydration();

  // Setup SPA tracking
  setupSPATracking();

  // Auto pageview
  if (!window.SSI_NO_AUTO_PAGEVIEW) {
    if (document.readyState === 'complete') {
      STATE.pageviews++;
      sendEvent('PageView');
    } else {
      window.addEventListener('load', function() {
        STATE.pageviews++;
        sendEvent('PageView');
      });
    }
  }

  log('Ghost Script v3 initialized');

})(window, document);
