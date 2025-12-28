"""
S.S.I. SHADOW — LIVERAMP ATS INTEGRATION
ENTERPRISE IDENTITY RESOLUTION

LiveRamp Authenticated Traffic Solution (ATS):
- Resolve identities across devices/browsers
- Match rate 90%+ for authenticated users
- Privacy-compliant (não usa cookies terceiros)
- Integra com DSPs e plataformas

Pricing: $5k-50k/mês dependendo do volume
Docs: https://liveramp.com/our-platform/identity-resolution/
"""

import os
import json
import hashlib
import base64
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
import requests
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import hmac

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('ssi_liveramp')

# =============================================================================
# TYPES
# =============================================================================

@dataclass
class IdentityEnvelope:
    """LiveRamp RampID envelope"""
    ramp_id: str
    envelope_type: str  # 'ats' | 'idl'
    created_at: datetime
    expires_at: datetime
    source: str
    confidence: float

@dataclass
class IdentityResolutionResult:
    """Result of identity resolution"""
    success: bool
    ramp_id: Optional[str]
    envelope: Optional[str]
    match_type: str  # 'deterministic' | 'probabilistic' | 'none'
    confidence: float
    linked_ids: List[str]
    metadata: Dict[str, Any]

# =============================================================================
# LIVERAMP ATS CLIENT
# =============================================================================

class LiveRampATSClient:
    """
    LiveRamp Authenticated Traffic Solution Client
    
    Fluxo:
    1. Coletar email/phone do usuário autenticado
    2. Hash com SHA-256
    3. Enviar para LiveRamp ATS API
    4. Receber RampID (identificador universal)
    5. Usar RampID para targeting cross-platform
    """
    
    BASE_URL = "https://api.liveramp.com"
    ATS_URL = "https://ats.rlcdn.com"
    
    def __init__(
        self,
        api_key: str,
        secret_key: str,
        placement_id: str,
        environment: str = 'production'
    ):
        self.api_key = api_key
        self.secret_key = secret_key
        self.placement_id = placement_id
        self.environment = environment
        self.session = requests.Session()
        self.session.headers['Authorization'] = f'Bearer {api_key}'
    
    def _normalize_email(self, email: str) -> str:
        """Normaliza email conforme especificação LiveRamp"""
        email = email.lower().strip()
        
        # Remover pontos do local part para Gmail
        local, domain = email.split('@')
        if domain in ['gmail.com', 'googlemail.com']:
            local = local.replace('.', '')
            # Remover tudo após +
            if '+' in local:
                local = local.split('+')[0]
        
        return f"{local}@{domain}"
    
    def _normalize_phone(self, phone: str, country_code: str = '55') -> str:
        """Normaliza telefone conforme especificação LiveRamp"""
        # Remover tudo exceto dígitos
        digits = ''.join(filter(str.isdigit, phone))
        
        # Adicionar código do país se não presente
        if not digits.startswith(country_code):
            digits = country_code + digits
        
        return digits
    
    def _hash_identifier(self, identifier: str) -> str:
        """Hash SHA-256 conforme especificação LiveRamp"""
        return hashlib.sha256(identifier.encode('utf-8')).hexdigest()
    
    def _create_envelope(self, ramp_id: str) -> str:
        """
        Cria envelope encriptado para o RampID.
        Usado para passar o ID de forma segura entre sistemas.
        """
        # Gerar nonce
        nonce = os.urandom(12)
        
        # Criar chave a partir do secret
        key = hashlib.sha256(self.secret_key.encode()).digest()
        
        # Encriptar
        aesgcm = AESGCM(key)
        
        payload = json.dumps({
            'ramp_id': ramp_id,
            'timestamp': datetime.now().isoformat(),
            'placement_id': self.placement_id
        }).encode()
        
        ciphertext = aesgcm.encrypt(nonce, payload, None)
        
        # Combinar nonce + ciphertext e encodar em base64
        envelope = base64.urlsafe_b64encode(nonce + ciphertext).decode()
        
        return envelope
    
    def _generate_signature(self, timestamp: str, body: str) -> str:
        """Gera assinatura HMAC para autenticação"""
        message = f"{timestamp}.{body}"
        signature = hmac.new(
            self.secret_key.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        return signature
    
    async def resolve_identity(
        self,
        email: str = None,
        phone: str = None,
        ip: str = None,
        user_agent: str = None
    ) -> IdentityResolutionResult:
        """
        Resolve identidade usando LiveRamp ATS.
        
        Prioridade:
        1. Email hasheado (determinístico)
        2. Phone hasheado (determinístico)
        3. IP + UA (probabilístico)
        """
        identifiers = []
        
        if email:
            normalized = self._normalize_email(email)
            hashed = self._hash_identifier(normalized)
            identifiers.append({
                'type': 'email_sha256',
                'value': hashed
            })
        
        if phone:
            normalized = self._normalize_phone(phone)
            hashed = self._hash_identifier(normalized)
            identifiers.append({
                'type': 'phone_sha256',
                'value': hashed
            })
        
        if not identifiers:
            return IdentityResolutionResult(
                success=False,
                ramp_id=None,
                envelope=None,
                match_type='none',
                confidence=0.0,
                linked_ids=[],
                metadata={'error': 'No identifiers provided'}
            )
        
        # Chamar ATS API
        timestamp = datetime.utcnow().isoformat()
        
        payload = {
            'placement_id': self.placement_id,
            'identifiers': identifiers,
            'context': {
                'ip': ip,
                'user_agent': user_agent
            }
        }
        
        body = json.dumps(payload)
        signature = self._generate_signature(timestamp, body)
        
        try:
            response = self.session.post(
                f"{self.ATS_URL}/v2/identity",
                json=payload,
                headers={
                    'X-Timestamp': timestamp,
                    'X-Signature': signature,
                    'Content-Type': 'application/json'
                },
                timeout=5
            )
            
            if response.ok:
                data = response.json()
                
                ramp_id = data.get('ramp_id')
                
                if ramp_id:
                    envelope = self._create_envelope(ramp_id)
                    
                    return IdentityResolutionResult(
                        success=True,
                        ramp_id=ramp_id,
                        envelope=envelope,
                        match_type='deterministic' if email or phone else 'probabilistic',
                        confidence=data.get('confidence', 0.95),
                        linked_ids=data.get('linked_ids', []),
                        metadata={
                            'match_source': 'email' if email else 'phone',
                            'segments': data.get('segments', [])
                        }
                    )
            
            return IdentityResolutionResult(
                success=False,
                ramp_id=None,
                envelope=None,
                match_type='none',
                confidence=0.0,
                linked_ids=[],
                metadata={'error': response.text}
            )
            
        except Exception as e:
            logger.error(f"LiveRamp ATS error: {e}")
            return IdentityResolutionResult(
                success=False,
                ramp_id=None,
                envelope=None,
                match_type='none',
                confidence=0.0,
                linked_ids=[],
                metadata={'error': str(e)}
            )
    
    def get_ats_js_tag(self) -> str:
        """
        Retorna tag JavaScript para ATS.js (client-side).
        Deve ser inserida nas páginas para coleta de first-party data.
        """
        return f"""
<!-- LiveRamp ATS.js -->
<script>
!function(l,i,v,e,r,a,m,p){{l['LiveRampObject']=r;l[r]=l[r]||function(){{
(l[r].q=l[r].q||[]).push(arguments)}};l[r].l=1*new Date();a=i.createElement(v),
m=i.getElementsByTagName(v)[0];a.async=1;a.src=e;m.parentNode.insertBefore(a,m)
}}(window,document,'script','https://ats-wrapper.privacymanager.io/ats.min.js','ats');

ats('init', {{
    placementID: '{self.placement_id}',
    storageType: 'localStorage',
    logging: 'error',
    emailHashing: true
}});

// Quando usuário autenticar:
// ats('setAdditionalData', {{ email: 'user@email.com' }});
</script>
        """.strip()
    
    def get_envelope_for_dsp(self, ramp_id: str) -> Dict[str, str]:
        """
        Gera envelopes para diferentes DSPs.
        Cada DSP pode ter formato específico.
        """
        return {
            'google_dv360': self._create_envelope(ramp_id),
            'meta_ads': self._create_envelope(ramp_id),
            'thetradedesk': self._create_envelope(ramp_id),
            'amazon_dsp': self._create_envelope(ramp_id)
        }


# =============================================================================
# TRANSUNION TRUAUDIENCE INTEGRATION
# =============================================================================

class TransUnionClient:
    """
    TransUnion TruAudience Integration
    
    Similar ao LiveRamp, mas com dados offline adicionais:
    - Credit data (para B2C)
    - Property records
    - Lifestyle data
    """
    
    BASE_URL = "https://api.transunion.com/truaudience"
    
    def __init__(self, api_key: str, client_id: str):
        self.api_key = api_key
        self.client_id = client_id
        self.session = requests.Session()
    
    def enrich_identity(
        self,
        email_hash: str = None,
        phone_hash: str = None,
        address_hash: str = None
    ) -> Dict[str, Any]:
        """
        Enriquece identidade com dados offline.
        """
        payload = {
            'client_id': self.client_id,
            'identifiers': {}
        }
        
        if email_hash:
            payload['identifiers']['email_sha256'] = email_hash
        if phone_hash:
            payload['identifiers']['phone_sha256'] = phone_hash
        if address_hash:
            payload['identifiers']['address_sha256'] = address_hash
        
        try:
            response = self.session.post(
                f"{self.BASE_URL}/v1/enrich",
                json=payload,
                headers={
                    'Authorization': f'Bearer {self.api_key}',
                    'Content-Type': 'application/json'
                },
                timeout=10
            )
            
            if response.ok:
                data = response.json()
                return {
                    'success': True,
                    'tru_id': data.get('tru_id'),
                    'segments': data.get('segments', []),
                    'demographics': data.get('demographics', {}),
                    'household': data.get('household', {}),
                    'confidence': data.get('confidence', 0)
                }
                
        except Exception as e:
            logger.error(f"TransUnion error: {e}")
        
        return {'success': False}


# =============================================================================
# UNIFIED IDENTITY SERVICE
# =============================================================================

class UnifiedIdentityService:
    """
    Serviço unificado de Identity Resolution.
    Combina múltiplas fontes para máximo match rate.
    """
    
    def __init__(
        self,
        liveramp_client: LiveRampATSClient = None,
        transunion_client: TransUnionClient = None,
        fingerprint_client = None  # FingerprintJS Pro
    ):
        self.liveramp = liveramp_client
        self.transunion = transunion_client
        self.fingerprint = fingerprint_client
    
    async def resolve(
        self,
        email: str = None,
        phone: str = None,
        ip: str = None,
        user_agent: str = None,
        fingerprint_id: str = None
    ) -> Dict[str, Any]:
        """
        Resolve identidade usando todas as fontes disponíveis.
        
        Hierarquia:
        1. LiveRamp (email/phone) - Determinístico 95%+
        2. TransUnion (enriquecimento) - Dados offline
        3. FingerprintJS (device) - Cross-browser 99%
        4. Probabilístico (IP+UA) - Fallback 60-70%
        """
        result = {
            'resolved': False,
            'identities': {},
            'confidence': 0,
            'method': 'none',
            'enrichment': {}
        }
        
        # 1. LiveRamp
        if self.liveramp and (email or phone):
            lr_result = await self.liveramp.resolve_identity(
                email=email,
                phone=phone,
                ip=ip,
                user_agent=user_agent
            )
            
            if lr_result.success:
                result['identities']['ramp_id'] = lr_result.ramp_id
                result['identities']['envelope'] = lr_result.envelope
                result['confidence'] = max(result['confidence'], lr_result.confidence)
                result['method'] = 'liveramp_deterministic'
                result['resolved'] = True
        
        # 2. TransUnion (enriquecimento adicional)
        if self.transunion and result['resolved']:
            email_hash = hashlib.sha256(email.encode()).hexdigest() if email else None
            tu_result = self.transunion.enrich_identity(email_hash=email_hash)
            
            if tu_result.get('success'):
                result['enrichment']['transunion'] = {
                    'segments': tu_result.get('segments', []),
                    'demographics': tu_result.get('demographics', {})
                }
        
        # 3. FingerprintJS
        if fingerprint_id:
            result['identities']['fingerprint_id'] = fingerprint_id
            if not result['resolved']:
                result['confidence'] = 0.85
                result['method'] = 'fingerprint'
                result['resolved'] = True
        
        # 4. Probabilístico
        if not result['resolved'] and ip and user_agent:
            # Fallback para hash probabilístico
            prob_id = hashlib.md5(f"{ip}:{user_agent}".encode()).hexdigest()[:16]
            result['identities']['probabilistic_id'] = prob_id
            result['confidence'] = 0.5
            result['method'] = 'probabilistic'
            result['resolved'] = True
        
        return result


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    'LiveRampATSClient',
    'TransUnionClient',
    'UnifiedIdentityService',
    'IdentityResolutionResult'
]
