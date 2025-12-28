// ============================================================================
// S.S.I. SHADOW Dashboard - Chart Components
// ============================================================================

import React from 'react';
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  Funnel,
  FunnelChart,
  LabelList,
} from 'recharts';
import { Card } from './ui';
import { TimeSeriesPoint, FunnelMetrics, TrustScoreDistribution } from '../types';

// ============================================================================
// Color Palette
// ============================================================================

const COLORS = {
  primary: '#3B82F6',
  secondary: '#8B5CF6',
  success: '#10B981',
  warning: '#F59E0B',
  danger: '#EF4444',
  info: '#06B6D4',
  gray: '#6B7280',
};

const PIE_COLORS = ['#3B82F6', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6', '#06B6D4'];

// ============================================================================
// Events Line Chart
// ============================================================================

interface EventsChartProps {
  data: TimeSeriesPoint[];
  title?: string;
}

export function EventsLineChart({ data, title = 'Eventos por Hora' }: EventsChartProps) {
  const formattedData = data.map((point) => ({
    time: new Date(point.timestamp).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }),
    value: point.value,
  }));

  return (
    <Card className="p-6">
      <h3 className="text-lg font-semibold text-gray-900 mb-4">{title}</h3>
      <ResponsiveContainer width="100%" height={300}>
        <AreaChart data={formattedData}>
          <defs>
            <linearGradient id="colorValue" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={COLORS.primary} stopOpacity={0.3} />
              <stop offset="95%" stopColor={COLORS.primary} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
          <XAxis 
            dataKey="time" 
            stroke="#9CA3AF"
            fontSize={12}
            tickLine={false}
          />
          <YAxis 
            stroke="#9CA3AF"
            fontSize={12}
            tickLine={false}
            tickFormatter={(value) => value.toLocaleString('pt-BR')}
          />
          <Tooltip 
            contentStyle={{ 
              backgroundColor: 'white',
              border: '1px solid #E5E7EB',
              borderRadius: '8px',
              boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)'
            }}
            formatter={(value: number) => [value.toLocaleString('pt-BR'), 'Eventos']}
          />
          <Area
            type="monotone"
            dataKey="value"
            stroke={COLORS.primary}
            strokeWidth={2}
            fill="url(#colorValue)"
          />
        </AreaChart>
      </ResponsiveContainer>
    </Card>
  );
}

// ============================================================================
// Platform Comparison Bar Chart
// ============================================================================

interface PlatformComparisonProps {
  data: {
    platform: string;
    events: number;
    successRate: number;
  }[];
}

export function PlatformComparisonChart({ data }: PlatformComparisonProps) {
  return (
    <Card className="p-6">
      <h3 className="text-lg font-semibold text-gray-900 mb-4">Eventos por Plataforma</h3>
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={data} layout="vertical">
          <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
          <XAxis type="number" stroke="#9CA3AF" fontSize={12} />
          <YAxis 
            dataKey="platform" 
            type="category" 
            stroke="#9CA3AF" 
            fontSize={12}
            width={80}
          />
          <Tooltip
            contentStyle={{ 
              backgroundColor: 'white',
              border: '1px solid #E5E7EB',
              borderRadius: '8px'
            }}
            formatter={(value: number) => [value.toLocaleString('pt-BR'), 'Eventos']}
          />
          <Bar dataKey="events" fill={COLORS.primary} radius={[0, 4, 4, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </Card>
  );
}

// ============================================================================
// Trust Score Distribution Chart
// ============================================================================

interface TrustScoreChartProps {
  distribution: TrustScoreDistribution[];
}

export function TrustScoreDistributionChart({ distribution }: TrustScoreChartProps) {
  const getBarColor = (range: string) => {
    if (range.startsWith('0.8')) return COLORS.success;
    if (range.startsWith('0.6')) return COLORS.info;
    if (range.startsWith('0.4')) return COLORS.warning;
    if (range.startsWith('0.2')) return COLORS.warning;
    return COLORS.danger;
  };

  return (
    <Card className="p-6">
      <h3 className="text-lg font-semibold text-gray-900 mb-4">Distribuição Trust Score</h3>
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={distribution}>
          <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
          <XAxis dataKey="range" stroke="#9CA3AF" fontSize={12} />
          <YAxis stroke="#9CA3AF" fontSize={12} tickFormatter={(v) => `${v}%`} />
          <Tooltip
            contentStyle={{ 
              backgroundColor: 'white',
              border: '1px solid #E5E7EB',
              borderRadius: '8px'
            }}
            formatter={(value: number) => [`${value.toFixed(1)}%`, 'Porcentagem']}
          />
          <Bar dataKey="percentage" radius={[4, 4, 0, 0]}>
            {distribution.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={getBarColor(entry.range)} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </Card>
  );
}

// ============================================================================
// LTV Segments Pie Chart
// ============================================================================

interface LTVPieChartProps {
  data: {
    name: string;
    value: number;
    total_ltv: number;
  }[];
}

export function LTVSegmentsPieChart({ data }: LTVPieChartProps) {
  const SEGMENT_COLORS = {
    VIP: '#8B5CF6',
    High: '#3B82F6',
    Medium: '#10B981',
    Low: '#9CA3AF',
  };

  return (
    <Card className="p-6">
      <h3 className="text-lg font-semibold text-gray-900 mb-4">Segmentos LTV</h3>
      <ResponsiveContainer width="100%" height={300}>
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="50%"
            innerRadius={60}
            outerRadius={100}
            paddingAngle={2}
            dataKey="value"
            label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
          >
            {data.map((entry, index) => (
              <Cell 
                key={`cell-${index}`} 
                fill={(SEGMENT_COLORS as any)[entry.name] || PIE_COLORS[index % PIE_COLORS.length]} 
              />
            ))}
          </Pie>
          <Tooltip
            contentStyle={{ 
              backgroundColor: 'white',
              border: '1px solid #E5E7EB',
              borderRadius: '8px'
            }}
            formatter={(value: number, name: string, props: any) => [
              `${value.toLocaleString('pt-BR')} usuários | R$ ${props.payload.total_ltv.toLocaleString('pt-BR')}`,
              name
            ]}
          />
        </PieChart>
      </ResponsiveContainer>
    </Card>
  );
}

// ============================================================================
// Funnel Chart
// ============================================================================

interface FunnelChartProps {
  metrics: FunnelMetrics;
}

export function ConversionFunnelChart({ metrics }: FunnelChartProps) {
  const data = [
    { name: 'PageViews', value: metrics.pageviews, fill: COLORS.primary },
    { name: 'ViewContent', value: metrics.view_content, fill: COLORS.info },
    { name: 'AddToCart', value: metrics.add_to_cart, fill: COLORS.warning },
    { name: 'Checkout', value: metrics.initiate_checkout, fill: COLORS.secondary },
    { name: 'Purchase', value: metrics.purchase, fill: COLORS.success },
  ];

  return (
    <Card className="p-6">
      <h3 className="text-lg font-semibold text-gray-900 mb-4">Funil de Conversão</h3>
      <ResponsiveContainer width="100%" height={400}>
        <FunnelChart>
          <Tooltip
            contentStyle={{ 
              backgroundColor: 'white',
              border: '1px solid #E5E7EB',
              borderRadius: '8px'
            }}
            formatter={(value: number) => [value.toLocaleString('pt-BR'), 'Eventos']}
          />
          <Funnel
            dataKey="value"
            data={data}
            isAnimationActive
          >
            <LabelList
              position="right"
              fill="#374151"
              stroke="none"
              dataKey="name"
            />
            <LabelList
              position="center"
              fill="#fff"
              stroke="none"
              dataKey={(entry: any) => entry.value.toLocaleString('pt-BR')}
            />
          </Funnel>
        </FunnelChart>
      </ResponsiveContainer>
      
      {/* Conversion Rates */}
      <div className="grid grid-cols-4 gap-4 mt-4 pt-4 border-t">
        <div className="text-center">
          <p className="text-sm text-gray-500">View → Cart</p>
          <p className="text-lg font-semibold text-gray-900">
            {metrics.conversion_rates.view_to_cart.toFixed(1)}%
          </p>
        </div>
        <div className="text-center">
          <p className="text-sm text-gray-500">Cart → Checkout</p>
          <p className="text-lg font-semibold text-gray-900">
            {metrics.conversion_rates.cart_to_checkout.toFixed(1)}%
          </p>
        </div>
        <div className="text-center">
          <p className="text-sm text-gray-500">Checkout → Purchase</p>
          <p className="text-lg font-semibold text-gray-900">
            {metrics.conversion_rates.checkout_to_purchase.toFixed(1)}%
          </p>
        </div>
        <div className="text-center">
          <p className="text-sm text-gray-500">Overall</p>
          <p className="text-lg font-semibold text-green-600">
            {metrics.conversion_rates.overall.toFixed(2)}%
          </p>
        </div>
      </div>
    </Card>
  );
}

// ============================================================================
// Bid Strategy Distribution Chart
// ============================================================================

interface BidStrategyChartProps {
  distribution: Record<string, number>;
}

export function BidStrategyChart({ distribution }: BidStrategyChartProps) {
  const STRATEGY_COLORS: Record<string, string> = {
    aggressive: '#EF4444',
    retention: '#F59E0B',
    acquisition: '#3B82F6',
    nurture: '#10B981',
    conservative: '#6B7280',
    exclude: '#1F2937',
  };

  const data = Object.entries(distribution).map(([name, value]) => ({
    name: name.charAt(0).toUpperCase() + name.slice(1),
    value,
    fill: STRATEGY_COLORS[name] || COLORS.gray,
  }));

  return (
    <Card className="p-6">
      <h3 className="text-lg font-semibold text-gray-900 mb-4">Estratégias de Lance</h3>
      <ResponsiveContainer width="100%" height={300}>
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="50%"
            outerRadius={100}
            dataKey="value"
            label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
          >
            {data.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={entry.fill} />
            ))}
          </Pie>
          <Tooltip
            contentStyle={{ 
              backgroundColor: 'white',
              border: '1px solid #E5E7EB',
              borderRadius: '8px'
            }}
            formatter={(value: number) => [value.toLocaleString('pt-BR'), 'Recomendações']}
          />
          <Legend />
        </PieChart>
      </ResponsiveContainer>
    </Card>
  );
}

// ============================================================================
// Churn Risk Chart
// ============================================================================

interface ChurnRiskChartProps {
  data: {
    critical: number;
    high: number;
    medium: number;
    low: number;
  };
}

export function ChurnRiskChart({ data }: ChurnRiskChartProps) {
  const chartData = [
    { name: 'Critical', value: data.critical, fill: '#EF4444' },
    { name: 'High', value: data.high, fill: '#F59E0B' },
    { name: 'Medium', value: data.medium, fill: '#3B82F6' },
    { name: 'Low', value: data.low, fill: '#10B981' },
  ];

  return (
    <Card className="p-6">
      <h3 className="text-lg font-semibold text-gray-900 mb-4">Risco de Churn</h3>
      <ResponsiveContainer width="100%" height={250}>
        <BarChart data={chartData} layout="vertical">
          <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
          <XAxis type="number" stroke="#9CA3AF" fontSize={12} />
          <YAxis dataKey="name" type="category" stroke="#9CA3AF" fontSize={12} width={60} />
          <Tooltip
            contentStyle={{ 
              backgroundColor: 'white',
              border: '1px solid #E5E7EB',
              borderRadius: '8px'
            }}
            formatter={(value: number) => [value.toLocaleString('pt-BR'), 'Usuários']}
          />
          <Bar dataKey="value" radius={[0, 4, 4, 0]}>
            {chartData.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={entry.fill} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </Card>
  );
}

// ============================================================================
// Multi-Line Chart (for comparing platforms)
// ============================================================================

interface MultiLineChartProps {
  data: {
    time: string;
    meta: number;
    tiktok: number;
    google: number;
  }[];
}

export function PlatformTimeSeriesChart({ data }: MultiLineChartProps) {
  return (
    <Card className="p-6">
      <h3 className="text-lg font-semibold text-gray-900 mb-4">Eventos por Plataforma</h3>
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
          <XAxis dataKey="time" stroke="#9CA3AF" fontSize={12} />
          <YAxis stroke="#9CA3AF" fontSize={12} />
          <Tooltip
            contentStyle={{ 
              backgroundColor: 'white',
              border: '1px solid #E5E7EB',
              borderRadius: '8px'
            }}
          />
          <Legend />
          <Line type="monotone" dataKey="meta" stroke="#3B82F6" strokeWidth={2} dot={false} />
          <Line type="monotone" dataKey="tiktok" stroke="#000000" strokeWidth={2} dot={false} />
          <Line type="monotone" dataKey="google" stroke="#EA4335" strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </Card>
  );
}
