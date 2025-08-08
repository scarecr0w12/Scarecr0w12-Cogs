from __future__ import annotations

from typing import List, Optional
import time


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


class SerpStubSearchProvider(SearchProvider):
    """Stub provider placeholder for a future real SERP integration.

    Returns a deterministic placeholder noting it is not yet implemented (fallback if real import fails).
    """
    name = "serp"

    async def search(self, query: str, topk: int = 5) -> List[str]:
        query = (query or "").strip()
        if not query:
            return []
        topk = max(1, min(int(topk), 10))
        return [f"[serp-stub] '{query}' provider not available (#{i})" for i in range(1, topk + 1)]


def build_search_provider(kind: str | None = None, api_key: Optional[str] = None) -> SearchProvider:
    kind = (kind or "dummy").lower()
    if kind == "dummy":
        return DummySearchProvider()
    if kind == "serp":
        # Attempt to import real Serp provider; fall back to stub if unavailable
        try:
            from .search_serp import SerpSearchProvider  # type: ignore
            return SerpSearchProvider(api_key=api_key)
        except Exception:
            return SerpStubSearchProvider()
    if kind == "serp-stub":
        return SerpStubSearchProvider()
    # Fallback to dummy if unknown
    return DummySearchProvider()
