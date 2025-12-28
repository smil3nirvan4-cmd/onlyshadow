"""
S.S.I. SHADOW — CUSTOMER DATA PLATFORM (CDP)
UNIFIED CUSTOMER PROFILES & AUDIENCE MANAGEMENT

CDP Core Features:
1. Identity Resolution - Unificar perfis cross-device
2. Profile Unification - Single customer view
3. Segmentation - Audiences dinâmicas
4. Activation - Sync para plataformas
5. Orchestration - Customer journeys

Integra com:
- Meta Custom Audiences
- Google Customer Match
- CRM systems
- Email platforms
"""

import os
import json
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Set, Callable, Union
from dataclasses import dataclass, field, asdict
from enum import Enum
from collections import defaultdict
import numpy as np

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('ssi_cdp')

# =============================================================================
# TYPES
# =============================================================================

class ProfileStatus(Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    CHURNED = "churned"
    PROSPECT = "prospect"


class SegmentType(Enum):
    STATIC = "static"  # Lista fixa
    DYNAMIC = "dynamic"  # Baseado em regras
    PREDICTIVE = "predictive"  # Baseado em ML
    LOOKALIKE = "lookalike"  # Similar a seed


@dataclass
class CustomerIdentity:
    """Identidades conhecidas do cliente"""
    ssi_id: str  # ID primário
    
    # Determinísticos
    email_hashes: List[str] = field(default_factory=list)
    phone_hashes: List[str] = field(default_factory=list)
    
    # Probabilísticos
    device_ids: List[str] = field(default_factory=list)
    browser_ids: List[str] = field(default_factory=list)
    
    # Third-party
    ramp_id: Optional[str] = None
    fingerprint_id: Optional[str] = None
    
    # Platform IDs
    meta_external_id: Optional[str] = None
    google_client_id: Optional[str] = None


@dataclass
class CustomerAttributes:
    """Atributos do cliente"""
    # Demographic
    country: Optional[str] = None
    region: Optional[str] = None
    city: Optional[str] = None
    language: Optional[str] = None
    
    # Device preferences
    primary_device: Optional[str] = None
    devices_used: List[str] = field(default_factory=list)
    
    # Behavioral
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    total_sessions: int = 0
    total_pageviews: int = 0
    
    # Engagement
    avg_session_duration: float = 0
    avg_scroll_depth: float = 0
    email_engagement_rate: float = 0
    
    # Source
    acquisition_source: Optional[str] = None
    acquisition_medium: Optional[str] = None
    acquisition_campaign: Optional[str] = None


@dataclass
class CustomerMetrics:
    """Métricas de negócio do cliente"""
    # Purchase
    total_orders: int = 0
    total_revenue: float = 0
    avg_order_value: float = 0
    last_order_date: Optional[datetime] = None
    
    # LTV
    predicted_ltv: float = 0
    ltv_segment: Optional[str] = None
    
    # Engagement
    recency_days: int = 999
    frequency_score: float = 0
    monetary_score: float = 0
    rfm_segment: Optional[str] = None
    
    # Propensity
    purchase_probability: float = 0
    churn_probability: float = 0
    
    # Quality
    trust_score: float = 0.5
    fraud_score: float = 0


@dataclass
class CustomerProfile:
    """Perfil unificado do cliente"""
    profile_id: str
    status: ProfileStatus
    
    identity: CustomerIdentity
    attributes: CustomerAttributes
    metrics: CustomerMetrics
    
    # Segments
    segments: List[str] = field(default_factory=list)
    
    # Tags (manuais ou automáticas)
    tags: List[str] = field(default_factory=list)
    
    # Custom properties
    custom_properties: Dict[str, Any] = field(default_factory=dict)
    
    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte para dict"""
        return asdict(self)


# =============================================================================
# SEGMENT DEFINITION
# =============================================================================

@dataclass
class SegmentCondition:
    """Condição para segmentação"""
    field: str  # e.g., 'metrics.total_revenue'
    operator: str  # 'eq', 'gt', 'lt', 'gte', 'lte', 'in', 'contains'
    value: Any


@dataclass
class Segment:
    """Definição de segmento"""
    id: str
    name: str
    description: str = ""
    segment_type: SegmentType = SegmentType.DYNAMIC
    
    # Conditions (AND)
    conditions: List[SegmentCondition] = field(default_factory=list)
    
    # Alternative conditions (OR)
    or_conditions: List[List[SegmentCondition]] = field(default_factory=list)
    
    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    created_by: str = ""
    
    # Stats
    profile_count: int = 0
    last_computed: Optional[datetime] = None
    
    def evaluate(self, profile: CustomerProfile) -> bool:
        """Avalia se profile pertence ao segmento"""
        
        def get_nested_value(obj, path: str):
            """Obtém valor de path nested (e.g., 'metrics.total_revenue')"""
            parts = path.split('.')
            current = obj
            
            for part in parts:
                if hasattr(current, part):
                    current = getattr(current, part)
                elif isinstance(current, dict):
                    current = current.get(part)
                else:
                    return None
            
            return current
        
        def check_condition(cond: SegmentCondition) -> bool:
            value = get_nested_value(profile, cond.field)
            
            if value is None:
                return False
            
            if cond.operator == 'eq':
                return value == cond.value
            elif cond.operator == 'neq':
                return value != cond.value
            elif cond.operator == 'gt':
                return value > cond.value
            elif cond.operator == 'gte':
                return value >= cond.value
            elif cond.operator == 'lt':
                return value < cond.value
            elif cond.operator == 'lte':
                return value <= cond.value
            elif cond.operator == 'in':
                return value in cond.value
            elif cond.operator == 'contains':
                return cond.value in value
            
            return False
        
        # Check AND conditions
        if self.conditions:
            if not all(check_condition(c) for c in self.conditions):
                return False
        
        # Check OR groups
        if self.or_conditions:
            for or_group in self.or_conditions:
                if all(check_condition(c) for c in or_group):
                    return True
            return False
        
        return True


# =============================================================================
# CDP ENGINE
# =============================================================================

class CDPEngine:
    """
    Engine principal do CDP.
    Gerencia profiles, segments e activations.
    """
    
    def __init__(self, storage=None):
        self.profiles: Dict[str, CustomerProfile] = {}
        self.segments: Dict[str, Segment] = {}
        self.segment_members: Dict[str, Set[str]] = defaultdict(set)
        self.storage = storage
        
        self._setup_default_segments()
    
    def _setup_default_segments(self):
        """Configura segmentos padrão"""
        
        # High Value Customers
        self.create_segment(Segment(
            id='high_value',
            name='High Value Customers',
            description='Clientes com LTV alto',
            conditions=[
                SegmentCondition('metrics.total_revenue', 'gte', 500),
                SegmentCondition('metrics.total_orders', 'gte', 2)
            ]
        ))
        
        # At Risk (Churn)
        self.create_segment(Segment(
            id='at_risk',
            name='At Risk of Churn',
            description='Clientes em risco de churn',
            conditions=[
                SegmentCondition('metrics.recency_days', 'gte', 30),
                SegmentCondition('metrics.churn_probability', 'gte', 0.5)
            ]
        ))
        
        # Hot Prospects
        self.create_segment(Segment(
            id='hot_prospects',
            name='Hot Prospects',
            description='Visitantes com alta probabilidade de conversão',
            conditions=[
                SegmentCondition('metrics.total_orders', 'eq', 0),
                SegmentCondition('metrics.purchase_probability', 'gte', 0.6)
            ]
        ))
        
        # Recent Buyers
        self.create_segment(Segment(
            id='recent_buyers',
            name='Recent Buyers',
            description='Compraram nos últimos 7 dias',
            conditions=[
                SegmentCondition('metrics.recency_days', 'lte', 7),
                SegmentCondition('metrics.total_orders', 'gte', 1)
            ]
        ))
        
        # Low Quality Traffic
        self.create_segment(Segment(
            id='low_quality',
            name='Low Quality Traffic',
            description='Tráfego de baixa qualidade',
            conditions=[
                SegmentCondition('metrics.trust_score', 'lt', 0.4)
            ]
        ))
    
    # =========================================================================
    # PROFILE MANAGEMENT
    # =========================================================================
    
    def get_or_create_profile(
        self,
        ssi_id: str,
        email_hash: str = None,
        phone_hash: str = None
    ) -> CustomerProfile:
        """Obtém ou cria profile"""
        
        # Try to find by ssi_id
        if ssi_id in self.profiles:
            return self.profiles[ssi_id]
        
        # Try to find by email
        if email_hash:
            for profile in self.profiles.values():
                if email_hash in profile.identity.email_hashes:
                    # Merge ssi_id
                    if ssi_id not in profile.identity.device_ids:
                        profile.identity.device_ids.append(ssi_id)
                    return profile
        
        # Create new profile
        profile = CustomerProfile(
            profile_id=ssi_id,
            status=ProfileStatus.PROSPECT,
            identity=CustomerIdentity(ssi_id=ssi_id),
            attributes=CustomerAttributes(first_seen=datetime.now()),
            metrics=CustomerMetrics()
        )
        
        if email_hash:
            profile.identity.email_hashes.append(email_hash)
        if phone_hash:
            profile.identity.phone_hashes.append(phone_hash)
        
        self.profiles[ssi_id] = profile
        
        return profile
    
    def update_profile(
        self,
        profile_id: str,
        updates: Dict[str, Any]
    ) -> CustomerProfile:
        """Atualiza profile com novos dados"""
        
        profile = self.profiles.get(profile_id)
        if not profile:
            raise ValueError(f"Profile {profile_id} not found")
        
        # Update identity
        if 'email_hash' in updates:
            if updates['email_hash'] not in profile.identity.email_hashes:
                profile.identity.email_hashes.append(updates['email_hash'])
        
        if 'phone_hash' in updates:
            if updates['phone_hash'] not in profile.identity.phone_hashes:
                profile.identity.phone_hashes.append(updates['phone_hash'])
        
        if 'device_id' in updates:
            if updates['device_id'] not in profile.identity.device_ids:
                profile.identity.device_ids.append(updates['device_id'])
        
        # Update attributes
        attrs = profile.attributes
        if 'country' in updates:
            attrs.country = updates['country']
        if 'city' in updates:
            attrs.city = updates['city']
        if 'device_type' in updates:
            attrs.primary_device = updates['device_type']
            if updates['device_type'] not in attrs.devices_used:
                attrs.devices_used.append(updates['device_type'])
        
        attrs.last_seen = datetime.now()
        attrs.total_sessions += 1
        
        # Update metrics
        metrics = profile.metrics
        if 'trust_score' in updates:
            # Exponential moving average
            metrics.trust_score = metrics.trust_score * 0.9 + updates['trust_score'] * 0.1
        
        if 'scroll_depth' in updates:
            attrs.avg_scroll_depth = attrs.avg_scroll_depth * 0.9 + updates['scroll_depth'] * 0.1
        
        # Update recency
        if attrs.last_seen:
            metrics.recency_days = (datetime.now() - attrs.last_seen).days
        
        # Update status
        if metrics.total_orders > 0:
            profile.status = ProfileStatus.ACTIVE
        elif metrics.recency_days > 90:
            profile.status = ProfileStatus.CHURNED
        
        profile.updated_at = datetime.now()
        
        # Re-evaluate segments
        self._evaluate_segments_for_profile(profile)
        
        return profile
    
    def record_purchase(
        self,
        profile_id: str,
        order_value: float,
        order_id: str = None
    ) -> CustomerProfile:
        """Registra uma compra"""
        
        profile = self.profiles.get(profile_id)
        if not profile:
            raise ValueError(f"Profile {profile_id} not found")
        
        metrics = profile.metrics
        metrics.total_orders += 1
        metrics.total_revenue += order_value
        metrics.avg_order_value = metrics.total_revenue / metrics.total_orders
        metrics.last_order_date = datetime.now()
        metrics.recency_days = 0
        
        profile.status = ProfileStatus.ACTIVE
        profile.updated_at = datetime.now()
        
        # Re-calculate RFM
        self._calculate_rfm(profile)
        
        # Re-evaluate segments
        self._evaluate_segments_for_profile(profile)
        
        return profile
    
    def _calculate_rfm(self, profile: CustomerProfile):
        """Calcula scores RFM"""
        metrics = profile.metrics
        
        # Recency score (lower is better)
        if metrics.recency_days <= 7:
            r_score = 5
        elif metrics.recency_days <= 30:
            r_score = 4
        elif metrics.recency_days <= 60:
            r_score = 3
        elif metrics.recency_days <= 90:
            r_score = 2
        else:
            r_score = 1
        
        # Frequency score
        if metrics.total_orders >= 10:
            f_score = 5
        elif metrics.total_orders >= 5:
            f_score = 4
        elif metrics.total_orders >= 3:
            f_score = 3
        elif metrics.total_orders >= 1:
            f_score = 2
        else:
            f_score = 1
        
        # Monetary score
        if metrics.total_revenue >= 1000:
            m_score = 5
        elif metrics.total_revenue >= 500:
            m_score = 4
        elif metrics.total_revenue >= 200:
            m_score = 3
        elif metrics.total_revenue >= 50:
            m_score = 2
        else:
            m_score = 1
        
        metrics.frequency_score = f_score
        metrics.monetary_score = m_score
        
        # RFM segment
        rfm_score = r_score * 100 + f_score * 10 + m_score
        
        if r_score >= 4 and f_score >= 4:
            metrics.rfm_segment = 'champions'
        elif r_score >= 3 and m_score >= 4:
            metrics.rfm_segment = 'loyal_customers'
        elif r_score >= 4 and f_score <= 2:
            metrics.rfm_segment = 'new_customers'
        elif r_score <= 2 and f_score >= 3:
            metrics.rfm_segment = 'at_risk'
        elif r_score <= 2 and f_score <= 2 and m_score <= 2:
            metrics.rfm_segment = 'lost'
        else:
            metrics.rfm_segment = 'regular'
    
    # =========================================================================
    # SEGMENT MANAGEMENT
    # =========================================================================
    
    def create_segment(self, segment: Segment):
        """Cria ou atualiza segmento"""
        self.segments[segment.id] = segment
        self.segment_members[segment.id] = set()
    
    def _evaluate_segments_for_profile(self, profile: CustomerProfile):
        """Avalia todos os segmentos para um profile"""
        profile.segments = []
        
        for segment_id, segment in self.segments.items():
            if segment.evaluate(profile):
                profile.segments.append(segment_id)
                self.segment_members[segment_id].add(profile.profile_id)
            else:
                self.segment_members[segment_id].discard(profile.profile_id)
    
    def compute_all_segments(self):
        """Recomputa todos os segmentos para todos os profiles"""
        logger.info("Computing all segments...")
        
        for segment_id in self.segments:
            self.segment_members[segment_id] = set()
        
        for profile in self.profiles.values():
            self._evaluate_segments_for_profile(profile)
        
        for segment_id, segment in self.segments.items():
            segment.profile_count = len(self.segment_members[segment_id])
            segment.last_computed = datetime.now()
        
        logger.info(f"Computed {len(self.segments)} segments for {len(self.profiles)} profiles")
    
    def get_segment_profiles(self, segment_id: str) -> List[CustomerProfile]:
        """Obtém profiles de um segmento"""
        profile_ids = self.segment_members.get(segment_id, set())
        return [self.profiles[pid] for pid in profile_ids if pid in self.profiles]
    
    # =========================================================================
    # EXPORT & ACTIVATION
    # =========================================================================
    
    def export_segment_for_meta(
        self,
        segment_id: str
    ) -> List[Dict[str, str]]:
        """
        Exporta segmento para Meta Custom Audiences.
        Retorna lista de hashes para upload.
        """
        profiles = self.get_segment_profiles(segment_id)
        
        export_data = []
        
        for profile in profiles:
            record = {}
            
            # Email hashes
            if profile.identity.email_hashes:
                record['email_hash'] = profile.identity.email_hashes[0]
            
            # Phone hashes
            if profile.identity.phone_hashes:
                record['phone_hash'] = profile.identity.phone_hashes[0]
            
            # External ID
            record['external_id'] = profile.profile_id
            
            if record:
                export_data.append(record)
        
        logger.info(f"Exported {len(export_data)} profiles for Meta Custom Audience")
        
        return export_data
    
    def export_segment_for_google(
        self,
        segment_id: str
    ) -> List[Dict[str, str]]:
        """
        Exporta segmento para Google Customer Match.
        """
        profiles = self.get_segment_profiles(segment_id)
        
        export_data = []
        
        for profile in profiles:
            record = {}
            
            if profile.identity.email_hashes:
                record['hashedEmail'] = profile.identity.email_hashes[0]
            
            if profile.identity.phone_hashes:
                record['hashedPhoneNumber'] = profile.identity.phone_hashes[0]
            
            if profile.attributes.country:
                record['countryCode'] = profile.attributes.country
            
            if record:
                export_data.append(record)
        
        return export_data
    
    def get_profile_summary(self) -> Dict[str, Any]:
        """Retorna resumo dos profiles"""
        
        total = len(self.profiles)
        
        status_counts = defaultdict(int)
        segment_counts = defaultdict(int)
        
        total_revenue = 0
        total_orders = 0
        
        for profile in self.profiles.values():
            status_counts[profile.status.value] += 1
            
            for seg in profile.segments:
                segment_counts[seg] += 1
            
            total_revenue += profile.metrics.total_revenue
            total_orders += profile.metrics.total_orders
        
        return {
            'total_profiles': total,
            'status_breakdown': dict(status_counts),
            'segment_breakdown': dict(segment_counts),
            'total_revenue': total_revenue,
            'total_orders': total_orders,
            'avg_revenue_per_profile': total_revenue / max(1, total),
            'avg_orders_per_profile': total_orders / max(1, total)
        }


# =============================================================================
# LOOKALIKE MODELING
# =============================================================================

class LookalikeModeler:
    """
    Cria audiences similares a um seed segment.
    Usa feature similarity para encontrar prospects parecidos com best customers.
    """
    
    def __init__(self, cdp: CDPEngine):
        self.cdp = cdp
    
    def _profile_to_vector(self, profile: CustomerProfile) -> np.ndarray:
        """Converte profile para vetor de features"""
        metrics = profile.metrics
        attrs = profile.attributes
        
        return np.array([
            metrics.trust_score,
            min(1, metrics.recency_days / 90),
            min(1, metrics.total_orders / 10),
            min(1, metrics.total_revenue / 1000),
            metrics.purchase_probability,
            attrs.avg_scroll_depth / 100 if attrs.avg_scroll_depth else 0,
            1 if attrs.primary_device == 'mobile' else 0
        ])
    
    def find_lookalikes(
        self,
        seed_segment_id: str,
        target_segment_id: str = None,
        top_n: int = 1000,
        similarity_threshold: float = 0.7
    ) -> List[str]:
        """
        Encontra profiles similares ao seed segment.
        
        seed_segment_id: Segmento de origem (best customers)
        target_segment_id: Pool para buscar (opcional)
        top_n: Número máximo de lookalikes
        similarity_threshold: Similaridade mínima
        """
        # Get seed profiles
        seed_profiles = self.cdp.get_segment_profiles(seed_segment_id)
        
        if not seed_profiles:
            return []
        
        # Compute seed centroid
        seed_vectors = np.array([
            self._profile_to_vector(p) for p in seed_profiles
        ])
        centroid = np.mean(seed_vectors, axis=0)
        
        # Get candidate pool
        if target_segment_id:
            candidates = self.cdp.get_segment_profiles(target_segment_id)
        else:
            # All non-seed profiles
            seed_ids = set(p.profile_id for p in seed_profiles)
            candidates = [
                p for p in self.cdp.profiles.values()
                if p.profile_id not in seed_ids
            ]
        
        # Calculate similarity scores
        similarities = []
        
        for profile in candidates:
            vec = self._profile_to_vector(profile)
            
            # Cosine similarity
            norm_centroid = np.linalg.norm(centroid)
            norm_vec = np.linalg.norm(vec)
            
            if norm_centroid > 0 and norm_vec > 0:
                similarity = np.dot(centroid, vec) / (norm_centroid * norm_vec)
            else:
                similarity = 0
            
            if similarity >= similarity_threshold:
                similarities.append((profile.profile_id, similarity))
        
        # Sort by similarity
        similarities.sort(key=lambda x: x[1], reverse=True)
        
        # Return top N
        lookalike_ids = [pid for pid, _ in similarities[:top_n]]
        
        logger.info(f"Found {len(lookalike_ids)} lookalike profiles (threshold: {similarity_threshold})")
        
        return lookalike_ids
    
    def create_lookalike_segment(
        self,
        seed_segment_id: str,
        lookalike_segment_id: str,
        top_n: int = 1000
    ) -> Segment:
        """Cria segmento de lookalikes"""
        
        lookalike_ids = self.find_lookalikes(seed_segment_id, top_n=top_n)
        
        # Create static segment
        segment = Segment(
            id=lookalike_segment_id,
            name=f"Lookalike of {seed_segment_id}",
            description=f"Top {len(lookalike_ids)} profiles similar to {seed_segment_id}",
            segment_type=SegmentType.LOOKALIKE
        )
        
        self.cdp.segments[lookalike_segment_id] = segment
        self.cdp.segment_members[lookalike_segment_id] = set(lookalike_ids)
        
        # Update profiles
        for pid in lookalike_ids:
            if pid in self.cdp.profiles:
                if lookalike_segment_id not in self.cdp.profiles[pid].segments:
                    self.cdp.profiles[pid].segments.append(lookalike_segment_id)
        
        segment.profile_count = len(lookalike_ids)
        segment.last_computed = datetime.now()
        
        return segment


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    'ProfileStatus',
    'SegmentType',
    'CustomerIdentity',
    'CustomerAttributes',
    'CustomerMetrics',
    'CustomerProfile',
    'Segment',
    'SegmentCondition',
    'CDPEngine',
    'LookalikeModeler'
]
