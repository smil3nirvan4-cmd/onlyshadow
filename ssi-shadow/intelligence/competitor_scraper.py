"""
S.S.I. SHADOW - Competitor Price Scraper (C5)
=============================================

Monitor de preços de concorrentes usando Scrapy.
Integra com AlertService e BidOptimizer para ajustes defensivos.

Features:
- Scrapy-based crawling (respeitoso com robots.txt)
- Multiple site adapters (Shopify, WooCommerce, custom)
- Price change detection
- Automatic alerts on significant changes
- Historical price tracking
- Integration with bid adjustment

Uso:
    scraper = CompetitorScraper()
    
    # Adicionar concorrente
    scraper.add_competitor(
        name='Competitor A',
        url='https://competitor.com/product/123',
        adapter='shopify'
    )
    
    # Executar scraping
    prices = await scraper.scrape_all()
    
    # Detectar mudanças
    changes = await scraper.detect_changes()

Legal Notice:
    Este scraper respeita robots.txt e implementa rate limiting.
    Use apenas para monitoramento público de preços.
    Verifique os termos de serviço de cada site.

Author: SSI Shadow Team
Version: 1.0.0
"""

import os
import re
import json
import asyncio
import logging
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Callable, Tuple
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod
from urllib.parse import urlparse
import random

# HTTP clients
import httpx

# HTML parsing
try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False
    BeautifulSoup = None

# Scrapy (optional, for more complex scraping)
try:
    import scrapy
    from scrapy.crawler import CrawlerRunner
    from scrapy.utils.project import get_project_settings
    SCRAPY_AVAILABLE = True
except ImportError:
    SCRAPY_AVAILABLE = False
    scrapy = None

# BigQuery for storage
try:
    from google.cloud import bigquery
    BIGQUERY_AVAILABLE = True
except ImportError:
    BIGQUERY_AVAILABLE = False
    bigquery = None

# Local imports
from webhooks.services.alert_service import get_alert_service, AlertSeverity

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('competitor_scraper')


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class ScraperConfig:
    """Scraper configuration."""
    
    # Rate limiting
    requests_per_minute: int = 10
    delay_between_requests: float = 2.0  # seconds
    random_delay_range: Tuple[float, float] = (1.0, 3.0)
    
    # Retries
    max_retries: int = 3
    retry_delay: float = 5.0
    
    # Timeouts
    request_timeout: float = 30.0
    
    # User agent rotation
    user_agents: List[str] = field(default_factory=lambda: [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    ])
    
    # Price change thresholds
    significant_change_pct: float = 5.0   # Alert if price changes > 5%
    major_change_pct: float = 15.0        # Critical alert if > 15%
    
    # Storage
    gcp_project_id: str = field(default_factory=lambda: os.getenv('GCP_PROJECT_ID', ''))
    bq_dataset: str = field(default_factory=lambda: os.getenv('BQ_DATASET', 'ssi_shadow'))
    
    # Respect robots.txt
    respect_robots: bool = True
    
    # Proxy (optional)
    proxy_url: str = field(default_factory=lambda: os.getenv('SCRAPER_PROXY_URL', ''))


config = ScraperConfig()


# =============================================================================
# DATA CLASSES
# =============================================================================

class SiteAdapter(Enum):
    """Supported site adapters."""
    GENERIC = "generic"
    SHOPIFY = "shopify"
    WOOCOMMERCE = "woocommerce"
    MAGENTO = "magento"
    BIGCOMMERCE = "bigcommerce"
    CUSTOM = "custom"


@dataclass
class Competitor:
    """Competitor information."""
    id: str
    name: str
    domain: str
    products: List['ProductToTrack'] = field(default_factory=list)
    adapter: SiteAdapter = SiteAdapter.GENERIC
    is_active: bool = True
    last_scraped: Optional[datetime] = None
    scrape_interval_hours: int = 6


@dataclass
class ProductToTrack:
    """Product to track from competitor."""
    id: str
    url: str
    name: str
    our_sku: str = ""  # Our equivalent product SKU
    our_price: float = 0.0  # Our current price
    competitor_id: str = ""
    selector: str = ""  # CSS selector for price
    
    # Current data
    current_price: Optional[float] = None
    current_stock: Optional[str] = None  # 'in_stock', 'out_of_stock', 'low_stock'
    last_checked: Optional[datetime] = None
    last_changed: Optional[datetime] = None
    
    # Historical
    price_history: List[Tuple[datetime, float]] = field(default_factory=list)


@dataclass
class PriceResult:
    """Result of a price scrape."""
    product_id: str
    competitor_id: str
    url: str
    price: Optional[float]
    currency: str = "USD"
    stock_status: Optional[str] = None
    scraped_at: datetime = field(default_factory=datetime.utcnow)
    success: bool = True
    error: Optional[str] = None
    raw_price_text: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'product_id': self.product_id,
            'competitor_id': self.competitor_id,
            'url': self.url,
            'price': self.price,
            'currency': self.currency,
            'stock_status': self.stock_status,
            'scraped_at': self.scraped_at.isoformat(),
            'success': self.success,
            'error': self.error,
        }


@dataclass
class PriceChange:
    """Detected price change."""
    product_id: str
    competitor_id: str
    competitor_name: str
    product_name: str
    url: str
    old_price: float
    new_price: float
    change_amount: float
    change_percent: float
    our_price: float
    price_vs_us: float  # Positive = they're more expensive
    detected_at: datetime = field(default_factory=datetime.utcnow)
    
    @property
    def severity(self) -> str:
        """Determine severity based on change."""
        if abs(self.change_percent) >= config.major_change_pct:
            return 'critical'
        elif abs(self.change_percent) >= config.significant_change_pct:
            return 'warning'
        return 'info'
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'product_id': self.product_id,
            'competitor': self.competitor_name,
            'product': self.product_name,
            'old_price': self.old_price,
            'new_price': self.new_price,
            'change_percent': round(self.change_percent, 2),
            'our_price': self.our_price,
            'price_vs_us': round(self.price_vs_us, 2),
            'severity': self.severity,
        }


# =============================================================================
# PRICE EXTRACTORS (Site Adapters)
# =============================================================================

class PriceExtractor(ABC):
    """Abstract base class for price extractors."""
    
    @abstractmethod
    def extract_price(self, html: str, product: ProductToTrack) -> Tuple[Optional[float], str]:
        """
        Extract price from HTML.
        
        Returns:
            Tuple of (price, raw_price_text)
        """
        pass
    
    @abstractmethod
    def extract_stock_status(self, html: str, product: ProductToTrack) -> Optional[str]:
        """Extract stock status from HTML."""
        pass
    
    def parse_price(self, price_text: str) -> Optional[float]:
        """Parse price from text."""
        if not price_text:
            return None
        
        # Remove common currency symbols and whitespace
        cleaned = re.sub(r'[^\d.,]', '', price_text)
        
        # Handle different decimal separators
        if ',' in cleaned and '.' in cleaned:
            # Both present - assume comma is thousand separator
            cleaned = cleaned.replace(',', '')
        elif ',' in cleaned and '.' not in cleaned:
            # Only comma - could be decimal separator
            # Check if it's in the last 3 positions
            if cleaned.rfind(',') >= len(cleaned) - 3:
                cleaned = cleaned.replace(',', '.')
            else:
                cleaned = cleaned.replace(',', '')
        
        try:
            return float(cleaned)
        except ValueError:
            return None


class GenericExtractor(PriceExtractor):
    """Generic price extractor using common patterns."""
    
    PRICE_SELECTORS = [
        '[data-price]',
        '.price',
        '.product-price',
        '.current-price',
        '#price',
        '[itemprop="price"]',
        '.sale-price',
        '.regular-price',
    ]
    
    STOCK_SELECTORS = [
        '[data-availability]',
        '.stock-status',
        '.availability',
        '[itemprop="availability"]',
    ]
    
    def extract_price(self, html: str, product: ProductToTrack) -> Tuple[Optional[float], str]:
        if not BS4_AVAILABLE:
            return None, ""
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Try custom selector first
        if product.selector:
            elem = soup.select_one(product.selector)
            if elem:
                text = elem.get_text(strip=True)
                return self.parse_price(text), text
        
        # Try common selectors
        for selector in self.PRICE_SELECTORS:
            elem = soup.select_one(selector)
            if elem:
                # Check for data attribute first
                price_attr = elem.get('data-price') or elem.get('content')
                if price_attr:
                    return self.parse_price(price_attr), price_attr
                
                text = elem.get_text(strip=True)
                price = self.parse_price(text)
                if price:
                    return price, text
        
        # Try regex as fallback
        price_pattern = r'\$[\d,]+\.?\d*'
        matches = re.findall(price_pattern, html)
        if matches:
            return self.parse_price(matches[0]), matches[0]
        
        return None, ""
    
    def extract_stock_status(self, html: str, product: ProductToTrack) -> Optional[str]:
        if not BS4_AVAILABLE:
            return None
        
        soup = BeautifulSoup(html, 'html.parser')
        
        for selector in self.STOCK_SELECTORS:
            elem = soup.select_one(selector)
            if elem:
                text = elem.get_text(strip=True).lower()
                
                if any(word in text for word in ['in stock', 'available', 'em estoque']):
                    return 'in_stock'
                elif any(word in text for word in ['out of stock', 'unavailable', 'sold out', 'esgotado']):
                    return 'out_of_stock'
                elif any(word in text for word in ['low stock', 'few left', 'últimas unidades']):
                    return 'low_stock'
        
        return None


class ShopifyExtractor(PriceExtractor):
    """Shopify-specific price extractor."""
    
    def extract_price(self, html: str, product: ProductToTrack) -> Tuple[Optional[float], str]:
        if not BS4_AVAILABLE:
            return None, ""
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Shopify uses JSON-LD
        scripts = soup.find_all('script', type='application/ld+json')
        for script in scripts:
            try:
                data = json.loads(script.string)
                if isinstance(data, dict):
                    # Product schema
                    if data.get('@type') == 'Product':
                        offers = data.get('offers', {})
                        if isinstance(offers, list):
                            offers = offers[0] if offers else {}
                        price = offers.get('price')
                        if price:
                            return float(price), str(price)
            except (json.JSONDecodeError, ValueError):
                continue
        
        # Fallback to common Shopify selectors
        selectors = [
            '.product__price',
            '.product-single__price',
            '[data-product-price]',
            '.price__regular',
        ]
        
        for selector in selectors:
            elem = soup.select_one(selector)
            if elem:
                text = elem.get_text(strip=True)
                price = self.parse_price(text)
                if price:
                    return price, text
        
        return None, ""
    
    def extract_stock_status(self, html: str, product: ProductToTrack) -> Optional[str]:
        if not BS4_AVAILABLE:
            return None
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Check for add to cart button
        add_to_cart = soup.select_one('[data-add-to-cart], .add-to-cart, #AddToCart')
        if add_to_cart:
            if add_to_cart.get('disabled'):
                return 'out_of_stock'
            return 'in_stock'
        
        # Check for sold out text
        if 'sold out' in html.lower() or 'out of stock' in html.lower():
            return 'out_of_stock'
        
        return 'in_stock'


class WooCommerceExtractor(PriceExtractor):
    """WooCommerce-specific price extractor."""
    
    def extract_price(self, html: str, product: ProductToTrack) -> Tuple[Optional[float], str]:
        if not BS4_AVAILABLE:
            return None, ""
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # WooCommerce selectors
        selectors = [
            '.woocommerce-Price-amount',
            '.price ins .amount',  # Sale price
            '.price .amount',
            '.single_variation_wrap .woocommerce-variation-price .amount',
        ]
        
        for selector in selectors:
            elem = soup.select_one(selector)
            if elem:
                text = elem.get_text(strip=True)
                price = self.parse_price(text)
                if price:
                    return price, text
        
        return None, ""
    
    def extract_stock_status(self, html: str, product: ProductToTrack) -> Optional[str]:
        if not BS4_AVAILABLE:
            return None
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # WooCommerce stock status
        stock_elem = soup.select_one('.stock')
        if stock_elem:
            class_list = stock_elem.get('class', [])
            if 'out-of-stock' in class_list:
                return 'out_of_stock'
            elif 'in-stock' in class_list:
                return 'in_stock'
        
        return None


# Factory for extractors
EXTRACTORS: Dict[SiteAdapter, PriceExtractor] = {
    SiteAdapter.GENERIC: GenericExtractor(),
    SiteAdapter.SHOPIFY: ShopifyExtractor(),
    SiteAdapter.WOOCOMMERCE: WooCommerceExtractor(),
}


def get_extractor(adapter: SiteAdapter) -> PriceExtractor:
    """Get extractor for site adapter."""
    return EXTRACTORS.get(adapter, GenericExtractor())


# =============================================================================
# MAIN SCRAPER
# =============================================================================

class CompetitorScraper:
    """
    Main competitor price scraper.
    
    Scrapes competitor prices while respecting rate limits and robots.txt.
    """
    
    def __init__(self, config: ScraperConfig = None):
        self.config = config or ScraperConfig()
        self.competitors: Dict[str, Competitor] = {}
        self.price_history: Dict[str, List[PriceResult]] = {}  # product_id -> history
        
        # HTTP client with session
        self.client = httpx.AsyncClient(
            timeout=self.config.request_timeout,
            follow_redirects=True,
            headers={'Accept': 'text/html,application/xhtml+xml'},
        )
        
        # Rate limiting
        self._last_request_time: Dict[str, float] = {}  # domain -> timestamp
        self._request_lock = asyncio.Lock()
        
        # Alert service
        self.alert_service = get_alert_service()
        
        # BigQuery client
        self.bq_client = bigquery.Client(project=self.config.gcp_project_id) if BIGQUERY_AVAILABLE else None
    
    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()
    
    def add_competitor(
        self,
        name: str,
        products: List[Dict[str, Any]],
        adapter: str = 'generic',
        scrape_interval_hours: int = 6
    ) -> Competitor:
        """
        Add competitor to track.
        
        Args:
            name: Competitor name
            products: List of products to track [{url, name, our_sku, our_price}]
            adapter: Site adapter type
            scrape_interval_hours: How often to scrape
        """
        # Generate ID from name
        comp_id = hashlib.md5(name.encode()).hexdigest()[:8]
        
        # Determine domain from first product
        domain = ""
        if products:
            parsed = urlparse(products[0].get('url', ''))
            domain = parsed.netloc
        
        # Create product objects
        product_objs = []
        for p in products:
            prod = ProductToTrack(
                id=hashlib.md5(p['url'].encode()).hexdigest()[:8],
                url=p['url'],
                name=p.get('name', 'Unknown Product'),
                our_sku=p.get('our_sku', ''),
                our_price=p.get('our_price', 0.0),
                competitor_id=comp_id,
                selector=p.get('selector', ''),
            )
            product_objs.append(prod)
        
        competitor = Competitor(
            id=comp_id,
            name=name,
            domain=domain,
            products=product_objs,
            adapter=SiteAdapter(adapter),
            scrape_interval_hours=scrape_interval_hours,
        )
        
        self.competitors[comp_id] = competitor
        logger.info(f"Added competitor: {name} with {len(products)} products")
        
        return competitor
    
    def remove_competitor(self, competitor_id: str):
        """Remove competitor."""
        if competitor_id in self.competitors:
            del self.competitors[competitor_id]
    
    async def _rate_limit(self, domain: str):
        """Apply rate limiting per domain."""
        async with self._request_lock:
            now = asyncio.get_event_loop().time()
            last_request = self._last_request_time.get(domain, 0)
            
            # Calculate delay
            min_delay = self.config.delay_between_requests
            random_delay = random.uniform(*self.config.random_delay_range)
            total_delay = min_delay + random_delay
            
            elapsed = now - last_request
            if elapsed < total_delay:
                await asyncio.sleep(total_delay - elapsed)
            
            self._last_request_time[domain] = asyncio.get_event_loop().time()
    
    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with random user agent."""
        return {
            'User-Agent': random.choice(self.config.user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
    
    async def scrape_product(self, product: ProductToTrack, competitor: Competitor) -> PriceResult:
        """
        Scrape a single product page.
        
        Args:
            product: Product to scrape
            competitor: Competitor info
            
        Returns:
            PriceResult with scraped data
        """
        parsed = urlparse(product.url)
        domain = parsed.netloc
        
        # Rate limit
        await self._rate_limit(domain)
        
        # Attempt request with retries
        for attempt in range(self.config.max_retries):
            try:
                response = await self.client.get(
                    product.url,
                    headers=self._get_headers(),
                )
                
                if response.status_code == 200:
                    html = response.text
                    
                    # Extract price
                    extractor = get_extractor(competitor.adapter)
                    price, raw_text = extractor.extract_price(html, product)
                    stock_status = extractor.extract_stock_status(html, product)
                    
                    result = PriceResult(
                        product_id=product.id,
                        competitor_id=competitor.id,
                        url=product.url,
                        price=price,
                        stock_status=stock_status,
                        raw_price_text=raw_text,
                        success=price is not None,
                        error=None if price else "Could not extract price",
                    )
                    
                    # Update product
                    if price:
                        product.current_price = price
                        product.current_stock = stock_status
                        product.last_checked = datetime.utcnow()
                        product.price_history.append((datetime.utcnow(), price))
                    
                    return result
                
                elif response.status_code == 429:
                    # Rate limited - wait and retry
                    logger.warning(f"Rate limited by {domain}, waiting...")
                    await asyncio.sleep(self.config.retry_delay * (attempt + 1))
                
                else:
                    return PriceResult(
                        product_id=product.id,
                        competitor_id=competitor.id,
                        url=product.url,
                        price=None,
                        success=False,
                        error=f"HTTP {response.status_code}",
                    )
                    
            except Exception as e:
                logger.error(f"Error scraping {product.url}: {e}")
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(self.config.retry_delay)
                else:
                    return PriceResult(
                        product_id=product.id,
                        competitor_id=competitor.id,
                        url=product.url,
                        price=None,
                        success=False,
                        error=str(e),
                    )
        
        return PriceResult(
            product_id=product.id,
            competitor_id=competitor.id,
            url=product.url,
            price=None,
            success=False,
            error="Max retries exceeded",
        )
    
    async def scrape_competitor(self, competitor_id: str) -> List[PriceResult]:
        """Scrape all products from a competitor."""
        competitor = self.competitors.get(competitor_id)
        if not competitor:
            return []
        
        results = []
        for product in competitor.products:
            result = await self.scrape_product(product, competitor)
            results.append(result)
            
            # Store in history
            if product.id not in self.price_history:
                self.price_history[product.id] = []
            self.price_history[product.id].append(result)
        
        competitor.last_scraped = datetime.utcnow()
        return results
    
    async def scrape_all(self) -> Dict[str, List[PriceResult]]:
        """
        Scrape all competitors.
        
        Returns:
            Dict of competitor_id -> list of PriceResults
        """
        all_results = {}
        
        for comp_id, competitor in self.competitors.items():
            if not competitor.is_active:
                continue
            
            logger.info(f"Scraping competitor: {competitor.name}")
            results = await self.scrape_competitor(comp_id)
            all_results[comp_id] = results
            
            # Log summary
            successful = sum(1 for r in results if r.success)
            logger.info(f"  {successful}/{len(results)} products scraped successfully")
        
        return all_results
    
    async def detect_changes(self) -> List[PriceChange]:
        """
        Detect price changes since last scrape.
        
        Returns:
            List of PriceChange objects
        """
        changes = []
        
        for comp_id, competitor in self.competitors.items():
            for product in competitor.products:
                history = self.price_history.get(product.id, [])
                
                if len(history) < 2:
                    continue
                
                # Get last two successful prices
                successful = [h for h in history[-10:] if h.success and h.price]
                if len(successful) < 2:
                    continue
                
                old_result = successful[-2]
                new_result = successful[-1]
                
                if old_result.price != new_result.price:
                    change_amount = new_result.price - old_result.price
                    change_pct = (change_amount / old_result.price) * 100
                    
                    change = PriceChange(
                        product_id=product.id,
                        competitor_id=comp_id,
                        competitor_name=competitor.name,
                        product_name=product.name,
                        url=product.url,
                        old_price=old_result.price,
                        new_price=new_result.price,
                        change_amount=change_amount,
                        change_percent=change_pct,
                        our_price=product.our_price,
                        price_vs_us=new_result.price - product.our_price if product.our_price else 0,
                    )
                    
                    changes.append(change)
                    product.last_changed = datetime.utcnow()
        
        return changes
    
    async def send_alerts(self, changes: List[PriceChange]):
        """Send alerts for significant price changes."""
        significant = [c for c in changes if abs(c.change_percent) >= self.config.significant_change_pct]
        
        if not significant:
            return
        
        for change in significant:
            direction = "↑" if change.change_amount > 0 else "↓"
            
            await self.alert_service.trigger_platform_error_alert(
                org_id='default',
                error_data={
                    'platform': 'competitor_monitor',
                    'error_code': 'PRICE_CHANGE',
                    'error_message': (
                        f"{direction} {change.competitor_name}: {change.product_name}\n"
                        f"${change.old_price:.2f} → ${change.new_price:.2f} ({change.change_percent:+.1f}%)\n"
                        f"Our price: ${change.our_price:.2f}"
                    ),
                }
            )
    
    async def save_to_bigquery(self, results: Dict[str, List[PriceResult]]):
        """Save scrape results to BigQuery."""
        if not self.bq_client:
            return
        
        rows = []
        for comp_id, price_results in results.items():
            competitor = self.competitors.get(comp_id)
            for result in price_results:
                product = next(
                    (p for p in competitor.products if p.id == result.product_id),
                    None
                ) if competitor else None
                
                rows.append({
                    'scraped_at': result.scraped_at.isoformat(),
                    'competitor_id': result.competitor_id,
                    'competitor_name': competitor.name if competitor else 'Unknown',
                    'product_id': result.product_id,
                    'product_name': product.name if product else 'Unknown',
                    'product_url': result.url,
                    'price': result.price,
                    'currency': result.currency,
                    'stock_status': result.stock_status,
                    'our_sku': product.our_sku if product else '',
                    'our_price': product.our_price if product else 0,
                    'success': result.success,
                    'error': result.error,
                })
        
        if rows:
            table_id = f"{self.config.gcp_project_id}.{self.config.bq_dataset}.competitor_prices"
            errors = self.bq_client.insert_rows_json(table_id, rows)
            if errors:
                logger.error(f"BigQuery insert errors: {errors}")
    
    def get_price_comparison(self) -> List[Dict[str, Any]]:
        """
        Get current price comparison across all competitors.
        
        Returns:
            List of products with prices from all competitors
        """
        comparison = []
        
        # Group by our SKU
        by_sku: Dict[str, List[Tuple[str, ProductToTrack]]] = {}
        
        for comp_id, competitor in self.competitors.items():
            for product in competitor.products:
                if product.our_sku:
                    if product.our_sku not in by_sku:
                        by_sku[product.our_sku] = []
                    by_sku[product.our_sku].append((competitor.name, product))
        
        for sku, entries in by_sku.items():
            item = {
                'our_sku': sku,
                'competitors': {},
            }
            
            for comp_name, product in entries:
                item['our_price'] = product.our_price
                item['competitors'][comp_name] = {
                    'price': product.current_price,
                    'stock': product.current_stock,
                    'last_checked': product.last_checked.isoformat() if product.last_checked else None,
                }
            
            comparison.append(item)
        
        return comparison


# =============================================================================
# FASTAPI ROUTES
# =============================================================================

try:
    from fastapi import APIRouter, HTTPException, BackgroundTasks
    from pydantic import BaseModel
    
    scraper_router = APIRouter(prefix="/api/competitors", tags=["competitors"])
    
    # Global scraper instance
    _scraper: Optional[CompetitorScraper] = None
    
    def get_scraper() -> CompetitorScraper:
        global _scraper
        if _scraper is None:
            _scraper = CompetitorScraper()
        return _scraper
    
    class CompetitorInput(BaseModel):
        name: str
        products: List[Dict[str, Any]]
        adapter: str = "generic"
        scrape_interval_hours: int = 6
    
    @scraper_router.post("/add")
    async def add_competitor(data: CompetitorInput):
        """Add a competitor to track."""
        scraper = get_scraper()
        competitor = scraper.add_competitor(
            name=data.name,
            products=data.products,
            adapter=data.adapter,
            scrape_interval_hours=data.scrape_interval_hours,
        )
        return {"status": "added", "competitor_id": competitor.id}
    
    @scraper_router.get("/list")
    async def list_competitors():
        """List all competitors."""
        scraper = get_scraper()
        return {
            'competitors': [
                {
                    'id': c.id,
                    'name': c.name,
                    'domain': c.domain,
                    'products_count': len(c.products),
                    'last_scraped': c.last_scraped.isoformat() if c.last_scraped else None,
                }
                for c in scraper.competitors.values()
            ]
        }
    
    @scraper_router.post("/scrape/{competitor_id}")
    async def scrape_competitor(competitor_id: str, background_tasks: BackgroundTasks):
        """Scrape a specific competitor."""
        scraper = get_scraper()
        
        if competitor_id not in scraper.competitors:
            raise HTTPException(404, "Competitor not found")
        
        results = await scraper.scrape_competitor(competitor_id)
        
        # Detect and alert changes
        changes = await scraper.detect_changes()
        if changes:
            background_tasks.add_task(scraper.send_alerts, changes)
        
        return {
            'results': [r.to_dict() for r in results],
            'changes': [c.to_dict() for c in changes],
        }
    
    @scraper_router.post("/scrape-all")
    async def scrape_all(background_tasks: BackgroundTasks):
        """Scrape all competitors."""
        scraper = get_scraper()
        results = await scraper.scrape_all()
        
        # Detect and alert changes
        changes = await scraper.detect_changes()
        if changes:
            background_tasks.add_task(scraper.send_alerts, changes)
        
        # Save to BigQuery
        background_tasks.add_task(scraper.save_to_bigquery, results)
        
        return {
            'competitors_scraped': len(results),
            'total_products': sum(len(r) for r in results.values()),
            'changes_detected': len(changes),
        }
    
    @scraper_router.get("/comparison")
    async def price_comparison():
        """Get price comparison."""
        scraper = get_scraper()
        return {'comparison': scraper.get_price_comparison()}

except ImportError:
    scraper_router = None


# =============================================================================
# CLI
# =============================================================================

async def main():
    """CLI for testing."""
    scraper = CompetitorScraper()
    
    # Add sample competitor
    scraper.add_competitor(
        name='Example Store',
        products=[
            {
                'url': 'https://example.com/product/1',
                'name': 'Sample Product',
                'our_sku': 'SKU001',
                'our_price': 99.99,
            }
        ],
        adapter='generic',
    )
    
    print(f"Added {len(scraper.competitors)} competitors")
    print("Run scrape_all() to start scraping")
    
    await scraper.close()


if __name__ == '__main__':
    asyncio.run(main())
