"""
S.S.I. SHADOW - LangChain Copy Architect (C8)
=============================================

Geração automática de copies de anúncios usando LangChain + Claude/GPT.
Cria variações otimizadas baseadas em performance histórica.

Features:
- Geração de headlines, primary text, CTAs
- Variações A/B automáticas
- Tone adaptation (urgent, aspirational, etc.)
- Performance-based learning
- Multi-language support
- Brand voice consistency

Uso:
    architect = CopyArchitect()
    
    # Gerar copy completo
    copy = await architect.generate_ad_copy(
        product_name='Tênis Runner Pro',
        product_description='Tênis de corrida com amortecimento...',
        target_audience='Corredores amadores 25-45 anos',
        tone='aspirational',
        platform='meta'
    )
    
    # Gerar variações
    variations = await architect.generate_variations(
        original_copy='Corra mais longe...',
        num_variations=5
    )

Author: SSI Shadow Team
Version: 1.0.0
"""

import os
import json
import asyncio
import logging
import re
from datetime import datetime
from typing import Optional, Dict, List, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod

# LangChain
try:
    from langchain.prompts import PromptTemplate, ChatPromptTemplate
    from langchain.chains import LLMChain
    from langchain.output_parsers import PydanticOutputParser
    from langchain_core.messages import HumanMessage, SystemMessage
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False

# LLM Providers
try:
    from langchain_anthropic import ChatAnthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    ChatAnthropic = None

try:
    from langchain_openai import ChatOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    ChatOpenAI = None

# Pydantic for structured output
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('copy_architect')


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class CopyArchitectConfig:
    """Configuration for copy generation."""
    
    # LLM Settings
    default_provider: str = field(default_factory=lambda: os.getenv('LLM_PROVIDER', 'anthropic'))
    anthropic_model: str = field(default_factory=lambda: os.getenv('ANTHROPIC_MODEL', 'claude-3-sonnet-20240229'))
    openai_model: str = field(default_factory=lambda: os.getenv('OPENAI_MODEL', 'gpt-4-turbo-preview'))
    temperature: float = 0.7
    max_tokens: int = 2000
    
    # API Keys
    anthropic_api_key: str = field(default_factory=lambda: os.getenv('ANTHROPIC_API_KEY', ''))
    openai_api_key: str = field(default_factory=lambda: os.getenv('OPENAI_API_KEY', ''))
    
    # Generation Settings
    default_language: str = 'pt-BR'
    max_headline_length: int = 40
    max_primary_text_length: int = 125
    max_description_length: int = 30
    
    # A/B Testing
    default_variations: int = 3


config = CopyArchitectConfig()


# =============================================================================
# DATA CLASSES
# =============================================================================

class CopyTone(Enum):
    """Available copy tones."""
    URGENT = "urgent"
    ASPIRATIONAL = "aspirational"
    INFORMATIONAL = "informational"
    PLAYFUL = "playful"
    TRUSTWORTHY = "trustworthy"
    EXCLUSIVE = "exclusive"
    FOMO = "fomo"
    EMOTIONAL = "emotional"
    PROFESSIONAL = "professional"


class AdPlatform(Enum):
    """Target ad platforms."""
    META = "meta"
    GOOGLE = "google"
    TIKTOK = "tiktok"
    LINKEDIN = "linkedin"
    TWITTER = "twitter"


# Pydantic models for structured output
class AdCopy(BaseModel):
    """Single ad copy."""
    headline: str = Field(description="Main headline (max 40 chars)")
    primary_text: str = Field(description="Primary text/body (max 125 chars)")
    description: str = Field(description="Short description (max 30 chars)")
    cta: str = Field(description="Call to action text")
    
    # Metadata
    tone: str = Field(default="", description="Tone used")
    language: str = Field(default="pt-BR", description="Language code")
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'headline': self.headline,
            'primary_text': self.primary_text,
            'description': self.description,
            'cta': self.cta,
            'tone': self.tone,
            'language': self.language,
        }


class AdCopySet(BaseModel):
    """Set of ad copy variations."""
    copies: List[AdCopy] = Field(description="List of ad copy variations")
    product_name: str = Field(default="", description="Product name")
    target_audience: str = Field(default="", description="Target audience")


@dataclass
class CopyGenerationResult:
    """Result of copy generation."""
    copies: List[AdCopy]
    prompt_used: str
    model_used: str
    generation_time_ms: float
    tokens_used: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'copies': [c.to_dict() for c in self.copies],
            'model': self.model_used,
            'generation_time_ms': self.generation_time_ms,
        }


# =============================================================================
# PROMPTS
# =============================================================================

SYSTEM_PROMPT = """You are an expert advertising copywriter specializing in digital marketing.
You create compelling, conversion-focused ad copy for social media and search platforms.

Your copy should:
- Be concise and impactful
- Include clear calls to action
- Appeal to emotions while being authentic
- Follow platform best practices
- Never be misleading or make false claims

You always respond in the specified language and tone."""

COPY_GENERATION_PROMPT = """Create {num_variations} ad copy variations for the following product:

**Product:** {product_name}
**Description:** {product_description}
**Target Audience:** {target_audience}
**Tone:** {tone}
**Platform:** {platform}
**Language:** {language}

**Constraints:**
- Headline: max {max_headline} characters
- Primary Text: max {max_primary_text} characters  
- Description: max {max_description} characters

**Additional Instructions:** {additional_instructions}

Return ONLY a valid JSON array with the following structure for each variation:
[
  {{
    "headline": "...",
    "primary_text": "...",
    "description": "...",
    "cta": "..."
  }}
]

Make each variation distinctly different in approach while maintaining the core message."""

VARIATION_PROMPT = """Create {num_variations} variations of this ad copy:

**Original Copy:**
Headline: {original_headline}
Primary Text: {original_primary_text}
Description: {original_description}
CTA: {original_cta}

**Instructions:**
- Keep the core message but vary the approach
- Try different emotional angles
- Experiment with different CTAs
- Maintain the same language: {language}

Return ONLY a valid JSON array with the structure shown above."""

TONE_GUIDELINES = {
    CopyTone.URGENT: "Create urgency with time-limited offers, scarcity, or immediate action needed.",
    CopyTone.ASPIRATIONAL: "Focus on dreams, goals, and the better version of themselves the customer can become.",
    CopyTone.INFORMATIONAL: "Lead with facts, features, and clear benefits. Be straightforward.",
    CopyTone.PLAYFUL: "Use humor, wordplay, and a light-hearted approach. Be fun but not silly.",
    CopyTone.TRUSTWORTHY: "Emphasize reliability, guarantees, social proof, and established track record.",
    CopyTone.EXCLUSIVE: "Make the audience feel special. Emphasize exclusivity and premium quality.",
    CopyTone.FOMO: "Highlight what they'll miss out on. Use social proof and popularity.",
    CopyTone.EMOTIONAL: "Connect on an emotional level. Tell a story. Create empathy.",
    CopyTone.PROFESSIONAL: "Be polished and business-like. Focus on ROI and professional benefits.",
}

PLATFORM_GUIDELINES = {
    AdPlatform.META: "Facebook/Instagram: Conversational, visual-focused, emoji-friendly. Hook in first line.",
    AdPlatform.GOOGLE: "Search Ads: Keyword-focused, benefit-driven, include numbers/stats.",
    AdPlatform.TIKTOK: "TikTok: Trendy, authentic, young voice. Start with hook. Use trending phrases.",
    AdPlatform.LINKEDIN: "LinkedIn: Professional, B2B focused, career/business benefits.",
    AdPlatform.TWITTER: "Twitter/X: Punchy, concise, personality-driven. Hashtag-aware.",
}


# =============================================================================
# LLM PROVIDERS
# =============================================================================

class LLMProvider(ABC):
    """Abstract LLM provider."""
    
    @abstractmethod
    async def generate(self, prompt: str, system_prompt: str = None) -> Tuple[str, int]:
        """Generate text from prompt. Returns (text, tokens_used)."""
        pass


class AnthropicProvider(LLMProvider):
    """Anthropic Claude provider."""
    
    def __init__(self, model: str = None, api_key: str = None):
        if not ANTHROPIC_AVAILABLE:
            raise RuntimeError("langchain-anthropic not installed")
        
        self.model = model or config.anthropic_model
        self.api_key = api_key or config.anthropic_api_key
        
        self.llm = ChatAnthropic(
            model=self.model,
            anthropic_api_key=self.api_key,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
        )
    
    async def generate(self, prompt: str, system_prompt: str = None) -> Tuple[str, int]:
        messages = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=prompt))
        
        # Run in executor for async
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self.llm.invoke(messages)
        )
        
        tokens = response.response_metadata.get('usage', {}).get('total_tokens', 0)
        return response.content, tokens


class OpenAIProvider(LLMProvider):
    """OpenAI GPT provider."""
    
    def __init__(self, model: str = None, api_key: str = None):
        if not OPENAI_AVAILABLE:
            raise RuntimeError("langchain-openai not installed")
        
        self.model = model or config.openai_model
        self.api_key = api_key or config.openai_api_key
        
        self.llm = ChatOpenAI(
            model=self.model,
            openai_api_key=self.api_key,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
        )
    
    async def generate(self, prompt: str, system_prompt: str = None) -> Tuple[str, int]:
        messages = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=prompt))
        
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self.llm.invoke(messages)
        )
        
        tokens = response.response_metadata.get('token_usage', {}).get('total_tokens', 0)
        return response.content, tokens


def get_llm_provider(provider: str = None) -> LLMProvider:
    """Get LLM provider by name."""
    provider = provider or config.default_provider
    
    if provider == 'anthropic' and ANTHROPIC_AVAILABLE:
        return AnthropicProvider()
    elif provider == 'openai' and OPENAI_AVAILABLE:
        return OpenAIProvider()
    elif ANTHROPIC_AVAILABLE:
        return AnthropicProvider()
    elif OPENAI_AVAILABLE:
        return OpenAIProvider()
    else:
        raise RuntimeError("No LLM provider available")


# =============================================================================
# COPY ARCHITECT
# =============================================================================

class CopyArchitect:
    """
    Main copy generation engine.
    
    Uses LangChain with Claude/GPT to generate optimized ad copies.
    """
    
    def __init__(self, provider: str = None):
        self.provider = get_llm_provider(provider)
        self.generation_history: List[CopyGenerationResult] = []
    
    def _parse_json_response(self, response: str) -> List[Dict]:
        """Parse JSON from LLM response."""
        # Try to find JSON array in response
        json_match = re.search(r'\[[\s\S]*\]', response)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass
        
        # Try parsing entire response
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass
        
        # Fallback: extract individual objects
        objects = re.findall(r'\{[^{}]+\}', response)
        result = []
        for obj in objects:
            try:
                result.append(json.loads(obj))
            except:
                continue
        
        return result
    
    def _build_system_prompt(self, tone: CopyTone, platform: AdPlatform) -> str:
        """Build system prompt with tone and platform guidelines."""
        parts = [SYSTEM_PROMPT]
        
        if tone in TONE_GUIDELINES:
            parts.append(f"\n**Tone Guidelines ({tone.value}):** {TONE_GUIDELINES[tone]}")
        
        if platform in PLATFORM_GUIDELINES:
            parts.append(f"\n**Platform Guidelines ({platform.value}):** {PLATFORM_GUIDELINES[platform]}")
        
        return "\n".join(parts)
    
    async def generate_ad_copy(
        self,
        product_name: str,
        product_description: str,
        target_audience: str,
        tone: str = 'aspirational',
        platform: str = 'meta',
        language: str = None,
        num_variations: int = None,
        additional_instructions: str = ""
    ) -> CopyGenerationResult:
        """
        Generate ad copy variations.
        
        Args:
            product_name: Name of the product/service
            product_description: Detailed description
            target_audience: Target audience description
            tone: Copy tone (see CopyTone enum)
            platform: Target platform (see AdPlatform enum)
            language: Target language (default: pt-BR)
            num_variations: Number of variations (default: 3)
            additional_instructions: Extra instructions
            
        Returns:
            CopyGenerationResult with generated copies
        """
        start_time = datetime.utcnow()
        
        # Parse enums
        try:
            tone_enum = CopyTone(tone)
        except ValueError:
            tone_enum = CopyTone.ASPIRATIONAL
        
        try:
            platform_enum = AdPlatform(platform)
        except ValueError:
            platform_enum = AdPlatform.META
        
        language = language or config.default_language
        num_variations = num_variations or config.default_variations
        
        # Build prompts
        system_prompt = self._build_system_prompt(tone_enum, platform_enum)
        
        user_prompt = COPY_GENERATION_PROMPT.format(
            num_variations=num_variations,
            product_name=product_name,
            product_description=product_description,
            target_audience=target_audience,
            tone=tone,
            platform=platform,
            language=language,
            max_headline=config.max_headline_length,
            max_primary_text=config.max_primary_text_length,
            max_description=config.max_description_length,
            additional_instructions=additional_instructions or "None",
        )
        
        # Generate
        response, tokens = await self.provider.generate(user_prompt, system_prompt)
        
        # Parse response
        parsed = self._parse_json_response(response)
        
        copies = []
        for item in parsed:
            try:
                copy = AdCopy(
                    headline=item.get('headline', '')[:config.max_headline_length],
                    primary_text=item.get('primary_text', '')[:config.max_primary_text_length],
                    description=item.get('description', '')[:config.max_description_length],
                    cta=item.get('cta', 'Saiba Mais'),
                    tone=tone,
                    language=language,
                )
                copies.append(copy)
            except Exception as e:
                logger.warning(f"Failed to parse copy: {e}")
        
        # Build result
        duration = (datetime.utcnow() - start_time).total_seconds() * 1000
        
        result = CopyGenerationResult(
            copies=copies,
            prompt_used=user_prompt,
            model_used=getattr(self.provider, 'model', 'unknown'),
            generation_time_ms=duration,
            tokens_used=tokens,
        )
        
        self.generation_history.append(result)
        
        return result
    
    async def generate_variations(
        self,
        original_headline: str,
        original_primary_text: str,
        original_description: str = "",
        original_cta: str = "Saiba Mais",
        num_variations: int = None,
        language: str = None
    ) -> CopyGenerationResult:
        """
        Generate variations of existing copy.
        
        Args:
            original_*: Original copy components
            num_variations: Number of variations
            language: Target language
            
        Returns:
            CopyGenerationResult with variations
        """
        start_time = datetime.utcnow()
        
        num_variations = num_variations or config.default_variations
        language = language or config.default_language
        
        prompt = VARIATION_PROMPT.format(
            num_variations=num_variations,
            original_headline=original_headline,
            original_primary_text=original_primary_text,
            original_description=original_description,
            original_cta=original_cta,
            language=language,
        )
        
        response, tokens = await self.provider.generate(prompt, SYSTEM_PROMPT)
        
        parsed = self._parse_json_response(response)
        
        copies = []
        for item in parsed:
            try:
                copy = AdCopy(
                    headline=item.get('headline', '')[:config.max_headline_length],
                    primary_text=item.get('primary_text', '')[:config.max_primary_text_length],
                    description=item.get('description', '')[:config.max_description_length],
                    cta=item.get('cta', 'Saiba Mais'),
                    language=language,
                )
                copies.append(copy)
            except Exception as e:
                logger.warning(f"Failed to parse variation: {e}")
        
        duration = (datetime.utcnow() - start_time).total_seconds() * 1000
        
        return CopyGenerationResult(
            copies=copies,
            prompt_used=prompt,
            model_used=getattr(self.provider, 'model', 'unknown'),
            generation_time_ms=duration,
            tokens_used=tokens,
        )
    
    async def improve_copy(
        self,
        copy: AdCopy,
        feedback: str,
        keep_tone: bool = True
    ) -> AdCopy:
        """
        Improve copy based on feedback.
        
        Args:
            copy: Original copy
            feedback: Improvement feedback
            keep_tone: Whether to maintain the same tone
            
        Returns:
            Improved AdCopy
        """
        prompt = f"""Improve this ad copy based on the feedback:

**Current Copy:**
Headline: {copy.headline}
Primary Text: {copy.primary_text}
Description: {copy.description}
CTA: {copy.cta}

**Feedback:** {feedback}

**Instructions:**
- Address the feedback while keeping the core message
- {"Maintain the " + copy.tone + " tone" if keep_tone and copy.tone else ""}
- Return ONLY a JSON object with headline, primary_text, description, cta"""
        
        response, _ = await self.provider.generate(prompt, SYSTEM_PROMPT)
        
        parsed = self._parse_json_response(response)
        
        if parsed:
            item = parsed[0] if isinstance(parsed, list) else parsed
            return AdCopy(
                headline=item.get('headline', copy.headline),
                primary_text=item.get('primary_text', copy.primary_text),
                description=item.get('description', copy.description),
                cta=item.get('cta', copy.cta),
                tone=copy.tone,
                language=copy.language,
            )
        
        return copy
    
    async def translate_copy(
        self,
        copy: AdCopy,
        target_language: str
    ) -> AdCopy:
        """
        Translate copy to another language.
        
        Args:
            copy: Original copy
            target_language: Target language code (e.g., 'en', 'es', 'pt-BR')
            
        Returns:
            Translated AdCopy
        """
        prompt = f"""Translate this ad copy to {target_language}:

**Original ({copy.language}):**
Headline: {copy.headline}
Primary Text: {copy.primary_text}
Description: {copy.description}
CTA: {copy.cta}

**Instructions:**
- Adapt the message culturally, don't just translate literally
- Keep the same emotional impact and tone
- Respect character limits (headline: 40, primary: 125, description: 30)
- Return ONLY a JSON object with headline, primary_text, description, cta"""
        
        response, _ = await self.provider.generate(prompt, SYSTEM_PROMPT)
        
        parsed = self._parse_json_response(response)
        
        if parsed:
            item = parsed[0] if isinstance(parsed, list) else parsed
            return AdCopy(
                headline=item.get('headline', ''),
                primary_text=item.get('primary_text', ''),
                description=item.get('description', ''),
                cta=item.get('cta', ''),
                tone=copy.tone,
                language=target_language,
            )
        
        return copy


# =============================================================================
# PERFORMANCE OPTIMIZER
# =============================================================================

class CopyPerformanceOptimizer:
    """
    Optimizes copy based on historical performance data.
    """
    
    def __init__(self):
        self.architect = CopyArchitect()
        self.performance_data: Dict[str, Dict[str, float]] = {}
    
    def record_performance(
        self,
        copy_hash: str,
        ctr: float,
        cvr: float,
        impressions: int
    ):
        """Record copy performance for learning."""
        self.performance_data[copy_hash] = {
            'ctr': ctr,
            'cvr': cvr,
            'impressions': impressions,
            'score': ctr * 0.3 + cvr * 0.7,  # Weighted score
        }
    
    async def generate_optimized_copy(
        self,
        product_name: str,
        product_description: str,
        target_audience: str,
        top_performing_copies: List[Dict[str, Any]] = None,
        **kwargs
    ) -> CopyGenerationResult:
        """
        Generate copy optimized based on historical performance.
        
        Args:
            product_name: Product name
            product_description: Product description
            target_audience: Target audience
            top_performing_copies: List of best performing copies with metrics
            
        Returns:
            CopyGenerationResult
        """
        additional_instructions = ""
        
        if top_performing_copies:
            # Build learning prompt
            examples = []
            for cp in top_performing_copies[:3]:
                examples.append(
                    f"- Headline: \"{cp.get('headline', '')}\" (CTR: {cp.get('ctr', 0):.2%})"
                )
            
            additional_instructions = (
                "Learn from these top-performing copies:\n" +
                "\n".join(examples) +
                "\nCreate new variations that follow similar patterns but are unique."
            )
        
        return await self.architect.generate_ad_copy(
            product_name=product_name,
            product_description=product_description,
            target_audience=target_audience,
            additional_instructions=additional_instructions,
            **kwargs
        )


# =============================================================================
# FASTAPI ROUTES
# =============================================================================

try:
    from fastapi import APIRouter, HTTPException
    from pydantic import BaseModel as PydanticBaseModel
    
    copy_router = APIRouter(prefix="/api/copy", tags=["copy"])
    
    class GenerateCopyRequest(PydanticBaseModel):
        product_name: str
        product_description: str
        target_audience: str
        tone: str = "aspirational"
        platform: str = "meta"
        language: str = "pt-BR"
        num_variations: int = 3
        additional_instructions: str = ""
    
    class VariationRequest(PydanticBaseModel):
        headline: str
        primary_text: str
        description: str = ""
        cta: str = "Saiba Mais"
        num_variations: int = 3
        language: str = "pt-BR"
    
    class TranslateRequest(PydanticBaseModel):
        headline: str
        primary_text: str
        description: str
        cta: str
        source_language: str = "pt-BR"
        target_language: str
    
    @copy_router.post("/generate")
    async def generate_copy(request: GenerateCopyRequest):
        """Generate ad copy variations."""
        architect = CopyArchitect()
        
        try:
            result = await architect.generate_ad_copy(
                product_name=request.product_name,
                product_description=request.product_description,
                target_audience=request.target_audience,
                tone=request.tone,
                platform=request.platform,
                language=request.language,
                num_variations=request.num_variations,
                additional_instructions=request.additional_instructions,
            )
            
            return result.to_dict()
            
        except Exception as e:
            raise HTTPException(500, str(e))
    
    @copy_router.post("/variations")
    async def generate_variations(request: VariationRequest):
        """Generate variations of existing copy."""
        architect = CopyArchitect()
        
        try:
            result = await architect.generate_variations(
                original_headline=request.headline,
                original_primary_text=request.primary_text,
                original_description=request.description,
                original_cta=request.cta,
                num_variations=request.num_variations,
                language=request.language,
            )
            
            return result.to_dict()
            
        except Exception as e:
            raise HTTPException(500, str(e))
    
    @copy_router.post("/translate")
    async def translate_copy(request: TranslateRequest):
        """Translate copy to another language."""
        architect = CopyArchitect()
        
        original = AdCopy(
            headline=request.headline,
            primary_text=request.primary_text,
            description=request.description,
            cta=request.cta,
            language=request.source_language,
        )
        
        try:
            translated = await architect.translate_copy(original, request.target_language)
            return translated.to_dict()
            
        except Exception as e:
            raise HTTPException(500, str(e))
    
    @copy_router.get("/tones")
    async def list_tones():
        """List available tones."""
        return {
            'tones': [
                {'value': t.value, 'description': TONE_GUIDELINES.get(t, '')}
                for t in CopyTone
            ]
        }
    
    @copy_router.get("/platforms")
    async def list_platforms():
        """List available platforms."""
        return {
            'platforms': [
                {'value': p.value, 'guidelines': PLATFORM_GUIDELINES.get(p, '')}
                for p in AdPlatform
            ]
        }

except ImportError:
    copy_router = None


# =============================================================================
# CLI
# =============================================================================

async def main():
    """CLI for testing."""
    architect = CopyArchitect()
    
    result = await architect.generate_ad_copy(
        product_name="Tênis Runner Pro X",
        product_description="Tênis de corrida profissional com tecnologia de amortecimento avançada, ideal para maratonistas e corredores de longa distância. Sola em carbono para maior impulso.",
        target_audience="Corredores amadores e profissionais, 25-45 anos, que buscam melhorar performance",
        tone="aspirational",
        platform="meta",
        num_variations=3,
    )
    
    print(f"\n{'='*60}")
    print(f"Generated {len(result.copies)} copies in {result.generation_time_ms:.0f}ms")
    print(f"Model: {result.model_used}")
    print(f"{'='*60}\n")
    
    for i, copy in enumerate(result.copies, 1):
        print(f"--- Variation {i} ---")
        print(f"Headline: {copy.headline}")
        print(f"Primary: {copy.primary_text}")
        print(f"Description: {copy.description}")
        print(f"CTA: {copy.cta}")
        print()


if __name__ == '__main__':
    asyncio.run(main())
