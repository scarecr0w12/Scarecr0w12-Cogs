from __future__ import annotations

"""SERP API search provider implementation.

Small, executor-offloaded HTTP call using requests (if present). Fallback errors are
returned as single-line strings with a [serp-error] prefix for user clarity.

No new mandatory dependency: if requests is missing, provider returns an error notice.
"""
from typing import List, Optional
import asyncio

from .search import SearchProvider

class SerpSearchProvider(SearchProvider):
    name = "serp"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key

    async def search(self, query: str, topk: int = 5) -> List[str]:
        query = (query or "").strip()
        if not query:
            return []
        if not self.api_key:
            return ["[serp-error] No API key configured for SERP provider"]
        topk = max(1, min(int(topk), 10))
        loop = asyncio.get_event_loop()
        try:
            return await loop.run_in_executor(None, self._search_sync, query, topk)
        except Exception as e:  # broad catch to keep user messaging simple
            return [f"[serp-error] Search failed: {str(e)[:100]}"]

    def _search_sync(self, query: str, topk: int) -> List[str]:
        try:
            import requests, json
        except ImportError:
            return ["[serp-error] Missing 'requests' dependency (install manually to enable real SERP search)"]
        url = "https://serpapi.com/search"
        params = {
            "engine": "google",
            "q": query,
            "api_key": self.api_key,
            "num": topk,
            "safe": "active",
        }
        try:
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            organics = data.get("organic_results", []) or []
            out: List[str] = []
            for r in organics[:topk]:
                title = r.get("title", "")
                snippet = r.get("snippet", "")
                link = r.get("link", "")
                line = title or link or "(untitled result)"
                if snippet:
                    line += f" - {snippet[:120]}"
                if link:
                    line += f" [{link}]"
                out.append(line[:200])
            if not out:
                return [f"[serp] No results found for '{query}'"]
            return out
        except requests.exceptions.Timeout:
            return [f"[serp-error] Request timeout for '{query}'"]
        except requests.exceptions.RequestException as e:
            return [f"[serp-error] Request failed: {str(e)[:80]}"]
        except (ValueError, KeyError) as e:
            return [f"[serp-error] Response parsing failed: {str(e)[:80]}"]
