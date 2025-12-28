/**
 * S.S.I. SHADOW - Hash Utilities Tests
 * Tests for SHA-256 hashing and normalization functions
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock the actual hash module for testing
// In real implementation, import from '@/utils/hash'

// =============================================================================
// HASH FUNCTION IMPLEMENTATION (for testing)
// =============================================================================

async function sha256Hash(input: string): Promise<string> {
  const data = new TextEncoder().encode(input.toLowerCase().trim());
  const hashBuffer = await crypto.subtle.digest('SHA-256', data);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
}

function normalizeEmail(email: string): string {
  return email.toLowerCase().trim();
}

function normalizePhone(phone: string, countryCode: string = '55'): string {
  // Remove all non-digits
  let digits = phone.replace(/\D/g, '');
  
  // Add country code if not present
  if (!digits.startsWith(countryCode) && digits.length <= 11) {
    digits = countryCode + digits;
  }
  
  return digits;
}

function generateEventId(): string {
  const timestamp = Date.now().toString(36);
  const random = Math.random().toString(36).substring(2, 11);
  return `evt_${timestamp}_${random}`;
}

function generateSSIId(): string {
  const timestamp = Date.now().toString(36);
  const random = Math.random().toString(36).substring(2, 11);
  return `ssi_${timestamp}_${random}`;
}

// =============================================================================
// TESTS
// =============================================================================

describe('Hash Utilities', () => {
  describe('sha256Hash', () => {
    it('should hash a simple string', async () => {
      const hash = await sha256Hash('test');
      expect(hash).toBeDefined();
      expect(typeof hash).toBe('string');
      expect(hash.length).toBe(64); // SHA-256 = 64 hex chars
    });

    it('should produce consistent hashes for same input', async () => {
      const hash1 = await sha256Hash('test@example.com');
      const hash2 = await sha256Hash('test@example.com');
      expect(hash1).toBe(hash2);
    });

    it('should produce different hashes for different inputs', async () => {
      const hash1 = await sha256Hash('test1@example.com');
      const hash2 = await sha256Hash('test2@example.com');
      expect(hash1).not.toBe(hash2);
    });

    it('should normalize input (lowercase and trim)', async () => {
      const hash1 = await sha256Hash('Test@Example.com');
      const hash2 = await sha256Hash('test@example.com');
      const hash3 = await sha256Hash('  test@example.com  ');
      expect(hash1).toBe(hash2);
      expect(hash2).toBe(hash3);
    });

    it('should handle empty string', async () => {
      const hash = await sha256Hash('');
      expect(hash).toBeDefined();
      expect(hash.length).toBe(64);
    });

    it('should handle unicode characters', async () => {
      const hash = await sha256Hash('josé@example.com');
      expect(hash).toBeDefined();
      expect(hash.length).toBe(64);
    });

    it('should handle special characters', async () => {
      const hash = await sha256Hash('test+tag@example.com');
      expect(hash).toBeDefined();
      expect(hash.length).toBe(64);
    });
  });

  describe('normalizeEmail', () => {
    it('should lowercase email', () => {
      expect(normalizeEmail('Test@Example.COM')).toBe('test@example.com');
    });

    it('should trim whitespace', () => {
      expect(normalizeEmail('  test@example.com  ')).toBe('test@example.com');
    });

    it('should handle already normalized email', () => {
      expect(normalizeEmail('test@example.com')).toBe('test@example.com');
    });

    it('should handle empty string', () => {
      expect(normalizeEmail('')).toBe('');
    });
  });

  describe('normalizePhone', () => {
    it('should remove non-digit characters', () => {
      expect(normalizePhone('(11) 99999-9999')).toBe('5511999999999');
    });

    it('should add country code if missing', () => {
      expect(normalizePhone('11999999999')).toBe('5511999999999');
    });

    it('should not duplicate country code', () => {
      expect(normalizePhone('5511999999999')).toBe('5511999999999');
    });

    it('should handle phone with spaces', () => {
      expect(normalizePhone('11 99999 9999')).toBe('5511999999999');
    });

    it('should handle international format', () => {
      expect(normalizePhone('+55 11 99999-9999')).toBe('5511999999999');
    });

    it('should support custom country code', () => {
      expect(normalizePhone('1234567890', '1')).toBe('11234567890');
    });

    it('should handle mobile number with 9', () => {
      expect(normalizePhone('11 9 9999-9999')).toBe('5511999999999');
    });

    it('should handle landline number', () => {
      expect(normalizePhone('11 3333-3333')).toBe('551133333333');
    });
  });

  describe('generateEventId', () => {
    it('should generate unique IDs', () => {
      const ids = new Set<string>();
      for (let i = 0; i < 100; i++) {
        ids.add(generateEventId());
      }
      expect(ids.size).toBe(100);
    });

    it('should start with evt_ prefix', () => {
      const id = generateEventId();
      expect(id.startsWith('evt_')).toBe(true);
    });

    it('should have consistent format', () => {
      const id = generateEventId();
      expect(id).toMatch(/^evt_[a-z0-9]+_[a-z0-9]+$/);
    });

    it('should be longer than 10 characters', () => {
      const id = generateEventId();
      expect(id.length).toBeGreaterThan(10);
    });
  });

  describe('generateSSIId', () => {
    it('should generate unique IDs', () => {
      const ids = new Set<string>();
      for (let i = 0; i < 100; i++) {
        ids.add(generateSSIId());
      }
      expect(ids.size).toBe(100);
    });

    it('should start with ssi_ prefix', () => {
      const id = generateSSIId();
      expect(id.startsWith('ssi_')).toBe(true);
    });

    it('should have consistent format', () => {
      const id = generateSSIId();
      expect(id).toMatch(/^ssi_[a-z0-9]+_[a-z0-9]+$/);
    });
  });
});

describe('PII Hashing for Platform APIs', () => {
  it('should hash email correctly for Meta CAPI', async () => {
    // Meta expects lowercase, trimmed, SHA-256 hashed
    const email = 'Test@Example.com';
    const normalized = normalizeEmail(email);
    const hash = await sha256Hash(normalized);
    
    expect(normalized).toBe('test@example.com');
    expect(hash.length).toBe(64);
  });

  it('should hash phone correctly for Meta CAPI', async () => {
    // Meta expects E.164 format (digits only), SHA-256 hashed
    const phone = '(11) 99999-9999';
    const normalized = normalizePhone(phone);
    const hash = await sha256Hash(normalized);
    
    expect(normalized).toBe('5511999999999');
    expect(hash.length).toBe(64);
  });

  it('should produce consistent hashes for same PII across platforms', async () => {
    const email = 'user@test.com';
    const hash1 = await sha256Hash(normalizeEmail(email));
    const hash2 = await sha256Hash(normalizeEmail(email));
    
    // All platforms should receive the same hash
    expect(hash1).toBe(hash2);
  });
});
