import { useState } from 'react';
import { Save, User, Bell, Shield, Database, Key } from 'lucide-react';

export default function Settings() {
  const [activeTab, setActiveTab] = useState('profile');
  
  const tabs = [
    { id: 'profile', label: 'Perfil', icon: User },
    { id: 'notifications', label: 'Notificações', icon: Bell },
    { id: 'security', label: 'Segurança', icon: Shield },
    { id: 'integrations', label: 'Integrações', icon: Database },
    { id: 'api', label: 'API Keys', icon: Key },
  ];

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Configurações</h1>
        <button className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-white transition-colors">
          <Save size={18} />
          Salvar Alterações
        </button>
      </div>
      
      <div className="flex gap-6">
        <nav className="w-64 space-y-1">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${
                activeTab === tab.id
                  ? 'bg-blue-600 text-white'
                  : 'text-gray-400 hover:bg-gray-800 hover:text-white'
              }`}
            >
              <tab.icon size={18} />
              {tab.label}
            </button>
          ))}
        </nav>
        
        <div className="flex-1 bg-gray-800/50 rounded-xl p-6 border border-gray-700">
          {activeTab === 'profile' && <ProfileSettings />}
          {activeTab === 'notifications' && <NotificationSettings />}
          {activeTab === 'security' && <SecuritySettings />}
          {activeTab === 'integrations' && <IntegrationSettings />}
          {activeTab === 'api' && <ApiSettings />}
        </div>
      </div>
    </div>
  );
}

function ProfileSettings() {
  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold text-white">Informações do Perfil</h2>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm text-gray-400 mb-2">Nome</label>
          <input type="text" className="w-full px-4 py-2 bg-gray-900 border border-gray-700 rounded-lg text-white" defaultValue="Admin" />
        </div>
        <div>
          <label className="block text-sm text-gray-400 mb-2">Email</label>
          <input type="email" className="w-full px-4 py-2 bg-gray-900 border border-gray-700 rounded-lg text-white" defaultValue="admin@shadow.system" />
        </div>
        <div>
          <label className="block text-sm text-gray-400 mb-2">Empresa</label>
          <input type="text" className="w-full px-4 py-2 bg-gray-900 border border-gray-700 rounded-lg text-white" defaultValue="S.S.I. Shadow" />
        </div>
        <div>
          <label className="block text-sm text-gray-400 mb-2">Cargo</label>
          <input type="text" className="w-full px-4 py-2 bg-gray-900 border border-gray-700 rounded-lg text-white" defaultValue="Administrador" />
        </div>
      </div>
    </div>
  );
}

function NotificationSettings() {
  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold text-white">Preferências de Notificação</h2>
      <div className="space-y-4">
        {['Alertas de Anomalia', 'Relatórios Diários', 'Atualizações de Sistema', 'Alertas de Budget'].map((item) => (
          <label key={item} className="flex items-center justify-between p-4 bg-gray-900 rounded-lg">
            <span className="text-white">{item}</span>
            <input type="checkbox" defaultChecked className="w-5 h-5 accent-blue-600" />
          </label>
        ))}
      </div>
    </div>
  );
}

function SecuritySettings() {
  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold text-white">Segurança da Conta</h2>
      <div className="space-y-4">
        <div>
          <label className="block text-sm text-gray-400 mb-2">Senha Atual</label>
          <input type="password" className="w-full px-4 py-2 bg-gray-900 border border-gray-700 rounded-lg text-white" />
        </div>
        <div>
          <label className="block text-sm text-gray-400 mb-2">Nova Senha</label>
          <input type="password" className="w-full px-4 py-2 bg-gray-900 border border-gray-700 rounded-lg text-white" />
        </div>
        <div>
          <label className="block text-sm text-gray-400 mb-2">Confirmar Nova Senha</label>
          <input type="password" className="w-full px-4 py-2 bg-gray-900 border border-gray-700 rounded-lg text-white" />
        </div>
      </div>
    </div>
  );
}

function IntegrationSettings() {
  const integrations = [
    { name: 'Meta Ads', status: 'connected', color: 'green' },
    { name: 'Google Ads', status: 'connected', color: 'green' },
    { name: 'TikTok Ads', status: 'connected', color: 'green' },
    { name: 'Shopify', status: 'disconnected', color: 'red' },
  ];
  
  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold text-white">Integrações</h2>
      <div className="space-y-3">
        {integrations.map((int) => (
          <div key={int.name} className="flex items-center justify-between p-4 bg-gray-900 rounded-lg">
            <span className="text-white">{int.name}</span>
            <span className={`px-3 py-1 rounded-full text-sm ${int.color === 'green' ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
              {int.status === 'connected' ? 'Conectado' : 'Desconectado'}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function ApiSettings() {
  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold text-white">API Keys</h2>
      <div className="p-4 bg-gray-900 rounded-lg">
        <label className="block text-sm text-gray-400 mb-2">Sua API Key</label>
        <div className="flex gap-2">
          <input type="text" readOnly className="flex-1 px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white font-mono text-sm" value="sk_live_xxxxxxxxxxxxxxxxxxxx" />
          <button className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-white">Copiar</button>
        </div>
      </div>
      <button className="px-4 py-2 bg-red-600 hover:bg-red-700 rounded-lg text-white">Regenerar API Key</button>
    </div>
  );
}
