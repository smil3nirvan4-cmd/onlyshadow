// @ts-nocheck

// ============================================================================
// S.S.I. SHADOW Dashboard - Main Dashboard Component
// ============================================================================

import React, { useState } from 'react';
import {
  Card,
  MetricCard,
  StatusBadge,
  ProgressBar,
  Spinner,
  Button,
  Tabs,
  Table,
  Select,
} from './ui';
import {
  EventsLineChart,
  TrustScoreDistributionChart,
  LTVSegmentsPieChart,
  ConversionFunnelChart,
  BidStrategyChart,
  ChurnRiskChart,
  PlatformComparisonChart,
} from './Charts';
import {
  useMockOverviewMetrics,
  useMockPlatformStatus,
  useMockTrustScoreMetrics,
  useMockMLPredictions,
  useMockBidMetrics,
  useMockRecentEvents,
  useMockFunnelMetrics,
  useMockEventsTimeSeries,
} from '../hooks/useData';
import { PlatformStatus, RecentEvent } from '../types';

// ============================================================================
// Icons (inline SVG)
// ============================================================================

const Icons = {
  Events: () => (
    <svg className="w-6 h-6 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
    </svg>
  ),
  Users: () => (
    <svg className="w-6 h-6 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" />
    </svg>
  ),
  Revenue: () => (
    <svg className="w-6 h-6 text-purple-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  ),
  Conversion: () => (
    <svg className="w-6 h-6 text-yellow-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
    </svg>
  ),
  Shield: () => (
    <svg className="w-6 h-6 text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
    </svg>
  ),
  Refresh: () => (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
    </svg>
  ),
};

// ============================================================================
// Platform Card Component
// ============================================================================

interface PlatformCardProps {
  platform: PlatformStatus;
}

function PlatformCard({ platform }: PlatformCardProps) {
  const getPlatformIcon = () => {
    switch (platform.platform) {
      case 'meta':
        return '📘';
      case 'tiktok':
        return '🎵';
      case 'google':
        return '🔍';
      case 'bigquery':
        return '📊';
      default:
        return '📡';
    }
  };

  const getPlatformName = () => {
    switch (platform.platform) {
      case 'meta':
        return 'Meta CAPI';
      case 'tiktok':
        return 'TikTok Events';
      case 'google':
        return 'Google GA4';
      case 'bigquery':
        return 'BigQuery';
      default:
        return platform.platform;
    }
  };

  return (
    <Card className="p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-2xl">{getPlatformIcon()}</span>
          <span className="font-medium text-gray-900">{getPlatformName()}</span>
        </div>
        <StatusBadge status={platform.status} />
      </div>
      
      <div className="space-y-2">
        <div className="flex justify-between text-sm">
          <span className="text-gray-500">Eventos enviados</span>
          <span className="font-medium">{platform.events_sent.toLocaleString('pt-BR')}</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-gray-500">Taxa de sucesso</span>
          <span className="font-medium text-green-600">{platform.success_rate}%</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-gray-500">Latência média</span>
          <span className="font-medium">{platform.avg_latency_ms}ms</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-gray-500">Erros (24h)</span>
          <span className={`font-medium ${platform.errors_24h > 0 ? 'text-red-600' : 'text-gray-600'}`}>
            {platform.errors_24h}
          </span>
        </div>
      </div>
      
      <div className="mt-3 pt-3 border-t">
        <ProgressBar value={platform.success_rate} color="green" size="sm" showLabel={false} />
      </div>
    </Card>
  );
}

// ============================================================================
// Recent Events Table Component
// ============================================================================

interface RecentEventsTableProps {
  events: RecentEvent[];
}

function RecentEventsTable({ events }: RecentEventsTableProps) {
  const columns = [
    {
      key: 'event_name',
      header: 'Evento',
      render: (event: RecentEvent) => (
        <span className="font-medium">{event.event_name}</span>
      ),
    },
    {
      key: 'timestamp',
      header: 'Horário',
      render: (event: RecentEvent) => (
        <span className="text-gray-500">
          {new Date(event.timestamp).toLocaleTimeString('pt-BR')}
        </span>
      ),
    },
    {
      key: 'value',
      header: 'Valor',
      render: (event: RecentEvent) => (
        event.value ? (
          <span className="text-green-600 font-medium">
            R$ {event.value.toFixed(2)}
          </span>
        ) : <span className="text-gray-400">-</span>
      ),
    },
    {
      key: 'trust_score',
      header: 'Trust',
      render: (event: RecentEvent) => (
        <div className="flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full ${
            event.trust_score >= 0.7 ? 'bg-green-500' :
            event.trust_score >= 0.4 ? 'bg-yellow-500' : 'bg-red-500'
          }`} />
          <span>{(event.trust_score * 100).toFixed(0)}%</span>
        </div>
      ),
    },
    {
      key: 'platforms',
      header: 'Plataformas',
      render: (event: RecentEvent) => (
        <div className="flex gap-1">
          {event.platforms.meta && <span title="Meta">📘</span>}
          {event.platforms.tiktok && <span title="TikTok">🎵</span>}
          {event.platforms.google && <span title="Google">🔍</span>}
          {event.platforms.bigquery && <span title="BigQuery">📊</span>}
        </div>
      ),
    },
    {
      key: 'processing_time_ms',
      header: 'Tempo',
      render: (event: RecentEvent) => (
        <span className="text-gray-500">{event.processing_time_ms.toFixed(0)}ms</span>
      ),
    },
  ];

  return (
    <Card>
      <div className="p-4 border-b">
        <h3 className="text-lg font-semibold text-gray-900">Eventos Recentes</h3>
      </div>
      <Table
        columns={columns}
        data={events}
        keyExtractor={(event) => event.event_id}
      />
    </Card>
  );
}

// ============================================================================
// Main Dashboard Component
// ============================================================================

export function Dashboard() {
  const [activeTab, setActiveTab] = useState('overview');
  const [dateRange, setDateRange] = useState('today');
  
  // Data hooks (using mock data for demo)
  const { data: overview } = useMockOverviewMetrics();
  const { data: platforms } = useMockPlatformStatus();
  const { data: trustMetrics } = useMockTrustScoreMetrics();
  const { data: mlPredictions } = useMockMLPredictions();
  const { data: bidMetrics } = useMockBidMetrics();
  const { data: recentEvents } = useMockRecentEvents();
  const { data: funnelMetrics } = useMockFunnelMetrics();
  const { data: eventsTimeSeries } = useMockEventsTimeSeries();

  const tabs = [
    { id: 'overview', label: 'Visão Geral' },
    { id: 'platforms', label: 'Plataformas' },
    { id: 'trust', label: 'Trust Score' },
    { id: 'ml', label: 'ML Predictions' },
    { id: 'funnel', label: 'Funil' },
  ];

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center py-4">
            <div className="flex items-center gap-3">
              <span className="text-2xl">🔮</span>
              <div>
                <h1 className="text-xl font-bold text-gray-900">S.S.I. SHADOW</h1>
                <p className="text-sm text-gray-500">Server-Side Intelligence Dashboard</p>
              </div>
            </div>
            
            <div className="flex items-center gap-4">
              <Select
                value={dateRange}
                onChange={setDateRange}
                options={[
                  { value: 'today', label: 'Hoje' },
                  { value: '7d', label: 'Últimos 7 dias' },
                  { value: '30d', label: 'Últimos 30 dias' },
                ]}
                className="w-40"
              />
              <Button variant="outline" size="sm">
                <Icons.Refresh />
              </Button>
            </div>
          </div>
          
          <Tabs tabs={tabs} activeTab={activeTab} onChange={setActiveTab} />
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {activeTab === 'overview' && overview && (
          <div className="space-y-6">
            {/* Metrics Cards */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              <MetricCard
                title="Eventos Hoje"
                value={overview.events_today}
                change={overview.events_change}
                changeLabel="vs ontem"
                icon={<Icons.Events />}
              />
              <MetricCard
                title="Usuários Únicos"
                value={overview.unique_users_today}
                change={overview.users_change}
                changeLabel="vs ontem"
                icon={<Icons.Users />}
              />
              <MetricCard
                title="Receita Hoje"
                value={overview.revenue_today}
                change={overview.revenue_change}
                changeLabel="vs ontem"
                format="currency"
                icon={<Icons.Revenue />}
              />
              <MetricCard
                title="Taxa de Conversão"
                value={overview.conversion_rate}
                change={overview.conversion_change}
                changeLabel="vs ontem"
                format="percent"
                icon={<Icons.Conversion />}
              />
            </div>

            {/* Platform Status */}
            {platforms && (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                {platforms.map((platform) => (
                  <PlatformCard key={platform.platform} platform={platform} />
                ))}
              </div>
            )}

            {/* Charts Row */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {eventsTimeSeries && (
                <EventsLineChart data={eventsTimeSeries} title="Eventos por Hora (Hoje)" />
              )}
              {trustMetrics && (
                <TrustScoreDistributionChart distribution={trustMetrics.distribution} />
              )}
            </div>

            {/* Recent Events */}
            {recentEvents && <RecentEventsTable events={recentEvents} />}
          </div>
        )}

        {activeTab === 'platforms' && platforms && (
          <div className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              {platforms.map((platform) => (
                <PlatformCard key={platform.platform} platform={platform} />
              ))}
            </div>
            
            <PlatformComparisonChart
              data={platforms.map((p) => ({
                platform: p.platform.charAt(0).toUpperCase() + p.platform.slice(1),
                events: p.events_sent,
                successRate: p.success_rate,
              }))}
            />
          </div>
        )}

        {activeTab === 'trust' && trustMetrics && (
          <div className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <MetricCard
                title="Trust Score Médio"
                value={(trustMetrics.avg_score * 100).toFixed(1) + '%'}
                icon={<Icons.Shield />}
              />
              <MetricCard
                title="Taxa de Bloqueio"
                value={trustMetrics.blocked_rate.toFixed(1) + '%'}
                trend="down"
              />
              <MetricCard
                title="Eventos Bloqueados"
                value={trustMetrics.actions.block}
              />
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <TrustScoreDistributionChart distribution={trustMetrics.distribution} />
              
              <Card className="p-6">
                <h3 className="text-lg font-semibold text-gray-900 mb-4">Top Motivos de Bloqueio</h3>
                <div className="space-y-3">
                  {trustMetrics.top_block_reasons.map((reason, i) => (
                    <div key={i} className="flex items-center justify-between">
                      <span className="text-sm text-gray-600">{reason.reason}</span>
                      <span className="font-medium">{reason.count.toLocaleString('pt-BR')}</span>
                    </div>
                  ))}
                </div>
              </Card>
            </div>
          </div>
        )}

        {activeTab === 'ml' && mlPredictions && bidMetrics && (
          <div className="space-y-6">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <LTVSegmentsPieChart
                data={[
                  { name: 'VIP', value: mlPredictions.ltv.vip.count, total_ltv: mlPredictions.ltv.vip.total_ltv },
                  { name: 'High', value: mlPredictions.ltv.high.count, total_ltv: mlPredictions.ltv.high.total_ltv },
                  { name: 'Medium', value: mlPredictions.ltv.medium.count, total_ltv: mlPredictions.ltv.medium.total_ltv },
                  { name: 'Low', value: mlPredictions.ltv.low.count, total_ltv: mlPredictions.ltv.low.total_ltv },
                ]}
              />
              
              <ChurnRiskChart data={mlPredictions.churn} />
            </div>

            <BidStrategyChart distribution={bidMetrics.strategy_distribution} />

            <Card className="p-6">
              <h3 className="text-lg font-semibold text-gray-900 mb-4">Multipliers por Estratégia</h3>
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
                {Object.entries(bidMetrics.avg_multiplier_by_strategy).map(([strategy, multiplier]) => (
                  <div key={strategy} className="text-center p-4 bg-gray-50 rounded-lg">
                    <p className="text-sm text-gray-500 capitalize">{strategy}</p>
                    <p className="text-xl font-bold text-gray-900">{multiplier.toFixed(2)}x</p>
                  </div>
                ))}
              </div>
            </Card>
          </div>
        )}

        {activeTab === 'funnel' && funnelMetrics && (
          <div className="space-y-6">
            <ConversionFunnelChart metrics={funnelMetrics} />
            
            <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
              <MetricCard title="PageViews" value={funnelMetrics.pageviews} />
              <MetricCard title="View Content" value={funnelMetrics.view_content} />
              <MetricCard title="Add to Cart" value={funnelMetrics.add_to_cart} />
              <MetricCard title="Checkout" value={funnelMetrics.initiate_checkout} />
              <MetricCard title="Purchase" value={funnelMetrics.purchase} />
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

export default Dashboard;
