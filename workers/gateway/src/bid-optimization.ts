/**
 * S.S.I. SHADOW — Bid Optimization Module
 * 
 * Responsabilidades:
 * - Calcular sinais de valor para otimização de leilões
 * - Gerar custom events que influenciam algoritmos de ads
 * - Segmentar visitantes por predicted LTV
 * - Enviar sinais de qualidade para plataformas
 */

// =============================================================================
// TIPOS
// =============================================================================

export interface VisitorSignals {
  ssiId: string;
  trustScore: number;
  ltvScore: number;
  intentScore: number;
  isReturning: boolean;
  deviceType: 'mobile' | 'tablet' | 'desktop';
  trafficSource: 'meta' | 'google' | 'tiktok' | 'organic' | 'direct';
  sessionDepth: number;
  cartValue?: number;
  previousPurchases: number;
  daysFromLastVisit?: number;
}

export interface BidSignal {
  eventName: string;
  value: number;
  currency: string;
  metadata: Record<string, any>;
  priority: 'critical' | 'high' | 'medium' | 'low';
}

export interface LTVSegment {
  tier: 'whale' | 'high' | 'medium' | 'low' | 'unknown';
  multiplier: number;
  description: string;
}

// =============================================================================
// LTV SEGMENTATION
// =============================================================================

/**
 * Segmenta visitante por LTV previsto
 * Usado para value-based bidding
 */
export function segmentByLTV(signals: VisitorSignals): LTVSegment {
  const { ltvScore, previousPurchases, isReturning } = signals;
  
  // Whale: Compradores frequentes com alto LTV
  if (previousPurchases >= 3 && ltvScore >= 0.85) {
    return {
      tier: 'whale',
      multiplier: 3.0,
      description: 'Cliente VIP - alto valor, comprador frequente'
    };
  }
  
  // High: Bom LTV score ou comprador recorrente
  if (ltvScore >= 0.7 || previousPurchases >= 2) {
    return {
      tier: 'high',
      multiplier: 2.0,
      description: 'Cliente de alto valor'
    };
  }
  
  // Medium: LTV moderado ou visitante retornante
  if (ltvScore >= 0.5 || (isReturning && ltvScore >= 0.4)) {
    return {
      tier: 'medium',
      multiplier: 1.5,
      description: 'Cliente de valor médio'
    };
  }
  
  // Low: Baixo LTV mas não descartável
  if (ltvScore >= 0.3) {
    return {
      tier: 'low',
      multiplier: 1.0,
      description: 'Cliente de valor padrão'
    };
  }
  
  // Unknown: Sem dados suficientes
  return {
    tier: 'unknown',
    multiplier: 0.8,
    description: 'Visitante novo sem histórico'
  };
}

// =============================================================================
// BID SIGNALS GENERATOR
// =============================================================================

/**
 * Gera sinais de bid baseados no comportamento do visitante
 * Esses eventos são enviados para as plataformas de ads
 */
export function generateBidSignals(
  signals: VisitorSignals,
  eventContext: {
    eventName: string;
    eventValue?: number;
    contentIds?: string[];
  }
): BidSignal[] {
  const bidSignals: BidSignal[] = [];
  const segment = segmentByLTV(signals);
  
  // 1. SSI_QualifiedVisitor - Visitante com trust score alto
  if (signals.trustScore >= 0.8) {
    const baseValue = eventContext.eventValue || 10;
    bidSignals.push({
      eventName: 'SSI_QualifiedVisitor',
      value: baseValue * 0.1 * segment.multiplier,
      currency: 'BRL',
      metadata: {
        trust_score: signals.trustScore,
        ltv_segment: segment.tier,
        traffic_source: signals.trafficSource
      },
      priority: 'medium'
    });
  }
  
  // 2. SSI_HighIntent - Visitante com alta probabilidade de conversão
  if (signals.intentScore >= 0.85) {
    const baseValue = eventContext.eventValue || signals.cartValue || 50;
    bidSignals.push({
      eventName: 'SSI_HighIntent',
      value: baseValue * 0.3 * segment.multiplier,
      currency: 'BRL',
      metadata: {
        intent_score: signals.intentScore,
        ltv_segment: segment.tier,
        session_depth: signals.sessionDepth,
        cart_value: signals.cartValue
      },
      priority: 'high'
    });
  }
  
  // 3. SSI_ReturningBuyer - Comprador retornando ao site
  if (signals.isReturning && signals.previousPurchases > 0) {
    bidSignals.push({
      eventName: 'SSI_ReturningBuyer',
      value: signals.ltvScore * 100 * 1.2,
      currency: 'BRL',
      metadata: {
        previous_purchases: signals.previousPurchases,
        days_since_last: signals.daysFromLastVisit,
        ltv_segment: segment.tier
      },
      priority: 'high'
    });
  }
  
  // 4. SSI_CartAbandoner - Carrinho abandonado (para retargeting agressivo)
  if (signals.cartValue && signals.cartValue > 0 && eventContext.eventName === 'PageView') {
    // Só dispara se visitante retorna após abandonar carrinho
    if (signals.isReturning) {
      bidSignals.push({
        eventName: 'SSI_CartAbandoner',
        value: signals.cartValue * 0.5,
        currency: 'BRL',
        metadata: {
          cart_value: signals.cartValue,
          ltv_segment: segment.tier,
          recovery_attempt: true
        },
        priority: 'critical'
      });
    }
  }
  
  // 5. SSI_WhaleSighting - Cliente VIP identificado
  if (segment.tier === 'whale') {
    bidSignals.push({
      eventName: 'SSI_WhaleSighting',
      value: signals.ltvScore * 200,
      currency: 'BRL',
      metadata: {
        ltv_score: signals.ltvScore,
        previous_purchases: signals.previousPurchases,
        segment: 'whale'
      },
      priority: 'critical'
    });
  }
  
  return bidSignals;
}

// =============================================================================
// VALUE ENRICHMENT
// =============================================================================

/**
 * Enriquece o valor de um evento para CAPI
 * Usado para value-based bidding optimization
 */
export function enrichEventValue(
  originalValue: number,
  signals: VisitorSignals
): {
  enrichedValue: number;
  predictedLTV: number;
  valueMultiplier: number;
  confidence: number;
} {
  const segment = segmentByLTV(signals);
  
  // Calcular predicted LTV baseado nos sinais
  let predictedLTV = originalValue * segment.multiplier;
  
  // Ajustes baseados em comportamento
  if (signals.isReturning) {
    predictedLTV *= 1.2; // Retornantes têm 20% mais LTV
  }
  
  if (signals.previousPurchases > 0) {
    // Cada compra anterior aumenta LTV previsto
    predictedLTV *= (1 + signals.previousPurchases * 0.15);
  }
  
  if (signals.deviceType === 'desktop') {
    predictedLTV *= 1.1; // Desktop converte melhor
  }
  
  // Calcular confiança da predição
  let confidence = signals.ltvScore;
  
  if (signals.previousPurchases > 0) {
    confidence = Math.min(1, confidence + 0.2); // Mais dados = mais confiança
  }
  
  return {
    enrichedValue: Math.round(predictedLTV * 100) / 100,
    predictedLTV: Math.round(predictedLTV * 100) / 100,
    valueMultiplier: segment.multiplier,
    confidence: Math.round(confidence * 100) / 100
  };
}

// =============================================================================
// AUDIENCE SIGNALS
// =============================================================================

/**
 * Gera sinais para criação de audiências customizadas
 */
export function generateAudienceSignals(signals: VisitorSignals): Record<string, any> {
  const segment = segmentByLTV(signals);
  
  return {
    // Segmentos de valor
    ltv_tier: segment.tier,
    ltv_score_bucket: Math.floor(signals.ltvScore * 10) / 10, // 0.1, 0.2, ...
    
    // Comportamento
    is_returning: signals.isReturning,
    purchase_frequency: signals.previousPurchases > 2 ? 'frequent' :
                        signals.previousPurchases > 0 ? 'occasional' : 'new',
    
    // Intent
    intent_level: signals.intentScore >= 0.8 ? 'high' :
                  signals.intentScore >= 0.5 ? 'medium' : 'low',
    
    // Device
    device_preference: signals.deviceType,
    
    // Source
    acquisition_channel: signals.trafficSource,
    
    // Engagement
    engagement_level: signals.sessionDepth >= 5 ? 'deep' :
                      signals.sessionDepth >= 2 ? 'medium' : 'shallow',
    
    // Trust
    traffic_quality: signals.trustScore >= 0.8 ? 'verified' :
                     signals.trustScore >= 0.5 ? 'standard' : 'suspicious'
  };
}

// =============================================================================
// CAPI PAYLOAD BUILDER
// =============================================================================

/**
 * Constrói payload otimizado para CAPI com todos os sinais de valor
 */
export function buildEnrichedCAPIPayload(
  baseEvent: {
    event_name: string;
    event_id: string;
    event_time: number;
    event_source_url: string;
    user_data: Record<string, any>;
    custom_data?: Record<string, any>;
  },
  signals: VisitorSignals
): Record<string, any> {
  const segment = segmentByLTV(signals);
  const audienceSignals = generateAudienceSignals(signals);
  
  // Enriquecer valor se existir
  let enrichedCustomData = { ...baseEvent.custom_data };
  
  if (enrichedCustomData.value) {
    const enrichment = enrichEventValue(enrichedCustomData.value, signals);
    enrichedCustomData = {
      ...enrichedCustomData,
      // Valor original para tracking
      original_value: enrichedCustomData.value,
      // Valor enriquecido para otimização
      predicted_ltv: enrichment.predictedLTV,
      value_confidence: enrichment.confidence
    };
  }
  
  return {
    event_name: baseEvent.event_name,
    event_id: baseEvent.event_id,
    event_time: baseEvent.event_time,
    event_source_url: baseEvent.event_source_url,
    action_source: 'website',
    
    user_data: {
      ...baseEvent.user_data,
      // External ID é o SSI ID hasheado
      external_id: signals.ssiId ? [signals.ssiId] : undefined
    },
    
    custom_data: {
      ...enrichedCustomData,
      
      // Sinais de valor para algoritmo
      ssi_ltv_score: signals.ltvScore,
      ssi_intent_score: signals.intentScore,
      ssi_trust_score: signals.trustScore,
      ssi_ltv_segment: segment.tier,
      ssi_value_multiplier: segment.multiplier,
      
      // Sinais de audiência
      ...audienceSignals
    }
  };
}

// =============================================================================
// BID STRATEGY RECOMMENDATIONS
// =============================================================================

export interface BidRecommendation {
  strategy: 'aggressive' | 'balanced' | 'conservative' | 'avoid';
  bidMultiplier: number;
  reasoning: string;
  customAudience: string[];
}

/**
 * Recomenda estratégia de bid baseada nos sinais
 */
export function recommendBidStrategy(signals: VisitorSignals): BidRecommendation {
  const segment = segmentByLTV(signals);
  
  // Evitar tráfego suspeito
  if (signals.trustScore < 0.4) {
    return {
      strategy: 'avoid',
      bidMultiplier: 0,
      reasoning: 'Trust score muito baixo - possível bot ou fraude',
      customAudience: ['ssi_exclude_low_trust']
    };
  }
  
  // Aggressive para whales e high intent
  if (segment.tier === 'whale' || (signals.intentScore >= 0.9 && signals.ltvScore >= 0.8)) {
    return {
      strategy: 'aggressive',
      bidMultiplier: 2.5,
      reasoning: `Cliente ${segment.tier} com intent ${(signals.intentScore * 100).toFixed(0)}%`,
      customAudience: ['ssi_vip', 'ssi_high_value', 'ssi_aggressive_bid']
    };
  }
  
  // Aggressive para cart abandoners retornando
  if (signals.cartValue && signals.cartValue > 100 && signals.isReturning) {
    return {
      strategy: 'aggressive',
      bidMultiplier: 2.0,
      reasoning: `Cart abandoner retornando - cart value R$${signals.cartValue}`,
      customAudience: ['ssi_cart_recovery', 'ssi_high_intent']
    };
  }
  
  // Balanced para medium-high
  if (segment.tier === 'high' || signals.intentScore >= 0.7) {
    return {
      strategy: 'balanced',
      bidMultiplier: 1.5,
      reasoning: `Visitante de alto valor - LTV tier ${segment.tier}`,
      customAudience: ['ssi_high_value', 'ssi_balanced_bid']
    };
  }
  
  // Conservative para medium
  if (segment.tier === 'medium') {
    return {
      strategy: 'conservative',
      bidMultiplier: 1.0,
      reasoning: 'Visitante de valor médio - bid padrão',
      customAudience: ['ssi_standard']
    };
  }
  
  // Conservative para low/unknown
  return {
    strategy: 'conservative',
    bidMultiplier: 0.8,
    reasoning: 'Visitante novo ou baixo valor - bid conservador',
    customAudience: ['ssi_prospecting', 'ssi_low_bid']
  };
}

// =============================================================================
// EXPORT ALL
// =============================================================================

export default {
  segmentByLTV,
  generateBidSignals,
  enrichEventValue,
  generateAudienceSignals,
  buildEnrichedCAPIPayload,
  recommendBidStrategy
};
