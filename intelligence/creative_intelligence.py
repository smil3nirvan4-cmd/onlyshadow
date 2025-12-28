"""
S.S.I. SHADOW — CREATIVE INTELLIGENCE
AI-POWERED CREATIVE ANALYSIS & OPTIMIZATION

Analisa criativos de anúncios usando AI:
1. Visual Analysis - Elementos visuais, cores, composição
2. Copy Analysis - Texto, CTAs, sentiment
3. Performance Prediction - Prever CTR/CVR
4. A/B Recommendations - Sugerir variações
5. Fatigue Detection - Detectar creative fatigue

Usa Vision API + NLP para análise.
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import re
from collections import Counter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('ssi_creative_intelligence')

# =============================================================================
# TYPES
# =============================================================================

class CreativeType(Enum):
    IMAGE = "image"
    VIDEO = "video"
    CAROUSEL = "carousel"
    COLLECTION = "collection"
    DYNAMIC = "dynamic"
    TEXT_ONLY = "text_only"


class CreativeElement(Enum):
    PRODUCT_IMAGE = "product_image"
    LIFESTYLE = "lifestyle"
    UGC = "user_generated_content"
    TESTIMONIAL = "testimonial"
    PRICE_CALLOUT = "price_callout"
    DISCOUNT_BADGE = "discount_badge"
    CTA_BUTTON = "cta_button"
    LOGO = "logo"
    FACE = "face"
    TEXT_OVERLAY = "text_overlay"


class EmotionalTone(Enum):
    URGENT = "urgent"
    ASPIRATIONAL = "aspirational"
    INFORMATIONAL = "informational"
    PLAYFUL = "playful"
    TRUSTWORTHY = "trustworthy"
    EXCLUSIVE = "exclusive"
    FEAR_OF_MISSING = "fomo"


@dataclass
class CreativeMetadata:
    """Metadados do criativo"""
    creative_id: str
    creative_type: CreativeType
    
    # Assets
    image_urls: List[str] = field(default_factory=list)
    video_url: Optional[str] = None
    
    # Copy
    headline: str = ""
    primary_text: str = ""
    description: str = ""
    cta_text: str = ""
    
    # Context
    campaign_id: str = ""
    ad_set_id: str = ""
    advertiser_id: str = ""
    
    # Dates
    created_at: datetime = field(default_factory=datetime.now)
    first_served: Optional[datetime] = None


@dataclass
class VisualAnalysis:
    """Resultado da análise visual"""
    # Elements detected
    elements: List[CreativeElement] = field(default_factory=list)
    element_positions: Dict[str, Dict[str, float]] = field(default_factory=dict)
    
    # Colors
    dominant_colors: List[str] = field(default_factory=list)
    color_harmony: float = 0  # 0-1
    contrast_score: float = 0  # 0-1
    
    # Composition
    rule_of_thirds: bool = False
    visual_hierarchy_score: float = 0
    clutter_score: float = 0  # Lower is better
    
    # Faces
    faces_detected: int = 0
    face_sentiment: str = ""  # 'happy', 'neutral', 'serious'
    
    # Brand
    logo_visible: bool = False
    logo_position: str = ""
    
    # Text
    text_overlay_area: float = 0  # % of image
    text_readability: float = 0


@dataclass
class CopyAnalysis:
    """Resultado da análise de copy"""
    # Basic
    word_count: int = 0
    character_count: int = 0
    sentence_count: int = 0
    
    # Readability
    flesch_score: float = 0  # Higher = easier to read
    avg_word_length: float = 0
    
    # Sentiment
    sentiment_score: float = 0  # -1 to 1
    emotional_tone: List[EmotionalTone] = field(default_factory=list)
    
    # Power words
    power_words: List[str] = field(default_factory=list)
    urgency_signals: List[str] = field(default_factory=list)
    social_proof_signals: List[str] = field(default_factory=list)
    
    # CTA
    cta_strength: float = 0  # 0-1
    cta_clarity: float = 0
    
    # Issues
    issues: List[str] = field(default_factory=list)


@dataclass
class PerformancePrediction:
    """Predição de performance"""
    predicted_ctr: float = 0
    predicted_cvr: float = 0
    predicted_engagement_rate: float = 0
    
    ctr_confidence_interval: Tuple[float, float] = (0, 0)
    
    # Relative to category
    ctr_percentile: int = 50  # 0-100
    
    # Factors
    positive_factors: List[str] = field(default_factory=list)
    negative_factors: List[str] = field(default_factory=list)
    
    # Recommendations
    improvement_suggestions: List[str] = field(default_factory=list)


@dataclass
class CreativeScore:
    """Score geral do criativo"""
    overall_score: float = 0  # 0-100
    
    visual_score: float = 0
    copy_score: float = 0
    relevance_score: float = 0
    
    predicted_performance: PerformancePrediction = None
    
    # Breakdown
    strengths: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)
    
    # Comparison
    vs_category_avg: float = 0  # % above/below


# =============================================================================
# COPY ANALYZER
# =============================================================================

class CopyAnalyzer:
    """Analisa copy de anúncios"""
    
    POWER_WORDS = [
        'grátis', 'free', 'novo', 'exclusivo', 'limitado', 'único',
        'garantido', 'comprovado', 'fácil', 'rápido', 'agora',
        'descubra', 'transforme', 'ganhe', 'economize', 'aproveite',
        'última', 'chance', 'imperdível', 'especial', 'premium'
    ]
    
    URGENCY_WORDS = [
        'agora', 'hoje', 'última', 'chance', 'limitado', 'acaba',
        'restam', 'poucos', 'urgente', 'imediato', 'pressa',
        'corra', 'não perca', 'só hoje', 'últimas unidades'
    ]
    
    SOCIAL_PROOF = [
        'milhares', 'clientes', 'aprovado', 'recomendado', 'avaliado',
        'estrelas', 'vendidos', 'best seller', 'mais vendido',
        'sucesso', 'confiado', 'certificado'
    ]
    
    CTA_WORDS = [
        'compre', 'clique', 'saiba', 'veja', 'descubra', 'garanta',
        'aproveite', 'confira', 'acesse', 'cadastre', 'inscreva',
        'baixe', 'experimente', 'comece', 'peça', 'reserve'
    ]
    
    def analyze(self, copy: str) -> CopyAnalysis:
        """Analisa copy completo"""
        
        if not copy:
            return CopyAnalysis()
        
        copy_lower = copy.lower()
        words = re.findall(r'\b\w+\b', copy_lower)
        sentences = re.split(r'[.!?]+', copy)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        # Basic counts
        word_count = len(words)
        char_count = len(copy)
        sentence_count = len(sentences)
        
        # Average word length
        avg_word_length = sum(len(w) for w in words) / max(1, len(words))
        
        # Flesch reading ease (simplified for Portuguese)
        if sentence_count > 0 and word_count > 0:
            avg_sentence_length = word_count / sentence_count
            flesch = 206.835 - (1.015 * avg_sentence_length) - (84.6 * (avg_word_length / 5))
            flesch = max(0, min(100, flesch))
        else:
            flesch = 50
        
        # Find power words
        power_words = [w for w in self.POWER_WORDS if w in copy_lower]
        urgency_signals = [w for w in self.URGENCY_WORDS if w in copy_lower]
        social_proof = [w for w in self.SOCIAL_PROOF if w in copy_lower]
        
        # Sentiment (simplified)
        positive_words = ['grátis', 'ganhe', 'melhor', 'novo', 'fácil', 'bom', 'ótimo']
        negative_words = ['não', 'sem', 'nunca', 'problema', 'difícil']
        
        pos_count = sum(1 for w in positive_words if w in copy_lower)
        neg_count = sum(1 for w in negative_words if w in copy_lower)
        
        if pos_count + neg_count > 0:
            sentiment = (pos_count - neg_count) / (pos_count + neg_count)
        else:
            sentiment = 0
        
        # Emotional tone
        emotional_tones = []
        if urgency_signals:
            emotional_tones.append(EmotionalTone.URGENT)
        if any(w in copy_lower for w in ['exclusivo', 'vip', 'premium', 'especial']):
            emotional_tones.append(EmotionalTone.EXCLUSIVE)
        if any(w in copy_lower for w in ['última', 'restam', 'acaba', 'limitado']):
            emotional_tones.append(EmotionalTone.FEAR_OF_MISSING)
        
        # CTA analysis
        cta_words_found = [w for w in self.CTA_WORDS if w in copy_lower]
        cta_strength = min(1.0, len(cta_words_found) / 2)
        cta_clarity = 1.0 if cta_words_found else 0.5
        
        # Issues
        issues = []
        if word_count > 125:
            issues.append("Copy muito longo (>125 palavras)")
        if not cta_words_found:
            issues.append("Falta CTA claro")
        if avg_word_length > 7:
            issues.append("Palavras muito longas (difícil leitura)")
        if sentence_count > 0 and word_count / sentence_count > 25:
            issues.append("Frases muito longas")
        
        return CopyAnalysis(
            word_count=word_count,
            character_count=char_count,
            sentence_count=sentence_count,
            flesch_score=flesch,
            avg_word_length=avg_word_length,
            sentiment_score=sentiment,
            emotional_tone=emotional_tones,
            power_words=power_words,
            urgency_signals=urgency_signals,
            social_proof_signals=social_proof,
            cta_strength=cta_strength,
            cta_clarity=cta_clarity,
            issues=issues
        )


# =============================================================================
# VISUAL ANALYZER
# =============================================================================

class VisualAnalyzer:
    """Analisa elementos visuais (mock - em produção usar Vision API)"""
    
    def analyze(self, image_url: str) -> VisualAnalysis:
        """
        Analisa imagem.
        Em produção, usar Google Vision API, AWS Rekognition, ou similar.
        """
        # Mock analysis - em produção integrar com Vision API
        
        analysis = VisualAnalysis()
        
        # Simular detecção de elementos baseado em URL patterns
        url_lower = image_url.lower()
        
        if 'product' in url_lower:
            analysis.elements.append(CreativeElement.PRODUCT_IMAGE)
        if 'lifestyle' in url_lower:
            analysis.elements.append(CreativeElement.LIFESTYLE)
        if 'sale' in url_lower or 'off' in url_lower:
            analysis.elements.append(CreativeElement.DISCOUNT_BADGE)
        
        # Default reasonable values
        analysis.dominant_colors = ['#1a73e8', '#ffffff', '#000000']
        analysis.color_harmony = 0.75
        analysis.contrast_score = 0.80
        analysis.visual_hierarchy_score = 0.70
        analysis.clutter_score = 0.25
        analysis.text_overlay_area = 0.15
        analysis.text_readability = 0.85
        
        return analysis


# =============================================================================
# PERFORMANCE PREDICTOR
# =============================================================================

class PerformancePredictor:
    """Prediz performance de criativos"""
    
    def __init__(self):
        # Baseline performance by element
        self.element_impact = {
            CreativeElement.PRODUCT_IMAGE: 0.05,
            CreativeElement.LIFESTYLE: 0.08,
            CreativeElement.UGC: 0.10,
            CreativeElement.TESTIMONIAL: 0.07,
            CreativeElement.DISCOUNT_BADGE: 0.12,
            CreativeElement.FACE: 0.06,
            CreativeElement.CTA_BUTTON: 0.04
        }
        
        # Baseline CTR
        self.baseline_ctr = 0.012  # 1.2%
        self.baseline_cvr = 0.025  # 2.5%
    
    def predict(
        self,
        visual: VisualAnalysis,
        copy: CopyAnalysis,
        creative_type: CreativeType
    ) -> PerformancePrediction:
        """Prediz performance baseado na análise"""
        
        # Start with baseline
        ctr_multiplier = 1.0
        cvr_multiplier = 1.0
        
        positive_factors = []
        negative_factors = []
        suggestions = []
        
        # Element impacts
        for element in visual.elements:
            impact = self.element_impact.get(element, 0)
            ctr_multiplier += impact
            
            if impact > 0.05:
                positive_factors.append(f"Elemento de alta performance: {element.value}")
        
        # Copy impacts
        if copy.power_words:
            ctr_multiplier += 0.05 * min(3, len(copy.power_words))
            positive_factors.append(f"{len(copy.power_words)} power words detectadas")
        
        if copy.urgency_signals:
            cvr_multiplier += 0.08
            positive_factors.append("Urgência no copy aumenta conversão")
        
        if copy.cta_strength > 0.5:
            cvr_multiplier += 0.05
            positive_factors.append("CTA forte")
        else:
            negative_factors.append("CTA fraco")
            suggestions.append("Adicione um CTA mais claro como 'Compre Agora'")
        
        # Visual quality impacts
        if visual.contrast_score > 0.8:
            ctr_multiplier += 0.03
        else:
            negative_factors.append("Baixo contraste visual")
            suggestions.append("Melhore o contraste da imagem")
        
        if visual.clutter_score > 0.5:
            ctr_multiplier -= 0.05
            negative_factors.append("Imagem muito poluída")
            suggestions.append("Simplifique a composição visual")
        
        if visual.text_overlay_area > 0.3:
            ctr_multiplier -= 0.08
            negative_factors.append("Muito texto na imagem")
            suggestions.append("Reduza texto sobreposto (regra 20%)")
        
        # Copy quality
        if copy.flesch_score < 40:
            ctr_multiplier -= 0.03
            negative_factors.append("Copy difícil de ler")
            suggestions.append("Simplifique o texto")
        
        if copy.word_count > 125:
            ctr_multiplier -= 0.05
            suggestions.append("Reduza o tamanho do copy")
        
        # Creative type adjustments
        if creative_type == CreativeType.VIDEO:
            ctr_multiplier += 0.15
            positive_factors.append("Vídeo geralmente tem melhor CTR")
        elif creative_type == CreativeType.CAROUSEL:
            ctr_multiplier += 0.08
        
        # Calculate predicted values
        predicted_ctr = self.baseline_ctr * ctr_multiplier
        predicted_cvr = self.baseline_cvr * cvr_multiplier
        
        # Confidence interval (simplified)
        ctr_std = predicted_ctr * 0.3
        ci = (predicted_ctr - 1.96 * ctr_std, predicted_ctr + 1.96 * ctr_std)
        
        # Percentile (mock)
        ctr_percentile = min(100, max(0, int(50 + (ctr_multiplier - 1) * 100)))
        
        return PerformancePrediction(
            predicted_ctr=predicted_ctr,
            predicted_cvr=predicted_cvr,
            predicted_engagement_rate=predicted_ctr * 1.5,
            ctr_confidence_interval=ci,
            ctr_percentile=ctr_percentile,
            positive_factors=positive_factors,
            negative_factors=negative_factors,
            improvement_suggestions=suggestions
        )


# =============================================================================
# CREATIVE INTELLIGENCE ENGINE
# =============================================================================

class CreativeIntelligenceEngine:
    """Engine principal de Creative Intelligence"""
    
    def __init__(self):
        self.copy_analyzer = CopyAnalyzer()
        self.visual_analyzer = VisualAnalyzer()
        self.performance_predictor = PerformancePredictor()
    
    def analyze_creative(
        self,
        metadata: CreativeMetadata
    ) -> CreativeScore:
        """Analisa um criativo completo"""
        
        # Analyze copy
        full_copy = f"{metadata.headline} {metadata.primary_text} {metadata.description}"
        copy_analysis = self.copy_analyzer.analyze(full_copy)
        
        # Analyze visuals
        visual_analysis = VisualAnalysis()
        if metadata.image_urls:
            visual_analysis = self.visual_analyzer.analyze(metadata.image_urls[0])
        
        # Predict performance
        prediction = self.performance_predictor.predict(
            visual_analysis,
            copy_analysis,
            metadata.creative_type
        )
        
        # Calculate scores
        copy_score = self._calculate_copy_score(copy_analysis)
        visual_score = self._calculate_visual_score(visual_analysis)
        
        # Overall score
        overall_score = (copy_score * 0.4 + visual_score * 0.4 + prediction.ctr_percentile * 0.2)
        
        # Compile strengths/weaknesses
        strengths = prediction.positive_factors[:5]
        weaknesses = prediction.negative_factors[:5]
        
        return CreativeScore(
            overall_score=overall_score,
            visual_score=visual_score,
            copy_score=copy_score,
            relevance_score=70,  # Would need audience context
            predicted_performance=prediction,
            strengths=strengths,
            weaknesses=weaknesses,
            vs_category_avg=(overall_score - 50) / 50 * 100
        )
    
    def _calculate_copy_score(self, analysis: CopyAnalysis) -> float:
        """Calcula score do copy"""
        score = 50  # Baseline
        
        # Positive signals
        score += len(analysis.power_words) * 3
        score += analysis.cta_strength * 15
        score += (analysis.flesch_score / 100) * 10
        
        if analysis.urgency_signals:
            score += 5
        if analysis.social_proof_signals:
            score += 5
        
        # Negative signals
        score -= len(analysis.issues) * 5
        
        return max(0, min(100, score))
    
    def _calculate_visual_score(self, analysis: VisualAnalysis) -> float:
        """Calcula score visual"""
        score = 50  # Baseline
        
        score += analysis.color_harmony * 15
        score += analysis.contrast_score * 15
        score += analysis.visual_hierarchy_score * 10
        score -= analysis.clutter_score * 20
        score += analysis.text_readability * 10
        
        if analysis.faces_detected > 0:
            score += 5
        
        return max(0, min(100, score))
    
    def detect_creative_fatigue(
        self,
        creative_id: str,
        performance_history: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Detecta creative fatigue baseado em histórico de performance.
        """
        if len(performance_history) < 7:
            return {'fatigue_detected': False, 'reason': 'Insufficient data'}
        
        # Get CTR trend
        ctrs = [d.get('ctr', 0) for d in performance_history[-14:]]
        
        if len(ctrs) < 7:
            return {'fatigue_detected': False}
        
        # Compare first half vs second half
        first_half = ctrs[:len(ctrs)//2]
        second_half = ctrs[len(ctrs)//2:]
        
        avg_first = sum(first_half) / len(first_half)
        avg_second = sum(second_half) / len(second_half)
        
        decline = (avg_first - avg_second) / avg_first if avg_first > 0 else 0
        
        fatigue_detected = decline > 0.15  # >15% decline
        
        return {
            'creative_id': creative_id,
            'fatigue_detected': fatigue_detected,
            'ctr_decline': decline,
            'avg_ctr_early': avg_first,
            'avg_ctr_recent': avg_second,
            'recommendation': 'Considere refresh do criativo' if fatigue_detected else 'Performance estável'
        }


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    'CreativeType',
    'CreativeElement',
    'EmotionalTone',
    'CreativeMetadata',
    'VisualAnalysis',
    'CopyAnalysis',
    'PerformancePrediction',
    'CreativeScore',
    'CopyAnalyzer',
    'VisualAnalyzer',
    'PerformancePredictor',
    'CreativeIntelligenceEngine'
]
