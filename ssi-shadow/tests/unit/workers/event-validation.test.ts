/**
 * S.S.I. SHADOW - Event Validation Tests
 * Tests for incoming event validation and sanitization
 */

import { describe, it, expect } from 'vitest';
import {
  mockPageViewBasic,
  mockPageViewFull,
  mockPurchaseBasic,
  mockPurchaseFull,
  mockLeadBasic,
  mockAddToCart,
  mockInitiateCheckout,
  mockViewContent,
  createMockEvent,
} from '@fixtures';

// =============================================================================
// TYPES
// =============================================================================

type EventName = 
  | 'PageView' | 'ViewContent' | 'Search' | 'AddToCart' | 'AddToWishlist'
  | 'InitiateCheckout' | 'AddPaymentInfo' | 'Purchase' | 'Lead'
  | 'CompleteRegistration' | 'Contact' | 'CustomizeProduct' | 'Donate'
  | 'FindLocation' | 'Schedule' | 'StartTrial' | 'SubmitApplication' | 'Subscribe';

interface ValidationResult {
  valid: boolean;
  errors: string[];
  sanitizedEvent?: Record<string, unknown>;
}

// =============================================================================
// VALIDATION IMPLEMENTATION
// =============================================================================

const VALID_EVENT_NAMES: EventName[] = [
  'PageView', 'ViewContent', 'Search', 'AddToCart', 'AddToWishlist',
  'InitiateCheckout', 'AddPaymentInfo', 'Purchase', 'Lead',
  'CompleteRegistration', 'Contact', 'CustomizeProduct', 'Donate',
  'FindLocation', 'Schedule', 'StartTrial', 'SubmitApplication', 'Subscribe',
];

function validateEvent(body: unknown): ValidationResult {
  const errors: string[] = [];

  // Check if body is an object
  if (!body || typeof body !== 'object') {
    return {
      valid: false,
      errors: ['Request body must be a JSON object'],
    };
  }

  const event = body as Record<string, unknown>;

  // Required: event_name
  if (!event.event_name || typeof event.event_name !== 'string') {
    errors.push('event_name is required and must be a string');
  } else if (!VALID_EVENT_NAMES.includes(event.event_name as EventName)) {
    errors.push(`Invalid event_name: ${event.event_name}`);
  }

  // Validate value is a number if present
  if (event.value !== undefined && typeof event.value !== 'number') {
    errors.push('value must be a number');
  }

  // Validate value is positive
  if (typeof event.value === 'number' && event.value < 0) {
    errors.push('value must be a positive number');
  }

  // Validate currency is a string if present
  if (event.currency !== undefined && typeof event.currency !== 'string') {
    errors.push('currency must be a string');
  }

  // Validate currency format (3 letters)
  if (typeof event.currency === 'string' && !/^[A-Z]{3}$/.test(event.currency)) {
    errors.push('currency must be a valid 3-letter ISO code');
  }

  // Validate content_ids is an array if present
  if (event.content_ids !== undefined && !Array.isArray(event.content_ids)) {
    errors.push('content_ids must be an array');
  }

  // Validate URL format if present
  if (event.url && typeof event.url === 'string') {
    try {
      new URL(event.url);
    } catch {
      errors.push('url must be a valid URL');
    }
  }

  // Validate email format if present
  if (event.email && typeof event.email === 'string') {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(event.email)) {
      errors.push('email must be a valid email address');
    }
  }

  // Validate phone format if present (basic check)
  if (event.phone && typeof event.phone === 'string') {
    const digitsOnly = event.phone.replace(/\D/g, '');
    if (digitsOnly.length < 10 || digitsOnly.length > 15) {
      errors.push('phone must be a valid phone number (10-15 digits)');
    }
  }

  // Validate timestamp if present
  if (event.timestamp !== undefined) {
    if (typeof event.timestamp !== 'number') {
      errors.push('timestamp must be a number');
    } else {
      const now = Date.now();
      const sevenDaysAgo = now - 7 * 24 * 60 * 60 * 1000;
      const oneMinuteInFuture = now + 60000;
      if (event.timestamp < sevenDaysAgo || event.timestamp > oneMinuteInFuture) {
        errors.push('timestamp must be within the last 7 days and not in the future');
      }
    }
  }

  // Validate scroll_depth
  if (event.scroll_depth !== undefined) {
    if (typeof event.scroll_depth !== 'number') {
      errors.push('scroll_depth must be a number');
    } else if (event.scroll_depth < 0 || event.scroll_depth > 100) {
      errors.push('scroll_depth must be between 0 and 100');
    }
  }

  // Validate num_items
  if (event.num_items !== undefined) {
    if (typeof event.num_items !== 'number' || !Number.isInteger(event.num_items)) {
      errors.push('num_items must be an integer');
    } else if (event.num_items < 0) {
      errors.push('num_items must be a positive integer');
    }
  }

  if (errors.length > 0) {
    return { valid: false, errors };
  }

  // Return sanitized event
  return {
    valid: true,
    errors: [],
    sanitizedEvent: {
      event_name: event.event_name,
      event_id: event.event_id || undefined,
      ssi_id: event.ssi_id || undefined,
      timestamp: event.timestamp || Date.now(),
      url: event.url || undefined,
      referrer: event.referrer || undefined,
      email: event.email || undefined,
      phone: event.phone || undefined,
      first_name: event.first_name || undefined,
      last_name: event.last_name || undefined,
      value: event.value || undefined,
      currency: event.currency || undefined,
      content_ids: event.content_ids || undefined,
      content_type: event.content_type || undefined,
      content_name: event.content_name || undefined,
      order_id: event.order_id || undefined,
      num_items: event.num_items || undefined,
      fbclid: event.fbclid || undefined,
      gclid: event.gclid || undefined,
      ttclid: event.ttclid || undefined,
      fbc: event.fbc || undefined,
      fbp: event.fbp || undefined,
      scroll_depth: event.scroll_depth || undefined,
      time_on_page: event.time_on_page || undefined,
      clicks: event.clicks || undefined,
    },
  };
}

// =============================================================================
// TESTS
// =============================================================================

describe('Event Validation', () => {
  describe('Required Fields', () => {
    it('should reject null body', () => {
      const result = validateEvent(null);
      expect(result.valid).toBe(false);
      expect(result.errors).toContain('Request body must be a JSON object');
    });

    it('should reject undefined body', () => {
      const result = validateEvent(undefined);
      expect(result.valid).toBe(false);
      expect(result.errors).toContain('Request body must be a JSON object');
    });

    it('should reject non-object body', () => {
      const result = validateEvent('string');
      expect(result.valid).toBe(false);
      expect(result.errors).toContain('Request body must be a JSON object');
    });

    it('should reject array body', () => {
      const result = validateEvent([]);
      expect(result.valid).toBe(false);
      // Arrays are objects in JS, but we want to check for actual objects
    });

    it('should reject empty object (missing event_name)', () => {
      const result = validateEvent({});
      expect(result.valid).toBe(false);
      expect(result.errors).toContain('event_name is required and must be a string');
    });

    it('should reject event without event_name', () => {
      const result = validateEvent({ url: 'https://example.com' });
      expect(result.valid).toBe(false);
      expect(result.errors).toContain('event_name is required and must be a string');
    });

    it('should reject non-string event_name', () => {
      const result = validateEvent({ event_name: 123 });
      expect(result.valid).toBe(false);
      expect(result.errors).toContain('event_name is required and must be a string');
    });
  });

  describe('Event Name Validation', () => {
    it('should accept valid PageView event', () => {
      const result = validateEvent({ event_name: 'PageView' });
      expect(result.valid).toBe(true);
    });

    it('should accept valid Purchase event', () => {
      const result = validateEvent({ event_name: 'Purchase', value: 100, currency: 'BRL' });
      expect(result.valid).toBe(true);
    });

    it('should accept valid Lead event', () => {
      const result = validateEvent({ event_name: 'Lead' });
      expect(result.valid).toBe(true);
    });

    it('should accept all valid event names', () => {
      for (const eventName of VALID_EVENT_NAMES) {
        const result = validateEvent({ event_name: eventName });
        expect(result.valid).toBe(true);
      }
    });

    it('should reject invalid event name', () => {
      const result = validateEvent({ event_name: 'InvalidEvent' });
      expect(result.valid).toBe(false);
      expect(result.errors[0]).toContain('Invalid event_name');
    });

    it('should be case sensitive', () => {
      const result = validateEvent({ event_name: 'pageview' }); // lowercase
      expect(result.valid).toBe(false);
      expect(result.errors[0]).toContain('Invalid event_name');
    });
  });

  describe('Value Validation', () => {
    it('should accept valid numeric value', () => {
      const result = validateEvent({ event_name: 'Purchase', value: 99.90 });
      expect(result.valid).toBe(true);
    });

    it('should accept zero value', () => {
      const result = validateEvent({ event_name: 'Lead', value: 0 });
      expect(result.valid).toBe(true);
    });

    it('should reject negative value', () => {
      const result = validateEvent({ event_name: 'Purchase', value: -10 });
      expect(result.valid).toBe(false);
      expect(result.errors).toContain('value must be a positive number');
    });

    it('should reject non-numeric value', () => {
      const result = validateEvent({ event_name: 'Purchase', value: '99.90' });
      expect(result.valid).toBe(false);
      expect(result.errors).toContain('value must be a number');
    });

    it('should accept integer value', () => {
      const result = validateEvent({ event_name: 'Purchase', value: 100 });
      expect(result.valid).toBe(true);
    });

    it('should accept large value', () => {
      const result = validateEvent({ event_name: 'Purchase', value: 999999.99 });
      expect(result.valid).toBe(true);
    });
  });

  describe('Currency Validation', () => {
    it('should accept valid BRL currency', () => {
      const result = validateEvent({ event_name: 'Purchase', currency: 'BRL' });
      expect(result.valid).toBe(true);
    });

    it('should accept valid USD currency', () => {
      const result = validateEvent({ event_name: 'Purchase', currency: 'USD' });
      expect(result.valid).toBe(true);
    });

    it('should reject lowercase currency', () => {
      const result = validateEvent({ event_name: 'Purchase', currency: 'brl' });
      expect(result.valid).toBe(false);
      expect(result.errors).toContain('currency must be a valid 3-letter ISO code');
    });

    it('should reject invalid currency format', () => {
      const result = validateEvent({ event_name: 'Purchase', currency: 'REAL' });
      expect(result.valid).toBe(false);
      expect(result.errors).toContain('currency must be a valid 3-letter ISO code');
    });

    it('should reject non-string currency', () => {
      const result = validateEvent({ event_name: 'Purchase', currency: 986 });
      expect(result.valid).toBe(false);
      expect(result.errors).toContain('currency must be a string');
    });
  });

  describe('URL Validation', () => {
    it('should accept valid HTTPS URL', () => {
      const result = validateEvent({ event_name: 'PageView', url: 'https://example.com/page' });
      expect(result.valid).toBe(true);
    });

    it('should accept valid HTTP URL', () => {
      const result = validateEvent({ event_name: 'PageView', url: 'http://example.com' });
      expect(result.valid).toBe(true);
    });

    it('should accept URL with query parameters', () => {
      const result = validateEvent({ event_name: 'PageView', url: 'https://example.com/page?id=123&utm=test' });
      expect(result.valid).toBe(true);
    });

    it('should reject invalid URL', () => {
      const result = validateEvent({ event_name: 'PageView', url: 'not-a-url' });
      expect(result.valid).toBe(false);
      expect(result.errors).toContain('url must be a valid URL');
    });

    it('should reject URL without protocol', () => {
      const result = validateEvent({ event_name: 'PageView', url: 'example.com' });
      expect(result.valid).toBe(false);
      expect(result.errors).toContain('url must be a valid URL');
    });
  });

  describe('Email Validation', () => {
    it('should accept valid email', () => {
      const result = validateEvent({ event_name: 'Lead', email: 'test@example.com' });
      expect(result.valid).toBe(true);
    });

    it('should accept email with subdomain', () => {
      const result = validateEvent({ event_name: 'Lead', email: 'test@mail.example.com' });
      expect(result.valid).toBe(true);
    });

    it('should accept email with plus sign', () => {
      const result = validateEvent({ event_name: 'Lead', email: 'test+tag@example.com' });
      expect(result.valid).toBe(true);
    });

    it('should reject email without @', () => {
      const result = validateEvent({ event_name: 'Lead', email: 'testexample.com' });
      expect(result.valid).toBe(false);
      expect(result.errors).toContain('email must be a valid email address');
    });

    it('should reject email without domain', () => {
      const result = validateEvent({ event_name: 'Lead', email: 'test@' });
      expect(result.valid).toBe(false);
      expect(result.errors).toContain('email must be a valid email address');
    });

    it('should reject email with spaces', () => {
      const result = validateEvent({ event_name: 'Lead', email: 'test @example.com' });
      expect(result.valid).toBe(false);
      expect(result.errors).toContain('email must be a valid email address');
    });
  });

  describe('Phone Validation', () => {
    it('should accept valid Brazilian phone with country code', () => {
      const result = validateEvent({ event_name: 'Lead', phone: '+5511999999999' });
      expect(result.valid).toBe(true);
    });

    it('should accept phone with formatting', () => {
      const result = validateEvent({ event_name: 'Lead', phone: '(11) 99999-9999' });
      expect(result.valid).toBe(true);
    });

    it('should accept 10-digit phone', () => {
      const result = validateEvent({ event_name: 'Lead', phone: '1199999999' });
      expect(result.valid).toBe(true);
    });

    it('should accept 11-digit phone', () => {
      const result = validateEvent({ event_name: 'Lead', phone: '11999999999' });
      expect(result.valid).toBe(true);
    });

    it('should reject too short phone', () => {
      const result = validateEvent({ event_name: 'Lead', phone: '123456' });
      expect(result.valid).toBe(false);
      expect(result.errors).toContain('phone must be a valid phone number (10-15 digits)');
    });

    it('should reject too long phone', () => {
      const result = validateEvent({ event_name: 'Lead', phone: '1234567890123456' });
      expect(result.valid).toBe(false);
      expect(result.errors).toContain('phone must be a valid phone number (10-15 digits)');
    });
  });

  describe('Timestamp Validation', () => {
    it('should accept current timestamp', () => {
      const result = validateEvent({ event_name: 'PageView', timestamp: Date.now() });
      expect(result.valid).toBe(true);
    });

    it('should accept timestamp from 1 day ago', () => {
      const oneDayAgo = Date.now() - 24 * 60 * 60 * 1000;
      const result = validateEvent({ event_name: 'PageView', timestamp: oneDayAgo });
      expect(result.valid).toBe(true);
    });

    it('should accept timestamp from 6 days ago', () => {
      const sixDaysAgo = Date.now() - 6 * 24 * 60 * 60 * 1000;
      const result = validateEvent({ event_name: 'PageView', timestamp: sixDaysAgo });
      expect(result.valid).toBe(true);
    });

    it('should reject timestamp from 8 days ago', () => {
      const eightDaysAgo = Date.now() - 8 * 24 * 60 * 60 * 1000;
      const result = validateEvent({ event_name: 'PageView', timestamp: eightDaysAgo });
      expect(result.valid).toBe(false);
      expect(result.errors[0]).toContain('timestamp must be within the last 7 days');
    });

    it('should reject timestamp in far future', () => {
      const future = Date.now() + 24 * 60 * 60 * 1000;
      const result = validateEvent({ event_name: 'PageView', timestamp: future });
      expect(result.valid).toBe(false);
      expect(result.errors[0]).toContain('timestamp');
    });

    it('should reject non-numeric timestamp', () => {
      const result = validateEvent({ event_name: 'PageView', timestamp: '2024-01-01' });
      expect(result.valid).toBe(false);
      expect(result.errors).toContain('timestamp must be a number');
    });
  });

  describe('Content IDs Validation', () => {
    it('should accept array of content IDs', () => {
      const result = validateEvent({ event_name: 'Purchase', content_ids: ['SKU-001', 'SKU-002'] });
      expect(result.valid).toBe(true);
    });

    it('should accept empty array', () => {
      const result = validateEvent({ event_name: 'Purchase', content_ids: [] });
      expect(result.valid).toBe(true);
    });

    it('should accept single item array', () => {
      const result = validateEvent({ event_name: 'ViewContent', content_ids: ['SKU-001'] });
      expect(result.valid).toBe(true);
    });

    it('should reject non-array content_ids', () => {
      const result = validateEvent({ event_name: 'Purchase', content_ids: 'SKU-001' });
      expect(result.valid).toBe(false);
      expect(result.errors).toContain('content_ids must be an array');
    });
  });

  describe('Scroll Depth Validation', () => {
    it('should accept valid scroll depth', () => {
      const result = validateEvent({ event_name: 'PageView', scroll_depth: 50 });
      expect(result.valid).toBe(true);
    });

    it('should accept 0 scroll depth', () => {
      const result = validateEvent({ event_name: 'PageView', scroll_depth: 0 });
      expect(result.valid).toBe(true);
    });

    it('should accept 100 scroll depth', () => {
      const result = validateEvent({ event_name: 'PageView', scroll_depth: 100 });
      expect(result.valid).toBe(true);
    });

    it('should reject negative scroll depth', () => {
      const result = validateEvent({ event_name: 'PageView', scroll_depth: -10 });
      expect(result.valid).toBe(false);
      expect(result.errors).toContain('scroll_depth must be between 0 and 100');
    });

    it('should reject scroll depth over 100', () => {
      const result = validateEvent({ event_name: 'PageView', scroll_depth: 150 });
      expect(result.valid).toBe(false);
      expect(result.errors).toContain('scroll_depth must be between 0 and 100');
    });
  });

  describe('Full Event Validation', () => {
    it('should validate mock PageView basic event', () => {
      const result = validateEvent(mockPageViewBasic);
      expect(result.valid).toBe(true);
    });

    it('should validate mock PageView full event', () => {
      const result = validateEvent(mockPageViewFull);
      expect(result.valid).toBe(true);
    });

    it('should validate mock Purchase basic event', () => {
      const result = validateEvent(mockPurchaseBasic);
      expect(result.valid).toBe(true);
    });

    it('should validate mock Purchase full event', () => {
      const result = validateEvent(mockPurchaseFull);
      expect(result.valid).toBe(true);
    });

    it('should validate mock Lead basic event', () => {
      const result = validateEvent(mockLeadBasic);
      expect(result.valid).toBe(true);
    });

    it('should validate mock AddToCart event', () => {
      const result = validateEvent(mockAddToCart);
      expect(result.valid).toBe(true);
    });

    it('should validate mock InitiateCheckout event', () => {
      const result = validateEvent(mockInitiateCheckout);
      expect(result.valid).toBe(true);
    });

    it('should validate mock ViewContent event', () => {
      const result = validateEvent(mockViewContent);
      expect(result.valid).toBe(true);
    });
  });

  describe('Event Sanitization', () => {
    it('should return sanitized event on valid input', () => {
      const result = validateEvent({
        event_name: 'Purchase',
        value: 99.90,
        currency: 'BRL',
        extra_field: 'should be ignored',
      });

      expect(result.valid).toBe(true);
      expect(result.sanitizedEvent).toBeDefined();
      expect(result.sanitizedEvent?.event_name).toBe('Purchase');
      expect(result.sanitizedEvent?.value).toBe(99.90);
      expect(result.sanitizedEvent?.currency).toBe('BRL');
      // Extra fields not in schema should be filtered out
    });

    it('should add timestamp if not provided', () => {
      const result = validateEvent({ event_name: 'PageView' });

      expect(result.valid).toBe(true);
      expect(result.sanitizedEvent?.timestamp).toBeDefined();
      expect(typeof result.sanitizedEvent?.timestamp).toBe('number');
    });
  });

  describe('Multiple Errors', () => {
    it('should return all validation errors', () => {
      const result = validateEvent({
        event_name: 'InvalidEvent',
        value: 'not a number',
        email: 'invalid-email',
        scroll_depth: 150,
      });

      expect(result.valid).toBe(false);
      expect(result.errors.length).toBeGreaterThan(1);
      expect(result.errors.some(e => e.includes('event_name'))).toBe(true);
      expect(result.errors.some(e => e.includes('value'))).toBe(true);
      expect(result.errors.some(e => e.includes('email'))).toBe(true);
      expect(result.errors.some(e => e.includes('scroll_depth'))).toBe(true);
    });
  });
});
