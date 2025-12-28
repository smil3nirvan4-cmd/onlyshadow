"""
S.S.I. SHADOW — FEATURE STORE
REAL-TIME FEATURE SERVING FOR ML

Similar ao Feast/Tecton mas simplificado para nosso caso de uso.

Features:
- Registro de feature definitions
- Compute batch + streaming
- Serving low-latency via Edge (Cloudflare KV)
- Feature versioning
- Point-in-time correctness

Arquitetura:
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  BigQuery   │────▶│ Feature     │────▶│ Cloudflare  │
│  (Offline)  │     │ Transform   │     │ KV (Online) │
└─────────────┘     └─────────────┘     └─────────────┘
                           ▲
                           │
                    ┌──────┴──────┐
                    │  Streaming  │
                    │  (Events)   │
                    └─────────────┘
"""

import os
import json
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Callable, Union
from dataclasses import dataclass, field, asdict
from enum import Enum
import numpy as np
from abc import ABC, abstractmethod

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('ssi_feature_store')

# =============================================================================
# TYPES
# =============================================================================

class FeatureType(Enum):
    INT = "int"
    FLOAT = "float"
    STRING = "string"
    BOOL = "bool"
    ARRAY_INT = "array_int"
    ARRAY_FLOAT = "array_float"
    EMBEDDING = "embedding"


class AggregationType(Enum):
    SUM = "sum"
    AVG = "avg"
    COUNT = "count"
    MIN = "min"
    MAX = "max"
    LAST = "last"
    FIRST = "first"
    COUNT_DISTINCT = "count_distinct"
    STDDEV = "stddev"


@dataclass
class FeatureDefinition:
    """Definição de uma feature"""
    name: str
    dtype: FeatureType
    description: str = ""
    
    # Source
    source_table: str = None
    source_column: str = None
    
    # Aggregation (para features agregadas)
    aggregation: AggregationType = None
    window_size: str = None  # '1h', '24h', '7d', '30d'
    group_by: List[str] = None
    
    # Computation
    transform_fn: str = None  # Nome da função de transformação
    dependencies: List[str] = None  # Features das quais depende
    
    # Metadata
    version: int = 1
    created_at: datetime = None
    updated_at: datetime = None
    owner: str = None
    tags: List[str] = None
    
    # Serving
    ttl_seconds: int = 3600  # TTL no cache online
    default_value: Any = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.updated_at is None:
            self.updated_at = datetime.now()
        if self.group_by is None:
            self.group_by = []
        if self.dependencies is None:
            self.dependencies = []
        if self.tags is None:
            self.tags = []


@dataclass
class FeatureView:
    """Conjunto de features relacionadas"""
    name: str
    entity: str  # 'user', 'session', 'campaign'
    features: List[str]  # Nomes das features
    description: str = ""
    
    # TTL
    online_ttl: timedelta = timedelta(hours=1)
    offline_ttl: timedelta = timedelta(days=30)
    
    # Tags
    tags: List[str] = None
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []


@dataclass
class FeatureVector:
    """Vetor de features para um entity"""
    entity_id: str
    features: Dict[str, Any]
    timestamp: datetime
    metadata: Dict[str, Any] = None


# =============================================================================
# FEATURE TRANSFORMS
# =============================================================================

class FeatureTransform(ABC):
    """Base class para transformações de features"""
    
    @abstractmethod
    def transform(self, data: Dict[str, Any]) -> Any:
        pass


class StandardScaler(FeatureTransform):
    """Normaliza feature para média 0 e std 1"""
    
    def __init__(self, mean: float = 0, std: float = 1):
        self.mean = mean
        self.std = std
    
    def transform(self, data: Dict[str, Any]) -> float:
        value = data.get('value', 0)
        if self.std == 0:
            return 0
        return (value - self.mean) / self.std


class MinMaxScaler(FeatureTransform):
    """Normaliza feature para range [0, 1]"""
    
    def __init__(self, min_val: float = 0, max_val: float = 1):
        self.min_val = min_val
        self.max_val = max_val
    
    def transform(self, data: Dict[str, Any]) -> float:
        value = data.get('value', 0)
        if self.max_val == self.min_val:
            return 0
        return (value - self.min_val) / (self.max_val - self.min_val)


class BucketTransform(FeatureTransform):
    """Discretiza feature em buckets"""
    
    def __init__(self, boundaries: List[float]):
        self.boundaries = sorted(boundaries)
    
    def transform(self, data: Dict[str, Any]) -> int:
        value = data.get('value', 0)
        for i, boundary in enumerate(self.boundaries):
            if value < boundary:
                return i
        return len(self.boundaries)


class LogTransform(FeatureTransform):
    """Aplica log1p para comprimir range"""
    
    def transform(self, data: Dict[str, Any]) -> float:
        value = data.get('value', 0)
        return np.log1p(max(0, value))


# =============================================================================
# FEATURE REGISTRY
# =============================================================================

class FeatureRegistry:
    """Registro central de features"""
    
    def __init__(self):
        self.features: Dict[str, FeatureDefinition] = {}
        self.views: Dict[str, FeatureView] = {}
        self.transforms: Dict[str, FeatureTransform] = {}
    
    def register_feature(self, feature: FeatureDefinition):
        """Registra uma feature"""
        self.features[feature.name] = feature
        logger.info(f"Registered feature: {feature.name}")
    
    def register_view(self, view: FeatureView):
        """Registra uma feature view"""
        self.views[view.name] = view
        logger.info(f"Registered view: {view.name}")
    
    def register_transform(self, name: str, transform: FeatureTransform):
        """Registra uma transformação"""
        self.transforms[name] = transform
    
    def get_feature(self, name: str) -> Optional[FeatureDefinition]:
        return self.features.get(name)
    
    def get_view(self, name: str) -> Optional[FeatureView]:
        return self.views.get(name)
    
    def list_features(self, tags: List[str] = None) -> List[str]:
        """Lista features, opcionalmente filtradas por tags"""
        if tags is None:
            return list(self.features.keys())
        
        return [
            name for name, feat in self.features.items()
            if any(t in feat.tags for t in tags)
        ]
    
    def export_schema(self) -> Dict[str, Any]:
        """Exporta schema do registry"""
        return {
            'features': {
                name: asdict(feat) 
                for name, feat in self.features.items()
            },
            'views': {
                name: asdict(view)
                for name, view in self.views.items()
            },
            'version': '1.0'
        }


# =============================================================================
# ONLINE FEATURE STORE (Cloudflare KV)
# =============================================================================

class OnlineFeatureStore:
    """
    Store online para serving de features em low-latency.
    Usa Cloudflare KV ou similar.
    """
    
    def __init__(
        self,
        kv_namespace = None,  # Cloudflare KV namespace
        redis_client = None,  # Ou Redis
        prefix: str = "features"
    ):
        self.kv = kv_namespace
        self.redis = redis_client
        self.prefix = prefix
        self._local_cache: Dict[str, Any] = {}
    
    def _make_key(self, entity_type: str, entity_id: str) -> str:
        """Cria chave para storage"""
        return f"{self.prefix}:{entity_type}:{entity_id}"
    
    async def get_features(
        self,
        entity_type: str,
        entity_id: str,
        feature_names: List[str] = None
    ) -> Optional[FeatureVector]:
        """
        Busca features para um entity.
        """
        key = self._make_key(entity_type, entity_id)
        
        # Tentar local cache primeiro
        if key in self._local_cache:
            cached = self._local_cache[key]
            if cached['expires'] > datetime.now().timestamp():
                features = cached['features']
                if feature_names:
                    features = {k: v for k, v in features.items() if k in feature_names}
                return FeatureVector(
                    entity_id=entity_id,
                    features=features,
                    timestamp=datetime.fromtimestamp(cached['timestamp'])
                )
        
        # Buscar do KV
        if self.kv:
            data = await self.kv.get(key)
            if data:
                parsed = json.loads(data)
                features = parsed['features']
                if feature_names:
                    features = {k: v for k, v in features.items() if k in feature_names}
                return FeatureVector(
                    entity_id=entity_id,
                    features=features,
                    timestamp=datetime.fromisoformat(parsed['timestamp'])
                )
        
        # Buscar do Redis
        if self.redis:
            data = self.redis.get(key)
            if data:
                parsed = json.loads(data)
                features = parsed['features']
                if feature_names:
                    features = {k: v for k, v in features.items() if k in feature_names}
                return FeatureVector(
                    entity_id=entity_id,
                    features=features,
                    timestamp=datetime.fromisoformat(parsed['timestamp'])
                )
        
        return None
    
    async def set_features(
        self,
        entity_type: str,
        entity_id: str,
        features: Dict[str, Any],
        ttl_seconds: int = 3600
    ):
        """
        Armazena features para um entity.
        """
        key = self._make_key(entity_type, entity_id)
        
        data = {
            'features': features,
            'timestamp': datetime.now().isoformat(),
            'entity_id': entity_id
        }
        
        serialized = json.dumps(data)
        
        # Local cache
        self._local_cache[key] = {
            'features': features,
            'timestamp': datetime.now().timestamp(),
            'expires': datetime.now().timestamp() + ttl_seconds
        }
        
        # KV
        if self.kv:
            await self.kv.put(key, serialized, expirationTtl=ttl_seconds)
        
        # Redis
        if self.redis:
            self.redis.setex(key, ttl_seconds, serialized)
    
    async def get_batch(
        self,
        entity_type: str,
        entity_ids: List[str],
        feature_names: List[str] = None
    ) -> Dict[str, FeatureVector]:
        """
        Busca features para múltiplos entities.
        """
        results = {}
        
        for entity_id in entity_ids:
            vector = await self.get_features(entity_type, entity_id, feature_names)
            if vector:
                results[entity_id] = vector
        
        return results


# =============================================================================
# OFFLINE FEATURE STORE (BigQuery)
# =============================================================================

class OfflineFeatureStore:
    """
    Store offline para training e batch processing.
    Usa BigQuery.
    """
    
    def __init__(self, bq_client, project_id: str, dataset_id: str = 'feature_store'):
        self.bq = bq_client
        self.project_id = project_id
        self.dataset_id = dataset_id
    
    def get_training_data(
        self,
        entity_type: str,
        entity_ids: List[str],
        feature_names: List[str],
        start_time: datetime,
        end_time: datetime
    ) -> List[Dict]:
        """
        Busca dados de training com point-in-time correctness.
        """
        features_str = ', '.join(feature_names)
        entity_ids_str = ', '.join([f"'{id}'" for id in entity_ids])
        
        query = f"""
        SELECT
            entity_id,
            feature_timestamp,
            {features_str}
        FROM `{self.project_id}.{self.dataset_id}.{entity_type}_features`
        WHERE entity_id IN ({entity_ids_str})
        AND feature_timestamp BETWEEN '{start_time.isoformat()}' AND '{end_time.isoformat()}'
        ORDER BY entity_id, feature_timestamp
        """
        
        results = []
        for row in self.bq.query(query).result():
            results.append(dict(row))
        
        return results
    
    def materialize_features(
        self,
        view: FeatureView,
        registry: FeatureRegistry,
        target_date: datetime = None
    ):
        """
        Materializa features de uma view para a tabela offline.
        """
        if target_date is None:
            target_date = datetime.now()
        
        # Construir query de materialização
        feature_selects = []
        
        for feature_name in view.features:
            feature = registry.get_feature(feature_name)
            if not feature:
                continue
            
            if feature.aggregation:
                agg_fn = feature.aggregation.value.upper()
                col = feature.source_column
                feature_selects.append(f"{agg_fn}({col}) as {feature_name}")
            else:
                feature_selects.append(f"{feature.source_column} as {feature_name}")
        
        features_sql = ', '.join(feature_selects)
        
        query = f"""
        INSERT INTO `{self.project_id}.{self.dataset_id}.{view.entity}_features`
        SELECT
            {view.entity}_id as entity_id,
            TIMESTAMP('{target_date.isoformat()}') as feature_timestamp,
            {features_sql}
        FROM `{self.project_id}.ssi_shadow.events`
        GROUP BY {view.entity}_id
        """
        
        job = self.bq.query(query)
        job.result()
        
        logger.info(f"Materialized features for view: {view.name}")


# =============================================================================
# FEATURE COMPUTATION ENGINE
# =============================================================================

class FeatureComputeEngine:
    """
    Engine para computar features em tempo real.
    """
    
    def __init__(
        self,
        registry: FeatureRegistry,
        online_store: OnlineFeatureStore
    ):
        self.registry = registry
        self.online_store = online_store
    
    async def compute_user_features(
        self,
        user_id: str,
        events: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Computa features de usuário a partir de eventos.
        """
        features = {}
        
        # Features de contagem
        features['event_count_24h'] = len(events)
        features['pageview_count'] = sum(1 for e in events if e.get('event_name') == 'PageView')
        features['product_view_count'] = sum(1 for e in events if e.get('event_name') == 'ViewContent')
        features['add_to_cart_count'] = sum(1 for e in events if e.get('event_name') == 'AddToCart')
        features['purchase_count'] = sum(1 for e in events if e.get('event_name') == 'Purchase')
        
        # Features de engagement
        if events:
            features['avg_scroll_depth'] = np.mean([
                e.get('scroll_depth', 0) for e in events
            ])
            features['avg_time_on_page'] = np.mean([
                e.get('time_on_page', 0) for e in events
            ])
            features['avg_trust_score'] = np.mean([
                e.get('trust_score', 0.5) for e in events
            ])
        else:
            features['avg_scroll_depth'] = 0
            features['avg_time_on_page'] = 0
            features['avg_trust_score'] = 0.5
        
        # Features de conversão
        features['has_purchased'] = int(features['purchase_count'] > 0)
        features['total_value'] = sum(
            float(e.get('custom_data', {}).get('value', 0)) 
            for e in events 
            if e.get('event_name') == 'Purchase'
        )
        
        # Funnel features
        features['view_to_cart_rate'] = (
            features['add_to_cart_count'] / max(1, features['product_view_count'])
        )
        features['cart_to_purchase_rate'] = (
            features['purchase_count'] / max(1, features['add_to_cart_count'])
        )
        
        # Device features
        if events:
            mobile_events = sum(1 for e in events if e.get('device_type') == 'mobile')
            features['mobile_rate'] = mobile_events / len(events)
        else:
            features['mobile_rate'] = 0
        
        # Source features
        if events:
            paid_events = sum(1 for e in events if e.get('fbclid') or e.get('gclid'))
            features['paid_traffic_rate'] = paid_events / len(events)
        else:
            features['paid_traffic_rate'] = 0
        
        # Store no online store
        await self.online_store.set_features(
            entity_type='user',
            entity_id=user_id,
            features=features,
            ttl_seconds=3600
        )
        
        return features
    
    async def compute_session_features(
        self,
        session_id: str,
        events: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Computa features de sessão.
        """
        features = {}
        
        if not events:
            return features
        
        # Duração
        timestamps = [e.get('timestamp', 0) for e in events]
        if len(timestamps) >= 2:
            features['session_duration_seconds'] = (max(timestamps) - min(timestamps)) / 1000
        else:
            features['session_duration_seconds'] = 0
        
        # Páginas
        features['pages_viewed'] = len(set(e.get('url', '') for e in events))
        
        # Engagement
        features['max_scroll_depth'] = max(e.get('scroll_depth', 0) for e in events)
        features['total_interactions'] = sum(e.get('interactions', 0) for e in events)
        
        # Intent signals
        features['viewed_product'] = int(any(e.get('event_name') == 'ViewContent' for e in events))
        features['added_to_cart'] = int(any(e.get('event_name') == 'AddToCart' for e in events))
        features['started_checkout'] = int(any(e.get('event_name') == 'InitiateCheckout' for e in events))
        
        # Store
        await self.online_store.set_features(
            entity_type='session',
            entity_id=session_id,
            features=features,
            ttl_seconds=1800  # 30 min
        )
        
        return features


# =============================================================================
# DEFAULT FEATURE DEFINITIONS
# =============================================================================

def register_default_features(registry: FeatureRegistry):
    """Registra features padrão do SSI Shadow"""
    
    # User features
    registry.register_feature(FeatureDefinition(
        name='user_event_count_24h',
        dtype=FeatureType.INT,
        description='Número de eventos nas últimas 24h',
        aggregation=AggregationType.COUNT,
        window_size='24h',
        tags=['user', 'engagement']
    ))
    
    registry.register_feature(FeatureDefinition(
        name='user_purchase_count',
        dtype=FeatureType.INT,
        description='Total de compras do usuário',
        aggregation=AggregationType.COUNT,
        tags=['user', 'conversion']
    ))
    
    registry.register_feature(FeatureDefinition(
        name='user_total_value',
        dtype=FeatureType.FLOAT,
        description='Valor total gasto pelo usuário',
        aggregation=AggregationType.SUM,
        tags=['user', 'ltv']
    ))
    
    registry.register_feature(FeatureDefinition(
        name='user_avg_trust_score',
        dtype=FeatureType.FLOAT,
        description='Trust score médio do usuário',
        aggregation=AggregationType.AVG,
        tags=['user', 'quality']
    ))
    
    registry.register_feature(FeatureDefinition(
        name='user_avg_scroll_depth',
        dtype=FeatureType.FLOAT,
        description='Scroll depth médio',
        aggregation=AggregationType.AVG,
        tags=['user', 'engagement']
    ))
    
    # Session features
    registry.register_feature(FeatureDefinition(
        name='session_duration',
        dtype=FeatureType.FLOAT,
        description='Duração da sessão em segundos',
        tags=['session']
    ))
    
    registry.register_feature(FeatureDefinition(
        name='session_pages_viewed',
        dtype=FeatureType.INT,
        description='Páginas únicas vistas na sessão',
        tags=['session', 'engagement']
    ))
    
    # Feature Views
    registry.register_view(FeatureView(
        name='user_ltv_features',
        entity='user',
        features=[
            'user_event_count_24h',
            'user_purchase_count',
            'user_total_value',
            'user_avg_trust_score',
            'user_avg_scroll_depth'
        ],
        description='Features para predição de LTV'
    ))
    
    registry.register_view(FeatureView(
        name='user_intent_features',
        entity='user',
        features=[
            'user_event_count_24h',
            'user_avg_scroll_depth',
            'user_avg_trust_score'
        ],
        description='Features para predição de intent'
    ))
    
    logger.info("Registered default features")


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    'FeatureType',
    'AggregationType',
    'FeatureDefinition',
    'FeatureView',
    'FeatureVector',
    'FeatureRegistry',
    'OnlineFeatureStore',
    'OfflineFeatureStore',
    'FeatureComputeEngine',
    'register_default_features'
]
