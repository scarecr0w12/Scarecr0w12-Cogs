from __future__ import annotations

from typing import List, Optional, Dict, Any
import time
import asyncio
import aiohttp

class SearchProvider:
    """Abstract search provider interface.

    Future real implementations (e.g., Bing, Tavily) should implement `search`.
    """
    name: str = "abstract"

    async def search(self, query: str, topk: int = 5) -> List[str]:  # pragma: no cover - interface
        raise NotImplementedError


class DummySearchProvider(SearchProvider):
    name = "dummy"

    async def search(self, query: str, topk: int = 5) -> List[str]:
        query = (query or "").strip()
        if not query:
            return []
        topk = max(1, min(int(topk), 10))
        now = int(time.time())
        results: List[str] = []
        for i in range(1, topk + 1):
            snippet = f"Result {i} for '{query}' at {now} – placeholder snippet lorem ipsum."[:160]
            results.append(snippet)
        return results


class SerpSearchProvider(SearchProvider):
    """Real SERP API provider for web search.
    
    Uses SerpAPI (serpapi.com) for web search results.
    Requires API key configuration.
    """
    name = "serp"
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
    
    async def search(self, query: str, topk: int = 5) -> List[str]:
        query = (query or "").strip()
        if not query:
            return []
        if not self.api_key:
            return [f"[serp-error] No API key configured for SERP provider"]
        
        topk = max(1, min(int(topk), 10))
        
        # Use executor to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        try:
            results = await loop.run_in_executor(None, self._search_sync, query, topk)
            return results
        except Exception as e:
            return [f"[serp-error] Search failed: {str(e)[:100]}"]
    
    def _search_sync(self, query: str, topk: int) -> List[str]:
        """Synchronous search implementation using requests."""
        try:
            import requests
            import json
        except ImportError:
            return [f"[serp-error] Missing requests dependency"]
        
        url = "https://serpapi.com/search"
        params = {
            "engine": "google",
            "q": query,
            "api_key": self.api_key,
            "num": topk,
            "safe": "active"
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            results = []
            organic_results = data.get("organic_results", [])
            
            for i, result in enumerate(organic_results[:topk]):
                title = result.get("title", "")
                snippet = result.get("snippet", "")
                link = result.get("link", "")
                
                # Format as: "Title - Snippet"
                formatted = f"{title}"
                if snippet:
                    formatted += f" - {snippet[:120]}"
                if link:
                    formatted += f" [{link}]"
                    
                results.append(formatted[:200])
            
            if not results:
                results = [f"[serp] No results found for '{query}'"]
                
            return results
            
        except requests.exceptions.Timeout:
            return [f"[serp-error] Request timeout for '{query}'"]
        except requests.exceptions.RequestException as e:
            return [f"[serp-error] Request failed: {str(e)[:80]}"]
        except (json.JSONDecodeError, KeyError) as e:
            return [f"[serp-error] Response parsing failed: {str(e)[:80]}"]


class SerpStubSearchProvider(SearchProvider):
    """Stub provider placeholder for a future real SERP integration.

    Returns a deterministic placeholder noting it is not yet implemented.
    """
    name = "serp"

    async def search(self, query: str, topk: int = 5) -> List[str]:
        query = (query or "").strip()
        if not query:
            return []
        topk = max(1, min(int(topk), 10))
        return [f"[serp-stub] '{query}' provider not yet implemented (#{i})" for i in range(1, topk + 1)]


def build_search_provider(kind: str | None = None, api_key: Optional[str] = None) -> SearchProvider:
    kind = (kind or "dummy").lower()
    if kind == "dummy":
        return DummySearchProvider()
    if kind == "serp":
        return SerpSearchProvider(api_key=api_key)
    if kind == "serp-stub":
        return SerpStubSearchProvider()
    # Fallback to dummy if unknown
    return DummySearchProvider()
