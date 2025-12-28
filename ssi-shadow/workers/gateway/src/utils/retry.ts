// ============================================================================
// S.S.I. SHADOW - Retry Logic with Exponential Backoff
// ============================================================================

import { RetryConfig } from '../types';

/**
 * Default retry configuration
 */
export const DEFAULT_RETRY_CONFIG: RetryConfig = {
  maxRetries: 3,
  baseDelayMs: 1000,
  maxDelayMs: 10000,
  retryableStatuses: [408, 429, 500, 502, 503, 504],
};

/**
 * Calculate delay with exponential backoff and jitter
 */
export function calculateDelay(attempt: number, config: RetryConfig): number {
  // Exponential backoff: baseDelay * 2^attempt
  const exponentialDelay = config.baseDelayMs * Math.pow(2, attempt);
  
  // Add jitter (±25% randomization to prevent thundering herd)
  const jitter = exponentialDelay * 0.25 * (Math.random() * 2 - 1);
  
  // Apply max delay cap
  const delay = Math.min(exponentialDelay + jitter, config.maxDelayMs);
  
  return Math.round(delay);
}

/**
 * Sleep for specified milliseconds
 */
export function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * Check if status code is retryable
 */
export function isRetryable(status: number, config: RetryConfig): boolean {
  return config.retryableStatuses.includes(status);
}

/**
 * Check if error is a network error (retryable)
 */
export function isNetworkError(error: unknown): boolean {
  if (error instanceof Error) {
    const message = error.message.toLowerCase();
    return (
      message.includes('network') ||
      message.includes('timeout') ||
      message.includes('econnreset') ||
      message.includes('econnrefused') ||
      message.includes('socket') ||
      message.includes('fetch failed')
    );
  }
  return false;
}

/**
 * Retry result type
 */
export interface RetryResult<T> {
  success: boolean;
  data?: T;
  error?: string;
  attempts: number;
  lastStatus?: number;
}

/**
 * Execute a function with retry logic
 */
export async function withRetry<T>(
  fn: () => Promise<Response>,
  config: RetryConfig = DEFAULT_RETRY_CONFIG,
  parseResponse: (response: Response) => Promise<T> = (r) => r.json() as Promise<T>
): Promise<RetryResult<T>> {
  let lastError: string = '';
  let lastStatus: number | undefined;
  
  for (let attempt = 0; attempt <= config.maxRetries; attempt++) {
    try {
      // Execute the function
      const response = await fn();
      lastStatus = response.status;
      
      // Success
      if (response.ok) {
        const data = await parseResponse(response);
        return {
          success: true,
          data,
          attempts: attempt + 1,
          lastStatus,
        };
      }
      
      // Non-retryable error
      if (!isRetryable(response.status, config)) {
        const errorText = await response.text();
        return {
          success: false,
          error: `HTTP ${response.status}: ${errorText}`,
          attempts: attempt + 1,
          lastStatus,
        };
      }
      
      // Retryable error - store for potential retry
      lastError = `HTTP ${response.status}`;
      
      // If not last attempt, wait before retry
      if (attempt < config.maxRetries) {
        const delay = calculateDelay(attempt, config);
        console.log(`[Retry] Attempt ${attempt + 1} failed with status ${response.status}. Retrying in ${delay}ms...`);
        await sleep(delay);
      }
      
    } catch (error) {
      // Network or other error
      const errorMessage = error instanceof Error ? error.message : String(error);
      lastError = errorMessage;
      
      // Check if it's a network error (retryable)
      if (isNetworkError(error)) {
        if (attempt < config.maxRetries) {
          const delay = calculateDelay(attempt, config);
          console.log(`[Retry] Attempt ${attempt + 1} failed with error: ${errorMessage}. Retrying in ${delay}ms...`);
          await sleep(delay);
          continue;
        }
      }
      
      // Non-retryable error
      return {
        success: false,
        error: errorMessage,
        attempts: attempt + 1,
        lastStatus,
      };
    }
  }
  
  // All retries exhausted
  return {
    success: false,
    error: `Max retries (${config.maxRetries}) exceeded. Last error: ${lastError}`,
    attempts: config.maxRetries + 1,
    lastStatus,
  };
}

/**
 * Retry configuration for Meta CAPI
 * Meta recommends retry on 5xx and 429 (rate limit)
 */
export const META_RETRY_CONFIG: RetryConfig = {
  maxRetries: 3,
  baseDelayMs: 1000,
  maxDelayMs: 8000,
  retryableStatuses: [429, 500, 502, 503, 504],
};

/**
 * Retry configuration for Google APIs
 */
export const GOOGLE_RETRY_CONFIG: RetryConfig = {
  maxRetries: 3,
  baseDelayMs: 1000,
  maxDelayMs: 10000,
  retryableStatuses: [408, 429, 500, 502, 503, 504],
};

/**
 * Retry configuration for TikTok API
 */
export const TIKTOK_RETRY_CONFIG: RetryConfig = {
  maxRetries: 3,
  baseDelayMs: 500,
  maxDelayMs: 5000,
  retryableStatuses: [429, 500, 502, 503, 504],
};
