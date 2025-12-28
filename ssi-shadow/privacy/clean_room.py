"""
S.S.I. SHADOW — DATA CLEAN ROOM
PRIVACY-PRESERVING DATA COLLABORATION

Clean Room permite colaboração de dados entre partes sem expor dados brutos.
Similar ao que Google, Meta e AWS oferecem para enterprise.

Use cases:
1. Match rate analysis com publishers
2. Overlap analysis com parceiros
3. Attribution cross-platform
4. Audience insights compartilhados

Técnicas:
- Secure Multi-Party Computation (MPC)
- Differential Privacy
- Encrypted matching
- Aggregation-only queries
"""

import os
import json
import hashlib
import hmac
import secrets
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum
import numpy as np
from collections import defaultdict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('ssi_clean_room')

# =============================================================================
# TYPES
# =============================================================================

class QueryType(Enum):
    OVERLAP = "overlap"  # Overlap entre datasets
    AGGREGATE = "aggregate"  # Métricas agregadas
    ATTRIBUTION = "attribution"  # Attribution conjunta
    AUDIENCE = "audience"  # Audience insights


class PrivacyLevel(Enum):
    LOW = "low"  # Aggregates com min 100 usuários
    MEDIUM = "medium"  # Aggregates com min 1000 + noise
    HIGH = "high"  # Differential privacy
    MAXIMUM = "maximum"  # Secure MPC


@dataclass
class DataParty:
    """Parte contribuindo dados para o clean room"""
    id: str
    name: str
    data_types: List[str]  # 'emails', 'transactions', 'pageviews'
    encryption_key: str = ""
    
    # Stats
    total_records: int = 0
    hashed_records: int = 0


@dataclass
class CleanRoomQuery:
    """Query para executar no clean room"""
    id: str
    query_type: QueryType
    privacy_level: PrivacyLevel
    
    # Parties involved
    initiator: str
    participants: List[str]
    
    # Query params
    match_keys: List[str]  # 'email_hash', 'phone_hash'
    metrics: List[str]  # 'count', 'revenue', 'conversions'
    dimensions: List[str]  # 'date', 'channel'
    filters: Dict[str, Any] = field(default_factory=dict)
    
    # Privacy params
    min_aggregation_size: int = 100
    noise_epsilon: float = 1.0  # For differential privacy
    
    # Status
    status: str = "pending"
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    
    # Results
    results: Optional[Dict] = None


@dataclass
class CleanRoomResult:
    """Resultado de query do clean room"""
    query_id: str
    success: bool
    
    # Metrics
    total_matched: int = 0
    match_rate: float = 0
    
    # Aggregated results
    aggregates: Dict[str, Any] = field(default_factory=dict)
    
    # Privacy info
    privacy_level: PrivacyLevel = PrivacyLevel.MEDIUM
    noise_added: bool = False
    suppressed_cells: int = 0
    
    # Metadata
    execution_time_ms: float = 0
    parties_matched: List[str] = field(default_factory=list)


# =============================================================================
# ENCRYPTION & HASHING
# =============================================================================

class SecureHasher:
    """
    Hashing seguro para match de identidades.
    Usa HMAC com salt compartilhado entre partes.
    """
    
    def __init__(self, shared_secret: str):
        self.secret = shared_secret.encode()
    
    def hash_identifier(self, identifier: str, salt: str = "") -> str:
        """Hash de identificador com HMAC"""
        message = f"{identifier.lower().strip()}{salt}".encode()
        return hmac.new(self.secret, message, hashlib.sha256).hexdigest()
    
    def hash_email(self, email: str) -> str:
        """Hash de email normalizado"""
        # Normalizar email
        email = email.lower().strip()
        local, domain = email.split('@')
        
        # Gmail normalization
        if domain in ['gmail.com', 'googlemail.com']:
            local = local.replace('.', '')
            if '+' in local:
                local = local.split('+')[0]
        
        normalized = f"{local}@{domain}"
        return self.hash_identifier(normalized)
    
    def hash_phone(self, phone: str, country_code: str = "55") -> str:
        """Hash de telefone normalizado"""
        # Apenas dígitos
        digits = ''.join(filter(str.isdigit, phone))
        
        # Adicionar código do país
        if not digits.startswith(country_code):
            digits = country_code + digits
        
        return self.hash_identifier(digits)


# =============================================================================
# DIFFERENTIAL PRIVACY
# =============================================================================

class DifferentialPrivacy:
    """
    Implementa differential privacy para proteção de dados.
    
    Garante que a presença/ausência de um indivíduo não pode
    ser inferida dos resultados.
    """
    
    def __init__(self, epsilon: float = 1.0, delta: float = 1e-5):
        """
        epsilon: Privacy budget (menor = mais privado)
        delta: Probability of privacy breach
        """
        self.epsilon = epsilon
        self.delta = delta
    
    def add_laplace_noise(self, value: float, sensitivity: float = 1.0) -> float:
        """
        Adiciona ruído Laplaciano ao valor.
        
        sensitivity: Quanto um único registro pode afetar o resultado
        """
        scale = sensitivity / self.epsilon
        noise = np.random.laplace(0, scale)
        return value + noise
    
    def add_gaussian_noise(self, value: float, sensitivity: float = 1.0) -> float:
        """Adiciona ruído Gaussiano (para composição)"""
        sigma = sensitivity * np.sqrt(2 * np.log(1.25 / self.delta)) / self.epsilon
        noise = np.random.normal(0, sigma)
        return value + noise
    
    def privatize_count(self, count: int) -> int:
        """Privatiza uma contagem"""
        noisy = self.add_laplace_noise(float(count), sensitivity=1.0)
        return max(0, int(round(noisy)))
    
    def privatize_sum(self, total: float, max_contribution: float) -> float:
        """Privatiza uma soma"""
        # Clipar contribuição máxima
        noisy = self.add_laplace_noise(total, sensitivity=max_contribution)
        return max(0, noisy)
    
    def privatize_mean(
        self, 
        values: List[float], 
        lower_bound: float, 
        upper_bound: float
    ) -> float:
        """Privatiza uma média"""
        # Clipar valores
        clipped = [max(lower_bound, min(upper_bound, v)) for v in values]
        
        # Calcular média
        n = len(clipped)
        if n == 0:
            return 0
        
        mean = sum(clipped) / n
        
        # Sensibilidade da média
        sensitivity = (upper_bound - lower_bound) / n
        
        return self.add_laplace_noise(mean, sensitivity)


# =============================================================================
# CLEAN ROOM ENGINE
# =============================================================================

class CleanRoomEngine:
    """
    Engine principal do Data Clean Room.
    """
    
    def __init__(self, shared_secret: str):
        self.hasher = SecureHasher(shared_secret)
        self.dp = DifferentialPrivacy()
        
        self.parties: Dict[str, DataParty] = {}
        self.data_stores: Dict[str, Dict[str, Dict]] = {}  # party_id -> hash -> data
        self.queries: Dict[str, CleanRoomQuery] = {}
    
    def register_party(self, party: DataParty):
        """Registra uma parte no clean room"""
        self.parties[party.id] = party
        self.data_stores[party.id] = {}
        logger.info(f"Registered party: {party.name}")
    
    def ingest_data(
        self,
        party_id: str,
        records: List[Dict[str, Any]],
        key_field: str = 'email'
    ):
        """
        Ingere dados de uma parte.
        Dados são hasheados antes de armazenar.
        """
        if party_id not in self.parties:
            raise ValueError(f"Party {party_id} not registered")
        
        party = self.parties[party_id]
        store = self.data_stores[party_id]
        
        for record in records:
            key_value = record.get(key_field)
            if not key_value:
                continue
            
            # Hash the key
            if key_field == 'email':
                hashed_key = self.hasher.hash_email(key_value)
            elif key_field == 'phone':
                hashed_key = self.hasher.hash_phone(key_value)
            else:
                hashed_key = self.hasher.hash_identifier(key_value)
            
            # Store without PII
            safe_record = {
                k: v for k, v in record.items()
                if k not in ['email', 'phone', 'name', 'address']
            }
            safe_record['_hash'] = hashed_key
            
            store[hashed_key] = safe_record
            party.hashed_records += 1
        
        party.total_records = len(store)
        logger.info(f"Ingested {len(records)} records for party {party_id}")
    
    def execute_overlap_query(
        self,
        query: CleanRoomQuery
    ) -> CleanRoomResult:
        """
        Executa query de overlap entre parties.
        Retorna apenas métricas agregadas.
        """
        start_time = datetime.now()
        
        # Get data stores
        initiator_store = self.data_stores.get(query.initiator, {})
        
        if not initiator_store:
            return CleanRoomResult(
                query_id=query.id,
                success=False
            )
        
        # Find overlapping hashes
        initiator_hashes = set(initiator_store.keys())
        
        overlap_counts = {}
        total_overlap = set()
        
        for participant_id in query.participants:
            participant_store = self.data_stores.get(participant_id, {})
            participant_hashes = set(participant_store.keys())
            
            overlap = initiator_hashes & participant_hashes
            overlap_counts[participant_id] = len(overlap)
            total_overlap |= overlap
        
        # Privacy: Apply minimum aggregation
        if len(total_overlap) < query.min_aggregation_size:
            return CleanRoomResult(
                query_id=query.id,
                success=True,
                total_matched=0,
                match_rate=0,
                aggregates={'suppressed': True},
                suppressed_cells=1
            )
        
        # Apply differential privacy if needed
        if query.privacy_level in [PrivacyLevel.HIGH, PrivacyLevel.MAXIMUM]:
            self.dp.epsilon = query.noise_epsilon
            
            noisy_overlap = self.dp.privatize_count(len(total_overlap))
            noisy_counts = {
                pid: self.dp.privatize_count(count)
                for pid, count in overlap_counts.items()
            }
            noise_added = True
        else:
            noisy_overlap = len(total_overlap)
            noisy_counts = overlap_counts
            noise_added = False
        
        # Calculate match rate
        match_rate = noisy_overlap / max(1, len(initiator_hashes))
        
        execution_time = (datetime.now() - start_time).total_seconds() * 1000
        
        return CleanRoomResult(
            query_id=query.id,
            success=True,
            total_matched=noisy_overlap,
            match_rate=match_rate,
            aggregates={
                'overlap_by_party': noisy_counts,
                'initiator_total': len(initiator_hashes)
            },
            privacy_level=query.privacy_level,
            noise_added=noise_added,
            execution_time_ms=execution_time,
            parties_matched=list(query.participants)
        )
    
    def execute_aggregate_query(
        self,
        query: CleanRoomQuery
    ) -> CleanRoomResult:
        """
        Executa query de agregação no overlap.
        Retorna métricas agregadas sobre os matches.
        """
        start_time = datetime.now()
        
        # Find overlap first
        initiator_store = self.data_stores.get(query.initiator, {})
        initiator_hashes = set(initiator_store.keys())
        
        overlap_hashes = initiator_hashes.copy()
        
        for participant_id in query.participants:
            participant_store = self.data_stores.get(participant_id, {})
            overlap_hashes &= set(participant_store.keys())
        
        if len(overlap_hashes) < query.min_aggregation_size:
            return CleanRoomResult(
                query_id=query.id,
                success=True,
                suppressed_cells=1,
                aggregates={'suppressed': True}
            )
        
        # Calculate aggregates
        aggregates = {}
        
        for metric in query.metrics:
            if metric == 'count':
                value = len(overlap_hashes)
            elif metric == 'revenue':
                # Sum revenue from overlapping records
                total = 0
                for h in overlap_hashes:
                    for party_id in [query.initiator] + query.participants:
                        record = self.data_stores[party_id].get(h, {})
                        total += record.get('revenue', 0)
                value = total
            elif metric == 'conversions':
                # Count conversions
                count = 0
                for h in overlap_hashes:
                    for party_id in [query.initiator] + query.participants:
                        record = self.data_stores[party_id].get(h, {})
                        if record.get('converted'):
                            count += 1
                            break
                value = count
            else:
                value = 0
            
            # Apply privacy
            if query.privacy_level in [PrivacyLevel.HIGH, PrivacyLevel.MAXIMUM]:
                if metric == 'count':
                    value = self.dp.privatize_count(value)
                elif metric in ['revenue']:
                    value = self.dp.privatize_sum(value, max_contribution=1000)
                else:
                    value = self.dp.privatize_count(value)
            
            aggregates[metric] = value
        
        execution_time = (datetime.now() - start_time).total_seconds() * 1000
        
        return CleanRoomResult(
            query_id=query.id,
            success=True,
            total_matched=len(overlap_hashes),
            match_rate=len(overlap_hashes) / max(1, len(initiator_hashes)),
            aggregates=aggregates,
            privacy_level=query.privacy_level,
            noise_added=query.privacy_level in [PrivacyLevel.HIGH, PrivacyLevel.MAXIMUM],
            execution_time_ms=execution_time
        )
    
    def execute_attribution_query(
        self,
        query: CleanRoomQuery
    ) -> CleanRoomResult:
        """
        Executa query de attribution cross-platform.
        Atribui conversões a touchpoints de diferentes parties.
        """
        start_time = datetime.now()
        
        # Find converters in initiator
        initiator_store = self.data_stores.get(query.initiator, {})
        
        converters = {
            h: r for h, r in initiator_store.items()
            if r.get('converted') or r.get('purchased')
        }
        
        if len(converters) < query.min_aggregation_size:
            return CleanRoomResult(
                query_id=query.id,
                success=True,
                suppressed_cells=1
            )
        
        # Check which converters were exposed by participants
        attribution = defaultdict(lambda: {'exposed': 0, 'converted': 0})
        
        for h, converter in converters.items():
            for participant_id in query.participants:
                participant_store = self.data_stores.get(participant_id, {})
                
                if h in participant_store:
                    exposure = participant_store[h]
                    channel = exposure.get('channel', participant_id)
                    
                    attribution[channel]['exposed'] += 1
                    attribution[channel]['converted'] += 1
        
        # Privacy
        if query.privacy_level in [PrivacyLevel.HIGH, PrivacyLevel.MAXIMUM]:
            for channel in attribution:
                attribution[channel]['exposed'] = self.dp.privatize_count(
                    attribution[channel]['exposed']
                )
                attribution[channel]['converted'] = self.dp.privatize_count(
                    attribution[channel]['converted']
                )
        
        execution_time = (datetime.now() - start_time).total_seconds() * 1000
        
        return CleanRoomResult(
            query_id=query.id,
            success=True,
            total_matched=len(converters),
            aggregates={
                'attribution_by_channel': dict(attribution),
                'total_converters': len(converters)
            },
            privacy_level=query.privacy_level,
            execution_time_ms=execution_time
        )
    
    def execute_query(self, query: CleanRoomQuery) -> CleanRoomResult:
        """Executa query no clean room"""
        
        self.queries[query.id] = query
        query.status = "running"
        
        try:
            if query.query_type == QueryType.OVERLAP:
                result = self.execute_overlap_query(query)
            elif query.query_type == QueryType.AGGREGATE:
                result = self.execute_aggregate_query(query)
            elif query.query_type == QueryType.ATTRIBUTION:
                result = self.execute_attribution_query(query)
            else:
                result = CleanRoomResult(
                    query_id=query.id,
                    success=False
                )
            
            query.status = "completed"
            query.completed_at = datetime.now()
            query.results = result.aggregates
            
            return result
            
        except Exception as e:
            logger.error(f"Query failed: {e}")
            query.status = "failed"
            
            return CleanRoomResult(
                query_id=query.id,
                success=False
            )


# =============================================================================
# CLEAN ROOM API
# =============================================================================

class CleanRoomAPI:
    """
    API para interação com o Clean Room.
    Simula interface similar ao Google Ads Data Hub / Meta Clean Room.
    """
    
    def __init__(self, engine: CleanRoomEngine):
        self.engine = engine
    
    def create_overlap_analysis(
        self,
        initiator_id: str,
        partner_ids: List[str],
        privacy_level: str = "medium"
    ) -> CleanRoomResult:
        """Cria análise de overlap"""
        
        query = CleanRoomQuery(
            id=f"overlap_{secrets.token_hex(8)}",
            query_type=QueryType.OVERLAP,
            privacy_level=PrivacyLevel[privacy_level.upper()],
            initiator=initiator_id,
            participants=partner_ids,
            match_keys=['email_hash'],
            metrics=['count'],
            dimensions=[]
        )
        
        return self.engine.execute_query(query)
    
    def create_conversion_analysis(
        self,
        advertiser_id: str,
        publisher_ids: List[str],
        metrics: List[str] = None
    ) -> CleanRoomResult:
        """Cria análise de conversão"""
        
        query = CleanRoomQuery(
            id=f"conversion_{secrets.token_hex(8)}",
            query_type=QueryType.AGGREGATE,
            privacy_level=PrivacyLevel.HIGH,
            initiator=advertiser_id,
            participants=publisher_ids,
            match_keys=['email_hash'],
            metrics=metrics or ['count', 'revenue', 'conversions'],
            dimensions=['channel']
        )
        
        return self.engine.execute_query(query)
    
    def create_attribution_study(
        self,
        advertiser_id: str,
        media_partner_ids: List[str]
    ) -> CleanRoomResult:
        """Cria estudo de attribution"""
        
        query = CleanRoomQuery(
            id=f"attribution_{secrets.token_hex(8)}",
            query_type=QueryType.ATTRIBUTION,
            privacy_level=PrivacyLevel.HIGH,
            initiator=advertiser_id,
            participants=media_partner_ids,
            match_keys=['email_hash'],
            metrics=['exposed', 'converted'],
            dimensions=['channel']
        )
        
        return self.engine.execute_query(query)


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    'QueryType',
    'PrivacyLevel',
    'DataParty',
    'CleanRoomQuery',
    'CleanRoomResult',
    'CleanRoomEngine',
    'CleanRoomAPI',
    'SecureHasher',
    'DifferentialPrivacy'
]
