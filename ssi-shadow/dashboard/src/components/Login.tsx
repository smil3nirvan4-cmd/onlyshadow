// ============================================================================
// S.S.I. SHADOW Dashboard - Login Component
// ============================================================================

import React, { useState, useEffect, FormEvent } from 'react';
import { useAuth } from '../contexts/AuthContext';

// =============================================================================
// STYLES (Tailwind-like inline)
// =============================================================================

const styles = {
  container: {
    minHeight: '100vh',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    background: 'linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #0f172a 100%)',
    padding: '1rem',
  },
  card: {
    width: '100%',
    maxWidth: '420px',
    backgroundColor: '#1e293b',
    borderRadius: '1rem',
    padding: '2rem',
    boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.5)',
    border: '1px solid rgba(255, 255, 255, 0.1)',
  },
  logo: {
    textAlign: 'center' as const,
    marginBottom: '2rem',
  },
  logoText: {
    fontSize: '2rem',
    fontWeight: 'bold',
    background: 'linear-gradient(90deg, #3b82f6, #8b5cf6)',
    WebkitBackgroundClip: 'text',
    WebkitTextFillColor: 'transparent',
    letterSpacing: '0.05em',
  },
  subtitle: {
    color: '#94a3b8',
    fontSize: '0.875rem',
    marginTop: '0.5rem',
  },
  form: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '1.25rem',
  },
  inputGroup: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '0.5rem',
  },
  label: {
    color: '#e2e8f0',
    fontSize: '0.875rem',
    fontWeight: '500',
  },
  input: {
    width: '100%',
    padding: '0.75rem 1rem',
    backgroundColor: '#0f172a',
    border: '1px solid #334155',
    borderRadius: '0.5rem',
    color: '#f1f5f9',
    fontSize: '1rem',
    outline: 'none',
    transition: 'border-color 0.2s, box-shadow 0.2s',
  },
  inputFocus: {
    borderColor: '#3b82f6',
    boxShadow: '0 0 0 3px rgba(59, 130, 246, 0.2)',
  },
  checkboxGroup: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  checkboxLabel: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
    color: '#94a3b8',
    fontSize: '0.875rem',
    cursor: 'pointer',
  },
  checkbox: {
    width: '1rem',
    height: '1rem',
    accentColor: '#3b82f6',
  },
  forgotLink: {
    color: '#3b82f6',
    fontSize: '0.875rem',
    textDecoration: 'none',
    cursor: 'pointer',
  },
  button: {
    width: '100%',
    padding: '0.875rem',
    background: 'linear-gradient(90deg, #3b82f6, #8b5cf6)',
    border: 'none',
    borderRadius: '0.5rem',
    color: '#ffffff',
    fontSize: '1rem',
    fontWeight: '600',
    cursor: 'pointer',
    transition: 'opacity 0.2s, transform 0.2s',
  },
  buttonDisabled: {
    opacity: 0.6,
    cursor: 'not-allowed',
  },
  buttonHover: {
    opacity: 0.9,
    transform: 'translateY(-1px)',
  },
  divider: {
    display: 'flex',
    alignItems: 'center',
    gap: '1rem',
    margin: '1.5rem 0',
  },
  dividerLine: {
    flex: 1,
    height: '1px',
    backgroundColor: '#334155',
  },
  dividerText: {
    color: '#64748b',
    fontSize: '0.75rem',
    textTransform: 'uppercase' as const,
    letterSpacing: '0.05em',
  },
  ssoButtons: {
    display: 'flex',
    gap: '0.75rem',
  },
  ssoButton: {
    flex: 1,
    padding: '0.75rem',
    backgroundColor: '#0f172a',
    border: '1px solid #334155',
    borderRadius: '0.5rem',
    color: '#e2e8f0',
    fontSize: '0.875rem',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '0.5rem',
    cursor: 'pointer',
    transition: 'background-color 0.2s, border-color 0.2s',
  },
  ssoButtonHover: {
    backgroundColor: '#1e293b',
    borderColor: '#475569',
  },
  error: {
    backgroundColor: 'rgba(239, 68, 68, 0.1)',
    border: '1px solid rgba(239, 68, 68, 0.3)',
    borderRadius: '0.5rem',
    padding: '0.75rem 1rem',
    color: '#fca5a5',
    fontSize: '0.875rem',
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
  },
  footer: {
    textAlign: 'center' as const,
    marginTop: '1.5rem',
    color: '#64748b',
    fontSize: '0.875rem',
  },
  footerLink: {
    color: '#3b82f6',
    textDecoration: 'none',
    fontWeight: '500',
    cursor: 'pointer',
  },
  spinner: {
    width: '1.25rem',
    height: '1.25rem',
    border: '2px solid rgba(255, 255, 255, 0.3)',
    borderTopColor: '#ffffff',
    borderRadius: '50%',
    animation: 'spin 0.8s linear infinite',
  },
};

// =============================================================================
// COMPONENT
// =============================================================================

interface LoginPageProps {
  onLoginSuccess?: () => void;
}

export default function LoginPage({ onLoginSuccess }: LoginPageProps) {
  const { login, loginWithSSO, isLoading, error, clearError, isAuthenticated } = useAuth();
  
  // Form state
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [rememberMe, setRememberMe] = useState(true);
  const [focused, setFocused] = useState<string | null>(null);
  const [hovered, setHovered] = useState<string | null>(null);
  
  // Redirect if already authenticated
  useEffect(() => {
    if (isAuthenticated && onLoginSuccess) {
      onLoginSuccess();
    }
  }, [isAuthenticated, onLoginSuccess]);
  
  // Clear error on input change
  useEffect(() => {
    if (error) {
      clearError();
    }
  }, [email, password]);
  
  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    
    if (!email || !password) return;
    
    const success = await login({
      email,
      password,
      remember_me: rememberMe,
    });
    
    if (success && onLoginSuccess) {
      onLoginSuccess();
    }
  };
  
  const handleSSO = (provider: 'google' | 'microsoft') => {
    loginWithSSO(provider);
  };
  
  return (
    <div style={styles.container}>
      {/* Add keyframes for spinner animation */}
      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
        input::placeholder {
          color: #64748b;
        }
        input:-webkit-autofill {
          -webkit-box-shadow: 0 0 0 30px #0f172a inset !important;
          -webkit-text-fill-color: #f1f5f9 !important;
        }
      `}</style>
      
      <div style={styles.card}>
        {/* Logo */}
        <div style={styles.logo}>
          <div style={styles.logoText}>S.S.I. SHADOW</div>
          <div style={styles.subtitle}>Secure Signal Intelligence Platform</div>
        </div>
        
        {/* Error message */}
        {error && (
          <div style={styles.error}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 22C6.477 22 2 17.523 2 12S6.477 2 12 2s10 4.477 10 10-4.477 10-10 10zm-1-7v2h2v-2h-2zm0-8v6h2V7h-2z"/>
            </svg>
            {error}
          </div>
        )}
        
        {/* Login form */}
        <form style={styles.form} onSubmit={handleSubmit}>
          <div style={styles.inputGroup}>
            <label style={styles.label} htmlFor="email">
              Email
            </label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              onFocus={() => setFocused('email')}
              onBlur={() => setFocused(null)}
              placeholder="you@company.com"
              style={{
                ...styles.input,
                ...(focused === 'email' ? styles.inputFocus : {}),
              }}
              required
              autoComplete="email"
              disabled={isLoading}
            />
          </div>
          
          <div style={styles.inputGroup}>
            <label style={styles.label} htmlFor="password">
              Password
            </label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onFocus={() => setFocused('password')}
              onBlur={() => setFocused(null)}
              placeholder="••••••••"
              style={{
                ...styles.input,
                ...(focused === 'password' ? styles.inputFocus : {}),
              }}
              required
              autoComplete="current-password"
              disabled={isLoading}
            />
          </div>
          
          <div style={styles.checkboxGroup}>
            <label style={styles.checkboxLabel}>
              <input
                type="checkbox"
                checked={rememberMe}
                onChange={(e) => setRememberMe(e.target.checked)}
                style={styles.checkbox}
                disabled={isLoading}
              />
              Remember me
            </label>
            <a style={styles.forgotLink} href="/forgot-password">
              Forgot password?
            </a>
          </div>
          
          <button
            type="submit"
            disabled={isLoading || !email || !password}
            onMouseEnter={() => setHovered('submit')}
            onMouseLeave={() => setHovered(null)}
            style={{
              ...styles.button,
              ...(isLoading || !email || !password ? styles.buttonDisabled : {}),
              ...(hovered === 'submit' && !isLoading ? styles.buttonHover : {}),
            }}
          >
            {isLoading ? (
              <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem' }}>
                <span style={styles.spinner}></span>
                Signing in...
              </span>
            ) : (
              'Sign In'
            )}
          </button>
        </form>
        
        {/* Divider */}
        <div style={styles.divider}>
          <div style={styles.dividerLine}></div>
          <span style={styles.dividerText}>or continue with</span>
          <div style={styles.dividerLine}></div>
        </div>
        
        {/* SSO buttons */}
        <div style={styles.ssoButtons}>
          <button
            type="button"
            onClick={() => handleSSO('google')}
            onMouseEnter={() => setHovered('google')}
            onMouseLeave={() => setHovered(null)}
            style={{
              ...styles.ssoButton,
              ...(hovered === 'google' ? styles.ssoButtonHover : {}),
            }}
            disabled={isLoading}
          >
            <svg width="18" height="18" viewBox="0 0 24 24">
              <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
              <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
              <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
              <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
            </svg>
            Google
          </button>
          
          <button
            type="button"
            onClick={() => handleSSO('microsoft')}
            onMouseEnter={() => setHovered('microsoft')}
            onMouseLeave={() => setHovered(null)}
            style={{
              ...styles.ssoButton,
              ...(hovered === 'microsoft' ? styles.ssoButtonHover : {}),
            }}
            disabled={isLoading}
          >
            <svg width="18" height="18" viewBox="0 0 24 24">
              <path fill="#F25022" d="M1 1h10v10H1z"/>
              <path fill="#00A4EF" d="M1 13h10v10H1z"/>
              <path fill="#7FBA00" d="M13 1h10v10H13z"/>
              <path fill="#FFB900" d="M13 13h10v10H13z"/>
            </svg>
            Microsoft
          </button>
        </div>
        
        {/* Footer */}
        <div style={styles.footer}>
          Don't have an account?{' '}
          <a style={styles.footerLink} href="/register">
            Sign up
          </a>
        </div>
      </div>
    </div>
  );
}
