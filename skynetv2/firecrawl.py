from __future__ import annotations

import re
import ipaddress
from typing import List, Dict, Any, Optional
import asyncio
import time
import requests
from urllib.parse import urlparse


class FirecrawlAdapter:
    """Real Firecrawl integration adapter for autosearch execution.
    
    Provides search/scrape/crawl/deep_research functionality using Firecrawl API.
    Includes safety checks to prevent internal IP access and localhost scraping.
    """
    
    name = "firecrawl"
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.base_url = "https://api.firecrawl.dev/v1"
        self.timeout = 30
        
        # Internal IP ranges to block for security
        self._blocked_networks = [
            ipaddress.ip_network('127.0.0.0/8'),      # localhost
            ipaddress.ip_network('10.0.0.0/8'),       # private class A
            ipaddress.ip_network('172.16.0.0/12'),    # private class B
            ipaddress.ip_network('192.168.0.0/16'),   # private class C
            ipaddress.ip_network('169.254.0.0/16'),   # link-local
            ipaddress.ip_network('::1/128'),          # IPv6 localhost
            ipaddress.ip_network('fc00::/7'),         # IPv6 private
        ]
    
    def _is_safe_url(self, url: str) -> bool:
        """Check if URL is safe to access (not internal IP or localhost)."""
        try:
            parsed = urlparse(url if url.startswith(('http://', 'https://')) else f'https://{url}')
            hostname = parsed.hostname
            
            if not hostname:
                return False
            
            # Block localhost variants
            if hostname.lower() in ['localhost', 'loopback']:
                return False
            
            # Check if hostname resolves to blocked IP ranges
            try:
                ip = ipaddress.ip_address(hostname)
                for network in self._blocked_networks:
                    if ip in network:
                        return False
            except ipaddress.AddressValueError:
                # Hostname is not an IP address, which is fine
                pass
                
            return True
        except Exception:
            return False
    
    def _validate_api_key(self) -> bool:
        """Check if API key is configured."""
        return bool(self.api_key and self.api_key.strip())
    
    async def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Dict[str, Any]:
        """Make async HTTP request to Firecrawl API."""
        if not self._validate_api_key():
            raise ValueError("Firecrawl API key not configured")
        
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        
        def _sync_request():
            if method.upper() == 'GET':
                response = requests.get(url, headers=headers, timeout=self.timeout, params=data or {})
            else:
                response = requests.post(url, headers=headers, json=data or {}, timeout=self.timeout)
            return response.json()
        
        # Run in executor to avoid blocking
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _sync_request)
    
    async def search(self, query: str, limit: int = 5) -> List[str]:
        """Search the web using Firecrawl search."""
        if not query.strip():
            return []
        
        try:
            result = await self._make_request('POST', '/search', {
                'query': query.strip(),
                'limit': min(limit, 10),  # Cap at 10 for safety
                'scrapeOptions': {
                    'formats': ['markdown'],
                    'onlyMainContent': True
                }
            })
            
            if not result.get('success', False):
                return [f"Search error: {result.get('error', 'Unknown error')}"]
            
            data = result.get('data', [])
            results = []
            
            for item in data[:limit]:
                url = item.get('url', '')
                title = item.get('title', '')
                content = item.get('markdown', '').strip()
                
                # Build result string
                result_parts = []
                if title:
                    result_parts.append(f"[{title}]")
                if url:
                    result_parts.append(f"({url})")
                if content:
                    # Truncate content to reasonable length
                    preview = content[:200] + '...' if len(content) > 200 else content
                    result_parts.append(f": {preview}")
                
                if result_parts:
                    results.append(' '.join(result_parts))
            
            return results if results else ["(no search results)"]
            
        except Exception as e:
            return [f"Search failed: {type(e).__name__}: {str(e)[:100]}"]
    
    async def scrape(self, url: str) -> str:
        """Scrape a single URL using Firecrawl."""
        if not url.strip():
            return "(empty URL)"
        
        # Safety check
        if not self._is_safe_url(url):
            return f"[scrape:blocked] URL blocked for security: {url[:100]}"
        
        try:
            result = await self._make_request('POST', '/scrape', {
                'url': url,
                'formats': ['markdown'],
                'onlyMainContent': True,
                'timeout': 30000
            })
            
            if not result.get('success', False):
                error = result.get('error', 'Unknown error')
                return f"[scrape:error] {error[:100]}"
            
            data = result.get('data', {})
            content = data.get('markdown', '').strip()
            
            if content:
                # Add metadata header
                metadata = data.get('metadata', {})
                title = metadata.get('title', '')
                source_url = metadata.get('sourceURL', url)
                
                header_parts = [f"Source: {source_url}"]
                if title:
                    header_parts.append(f"Title: {title}")
                
                return f"[scrape:firecrawl] {' | '.join(header_parts)}\n\n{content}"
            else:
                return f"[scrape:empty] No content extracted from {url}"
                
        except Exception as e:
            return f"[scrape:error] {type(e).__name__}: {str(e)[:100]}"
    
    async def scrape_multi(self, urls: List[str]) -> List[str]:
        """Scrape multiple URLs."""
        if not urls:
            return []
        
        # Limit to 5 URLs for safety and performance
        safe_urls = []
        results = []
        
        for url in urls[:5]:
            if self._is_safe_url(url):
                safe_urls.append(url)
            else:
                results.append(f"[scrape:blocked] {url[:80]}")
        
        # Scrape safe URLs
        for url in safe_urls:
            result = await self.scrape(url)
            results.append(result)
        
        return results
    
    async def crawl(self, url: str, max_depth: int = 2, limit: int = 20) -> List[str]:
        """Crawl a website using Firecrawl."""
        if not url.strip():
            return ["(empty URL)"]
        
        # Safety check
        if not self._is_safe_url(url):
            return [f"[crawl:blocked] URL blocked for security: {url[:100]}"]
        
        # Enforce safety caps
        max_depth = max(1, min(3, max_depth))
        limit = max(5, min(50, limit))
        
        try:
            # Start crawl job
            crawl_result = await self._make_request('POST', '/crawl', {
                'url': url,
                'limit': limit,
                'scrapeOptions': {
                    'formats': ['markdown'],
                    'onlyMainContent': True
                },
                'maxDepth': max_depth
            })
            
            if not crawl_result.get('success', False):
                error = crawl_result.get('error', 'Unknown error')
                return [f"[crawl:error] {error[:100]}"]
            
            crawl_id = crawl_result.get('id')
            if not crawl_id:
                return ["[crawl:error] No crawl ID returned"]
            
            # Poll for completion (simple polling with timeout)
            max_wait = 60  # 60 seconds max wait
            start_time = time.time()
            
            while time.time() - start_time < max_wait:
                status_result = await self._make_request('GET', f'/crawl/{crawl_id}')
                
                if not status_result.get('success', False):
                    break
                
                status = status_result.get('status', '')
                if status == 'completed':
                    data = status_result.get('data', [])
                    discovered_urls = []
                    
                    for item in data[:limit]:
                        item_url = item.get('metadata', {}).get('sourceURL', '')
                        title = item.get('metadata', {}).get('title', '')
                        
                        if item_url:
                            if title:
                                discovered_urls.append(f"{item_url} [{title}]")
                            else:
                                discovered_urls.append(item_url)
                    
                    return discovered_urls if discovered_urls else ["[crawl:empty] No pages discovered"]
                
                elif status in ['failed', 'cancelled']:
                    return [f"[crawl:failed] Crawl {status}"]
                
                # Wait before next check
                await asyncio.sleep(2)
            
            return ["[crawl:timeout] Crawl timed out"]
            
        except Exception as e:
            return [f"[crawl:error] {type(e).__name__}: {str(e)[:100]}"]
    
    async def deep_research(self, query: str) -> Dict[str, Any]:
        """Perform deep research using search + scrape combination."""
        if not query.strip():
            return {
                "query": "(empty query)",
                "steps": [],
                "summary": "No query provided for research."
            }
        
        steps = []
        summary = ""
        
        try:
            steps.append("1. Searching for relevant sources...")
            
            # Search for relevant URLs
            search_results = await self.search(query, limit=3)
            if not search_results or search_results == ["(no search results)"]:
                return {
                    "query": query[:180],
                    "steps": steps + ["2. No search results found"],
                    "summary": "Unable to find relevant sources for research."
                }
            
            steps.append(f"2. Found {len(search_results)} sources, extracting content...")
            
            # Extract URLs from search results for scraping
            urls_to_scrape = []
            for result in search_results[:2]:  # Limit to top 2 for deep research
                # Extract URL from result format: [title] (url) : content
                url_match = re.search(r'\(([^)]+)\)', result)
                if url_match:
                    urls_to_scrape.append(url_match.group(1))
            
            # Scrape the URLs
            content_pieces = []
            if urls_to_scrape:
                steps.append("3. Scraping detailed content from sources...")
                for url in urls_to_scrape:
                    scraped = await self.scrape(url)
                    if scraped and not scraped.startswith('[scrape:error]'):
                        content_pieces.append(scraped[:500])  # Limit content length
            
            steps.append("4. Synthesizing research summary...")
            
            # Create summary from gathered content
            if content_pieces:
                summary = f"Research on '{query}':\n\n"
                for i, content in enumerate(content_pieces, 1):
                    summary += f"Source {i}: {content[:200]}...\n\n"
                
                summary += f"Found {len(content_pieces)} relevant sources with detailed information."
            else:
                summary = f"Research completed for '{query}' but no detailed content could be extracted from sources."
            
        except Exception as e:
            steps.append(f"Error during research: {type(e).__name__}")
            summary = f"Research failed: {str(e)[:200]}"
        
        return {
            "query": query[:180],
            "steps": steps,
            "summary": summary
        }


# Factory function to build appropriate adapter
def build_firecrawl_adapter(api_key: Optional[str] = None) -> FirecrawlAdapter:
    """Build Firecrawl adapter with API key."""
    return FirecrawlAdapter(api_key=api_key)
