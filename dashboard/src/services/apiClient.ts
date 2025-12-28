// ============================================================================
// S.S.I. SHADOW Dashboard - API Client
// ============================================================================
// Cliente HTTP centralizado com:
// - Interceptor de autenticação (Bearer token)
// - Tratamento automático de 401 (logout)
// - Retry com exponential backoff
// - Request/Response logging em desenvolvimento
// - Tipagem TypeScript completa
// ============================================================================

// =============================================================================
// TYPES
// =============================================================================

export interface ApiClientConfig {
  baseUrl?: string;
  timeout?: number;
  retries?: number;
  retryDelay?: number;
  onUnauthorized?: () => void;
  onError?: (error: ApiError) => void;
  debug?: boolean;
}

export interface RequestConfig extends Omit<RequestInit, 'body'> {
  params?: Record<string, string | number | boolean | undefined>;
  data?: unknown;
  timeout?: number;
  retries?: number;
  skipAuth?: boolean;
}

export interface ApiResponse<T = unknown> {
  data: T;
  status: number;
  statusText: string;
  headers: Headers;
  ok: boolean;
}

export interface ApiError extends Error {
  status?: number;
  statusText?: string;
  data?: unknown;
  code?: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  has_next: boolean;
  has_prev: boolean;
}

// =============================================================================
// CONSTANTS
// =============================================================================

const DEFAULT_CONFIG: Required<ApiClientConfig> = {
  baseUrl: import.meta.env.VITE_API_URL || 'http://localhost:8000/api',
  timeout: 30000,
  retries: 3,
  retryDelay: 1000,
  onUnauthorized: () => {},
  onError: () => {},
  debug: import.meta.env.DEV,
};

const TOKEN_KEY = 'ssi_shadow_token';

// =============================================================================
// API CLIENT CLASS
// =============================================================================

class ApiClient {
  private config: Required<ApiClientConfig>;
  private abortControllers: Map<string, AbortController> = new Map();
  
  constructor(config: ApiClientConfig = {}) {
    this.config = { ...DEFAULT_CONFIG, ...config };
  }
  
  // ===========================================================================
  // CONFIGURATION
  // ===========================================================================
  
  /**
   * Update client configuration
   */
  configure(config: Partial<ApiClientConfig>): void {
    this.config = { ...this.config, ...config };
  }
  
  /**
   * Set unauthorized callback (called on 401)
   */
  setOnUnauthorized(callback: () => void): void {
    this.config.onUnauthorized = callback;
  }
  
  /**
   * Set error callback
   */
  setOnError(callback: (error: ApiError) => void): void {
    this.config.onError = callback;
  }
  
  // ===========================================================================
  // TOKEN MANAGEMENT
  // ===========================================================================
  
  /**
   * Get stored auth token
   */
  getToken(): string | null {
    try {
      return localStorage.getItem(TOKEN_KEY);
    } catch {
      return null;
    }
  }
  
  /**
   * Set auth token
   */
  setToken(token: string): void {
    try {
      localStorage.setItem(TOKEN_KEY, token);
    } catch (e) {
      console.error('Failed to save token:', e);
    }
  }
  
  /**
   * Clear auth token
   */
  clearToken(): void {
    try {
      localStorage.removeItem(TOKEN_KEY);
    } catch {
      // Ignore
    }
  }
  
  // ===========================================================================
  // REQUEST HELPERS
  // ===========================================================================
  
  /**
   * Build full URL with query params
   */
  private buildUrl(endpoint: string, params?: Record<string, string | number | boolean | undefined>): string {
    // Handle absolute URLs
    if (endpoint.startsWith('http://') || endpoint.startsWith('https://')) {
      return endpoint;
    }
    
    // Build relative URL
    const baseUrl = this.config.baseUrl.replace(/\/$/, '');
    const path = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
    let url = `${baseUrl}${path}`;
    
    // Add query params
    if (params && Object.keys(params).length > 0) {
      const searchParams = new URLSearchParams();
      Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined && value !== null) {
          searchParams.append(key, String(value));
        }
      });
      url += `?${searchParams.toString()}`;
    }
    
    return url;
  }
  
  /**
   * Build request headers
   */
  private buildHeaders(config: RequestConfig): Headers {
    const headers = new Headers(config.headers);
    
    // Set default content type if not provided and has body
    if (config.data && !headers.has('Content-Type')) {
      headers.set('Content-Type', 'application/json');
    }
    
    // Add auth token if not skipped
    if (!config.skipAuth) {
      const token = this.getToken();
      if (token) {
        headers.set('Authorization', `Bearer ${token}`);
      }
    }
    
    return headers;
  }
  
  /**
   * Create API error from response
   */
  private async createError(response: Response, message?: string): Promise<ApiError> {
    let data: unknown;
    
    try {
      const contentType = response.headers.get('content-type');
      if (contentType?.includes('application/json')) {
        data = await response.json();
      } else {
        data = await response.text();
      }
    } catch {
      data = null;
    }
    
    const error = new Error(
      message || 
      (data as { detail?: string; message?: string })?.detail ||
      (data as { detail?: string; message?: string })?.message ||
      response.statusText ||
      'Request failed'
    ) as ApiError;
    
    error.status = response.status;
    error.statusText = response.statusText;
    error.data = data;
    error.name = 'ApiError';
    
    return error;
  }
  
  /**
   * Log request/response for debugging
   */
  private log(type: 'request' | 'response' | 'error', data: unknown): void {
    if (!this.config.debug) return;
    
    const prefix = {
      request: '🔵 API Request:',
      response: '🟢 API Response:',
      error: '🔴 API Error:',
    }[type];
    
    console.log(prefix, data);
  }
  
  // ===========================================================================
  // CORE REQUEST METHOD
  // ===========================================================================
  
  /**
   * Make HTTP request with retry and error handling
   */
  async request<T = unknown>(
    method: string,
    endpoint: string,
    config: RequestConfig = {}
  ): Promise<ApiResponse<T>> {
    const url = this.buildUrl(endpoint, config.params);
    const headers = this.buildHeaders(config);
    const timeout = config.timeout || this.config.timeout;
    const maxRetries = config.retries ?? this.config.retries;
    
    // Create abort controller for timeout
    const controller = new AbortController();
    const requestId = `${method}:${url}:${Date.now()}`;
    this.abortControllers.set(requestId, controller);
    
    // Set timeout
    const timeoutId = setTimeout(() => {
      controller.abort();
    }, timeout);
    
    // Prepare request body
    let body: BodyInit | undefined;
    if (config.data !== undefined) {
      body = typeof config.data === 'string' 
        ? config.data 
        : JSON.stringify(config.data);
    }
    
    const requestInit: RequestInit = {
      method,
      headers,
      body,
      signal: controller.signal,
      credentials: config.credentials || 'same-origin',
      mode: config.mode || 'cors',
    };
    
    this.log('request', { method, url, headers: Object.fromEntries(headers), body: config.data });
    
    let lastError: ApiError | null = null;
    let attempt = 0;
    
    while (attempt <= maxRetries) {
      try {
        const response = await fetch(url, requestInit);
        
        clearTimeout(timeoutId);
        this.abortControllers.delete(requestId);
        
        // Handle 401 Unauthorized
        if (response.status === 401) {
          const error = await this.createError(response, 'Unauthorized');
          this.log('error', { status: 401, error });
          
          // Clear token and trigger callback
          this.clearToken();
          this.config.onUnauthorized();
          
          throw error;
        }
        
        // Handle other error status codes
        if (!response.ok) {
          const error = await this.createError(response);
          this.log('error', { status: response.status, error });
          
          // Don't retry client errors (4xx) except 408, 429
          if (response.status >= 400 && response.status < 500 && 
              response.status !== 408 && response.status !== 429) {
            this.config.onError(error);
            throw error;
          }
          
          throw error;
        }
        
        // Parse response
        let data: T;
        const contentType = response.headers.get('content-type');
        
        if (contentType?.includes('application/json')) {
          data = await response.json() as T;
        } else if (contentType?.includes('text/')) {
          data = await response.text() as unknown as T;
        } else {
          data = await response.blob() as unknown as T;
        }
        
        this.log('response', { status: response.status, data });
        
        return {
          data,
          status: response.status,
          statusText: response.statusText,
          headers: response.headers,
          ok: true,
        };
        
      } catch (error) {
        clearTimeout(timeoutId);
        this.abortControllers.delete(requestId);
        
        // Handle abort/timeout
        if (error instanceof DOMException && error.name === 'AbortError') {
          lastError = new Error('Request timeout') as ApiError;
          lastError.code = 'TIMEOUT';
        } else if (error instanceof TypeError) {
          // Network error
          lastError = new Error('Network error') as ApiError;
          lastError.code = 'NETWORK_ERROR';
        } else {
          lastError = error as ApiError;
        }
        
        // Check if we should retry
        const isRetryable = !lastError.status || 
          lastError.status >= 500 ||
          lastError.status === 408 ||
          lastError.status === 429 ||
          lastError.code === 'TIMEOUT' ||
          lastError.code === 'NETWORK_ERROR';
        
        if (!isRetryable || attempt >= maxRetries) {
          this.config.onError(lastError);
          throw lastError;
        }
        
        // Exponential backoff
        const delay = this.config.retryDelay * Math.pow(2, attempt);
        console.warn(`Retrying request in ${delay}ms (attempt ${attempt + 1}/${maxRetries})`);
        await new Promise(resolve => setTimeout(resolve, delay));
        
        attempt++;
      }
    }
    
    throw lastError || new Error('Request failed after retries');
  }
  
  // ===========================================================================
  // HTTP METHOD SHORTCUTS
  // ===========================================================================
  
  /**
   * GET request
   */
  async get<T = unknown>(endpoint: string, config?: RequestConfig): Promise<ApiResponse<T>> {
    return this.request<T>('GET', endpoint, config);
  }
  
  /**
   * POST request
   */
  async post<T = unknown>(endpoint: string, data?: unknown, config?: RequestConfig): Promise<ApiResponse<T>> {
    return this.request<T>('POST', endpoint, { ...config, data });
  }
  
  /**
   * PUT request
   */
  async put<T = unknown>(endpoint: string, data?: unknown, config?: RequestConfig): Promise<ApiResponse<T>> {
    return this.request<T>('PUT', endpoint, { ...config, data });
  }
  
  /**
   * PATCH request
   */
  async patch<T = unknown>(endpoint: string, data?: unknown, config?: RequestConfig): Promise<ApiResponse<T>> {
    return this.request<T>('PATCH', endpoint, { ...config, data });
  }
  
  /**
   * DELETE request
   */
  async delete<T = unknown>(endpoint: string, config?: RequestConfig): Promise<ApiResponse<T>> {
    return this.request<T>('DELETE', endpoint, config);
  }
  
  // ===========================================================================
  // UTILITY METHODS
  // ===========================================================================
  
  /**
   * Cancel all pending requests
   */
  cancelAll(): void {
    this.abortControllers.forEach((controller) => {
      controller.abort();
    });
    this.abortControllers.clear();
  }
  
  /**
   * Upload file with progress tracking
   */
  async upload<T = unknown>(
    endpoint: string,
    file: File | Blob,
    config?: RequestConfig & {
      fieldName?: string;
      additionalData?: Record<string, string>;
      onProgress?: (progress: number) => void;
    }
  ): Promise<ApiResponse<T>> {
    const formData = new FormData();
    formData.append(config?.fieldName || 'file', file);
    
    if (config?.additionalData) {
      Object.entries(config.additionalData).forEach(([key, value]) => {
        formData.append(key, value);
      });
    }
    
    // Note: For progress tracking, you'd need XMLHttpRequest instead of fetch
    // This is a simplified version
    return this.request<T>('POST', endpoint, {
      ...config,
      data: formData,
      headers: {
        ...config?.headers,
        // Don't set Content-Type for FormData - browser will set it with boundary
      },
    });
  }
  
  /**
   * Download file
   */
  async download(
    endpoint: string,
    filename?: string,
    config?: RequestConfig
  ): Promise<void> {
    const response = await this.request<Blob>('GET', endpoint, {
      ...config,
    });
    
    // Create download link
    const url = URL.createObjectURL(response.data);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename || 'download';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }
}

// =============================================================================
// DEFAULT INSTANCE
// =============================================================================

const apiClient = new ApiClient();

// =============================================================================
// CONVENIENCE FUNCTIONS
// =============================================================================

/**
 * Configure the default API client
 */
export function configureApi(config: ApiClientConfig): void {
  apiClient.configure(config);
}

/**
 * Set the auth token
 */
export function setAuthToken(token: string): void {
  apiClient.setToken(token);
}

/**
 * Clear the auth token
 */
export function clearAuthToken(): void {
  apiClient.clearToken();
}

/**
 * Set callback for unauthorized responses
 */
export function onUnauthorized(callback: () => void): void {
  apiClient.setOnUnauthorized(callback);
}

// =============================================================================
// API ENDPOINT HELPERS
// =============================================================================

export const api = {
  // Auth endpoints
  auth: {
    login: (email: string, password: string) => 
      apiClient.post<{ access_token: string; refresh_token: string; user: unknown }>('/auth/login', { email, password }),
    
    logout: () => 
      apiClient.post('/auth/logout'),
    
    register: (data: { email: string; password: string; name: string }) =>
      apiClient.post('/auth/register', data),
    
    refresh: (refreshToken: string) =>
      apiClient.post<{ access_token: string }>('/auth/refresh', { refresh_token: refreshToken }),
    
    me: () => 
      apiClient.get('/auth/me'),
    
    updateProfile: (data: Partial<{ name: string; avatar_url: string }>) =>
      apiClient.patch('/auth/me', data),
    
    changePassword: (oldPassword: string, newPassword: string) =>
      apiClient.post('/auth/change-password', { old_password: oldPassword, new_password: newPassword }),
  },
  
  // Dashboard endpoints
  dashboard: {
    overview: () => 
      apiClient.get('/dashboard/overview'),
    
    metrics: (startDate: string, endDate: string) =>
      apiClient.get('/dashboard/metrics', { params: { start_date: startDate, end_date: endDate } }),
    
    events: (params?: { page?: number; limit?: number; event_type?: string }) =>
      apiClient.get('/dashboard/events', { params }),
    
    conversions: (params?: { start_date?: string; end_date?: string }) =>
      apiClient.get('/dashboard/conversions', { params }),
  },
  
  // Identity endpoints
  identity: {
    graph: (canonicalId: string) =>
      apiClient.get(`/identity/graph/${canonicalId}`),
    
    search: (query: string) =>
      apiClient.get('/identity/search', { params: { q: query } }),
    
    profiles: (params?: { page?: number; limit?: number }) =>
      apiClient.get('/identity/profiles', { params }),
  },
  
  // Campaigns endpoints
  campaigns: {
    list: (params?: { page?: number; limit?: number; status?: string }) =>
      apiClient.get('/campaigns', { params }),
    
    get: (id: string) =>
      apiClient.get(`/campaigns/${id}`),
    
    create: (data: unknown) =>
      apiClient.post('/campaigns', data),
    
    update: (id: string, data: unknown) =>
      apiClient.patch(`/campaigns/${id}`, data),
    
    delete: (id: string) =>
      apiClient.delete(`/campaigns/${id}`),
  },
  
  // Webhooks endpoints
  webhooks: {
    list: () =>
      apiClient.get('/webhooks'),
    
    get: (id: string) =>
      apiClient.get(`/webhooks/${id}`),
    
    create: (data: unknown) =>
      apiClient.post('/webhooks', data),
    
    update: (id: string, data: unknown) =>
      apiClient.patch(`/webhooks/${id}`, data),
    
    delete: (id: string) =>
      apiClient.delete(`/webhooks/${id}`),
    
    test: (id: string) =>
      apiClient.post(`/webhooks/${id}/test`),
  },
  
  // Settings endpoints
  settings: {
    get: () =>
      apiClient.get('/settings'),
    
    update: (data: unknown) =>
      apiClient.patch('/settings', data),
    
    organization: () =>
      apiClient.get('/settings/organization'),
    
    updateOrganization: (data: unknown) =>
      apiClient.patch('/settings/organization', data),
  },
};

// =============================================================================
// EXPORTS
// =============================================================================

export { ApiClient, apiClient };
export default apiClient;
