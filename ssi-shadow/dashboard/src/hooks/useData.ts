// ============================================================================
// S.S.I. SHADOW Dashboard - Data Hooks
// ============================================================================

import { useState, useEffect, useCallback } from 'react';
import {
  OverviewMetrics,
  PlatformStatus,
  TrustScoreMetrics,
  MLPredictionsOverview,
  BidMetrics,
  RecentEvent,
  FunnelMetrics,
  SystemConfig,
  TimeSeriesPoint,
} from '../types';

// ============================================================================
// Configuration
// ============================================================================

const API_BASE_URL = import.meta.env.VITE_API_URL || 'https://ssi-shadow.workers.dev';

// ============================================================================
// Generic Fetch Hook
// ============================================================================

interface UseFetchResult<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

function useFetch<T>(endpoint: string, refreshInterval?: number): UseFetchResult<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const response = await fetch(`${API_BASE_URL}${endpoint}`);
      
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      
      const result = await response.json();
      setData(result.data || result);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  }, [endpoint]);

  useEffect(() => {
    fetchData();
    
    if (refreshInterval) {
      const interval = setInterval(fetchData, refreshInterval);
      return () => clearInterval(interval);
    }
  }, [fetchData, refreshInterval]);

  return { data, loading, error, refetch: fetchData };
}

// ============================================================================
// Overview Metrics Hook
// ============================================================================

export function useOverviewMetrics(): UseFetchResult<OverviewMetrics> {
  return useFetch<OverviewMetrics>('/api/dashboard/overview', 30000); // 30s refresh
}

// Mock data for development
export function useMockOverviewMetrics(): UseFetchResult<OverviewMetrics> {
  const [data] = useState<OverviewMetrics>({
    events_today: 45892,
    events_change: 12.5,
    unique_users_today: 12847,
    users_change: 8.3,
    revenue_today: 28459.90,
    revenue_change: 15.2,
    conversion_rate: 3.42,
    conversion_change: 0.8,
    avg_trust_score: 0.78,
    bot_block_rate: 18.5,
  });

  return { data, loading: false, error: null, refetch: () => {} };
}

// ============================================================================
// Platform Status Hook
// ============================================================================

export function usePlatformStatus(): UseFetchResult<PlatformStatus[]> {
  return useFetch<PlatformStatus[]>('/api/dashboard/platforms', 10000); // 10s refresh
}

export function useMockPlatformStatus(): UseFetchResult<PlatformStatus[]> {
  const [data] = useState<PlatformStatus[]>([
    {
      platform: 'meta',
      enabled: true,
      status: 'healthy',
      events_sent: 42156,
      success_rate: 99.8,
      avg_latency_ms: 124,
      last_event_at: new Date().toISOString(),
      errors_24h: 12,
    },
    {
      platform: 'tiktok',
      enabled: true,
      status: 'healthy',
      events_sent: 38924,
      success_rate: 99.5,
      avg_latency_ms: 156,
      last_event_at: new Date().toISOString(),
      errors_24h: 24,
    },
    {
      platform: 'google',
      enabled: true,
      status: 'healthy',
      events_sent: 41283,
      success_rate: 99.9,
      avg_latency_ms: 98,
      last_event_at: new Date().toISOString(),
      errors_24h: 5,
    },
    {
      platform: 'bigquery',
      enabled: true,
      status: 'healthy',
      events_sent: 45892,
      success_rate: 100,
      avg_latency_ms: 45,
      last_event_at: new Date().toISOString(),
      errors_24h: 0,
    },
  ]);

  return { data, loading: false, error: null, refetch: () => {} };
}

// ============================================================================
// Trust Score Metrics Hook
// ============================================================================

export function useTrustScoreMetrics(): UseFetchResult<TrustScoreMetrics> {
  return useFetch<TrustScoreMetrics>('/api/dashboard/trust-score', 60000);
}

export function useMockTrustScoreMetrics(): UseFetchResult<TrustScoreMetrics> {
  const [data] = useState<TrustScoreMetrics>({
    distribution: [
      { range: '0.0-0.2', count: 2845, percentage: 6.2 },
      { range: '0.2-0.4', count: 5612, percentage: 12.2 },
      { range: '0.4-0.6', count: 8923, percentage: 19.4 },
      { range: '0.6-0.8', count: 15847, percentage: 34.5 },
      { range: '0.8-1.0', count: 12665, percentage: 27.7 },
    ],
    actions: {
      allow: 37435,
      challenge: 5612,
      block: 2845,
    },
    avg_score: 0.78,
    blocked_rate: 6.2,
    top_block_reasons: [
      { reason: 'Bot User-Agent', count: 1245 },
      { reason: 'Datacenter IP', count: 892 },
      { reason: 'Rate Limit Exceeded', count: 456 },
      { reason: 'Headless Browser', count: 252 },
    ],
  });

  return { data, loading: false, error: null, refetch: () => {} };
}

// ============================================================================
// ML Predictions Hook
// ============================================================================

export function useMLPredictions(): UseFetchResult<MLPredictionsOverview> {
  return useFetch<MLPredictionsOverview>('/api/dashboard/ml-predictions', 300000);
}

export function useMockMLPredictions(): UseFetchResult<MLPredictionsOverview> {
  const [data] = useState<MLPredictionsOverview>({
    ltv: {
      vip: { count: 245, total_ltv: 245000, avg_ltv: 1000 },
      high: { count: 1823, total_ltv: 546900, avg_ltv: 300 },
      medium: { count: 4562, total_ltv: 456200, avg_ltv: 100 },
      low: { count: 6217, total_ltv: 124340, avg_ltv: 20 },
    },
    churn: {
      critical: 156,
      high: 423,
      medium: 1245,
      low: 10023,
    },
    propensity: {
      very_high: 892,
      high: 2156,
      medium: 4523,
      low: 3245,
      very_low: 2031,
    },
    last_updated: new Date().toISOString(),
  });

  return { data, loading: false, error: null, refetch: () => {} };
}

// ============================================================================
// Bid Metrics Hook
// ============================================================================

export function useBidMetrics(): UseFetchResult<BidMetrics> {
  return useFetch<BidMetrics>('/api/dashboard/bid-metrics', 60000);
}

export function useMockBidMetrics(): UseFetchResult<BidMetrics> {
  const [data] = useState<BidMetrics>({
    avg_multiplier: 1.15,
    strategy_distribution: {
      aggressive: 892,
      retention: 423,
      acquisition: 1567,
      nurture: 4523,
      conservative: 3245,
      exclude: 2845,
    },
    avg_multiplier_by_strategy: {
      aggressive: 1.65,
      retention: 1.45,
      acquisition: 1.25,
      nurture: 1.05,
      conservative: 0.85,
      exclude: 0,
    },
    recommendations_today: 45892,
  });

  return { data, loading: false, error: null, refetch: () => {} };
}

// ============================================================================
// Recent Events Hook
// ============================================================================

export function useRecentEvents(limit: number = 10): UseFetchResult<RecentEvent[]> {
  return useFetch<RecentEvent[]>(`/api/dashboard/recent-events?limit=${limit}`, 5000);
}

export function useMockRecentEvents(): UseFetchResult<RecentEvent[]> {
  const [data] = useState<RecentEvent[]>(
    Array.from({ length: 10 }, (_, i) => ({
      event_id: `evt_${Date.now()}_${i}`,
      event_name: ['PageView', 'ViewContent', 'AddToCart', 'Purchase'][i % 4],
      ssi_id: `ssi_${Math.random().toString(36).substr(2, 9)}`,
      timestamp: new Date(Date.now() - i * 60000).toISOString(),
      value: i % 4 === 3 ? Math.random() * 500 : undefined,
      trust_score: 0.5 + Math.random() * 0.5,
      trust_action: Math.random() > 0.1 ? 'allow' : 'block',
      platforms: {
        meta: true,
        tiktok: true,
        google: true,
        bigquery: true,
      },
      processing_time_ms: 50 + Math.random() * 150,
    }))
  );

  return { data, loading: false, error: null, refetch: () => {} };
}

// ============================================================================
// Funnel Metrics Hook
// ============================================================================

export function useFunnelMetrics(): UseFetchResult<FunnelMetrics> {
  return useFetch<FunnelMetrics>('/api/dashboard/funnel', 60000);
}

export function useMockFunnelMetrics(): UseFetchResult<FunnelMetrics> {
  const [data] = useState<FunnelMetrics>({
    pageviews: 45892,
    view_content: 28456,
    add_to_cart: 8923,
    initiate_checkout: 4562,
    purchase: 1567,
    conversion_rates: {
      view_to_cart: 31.4,
      cart_to_checkout: 51.1,
      checkout_to_purchase: 34.4,
      overall: 3.42,
    },
  });

  return { data, loading: false, error: null, refetch: () => {} };
}

// ============================================================================
// Time Series Hook
// ============================================================================

export function useEventsTimeSeries(
  period: 'hour' | 'day' | 'week' = 'day'
): UseFetchResult<TimeSeriesPoint[]> {
  return useFetch<TimeSeriesPoint[]>(`/api/dashboard/events-timeseries?period=${period}`, 60000);
}

export function useMockEventsTimeSeries(): UseFetchResult<TimeSeriesPoint[]> {
  const [data] = useState<TimeSeriesPoint[]>(
    Array.from({ length: 24 }, (_, i) => ({
      timestamp: new Date(Date.now() - (23 - i) * 3600000).toISOString(),
      value: 1000 + Math.random() * 2000,
    }))
  );

  return { data, loading: false, error: null, refetch: () => {} };
}

// ============================================================================
// System Config Hook
// ============================================================================

export function useSystemConfig(): UseFetchResult<SystemConfig> {
  return useFetch<SystemConfig>('/api/config', 300000);
}

export function useMockSystemConfig(): UseFetchResult<SystemConfig> {
  const [data] = useState<SystemConfig>({
    platforms: {
      meta: { enabled: true, pixel_id: '1234567890', test_mode: false },
      tiktok: { enabled: true, pixel_id: 'ABCDEFGH' },
      google: { enabled: true, measurement_id: 'G-XXXXXXXX' },
      bigquery: { enabled: true, project_id: 'my-project', dataset: 'ssi_shadow' },
    },
    trust_score: {
      threshold: 0.3,
      rate_limit_enabled: true,
    },
    bid_optimization: {
      min_multiplier: 0.5,
      max_multiplier: 2.0,
    },
  });

  return { data, loading: false, error: null, refetch: () => {} };
}
