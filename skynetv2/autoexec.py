from __future__ import annotations

from typing import List, Dict, Any, Optional
from .firecrawl import build_firecrawl_adapter

# Internal placeholder execution adapter for autosearch non-search modes.
# Now supports real Firecrawl integration when API key is provided.

class AutoExecAdapter:
    name = "placeholder"

    async def scrape(self, url: str) -> str:
        return f"[scrape:stub] Fetched summary for {url[:80]} (not implemented)."

    async def scrape_multi(self, urls: List[str]) -> List[str]:
        out = []
        for u in urls[:5]:
            out.append(f"[scrape:stub] {u[:80]} -> (content not implemented)")
        return out

    async def crawl(self, url: str, max_depth: int = 2, limit: int = 20) -> List[str]:
        # Return synthetic discovered URLs (stub)
        discovered = []
        base = url.rstrip('/')
        for i in range(1, min(limit, 5) + 1):
            discovered.append(f"{base}/page-{i}")
        return discovered

    async def deep_research(self, query: str) -> Dict[str, Any]:
        return {
            "query": query[:180],
            "steps": [
                "(stub) gather top sources",
                "(stub) extract key points",
                "(stub) synthesize summary",
            ],
            "summary": "Deep research execution is not implemented yet (placeholder).",
        }


# Simple factory indirection supporting both placeholder and real Firecrawl adapter.
_SINGLETON: AutoExecAdapter | None = None

def build_autoexec_adapter(api_key: Optional[str] = None) -> AutoExecAdapter:
    """Build autoexec adapter - Firecrawl if API key provided, placeholder otherwise."""
    global _SINGLETON
    
    # If API key provided, always return a new Firecrawl adapter
    if api_key and api_key.strip():
        return build_firecrawl_adapter(api_key=api_key)
    
    # Otherwise return singleton placeholder
    if _SINGLETON is None:
        _SINGLETON = AutoExecAdapter()
    return _SINGLETON
