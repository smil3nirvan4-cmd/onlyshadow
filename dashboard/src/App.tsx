// ============================================================================
// S.S.I. SHADOW Dashboard - App Entry
// ============================================================================

import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { Layout } from './components/Layout';
import { Dashboard } from './components/Dashboard';
import { Login } from './components/Login';
import Settings from './pages/Settings';
import Neural from './pages/Neural';

// Componente de Proteção de Rota
const PrivateRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isAuthenticated, isLoading } = useAuth();
  if (isLoading) return <div className="min-h-screen bg-gray-900 flex items-center justify-center text-blue-500">Loading Shadow Protocol...</div>;
  return isAuthenticated ? <>{children}</> : <Navigate to="/login" />;
};

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/" element={
            <PrivateRoute>
              <Layout />
            </PrivateRoute>
          }>
            <Route index element={<Dashboard />} />
            <Route path="ads" element={<div className="p-8 text-white">Ads Engine Module (Coming Soon)</div>} />
            <Route path="tracking" element={<div className="p-8 text-white">Ghost Workers Module (Coming Soon)</div>} />
            <Route path="settings" element={<Settings />} />
            <Route path="neural" element={<Neural />} />
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
};
