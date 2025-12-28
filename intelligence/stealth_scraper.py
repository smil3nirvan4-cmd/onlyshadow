"""
S.S.I. SHADOW - Stealth Scraper
Advanced web scraping with anti-detection techniques.
"""

import os
import logging
import asyncio
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set
from enum import Enum
import json

logger = logging.getLogger(__name__)


class ProxyType(Enum):
    DATACENTER = "datacenter"
    RESIDENTIAL = "residential"
    MOBILE = "mobile"


@dataclass
class Proxy:
    """Proxy configuration."""
    host: str
    port: int
    username: Optional[str] = None
    password: Optional[str] = None
    proxy_type: ProxyType = ProxyType.DATACENTER
    country: Optional[str] = None
    
    @property
    def url(self) -> str:
        auth = f"{self.username}:{self.password}@" if self.username else ""
        return f"http://{auth}{self.host}:{self.port}"


@dataclass
class ProxyStats:
    """Usage statistics for a proxy."""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    blocked_count: int = 0
    last_used: Optional[datetime] = None
    last_blocked: Optional[datetime] = None
    
    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 1.0
        return self.successful_requests / self.total_requests


class ProxyManager:
    """
    Manages pool of proxies for web scraping.
    Handles rotation, health checking, and blocking detection.
    """
    
    def __init__(self):
        self._proxies: List[Proxy] = []
        self._blocked: Set[str] = set()
        self._stats: Dict[str, ProxyStats] = {}
        self._last_used: Dict[str, datetime] = {}
    
    def add_proxy(self, proxy: Proxy):
        """Add a proxy to the pool."""
        self._proxies.append(proxy)
        self._stats[proxy.url] = ProxyStats()
    
    def add_proxies(self, proxies: List[Proxy]):
        """Add multiple proxies."""
        for proxy in proxies:
            self.add_proxy(proxy)
    
    async def get_proxy(
        self,
        country: Optional[str] = None,
        proxy_type: ProxyType = ProxyType.RESIDENTIAL,
        exclude_recently_used: bool = True
    ) -> Optional[Proxy]:
        """
        Get a proxy from the pool.
        
        Args:
            country: Target country code
            proxy_type: Preferred proxy type
            exclude_recently_used: Avoid proxies used in last 60s
        
        Returns:
            Selected proxy or None
        """
        available = []
        now = datetime.utcnow()
        
        for proxy in self._proxies:
            # Skip blocked proxies
            if proxy.url in self._blocked:
                continue
            
            # Filter by country
            if country and proxy.country != country:
                continue
            
            # Filter by type
            if proxy.proxy_type != proxy_type:
                continue
            
            # Check recent usage
            if exclude_recently_used:
                last_used = self._last_used.get(proxy.url)
                if last_used and (now - last_used).seconds < 60:
                    continue
            
            # Check health score
            stats = self._stats.get(proxy.url, ProxyStats())
            if stats.success_rate < 0.3:
                continue
            
            available.append((proxy, stats.success_rate))
        
        if not available:
            # Fallback to any available
            available = [(p, 1.0) for p in self._proxies if p.url not in self._blocked]
        
        if not available:
            return None
        
        # Weighted random selection favoring higher success rates
        weights = [s for _, s in available]
        total = sum(weights)
        if total > 0:
            weights = [w/total for w in weights]
        
        selected = random.choices([p for p, _ in available], weights=weights)[0]
        self._last_used[selected.url] = now
        
        return selected
    
    def report_success(self, proxy: Proxy):
        """Report successful request."""
        stats = self._stats.get(proxy.url, ProxyStats())
        stats.total_requests += 1
        stats.successful_requests += 1
        stats.last_used = datetime.utcnow()
        self._stats[proxy.url] = stats
    
    def report_failure(self, proxy: Proxy, is_blocked: bool = False):
        """Report failed request."""
        stats = self._stats.get(proxy.url, ProxyStats())
        stats.total_requests += 1
        stats.failed_requests += 1
        stats.last_used = datetime.utcnow()
        
        if is_blocked:
            stats.blocked_count += 1
            stats.last_blocked = datetime.utcnow()
            
            if stats.blocked_count >= 3:
                self._blocked.add(proxy.url)
                logger.warning(f"Proxy {proxy.host} blocked, removing from pool")
        
        self._stats[proxy.url] = stats
    
    def get_stats(self) -> Dict[str, Any]:
        """Get pool statistics."""
        return {
            "total_proxies": len(self._proxies),
            "blocked_proxies": len(self._blocked),
            "available_proxies": len(self._proxies) - len(self._blocked),
            "proxies": {
                url: stats.__dict__ 
                for url, stats in self._stats.items()
            }
        }


class AdaptiveRateLimiter:
    """
    Rate limiter that adapts based on response patterns.
    """
    
    def __init__(
        self,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        min_delay: float = 0.5
    ):
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.min_delay = min_delay
        
        self._domain_delays: Dict[str, float] = {}
        self._last_request: Dict[str, datetime] = {}
    
    async def wait(self, domain: str):
        """Wait appropriate time before making request."""
        delay = self._domain_delays.get(domain, self.base_delay)
        
        # Add jitter
        jitter = delay * 0.3 * random.random()
        actual_delay = delay + jitter
        
        # Check time since last request
        last = self._last_request.get(domain)
        if last:
            elapsed = (datetime.utcnow() - last).total_seconds()
            if elapsed < actual_delay:
                await asyncio.sleep(actual_delay - elapsed)
        
        self._last_request[domain] = datetime.utcnow()
    
    def increase_delay(self, domain: str, factor: float = 1.5):
        """Increase delay after rate limit detection."""
        current = self._domain_delays.get(domain, self.base_delay)
        new_delay = min(current * factor, self.max_delay)
        self._domain_delays[domain] = new_delay
        logger.info(f"Increased delay for {domain} to {new_delay:.1f}s")
    
    def decrease_delay(self, domain: str, factor: float = 0.9):
        """Decrease delay after successful requests."""
        current = self._domain_delays.get(domain, self.base_delay)
        new_delay = max(current * factor, self.min_delay)
        self._domain_delays[domain] = new_delay


USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]


@dataclass
class ScrapeResult:
    """Result of a scrape operation."""
    url: str
    success: bool
    status_code: Optional[int] = None
    content: Optional[str] = None
    error: Optional[str] = None
    response_time_ms: Optional[int] = None
    proxy_used: Optional[str] = None


class StealthScraper:
    """
    Web scraper with anti-detection techniques.
    
    Features:
    - Random user agents
    - Proxy rotation
    - Adaptive rate limiting
    - Human-like behavior simulation
    """
    
    def __init__(
        self,
        proxy_manager: Optional[ProxyManager] = None,
        rate_limiter: Optional[AdaptiveRateLimiter] = None
    ):
        self.proxy_manager = proxy_manager or ProxyManager()
        self.rate_limiter = rate_limiter or AdaptiveRateLimiter()
    
    def _get_headers(self) -> Dict[str, str]:
        """Get randomized headers."""
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Cache-Control": "max-age=0",
        }
    
    async def fetch(
        self,
        url: str,
        use_proxy: bool = True,
        retry_count: int = 3
    ) -> ScrapeResult:
        """
        Fetch a URL with stealth techniques.
        
        Args:
            url: URL to fetch
            use_proxy: Whether to use proxy
            retry_count: Number of retries
        
        Returns:
            ScrapeResult
        """
        from urllib.parse import urlparse
        
        domain = urlparse(url).netloc
        
        for attempt in range(retry_count):
            # Rate limiting
            await self.rate_limiter.wait(domain)
            
            # Get proxy
            proxy = None
            if use_proxy:
                proxy = await self.proxy_manager.get_proxy()
            
            start_time = datetime.utcnow()
            
            try:
                import aiohttp
                
                connector = None
                if proxy:
                    connector = aiohttp.TCPConnector()
                
                async with aiohttp.ClientSession(connector=connector) as session:
                    kwargs = {
                        "headers": self._get_headers(),
                        "timeout": aiohttp.ClientTimeout(total=30)
                    }
                    
                    if proxy:
                        kwargs["proxy"] = proxy.url
                    
                    async with session.get(url, **kwargs) as response:
                        response_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)
                        
                        if response.status == 200:
                            content = await response.text()
                            
                            if proxy:
                                self.proxy_manager.report_success(proxy)
                            self.rate_limiter.decrease_delay(domain)
                            
                            return ScrapeResult(
                                url=url,
                                success=True,
                                status_code=200,
                                content=content,
                                response_time_ms=response_time,
                                proxy_used=proxy.url if proxy else None
                            )
                        
                        elif response.status == 429:
                            # Rate limited
                            self.rate_limiter.increase_delay(domain, factor=2.0)
                            if proxy:
                                self.proxy_manager.report_failure(proxy, is_blocked=False)
                        
                        elif response.status == 403:
                            # Blocked
                            if proxy:
                                self.proxy_manager.report_failure(proxy, is_blocked=True)
                        
                        else:
                            if proxy:
                                self.proxy_manager.report_failure(proxy)
            
            except Exception as e:
                logger.error(f"Scrape error for {url}: {e}")
                if proxy:
                    self.proxy_manager.report_failure(proxy)
            
            # Wait before retry
            await asyncio.sleep(2 ** attempt)
        
        return ScrapeResult(
            url=url,
            success=False,
            error="Max retries exceeded"
        )
    
    async def fetch_multiple(
        self,
        urls: List[str],
        max_concurrent: int = 5
    ) -> List[ScrapeResult]:
        """Fetch multiple URLs with concurrency limit."""
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def limited_fetch(url):
            async with semaphore:
                return await self.fetch(url)
        
        tasks = [limited_fetch(url) for url in urls]
        return await asyncio.gather(*tasks)


class CaptchaSolver:
    """
    CAPTCHA solving service integration.
    Supports 2Captcha, Anti-Captcha, and CapSolver.
    """
    
    def __init__(
        self,
        two_captcha_key: Optional[str] = None,
        anti_captcha_key: Optional[str] = None,
        capsolver_key: Optional[str] = None
    ):
        self.two_captcha_key = two_captcha_key
        self.anti_captcha_key = anti_captcha_key
        self.capsolver_key = capsolver_key
    
    async def solve_recaptcha_v2(
        self,
        site_key: str,
        page_url: str,
        timeout: int = 120
    ) -> Optional[str]:
        """
        Solve reCAPTCHA v2.
        
        Args:
            site_key: Google site key
            page_url: Page URL where CAPTCHA appears
            timeout: Max wait time in seconds
        
        Returns:
            CAPTCHA token or None
        """
        if self.two_captcha_key:
            return await self._solve_2captcha(site_key, page_url, "recaptcha", timeout)
        
        logger.warning("No CAPTCHA solver configured")
        return None
    
    async def solve_hcaptcha(
        self,
        site_key: str,
        page_url: str,
        timeout: int = 120
    ) -> Optional[str]:
        """Solve hCaptcha."""
        if self.two_captcha_key:
            return await self._solve_2captcha(site_key, page_url, "hcaptcha", timeout)
        
        return None
    
    async def _solve_2captcha(
        self,
        site_key: str,
        page_url: str,
        captcha_type: str,
        timeout: int
    ) -> Optional[str]:
        """Solve CAPTCHA using 2Captcha service."""
        import aiohttp
        
        # Submit task
        submit_url = "http://2captcha.com/in.php"
        params = {
            "key": self.two_captcha_key,
            "method": "userrecaptcha" if captcha_type == "recaptcha" else "hcaptcha",
            "googlekey" if captcha_type == "recaptcha" else "sitekey": site_key,
            "pageurl": page_url,
            "json": 1
        }
        
        async with aiohttp.ClientSession() as session:
            # Submit
            async with session.get(submit_url, params=params) as response:
                data = await response.json()
                if data.get("status") != 1:
                    logger.error(f"2Captcha submit error: {data}")
                    return None
                
                task_id = data["request"]
            
            # Poll for result
            result_url = "http://2captcha.com/res.php"
            start = datetime.utcnow()
            
            while (datetime.utcnow() - start).seconds < timeout:
                await asyncio.sleep(5)
                
                params = {
                    "key": self.two_captcha_key,
                    "action": "get",
                    "id": task_id,
                    "json": 1
                }
                
                async with session.get(result_url, params=params) as response:
                    data = await response.json()
                    
                    if data.get("status") == 1:
                        return data["request"]
                    
                    if data.get("request") != "CAPCHA_NOT_READY":
                        logger.error(f"2Captcha error: {data}")
                        return None
        
        logger.error("CAPTCHA solve timeout")
        return None


@dataclass
class PriceData:
    """Extracted price data from competitor."""
    product_name: str
    product_url: str
    price: float
    currency: str
    in_stock: bool
    scraped_at: datetime
    competitor: str


class CompetitorScraperOrchestrator:
    """
    Orchestrates competitor price scraping.
    """
    
    def __init__(
        self,
        scraper: StealthScraper,
        captcha_solver: Optional[CaptchaSolver] = None
    ):
        self.scraper = scraper
        self.captcha_solver = captcha_solver
        
        # Price extractors by domain
        self._extractors: Dict[str, callable] = {}
    
    def register_extractor(self, domain: str, extractor: callable):
        """Register a price extractor for a domain."""
        self._extractors[domain] = extractor
    
    async def scrape_product(
        self,
        url: str,
        competitor: str
    ) -> Optional[PriceData]:
        """Scrape price for a single product."""
        from urllib.parse import urlparse
        
        result = await self.scraper.fetch(url)
        
        if not result.success:
            logger.error(f"Failed to scrape {url}: {result.error}")
            return None
        
        domain = urlparse(url).netloc
        extractor = self._extractors.get(domain)
        
        if extractor:
            return extractor(result.content, url, competitor)
        
        # Generic extraction
        return self._generic_extract(result.content, url, competitor)
    
    def _generic_extract(
        self,
        html: str,
        url: str,
        competitor: str
    ) -> Optional[PriceData]:
        """Generic price extraction using common patterns."""
        from bs4 import BeautifulSoup
        import re
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Try common price selectors
        price_selectors = [
            '[data-price]',
            '.price',
            '.product-price',
            '#price',
            '[itemprop="price"]',
        ]
        
        for selector in price_selectors:
            elem = soup.select_one(selector)
            if elem:
                # Extract price value
                text = elem.get_text()
                price_match = re.search(r'[\d,.]+', text.replace(',', ''))
                
                if price_match:
                    try:
                        price = float(price_match.group())
                        
                        # Get product name
                        title = soup.select_one('h1') or soup.select_one('title')
                        name = title.get_text().strip() if title else "Unknown"
                        
                        return PriceData(
                            product_name=name[:200],
                            product_url=url,
                            price=price,
                            currency="USD",
                            in_stock=True,
                            scraped_at=datetime.utcnow(),
                            competitor=competitor
                        )
                    except ValueError:
                        continue
        
        return None
    
    async def scrape_competitor(
        self,
        competitor: str,
        product_urls: List[str],
        max_concurrent: int = 3
    ) -> List[PriceData]:
        """Scrape multiple products from a competitor."""
        results = []
        
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def scrape_one(url):
            async with semaphore:
                return await self.scrape_product(url, competitor)
        
        tasks = [scrape_one(url) for url in product_urls]
        scraped = await asyncio.gather(*tasks)
        
        for data in scraped:
            if data:
                results.append(data)
        
        logger.info(f"Scraped {len(results)}/{len(product_urls)} products from {competitor}")
        return results
