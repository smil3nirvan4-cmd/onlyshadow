import { Brain, Cpu, Activity, Zap, TrendingUp } from 'lucide-react';

export default function Neural() {
  const metrics = [
    { label: 'Modelos Ativos', value: '12', icon: Brain, color: 'blue' },
    { label: 'Predições/hora', value: '45.2K', icon: Cpu, color: 'green' },
    { label: 'Acurácia Média', value: '94.7%', icon: TrendingUp, color: 'purple' },
    { label: 'Latência Média', value: '23ms', icon: Zap, color: 'yellow' },
  ];

  const models = [
    { name: 'LTV Predictor', status: 'active', accuracy: 96.2, predictions: '12.4K' },
    { name: 'Churn Detection', status: 'active', accuracy: 91.8, predictions: '8.7K' },
    { name: 'Fraud Detector', status: 'active', accuracy: 98.1, predictions: '45.2K' },
    { name: 'Intent Classifier', status: 'training', accuracy: 87.3, predictions: '0' },
    { name: 'Conversion Optimizer', status: 'active', accuracy: 93.5, predictions: '15.8K' },
  ];

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Neural Core</h1>
          <p className="text-gray-400">Centro de Inteligência Artificial e Machine Learning</p>
        </div>
        <button className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded-lg text-white transition-colors">
          <Brain size={18} />
          Treinar Novo Modelo
        </button>
      </div>

      <div className="grid grid-cols-4 gap-4">
        {metrics.map((metric) => (
          <div key={metric.label} className="bg-gray-800/50 rounded-xl p-6 border border-gray-700">
            <div className="flex items-center justify-between mb-4">
              <metric.icon className={`text-${metric.color}-400`} size={24} />
              <Activity size={16} className="text-green-400" />
            </div>
            <p className="text-3xl font-bold text-white">{metric.value}</p>
            <p className="text-gray-400 text-sm">{metric.label}</p>
          </div>
        ))}
      </div>

      <div className="bg-gray-800/50 rounded-xl border border-gray-700">
        <div className="p-4 border-b border-gray-700">
          <h2 className="text-lg font-semibold text-white">Modelos de ML</h2>
        </div>
        <div className="divide-y divide-gray-700">
          {models.map((model) => (
            <div key={model.name} className="p-4 flex items-center justify-between hover:bg-gray-800/50 transition-colors">
              <div className="flex items-center gap-4">
                <div className={`w-3 h-3 rounded-full ${model.status === 'active' ? 'bg-green-400' : 'bg-yellow-400 animate-pulse'}`} />
                <div>
                  <p className="text-white font-medium">{model.name}</p>
                  <p className="text-gray-400 text-sm">{model.status === 'active' ? 'Ativo' : 'Treinando...'}</p>
                </div>
              </div>
              <div className="flex items-center gap-8">
                <div className="text-right">
                  <p className="text-white font-medium">{model.accuracy}%</p>
                  <p className="text-gray-400 text-sm">Acurácia</p>
                </div>
                <div className="text-right">
                  <p className="text-white font-medium">{model.predictions}</p>
                  <p className="text-gray-400 text-sm">Predições/24h</p>
                </div>
                <button className="px-3 py-1 bg-gray-700 hover:bg-gray-600 rounded text-white text-sm">
                  Detalhes
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
