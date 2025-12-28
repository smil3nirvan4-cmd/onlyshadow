// ============================================================================
// S.S.I. SHADOW Dashboard - Authentication Context
// ============================================================================
// Gerencia estado de autenticação global da aplicação
// Suporta JWT tokens com refresh automático
// ============================================================================

import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  useMemo,
  ReactNode,
} from 'react';

// =============================================================================
// TYPES
// =============================================================================

export interface User {
  id: string;
  email: string;
  name: string;
  role: 'admin' | 'manager' | 'analyst' | 'viewer';
  organization_id: string;
  organization_name?: string;
  avatar_url?: string;
  permissions?: string[];
  created_at?: string;
  last_login?: string;
}

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface LoginCredentials {
  email: string;
  password: string;
  remember_me?: boolean;
}

export interface RegisterData {
  email: string;
  password: string;
  name: string;
  organization_name?: string;
}

export interface AuthState {
  user: User | null;
  token: string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;
}

export interface AuthContextType extends AuthState {
  // Auth actions
  login: (credentials: LoginCredentials) => Promise<boolean>;
  logout: () => Promise<void>;
  register: (data: RegisterData) => Promise<boolean>;
  refreshAccessToken: () => Promise<boolean>;
  
  // SSO actions
  loginWithSSO: (provider: 'google' | 'microsoft' | 'saml', orgId?: string) => void;
  handleSSOCallback: (params: URLSearchParams) => Promise<boolean>;
  
  // User actions
  updateProfile: (data: Partial<User>) => Promise<boolean>;
  changePassword: (oldPassword: string, newPassword: string) => Promise<boolean>;
  
  // Utility
  clearError: () => void;
  hasPermission: (permission: string) => boolean;
  hasRole: (role: string | string[]) => boolean;
}

// =============================================================================
// CONSTANTS
// =============================================================================

const TOKEN_KEY = 'ssi_shadow_token';
const REFRESH_TOKEN_KEY = 'ssi_shadow_refresh_token';
const USER_KEY = 'ssi_shadow_user';
const TOKEN_EXPIRY_KEY = 'ssi_shadow_token_expiry';

// API base URL (configure via environment variable)
const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

// Token refresh threshold (refresh 5 minutes before expiry)
const REFRESH_THRESHOLD_MS = 5 * 60 * 1000;

// =============================================================================
// CONTEXT
// =============================================================================

const AuthContext = createContext<AuthContextType | undefined>(undefined);

// =============================================================================
// STORAGE HELPERS
// =============================================================================

const storage = {
  get: (key: string): string | null => {
    try {
      return localStorage.getItem(key);
    } catch {
      return null;
    }
  },
  
  set: (key: string, value: string): void => {
    try {
      localStorage.setItem(key, value);
    } catch (e) {
      console.error('Failed to save to localStorage:', e);
    }
  },
  
  remove: (key: string): void => {
    try {
      localStorage.removeItem(key);
    } catch {
      // Ignore
    }
  },
  
  getJSON: <T>(key: string): T | null => {
    try {
      const item = localStorage.getItem(key);
      return item ? JSON.parse(item) : null;
    } catch {
      return null;
    }
  },
  
  setJSON: <T>(key: string, value: T): void => {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch (e) {
      console.error('Failed to save to localStorage:', e);
    }
  },
};

// =============================================================================
// AUTH PROVIDER COMPONENT
// =============================================================================

interface AuthProviderProps {
  children: ReactNode;
}

export function AuthProvider({ children }: AuthProviderProps) {
  // State
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  // Derived state
  const isAuthenticated = useMemo(() => !!token && !!user, [token, user]);
  
  // ===========================================================================
  // INITIALIZATION
  // ===========================================================================
  
  useEffect(() => {
    const initializeAuth = async () => {
      try {
        // Load stored credentials
        const storedToken = storage.get(TOKEN_KEY);
        const storedRefreshToken = storage.get(REFRESH_TOKEN_KEY);
        const storedUser = storage.getJSON<User>(USER_KEY);
        const tokenExpiry = storage.get(TOKEN_EXPIRY_KEY);
        
        if (storedToken && storedUser) {
          // Check if token is expired
          const expiryTime = tokenExpiry ? parseInt(tokenExpiry, 10) : 0;
          const now = Date.now();
          
          if (expiryTime > now) {
            // Token still valid
            setToken(storedToken);
            setRefreshToken(storedRefreshToken);
            setUser(storedUser);
            
            // Schedule token refresh
            const timeUntilRefresh = expiryTime - now - REFRESH_THRESHOLD_MS;
            if (timeUntilRefresh > 0) {
              setTimeout(() => refreshAccessToken(), timeUntilRefresh);
            }
          } else if (storedRefreshToken) {
            // Token expired, try to refresh
            await refreshAccessToken();
          } else {
            // No valid tokens, clear storage
            clearStoredAuth();
          }
        }
      } catch (e) {
        console.error('Auth initialization error:', e);
        clearStoredAuth();
      } finally {
        setIsLoading(false);
      }
    };
    
    initializeAuth();
  }, []);
  
  // ===========================================================================
  // HELPER FUNCTIONS
  // ===========================================================================
  
  const clearStoredAuth = useCallback(() => {
    storage.remove(TOKEN_KEY);
    storage.remove(REFRESH_TOKEN_KEY);
    storage.remove(USER_KEY);
    storage.remove(TOKEN_EXPIRY_KEY);
    setToken(null);
    setRefreshToken(null);
    setUser(null);
  }, []);
  
  const saveAuthData = useCallback((tokens: AuthTokens, userData: User) => {
    const expiryTime = Date.now() + tokens.expires_in * 1000;
    
    storage.set(TOKEN_KEY, tokens.access_token);
    storage.set(REFRESH_TOKEN_KEY, tokens.refresh_token);
    storage.setJSON(USER_KEY, userData);
    storage.set(TOKEN_EXPIRY_KEY, expiryTime.toString());
    
    setToken(tokens.access_token);
    setRefreshToken(tokens.refresh_token);
    setUser(userData);
    
    // Schedule token refresh
    const refreshDelay = tokens.expires_in * 1000 - REFRESH_THRESHOLD_MS;
    if (refreshDelay > 0) {
      setTimeout(() => refreshAccessToken(), refreshDelay);
    }
  }, []);
  
  const apiRequest = useCallback(async (
    endpoint: string,
    options: RequestInit = {}
  ): Promise<Response> => {
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    };
    
    if (token) {
      (headers as Record<string, string>)['Authorization'] = `Bearer ${token}`;
    }
    
    const response = await fetch(`${API_BASE_URL}${endpoint}`, {
      ...options,
      headers,
    });
    
    return response;
  }, [token]);
  
  // ===========================================================================
  // AUTH ACTIONS
  // ===========================================================================
  
  const login = useCallback(async (credentials: LoginCredentials): Promise<boolean> => {
    setIsLoading(true);
    setError(null);
    
    try {
      const response = await fetch(`${API_BASE_URL}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(credentials),
      });
      
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || errorData.message || 'Login failed');
      }
      
      const data = await response.json();
      
      // Validate response structure
      if (!data.access_token || !data.user) {
        throw new Error('Invalid server response');
      }
      
      // Save auth data
      saveAuthData(
        {
          access_token: data.access_token,
          refresh_token: data.refresh_token || '',
          token_type: data.token_type || 'bearer',
          expires_in: data.expires_in || 3600,
        },
        data.user
      );
      
      console.log('✅ Login successful:', data.user.email);
      return true;
      
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Login failed';
      setError(message);
      console.error('❌ Login error:', message);
      return false;
    } finally {
      setIsLoading(false);
    }
  }, [saveAuthData]);
  
  const logout = useCallback(async (): Promise<void> => {
    setIsLoading(true);
    
    try {
      // Call logout endpoint (optional, but good practice)
      if (token) {
        await fetch(`${API_BASE_URL}/auth/logout`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`,
          },
        }).catch(() => {
          // Ignore logout API errors
        });
      }
    } finally {
      // Clear local state regardless of API response
      clearStoredAuth();
      setIsLoading(false);
      console.log('👋 Logged out');
    }
  }, [token, clearStoredAuth]);
  
  const register = useCallback(async (data: RegisterData): Promise<boolean> => {
    setIsLoading(true);
    setError(null);
    
    try {
      const response = await fetch(`${API_BASE_URL}/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || errorData.message || 'Registration failed');
      }
      
      const result = await response.json();
      
      // Auto-login after registration if tokens provided
      if (result.access_token && result.user) {
        saveAuthData(
          {
            access_token: result.access_token,
            refresh_token: result.refresh_token || '',
            token_type: result.token_type || 'bearer',
            expires_in: result.expires_in || 3600,
          },
          result.user
        );
      }
      
      return true;
      
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Registration failed';
      setError(message);
      return false;
    } finally {
      setIsLoading(false);
    }
  }, [saveAuthData]);
  
  const refreshAccessToken = useCallback(async (): Promise<boolean> => {
    const currentRefreshToken = refreshToken || storage.get(REFRESH_TOKEN_KEY);
    
    if (!currentRefreshToken) {
      clearStoredAuth();
      return false;
    }
    
    try {
      const response = await fetch(`${API_BASE_URL}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: currentRefreshToken }),
      });
      
      if (!response.ok) {
        throw new Error('Token refresh failed');
      }
      
      const data = await response.json();
      
      // Update tokens
      const expiryTime = Date.now() + (data.expires_in || 3600) * 1000;
      
      storage.set(TOKEN_KEY, data.access_token);
      storage.set(TOKEN_EXPIRY_KEY, expiryTime.toString());
      
      if (data.refresh_token) {
        storage.set(REFRESH_TOKEN_KEY, data.refresh_token);
        setRefreshToken(data.refresh_token);
      }
      
      setToken(data.access_token);
      
      // Update user if provided
      if (data.user) {
        storage.setJSON(USER_KEY, data.user);
        setUser(data.user);
      }
      
      // Schedule next refresh
      const refreshDelay = (data.expires_in || 3600) * 1000 - REFRESH_THRESHOLD_MS;
      if (refreshDelay > 0) {
        setTimeout(() => refreshAccessToken(), refreshDelay);
      }
      
      console.log('🔄 Token refreshed');
      return true;
      
    } catch (e) {
      console.error('Token refresh failed:', e);
      clearStoredAuth();
      return false;
    }
  }, [refreshToken, clearStoredAuth]);
  
  // ===========================================================================
  // SSO ACTIONS
  // ===========================================================================
  
  const loginWithSSO = useCallback((
    provider: 'google' | 'microsoft' | 'saml',
    orgId?: string
  ): void => {
    const params = new URLSearchParams({
      provider,
      redirect_uri: `${window.location.origin}/auth/callback`,
    });
    
    if (orgId) {
      params.set('org_id', orgId);
    }
    
    // Redirect to SSO endpoint
    window.location.href = `${API_BASE_URL}/auth/sso/authorize?${params.toString()}`;
  }, []);
  
  const handleSSOCallback = useCallback(async (params: URLSearchParams): Promise<boolean> => {
    setIsLoading(true);
    setError(null);
    
    try {
      const code = params.get('code');
      const state = params.get('state');
      const errorParam = params.get('error');
      
      if (errorParam) {
        throw new Error(params.get('error_description') || 'SSO authentication failed');
      }
      
      if (!code) {
        throw new Error('No authorization code received');
      }
      
      const response = await fetch(`${API_BASE_URL}/auth/sso/callback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code, state }),
      });
      
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'SSO callback failed');
      }
      
      const data = await response.json();
      
      saveAuthData(
        {
          access_token: data.access_token,
          refresh_token: data.refresh_token || '',
          token_type: data.token_type || 'bearer',
          expires_in: data.expires_in || 3600,
        },
        data.user
      );
      
      return true;
      
    } catch (e) {
      const message = e instanceof Error ? e.message : 'SSO authentication failed';
      setError(message);
      return false;
    } finally {
      setIsLoading(false);
    }
  }, [saveAuthData]);
  
  // ===========================================================================
  // USER ACTIONS
  // ===========================================================================
  
  const updateProfile = useCallback(async (data: Partial<User>): Promise<boolean> => {
    setError(null);
    
    try {
      const response = await apiRequest('/auth/me', {
        method: 'PATCH',
        body: JSON.stringify(data),
      });
      
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Failed to update profile');
      }
      
      const updatedUser = await response.json();
      
      setUser(prev => prev ? { ...prev, ...updatedUser } : null);
      storage.setJSON(USER_KEY, { ...user, ...updatedUser });
      
      return true;
      
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Failed to update profile';
      setError(message);
      return false;
    }
  }, [apiRequest, user]);
  
  const changePassword = useCallback(async (
    oldPassword: string,
    newPassword: string
  ): Promise<boolean> => {
    setError(null);
    
    try {
      const response = await apiRequest('/auth/change-password', {
        method: 'POST',
        body: JSON.stringify({ old_password: oldPassword, new_password: newPassword }),
      });
      
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Failed to change password');
      }
      
      return true;
      
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Failed to change password';
      setError(message);
      return false;
    }
  }, [apiRequest]);
  
  // ===========================================================================
  // UTILITY FUNCTIONS
  // ===========================================================================
  
  const clearError = useCallback(() => {
    setError(null);
  }, []);
  
  const hasPermission = useCallback((permission: string): boolean => {
    if (!user) return false;
    
    // Admin has all permissions
    if (user.role === 'admin') return true;
    
    // Check specific permissions
    return user.permissions?.includes(permission) ?? false;
  }, [user]);
  
  const hasRole = useCallback((role: string | string[]): boolean => {
    if (!user) return false;
    
    const roles = Array.isArray(role) ? role : [role];
    return roles.includes(user.role);
  }, [user]);
  
  // ===========================================================================
  // CONTEXT VALUE
  // ===========================================================================
  
  const contextValue = useMemo<AuthContextType>(() => ({
    // State
    user,
    token,
    refreshToken,
    isAuthenticated,
    isLoading,
    error,
    
    // Auth actions
    login,
    logout,
    register,
    refreshAccessToken,
    
    // SSO actions
    loginWithSSO,
    handleSSOCallback,
    
    // User actions
    updateProfile,
    changePassword,
    
    // Utility
    clearError,
    hasPermission,
    hasRole,
  }), [
    user,
    token,
    refreshToken,
    isAuthenticated,
    isLoading,
    error,
    login,
    logout,
    register,
    refreshAccessToken,
    loginWithSSO,
    handleSSOCallback,
    updateProfile,
    changePassword,
    clearError,
    hasPermission,
    hasRole,
  ]);
  
  return (
    <AuthContext.Provider value={contextValue}>
      {children}
    </AuthContext.Provider>
  );
}

// =============================================================================
// HOOKS
// =============================================================================

/**
 * Hook to access auth context
 */
export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  
  return context;
}

/**
 * Hook to require authentication
 * Redirects to login if not authenticated
 */
export function useRequireAuth(redirectTo: string = '/login'): AuthContextType {
  const auth = useAuth();
  
  useEffect(() => {
    if (!auth.isLoading && !auth.isAuthenticated) {
      // Store current location for redirect after login
      sessionStorage.setItem('auth_redirect', window.location.pathname);
      window.location.href = redirectTo;
    }
  }, [auth.isLoading, auth.isAuthenticated, redirectTo]);
  
  return auth;
}

/**
 * Hook to check permissions
 */
export function usePermission(permission: string): boolean {
  const { hasPermission } = useAuth();
  return hasPermission(permission);
}

/**
 * Hook to check roles
 */
export function useRole(role: string | string[]): boolean {
  const { hasRole } = useAuth();
  return hasRole(role);
}

// =============================================================================
// EXPORTS
// =============================================================================

export default AuthContext;
