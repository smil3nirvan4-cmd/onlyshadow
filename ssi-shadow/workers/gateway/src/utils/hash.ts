// ============================================================================
// S.S.I. SHADOW - SHA-256 Hashing Utilities
// ============================================================================

/**
 * Computes SHA-256 hash of a string using Web Crypto API
 * Returns lowercase hexadecimal string
 */
export async function sha256(data: string): Promise<string> {
  const encoder = new TextEncoder();
  const dataBuffer = encoder.encode(data);
  const hashBuffer = await crypto.subtle.digest('SHA-256', dataBuffer);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  const hashHex = hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
  return hashHex;
}

/**
 * Synchronous SHA-256 hash using Web Crypto API
 * Note: This returns a Promise, use with await
 */
export async function hashPII(value: string | undefined | null): Promise<string | undefined> {
  if (!value || value.trim() === '') {
    return undefined;
  }
  return sha256(value);
}

/**
 * Hash multiple values and return as array (for Meta CAPI format)
 */
export async function hashToArray(value: string | undefined | null): Promise<string[] | undefined> {
  const hash = await hashPII(value);
  return hash ? [hash] : undefined;
}

/**
 * Generate UUID v4
 * Uses Web Crypto API for secure random generation
 */
export function generateUUID(): string {
  return crypto.randomUUID();
}

/**
 * Generate a unique event ID
 * Format: timestamp-random for debugging purposes
 */
export function generateEventId(): string {
  return crypto.randomUUID();
}

/**
 * Generate SSI ID if not provided
 * This creates a persistent identifier for the user
 */
export function generateSSIId(): string {
  return `ssi_${crypto.randomUUID().replace(/-/g, '')}`;
}
