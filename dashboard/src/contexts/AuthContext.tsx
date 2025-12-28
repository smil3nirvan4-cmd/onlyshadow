import React, { createContext, useContext, useState, useEffect } from 'react';

interface User {
  id: string;
  email: string;
  name: string;
  role: string;
}

interface AuthContextType {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (credentials: any) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    // Simulação de check de sessão para evitar erros no build
    const token = localStorage.getItem('shadow_token');
    if (token) {
        setUser({ id: '1', email: 'admin@shadow.system', name: 'Admin', role: 'admin' });
    }
    setIsLoading(false);
  }, []);

  const login = async (credentials: any) => {
    setIsLoading(true);
    try {
      // Login simulado para Mock Mode
      console.log('Login attempt:', credentials);
      localStorage.setItem('shadow_token', 'mock-token');
      setUser({ id: '1', email: credentials.email, name: 'Admin', role: 'admin' });
    } catch (error) {
      console.error(error);
    } finally {
      setIsLoading(false);
    }
  };

  const logout = () => {
    localStorage.removeItem('shadow_token');
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, isAuthenticated: !!user, isLoading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
