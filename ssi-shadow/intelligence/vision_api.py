"""
S.S.I. SHADOW - Vision API Integration (C7)
===========================================

Integração com Google Cloud Vision API para análise real de imagens.
Substitui stubs existentes em creative_intelligence.py.

Features:
- Label detection (objects, scenes)
- Face detection (emotions, positions)
- Text detection (OCR)
- Safe search (inappropriate content)
- Color analysis
- Logo detection

Uso:
    analyzer = VisionAnalyzer()
    
    # Analisar imagem
    result = await analyzer.analyze_image(image_url)
    
    # Ou com arquivo local
    result = await analyzer.analyze_file('/path/to/image.jpg')

Author: SSI Shadow Team
Version: 1.0.0
"""

import os
import io
import base64
import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict, List, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum

import httpx

# Google Cloud Vision
try:
    from google.cloud import vision
    from google.cloud.vision import Image, Feature
    VISION_AVAILABLE = True
except ImportError:
    VISION_AVAILABLE = False
    vision = None

# Alternative: CLIP for local inference
try:
    import torch
    import clip
    from PIL import Image as PILImage
    CLIP_AVAILABLE = True
except ImportError:
    CLIP_AVAILABLE = False
    torch = None
    clip = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('vision_analyzer')


# =============================================================================
# DATA CLASSES
# =============================================================================

class ContentCategory(Enum):
    """Safe search categories."""
    SAFE = "safe"
    UNKNOWN = "unknown"
    POSSIBLE = "possible"
    LIKELY = "likely"
    VERY_LIKELY = "very_likely"


@dataclass
class DetectedObject:
    """Detected object in image."""
    name: str
    score: float
    bounding_box: Optional[Dict[str, float]] = None


@dataclass
class DetectedFace:
    """Detected face with emotions."""
    joy: float  # 0-1
    sorrow: float
    anger: float
    surprise: float
    confidence: float
    bounding_box: Optional[Dict[str, float]] = None
    
    @property
    def dominant_emotion(self) -> str:
        emotions = {
            'joy': self.joy,
            'sorrow': self.sorrow,
            'anger': self.anger,
            'surprise': self.surprise,
        }
        return max(emotions, key=emotions.get)


@dataclass
class DetectedText:
    """Detected text in image (OCR)."""
    text: str
    confidence: float
    bounding_box: Optional[Dict[str, float]] = None
    language: str = "en"


@dataclass
class ColorInfo:
    """Color information."""
    hex: str
    rgb: Tuple[int, int, int]
    score: float
    pixel_fraction: float


@dataclass
class SafeSearchResult:
    """Safe search annotation."""
    adult: ContentCategory
    violence: ContentCategory
    racy: ContentCategory
    spoof: ContentCategory
    medical: ContentCategory
    
    @property
    def is_safe(self) -> bool:
        unsafe_levels = {ContentCategory.LIKELY, ContentCategory.VERY_LIKELY}
        return all([
            self.adult not in unsafe_levels,
            self.violence not in unsafe_levels,
            self.racy not in unsafe_levels,
        ])


@dataclass
class VisionAnalysisResult:
    """Complete vision analysis result."""
    # Source
    source: str  # url or filepath
    width: int = 0
    height: int = 0
    
    # Detections
    objects: List[DetectedObject] = field(default_factory=list)
    faces: List[DetectedFace] = field(default_factory=list)
    texts: List[DetectedText] = field(default_factory=list)
    logos: List[str] = field(default_factory=list)
    
    # Colors
    colors: List[ColorInfo] = field(default_factory=list)
    dominant_color: Optional[str] = None
    
    # Safe search
    safe_search: Optional[SafeSearchResult] = None
    
    # Labels (scene/context)
    labels: List[Tuple[str, float]] = field(default_factory=list)  # (label, score)
    
    # Web detection
    web_entities: List[Tuple[str, float]] = field(default_factory=list)
    similar_images: List[str] = field(default_factory=list)
    
    # Metadata
    analyzed_at: datetime = field(default_factory=datetime.utcnow)
    analysis_duration_ms: float = 0
    provider: str = "google_vision"  # or "clip"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'source': self.source,
            'dimensions': {'width': self.width, 'height': self.height},
            'objects': [{'name': o.name, 'score': o.score} for o in self.objects],
            'faces': [{'emotion': f.dominant_emotion, 'joy': f.joy} for f in self.faces],
            'text_detected': [t.text for t in self.texts],
            'logos': self.logos,
            'dominant_color': self.dominant_color,
            'is_safe': self.safe_search.is_safe if self.safe_search else True,
            'labels': dict(self.labels[:10]),
            'analyzed_at': self.analyzed_at.isoformat(),
        }


# =============================================================================
# GOOGLE CLOUD VISION ANALYZER
# =============================================================================

class GoogleVisionAnalyzer:
    """
    Analyzer using Google Cloud Vision API.
    
    Requires:
        - GOOGLE_APPLICATION_CREDENTIALS env var
        - google-cloud-vision package
    """
    
    def __init__(self):
        if not VISION_AVAILABLE:
            raise RuntimeError("google-cloud-vision not installed")
        
        self.client = vision.ImageAnnotatorClient()
    
    def _likelihood_to_float(self, likelihood) -> float:
        """Convert Vision API likelihood enum to float."""
        mapping = {
            'UNKNOWN': 0.0,
            'VERY_UNLIKELY': 0.1,
            'UNLIKELY': 0.3,
            'POSSIBLE': 0.5,
            'LIKELY': 0.7,
            'VERY_LIKELY': 0.9,
        }
        return mapping.get(likelihood.name, 0.0)
    
    def _likelihood_to_category(self, likelihood) -> ContentCategory:
        """Convert Vision API likelihood to category."""
        mapping = {
            'UNKNOWN': ContentCategory.UNKNOWN,
            'VERY_UNLIKELY': ContentCategory.SAFE,
            'UNLIKELY': ContentCategory.SAFE,
            'POSSIBLE': ContentCategory.POSSIBLE,
            'LIKELY': ContentCategory.LIKELY,
            'VERY_LIKELY': ContentCategory.VERY_LIKELY,
        }
        return mapping.get(likelihood.name, ContentCategory.UNKNOWN)
    
    async def analyze(self, image_source: str) -> VisionAnalysisResult:
        """
        Analyze image using Google Cloud Vision.
        
        Args:
            image_source: URL or file path
            
        Returns:
            VisionAnalysisResult with all detections
        """
        start_time = datetime.utcnow()
        
        # Load image
        if image_source.startswith(('http://', 'https://')):
            image = vision.Image()
            image.source.image_uri = image_source
        else:
            with open(image_source, 'rb') as f:
                content = f.read()
            image = vision.Image(content=content)
        
        # Define features to detect
        features = [
            vision.Feature(type_=vision.Feature.Type.LABEL_DETECTION, max_results=20),
            vision.Feature(type_=vision.Feature.Type.OBJECT_LOCALIZATION, max_results=20),
            vision.Feature(type_=vision.Feature.Type.FACE_DETECTION, max_results=10),
            vision.Feature(type_=vision.Feature.Type.TEXT_DETECTION),
            vision.Feature(type_=vision.Feature.Type.LOGO_DETECTION, max_results=5),
            vision.Feature(type_=vision.Feature.Type.IMAGE_PROPERTIES),
            vision.Feature(type_=vision.Feature.Type.SAFE_SEARCH_DETECTION),
            vision.Feature(type_=vision.Feature.Type.WEB_DETECTION, max_results=10),
        ]
        
        # Make request (run in executor for async)
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self.client.annotate_image({
                'image': image,
                'features': features,
            })
        )
        
        # Parse results
        result = VisionAnalysisResult(
            source=image_source,
            provider='google_vision',
        )
        
        # Objects
        for obj in response.localized_object_annotations:
            result.objects.append(DetectedObject(
                name=obj.name,
                score=obj.score,
                bounding_box=self._parse_bounding_poly(obj.bounding_poly)
            ))
        
        # Faces
        for face in response.face_annotations:
            result.faces.append(DetectedFace(
                joy=self._likelihood_to_float(face.joy_likelihood),
                sorrow=self._likelihood_to_float(face.sorrow_likelihood),
                anger=self._likelihood_to_float(face.anger_likelihood),
                surprise=self._likelihood_to_float(face.surprise_likelihood),
                confidence=face.detection_confidence,
                bounding_box=self._parse_bounding_poly(face.bounding_poly)
            ))
        
        # Text (OCR)
        for text in response.text_annotations[1:]:  # Skip first (full text)
            result.texts.append(DetectedText(
                text=text.description,
                confidence=1.0,  # Vision API doesn't provide confidence for text
                bounding_box=self._parse_bounding_poly(text.bounding_poly)
            ))
        
        # Full text as first element
        if response.text_annotations:
            result.texts.insert(0, DetectedText(
                text=response.text_annotations[0].description,
                confidence=1.0,
            ))
        
        # Logos
        for logo in response.logo_annotations:
            result.logos.append(logo.description)
        
        # Colors
        if response.image_properties_annotation.dominant_colors:
            for color in response.image_properties_annotation.dominant_colors.colors:
                rgb = (
                    int(color.color.red),
                    int(color.color.green),
                    int(color.color.blue)
                )
                hex_color = '#{:02x}{:02x}{:02x}'.format(*rgb)
                
                result.colors.append(ColorInfo(
                    hex=hex_color,
                    rgb=rgb,
                    score=color.score,
                    pixel_fraction=color.pixel_fraction
                ))
            
            if result.colors:
                result.dominant_color = result.colors[0].hex
        
        # Safe search
        safe = response.safe_search_annotation
        result.safe_search = SafeSearchResult(
            adult=self._likelihood_to_category(safe.adult),
            violence=self._likelihood_to_category(safe.violence),
            racy=self._likelihood_to_category(safe.racy),
            spoof=self._likelihood_to_category(safe.spoof),
            medical=self._likelihood_to_category(safe.medical),
        )
        
        # Labels
        for label in response.label_annotations:
            result.labels.append((label.description, label.score))
        
        # Web detection
        if response.web_detection:
            for entity in response.web_detection.web_entities:
                if entity.description:
                    result.web_entities.append((entity.description, entity.score))
            
            for img in response.web_detection.visually_similar_images[:5]:
                result.similar_images.append(img.url)
        
        # Duration
        result.analysis_duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
        
        return result
    
    def _parse_bounding_poly(self, poly) -> Dict[str, float]:
        """Parse bounding polygon to dict."""
        if not poly.normalized_vertices:
            if not poly.vertices:
                return {}
            vertices = poly.vertices
            # Assume 1000x1000 if not normalized
            return {
                'x': vertices[0].x / 1000,
                'y': vertices[0].y / 1000,
                'width': (vertices[2].x - vertices[0].x) / 1000,
                'height': (vertices[2].y - vertices[0].y) / 1000,
            }
        
        v = poly.normalized_vertices
        return {
            'x': v[0].x,
            'y': v[0].y,
            'width': v[2].x - v[0].x,
            'height': v[2].y - v[0].y,
        }


# =============================================================================
# CLIP LOCAL ANALYZER (Fallback)
# =============================================================================

class CLIPAnalyzer:
    """
    Local image analyzer using OpenAI's CLIP model.
    
    Use when:
        - No Google Cloud credentials
        - Want to run locally/offline
        - Need custom label detection
    
    Requires:
        - torch
        - clip (pip install git+https://github.com/openai/CLIP.git)
        - PIL
    """
    
    # Common labels for ad creative analysis
    DEFAULT_LABELS = [
        # Products
        'product photo', 'packshot', 'lifestyle photo', 'model wearing product',
        # People
        'person', 'face', 'woman', 'man', 'group of people', 'family',
        # Emotions
        'happy', 'excited', 'surprised', 'serious', 'professional',
        # Elements
        'text overlay', 'logo', 'price tag', 'discount badge', 'call to action button',
        # Styles
        'minimalist', 'colorful', 'professional', 'casual', 'luxury', 'budget-friendly',
        # Scenes
        'outdoor', 'indoor', 'studio', 'nature', 'urban', 'home',
    ]
    
    def __init__(self, device: str = None):
        if not CLIP_AVAILABLE:
            raise RuntimeError("CLIP not installed")
        
        self.device = device or ('cuda' if torch.cuda.is_available() else 'cpu')
        self.model, self.preprocess = clip.load('ViT-B/32', device=self.device)
        
        # Pre-compute text features for default labels
        self._label_features = None
    
    def _get_label_features(self, labels: List[str] = None):
        """Get or compute text features for labels."""
        labels = labels or self.DEFAULT_LABELS
        
        with torch.no_grad():
            text_tokens = clip.tokenize(labels).to(self.device)
            return self.model.encode_text(text_tokens)
    
    async def analyze(
        self,
        image_source: str,
        custom_labels: List[str] = None
    ) -> VisionAnalysisResult:
        """
        Analyze image using CLIP.
        
        Args:
            image_source: URL or file path
            custom_labels: Custom labels to detect
            
        Returns:
            VisionAnalysisResult (limited compared to Google Vision)
        """
        start_time = datetime.utcnow()
        
        # Load image
        if image_source.startswith(('http://', 'https://')):
            async with httpx.AsyncClient() as client:
                response = await client.get(image_source)
                image = PILImage.open(io.BytesIO(response.content))
        else:
            image = PILImage.open(image_source)
        
        # Get image dimensions
        width, height = image.size
        
        # Preprocess
        image_input = self.preprocess(image).unsqueeze(0).to(self.device)
        
        # Get labels
        labels = custom_labels or self.DEFAULT_LABELS
        text_features = self._get_label_features(labels)
        
        # Compute similarity
        with torch.no_grad():
            image_features = self.model.encode_image(image_input)
            
            # Normalize
            image_features = image_features / image_features.norm(dim=-1, keepdim=True)
            text_features = text_features / text_features.norm(dim=-1, keepdim=True)
            
            # Similarity
            similarity = (image_features @ text_features.T).squeeze(0)
            
            # Softmax for probabilities
            probs = similarity.softmax(dim=-1).cpu().numpy()
        
        # Build result
        result = VisionAnalysisResult(
            source=image_source,
            width=width,
            height=height,
            provider='clip',
        )
        
        # Add labels with scores
        for label, prob in zip(labels, probs):
            if prob > 0.05:  # Threshold
                result.labels.append((label, float(prob)))
        
        # Sort by score
        result.labels.sort(key=lambda x: x[1], reverse=True)
        
        # Extract dominant color (simple method)
        image_rgb = image.convert('RGB')
        pixels = list(image_rgb.getdata())
        avg_color = tuple(sum(c) // len(c) for c in zip(*pixels))
        result.dominant_color = '#{:02x}{:02x}{:02x}'.format(*avg_color)
        
        result.analysis_duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
        
        return result


# =============================================================================
# MAIN ANALYZER (Auto-selects backend)
# =============================================================================

class VisionAnalyzer:
    """
    Main vision analyzer that auto-selects the best available backend.
    
    Priority:
        1. Google Cloud Vision (if credentials available)
        2. CLIP (local fallback)
        3. Error
    """
    
    def __init__(self, prefer_local: bool = False):
        self.analyzer = None
        
        if prefer_local and CLIP_AVAILABLE:
            self.analyzer = CLIPAnalyzer()
            logger.info("Using CLIP for vision analysis (local)")
        elif VISION_AVAILABLE and os.getenv('GOOGLE_APPLICATION_CREDENTIALS'):
            self.analyzer = GoogleVisionAnalyzer()
            logger.info("Using Google Cloud Vision API")
        elif CLIP_AVAILABLE:
            self.analyzer = CLIPAnalyzer()
            logger.info("Using CLIP for vision analysis (local fallback)")
        else:
            logger.error("No vision backend available!")
    
    async def analyze_image(self, image_url: str) -> Optional[VisionAnalysisResult]:
        """Analyze image from URL."""
        if not self.analyzer:
            return None
        
        try:
            return await self.analyzer.analyze(image_url)
        except Exception as e:
            logger.error(f"Vision analysis error: {e}")
            return None
    
    async def analyze_file(self, file_path: str) -> Optional[VisionAnalysisResult]:
        """Analyze local image file."""
        if not self.analyzer:
            return None
        
        try:
            return await self.analyzer.analyze(file_path)
        except Exception as e:
            logger.error(f"Vision analysis error: {e}")
            return None
    
    async def analyze_batch(
        self,
        sources: List[str],
        concurrency: int = 5
    ) -> List[Optional[VisionAnalysisResult]]:
        """Analyze multiple images."""
        semaphore = asyncio.Semaphore(concurrency)
        
        async def analyze_one(source):
            async with semaphore:
                return await self.analyze_image(source)
        
        return await asyncio.gather(*[analyze_one(s) for s in sources])
    
    def is_available(self) -> bool:
        """Check if analyzer is available."""
        return self.analyzer is not None


# =============================================================================
# CREATIVE ANALYZER (High-level for ads)
# =============================================================================

class CreativeVisualAnalyzer:
    """
    High-level analyzer specifically for ad creatives.
    
    Provides:
        - Element detection (product, face, text, etc.)
        - Composition scoring
        - Brand safety check
        - Performance prediction signals
    """
    
    def __init__(self):
        self.vision = VisionAnalyzer()
    
    async def analyze_creative(self, image_url: str) -> Dict[str, Any]:
        """
        Analyze ad creative for insights.
        
        Returns:
            Dict with creative analysis
        """
        result = await self.vision.analyze_image(image_url)
        
        if not result:
            return {'error': 'Analysis failed'}
        
        # Determine creative elements
        elements = []
        
        # Check for faces
        if result.faces:
            elements.append('face')
            if any(f.joy > 0.7 for f in result.faces):
                elements.append('happy_face')
        
        # Check for text
        if result.texts:
            elements.append('text_overlay')
            # Check for specific text patterns
            full_text = ' '.join(t.text for t in result.texts).lower()
            if any(word in full_text for word in ['off', '%', 'sale', 'discount']):
                elements.append('discount_badge')
            if any(word in full_text for word in ['shop', 'buy', 'get', 'order']):
                elements.append('cta_text')
        
        # Check for logos
        if result.logos:
            elements.append('logo')
        
        # Check labels for product/lifestyle
        label_names = [l[0].lower() for l in result.labels]
        if any(l in label_names for l in ['product', 'packshot', 'item']):
            elements.append('product_image')
        if any(l in label_names for l in ['lifestyle', 'person', 'model']):
            elements.append('lifestyle')
        
        # Composition score (simple heuristic)
        composition_score = 0.5
        if result.faces and len(result.faces) == 1:
            composition_score += 0.2  # Single face is usually good
        if elements and len(elements) <= 3:
            composition_score += 0.1  # Not too cluttered
        if result.dominant_color:
            composition_score += 0.1  # Has clear color scheme
        
        # Brand safety
        is_safe = result.safe_search.is_safe if result.safe_search else True
        
        return {
            'image_url': image_url,
            'elements': elements,
            'has_face': bool(result.faces),
            'has_text': bool(result.texts),
            'has_logo': bool(result.logos),
            'dominant_color': result.dominant_color,
            'color_count': len(result.colors),
            'composition_score': min(1.0, composition_score),
            'is_brand_safe': is_safe,
            'labels': result.labels[:10],
            'similar_images': result.similar_images[:3],
            'analysis_ms': result.analysis_duration_ms,
        }


# =============================================================================
# FASTAPI ROUTES
# =============================================================================

try:
    from fastapi import APIRouter, HTTPException
    from pydantic import BaseModel
    
    vision_router = APIRouter(prefix="/api/vision", tags=["vision"])
    
    class AnalyzeRequest(BaseModel):
        image_url: str
        
    @vision_router.post("/analyze")
    async def analyze_image(request: AnalyzeRequest):
        """Analyze an image."""
        analyzer = VisionAnalyzer()
        
        if not analyzer.is_available():
            raise HTTPException(503, "Vision API not available")
        
        result = await analyzer.analyze_image(request.image_url)
        
        if not result:
            raise HTTPException(500, "Analysis failed")
        
        return result.to_dict()
    
    @vision_router.post("/analyze-creative")
    async def analyze_creative(request: AnalyzeRequest):
        """Analyze an ad creative."""
        analyzer = CreativeVisualAnalyzer()
        return await analyzer.analyze_creative(request.image_url)

except ImportError:
    vision_router = None


# =============================================================================
# CLI
# =============================================================================

async def main():
    """CLI for testing."""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python vision_api.py <image_url_or_path>")
        return
    
    analyzer = VisionAnalyzer()
    
    if not analyzer.is_available():
        print("No vision backend available!")
        return
    
    result = await analyzer.analyze_image(sys.argv[1])
    
    if result:
        import json
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print("Analysis failed")


if __name__ == '__main__':
    asyncio.run(main())
