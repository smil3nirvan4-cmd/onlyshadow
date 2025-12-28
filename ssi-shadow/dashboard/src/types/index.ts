// ============================================================================
// S.S.I. SHADOW Dashboard - Types
// ============================================================================

// ============================================================================
// API Response Types
// ============================================================================

export interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
  timestamp: string;
}

// ============================================================================
// Metrics Types
// ============================================================================

export interface OverviewMetrics {
  events_today: number;
  events_change: number; // percentage
  unique_users_today: number;
  users_change: number;
  revenue_today: number;
  revenue_change: number;
  conversion_rate: number;
  conversion_change: number;
  avg_trust_score: number;
  bot_block_rate: number;
}

export interface PlatformStatus {
  platform: 'meta' | 'tiktok' | 'google' | 'bigquery';
  enabled: boolean;
  status: 'healthy' | 'degraded' | 'down';
  events_sent: number;
  success_rate: number;
  avg_latency_ms: number;
  last_event_at: string;
  errors_24h: number;
}

export interface TimeSeriesPoint {
  timestamp: string;
  value: number;
}

export interface EventsTimeSeries {
  total: TimeSeriesPoint[];
  by_platform: {
    meta: TimeSeriesPoint[];
    tiktok: TimeSeriesPoint[];
    google: TimeSeriesPoint[];
  };
}

export interface FunnelMetrics {
  pageviews: number;
  view_content: number;
  add_to_cart: number;
  initiate_checkout: number;
  purchase: number;
  conversion_rates: {
    view_to_cart: number;
    cart_to_checkout: number;
    checkout_to_purchase: number;
    overall: number;
  };
}

// ============================================================================
// Trust Score Types
// ============================================================================

export interface TrustScoreDistribution {
  range: string;
  count: number;
  percentage: number;
}

export interface TrustScoreMetrics {
  distribution: TrustScoreDistribution[];
  actions: {
    allow: number;
    challenge: number;
    block: number;
  };
  avg_score: number;
  blocked_rate: number;
  top_block_reasons: {
    reason: string;
    count: number;
  }[];
}

// ============================================================================
// ML Predictions Types
// ============================================================================

export interface LTVSegments {
  vip: { count: number; total_ltv: number; avg_ltv: number };
  high: { count: number; total_ltv: number; avg_ltv: number };
  medium: { count: number; total_ltv: number; avg_ltv: number };
  low: { count: number; total_ltv: number; avg_ltv: number };
}

export interface ChurnMetrics {
  critical: number;
  high: number;
  medium: number;
  low: number;
  value_at_risk: number;
}

export interface PropensityMetrics {
  very_high: number;
  high: number;
  medium: number;
  low: number;
  very_low: number;
  expected_conversions: number;
}

export interface MLPredictionsOverview {
  ltv: LTVSegments;
  churn: ChurnMetrics;
  propensity: PropensityMetrics;
  last_updated: string;
}

// ============================================================================
// Bid Optimization Types
// ============================================================================

export interface BidStrategyDistribution {
  aggressive: number;
  retention: number;
  acquisition: number;
  nurture: number;
  conservative: number;
  exclude: number;
}

export interface BidMetrics {
  avg_multiplier: number;
  strategy_distribution: BidStrategyDistribution;
  avg_multiplier_by_strategy: Record<string, number>;
  recommendations_today: number;
}

// ============================================================================
// Events Types
// ============================================================================

export interface RecentEvent {
  event_id: string;
  event_name: string;
  ssi_id: string;
  timestamp: string;
  value?: number;
  trust_score: number;
  trust_action: string;
  platforms: {
    meta: boolean;
    tiktok: boolean;
    google: boolean;
    bigquery: boolean;
  };
  processing_time_ms: number;
}

export interface EventsByType {
  event_name: string;
  count: number;
  percentage: number;
}

// ============================================================================
// Configuration Types
// ============================================================================

export interface SystemConfig {
  platforms: {
    meta: { enabled: boolean; pixel_id: string; test_mode: boolean };
    tiktok: { enabled: boolean; pixel_id: string };
    google: { enabled: boolean; measurement_id: string };
    bigquery: { enabled: boolean; project_id: string; dataset: string };
  };
  trust_score: {
    threshold: number;
    rate_limit_enabled: boolean;
  };
  bid_optimization: {
    min_multiplier: number;
    max_multiplier: number;
  };
}

// ============================================================================
// Dashboard State Types
// ============================================================================

export interface DateRange {
  start: Date;
  end: Date;
  preset?: 'today' | '7d' | '30d' | 'custom';
}

export interface DashboardFilters {
  dateRange: DateRange;
  platform?: 'meta' | 'tiktok' | 'google' | 'all';
  eventType?: string;
}

// ============================================================================
// Chart Types
// ============================================================================

export interface ChartDataPoint {
  name: string;
  value: number;
  [key: string]: string | number;
}

export interface PieChartData {
  name: string;
  value: number;
  color: string;
}
