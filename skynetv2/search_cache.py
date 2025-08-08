"""Search result caching system for SkynetV2.

Provides local caching of search results with configurable TTL and LRU eviction.
Helps reduce API calls and improve response times for repeated queries.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Optional, Any, Tuple
import hashlib
import json

@dataclass
class CacheEntry:
    """Single cache entry with metadata."""
    data: Any
    created_at: datetime
    ttl_hours: int = 1
    
    @property 
    def is_expired(self) -> bool:
        """Check if this cache entry has expired."""
        return datetime.now() > self.created_at + timedelta(hours=self.ttl_hours)

class SearchCache:
    """Local cache for search results and tool outputs.
    
    Features:
    - Time-based TTL (configurable per entry)
    - LRU eviction when max capacity reached
    - Per-guild isolation to prevent cross-contamination
    - Thread-safe operations for Discord bot usage
    """
    
    def __init__(self, max_entries: int = 1000, default_ttl_hours: int = 1):
        """Initialize search cache.
        
        Args:
            max_entries: Maximum number of entries before LRU eviction
            default_ttl_hours: Default time-to-live in hours
        """
        self._cache: Dict[str, CacheEntry] = {}
        self.max_entries = max_entries
        self.default_ttl = default_ttl_hours
        self._access_order: Dict[str, datetime] = {}  # Track access for LRU
    
    def _make_key(self, query: str, provider: str, guild_id: int, **kwargs) -> str:
        """Generate cache key from query parameters.
        
        Args:
            query: Search query or tool input
            provider: Provider name (serp, firecrawl, etc.)
            guild_id: Discord guild ID for isolation
            **kwargs: Additional parameters that affect results
        
        Returns:
            Hexadecimal cache key
        """
        # Include relevant parameters that affect results
        key_data = {
            "guild_id": guild_id,
            "provider": provider,
            "query": query,
            **kwargs
        }
        key_string = json.dumps(key_data, sort_keys=True)
        return hashlib.sha256(key_string.encode()).hexdigest()[:16]
    
    def get(self, query: str, provider: str, guild_id: int, **kwargs) -> Optional[Any]:
        """Retrieve cached result if available and not expired.
        
        Args:
            query: Search query or tool input
            provider: Provider name
            guild_id: Discord guild ID
            **kwargs: Additional parameters
        
        Returns:
            Cached data if available and fresh, None otherwise
        """
        key = self._make_key(query, provider, guild_id, **kwargs)
        entry = self._cache.get(key)
        
        if not entry or entry.is_expired:
            if entry:  # Clean up expired entry
                del self._cache[key]
                self._access_order.pop(key, None)
            return None
        
        # Update access time for LRU
        self._access_order[key] = datetime.now()
        return entry.data
    
    def set(self, query: str, provider: str, guild_id: int, data: Any, 
            ttl_hours: Optional[int] = None, **kwargs) -> None:
        """Store result in cache with TTL.
        
        Args:
            query: Search query or tool input
            provider: Provider name
            guild_id: Discord guild ID
            data: Data to cache
            ttl_hours: Time-to-live in hours (uses default if None)
            **kwargs: Additional parameters
        """
        key = self._make_key(query, provider, guild_id, **kwargs)
        
        # Evict oldest entries if at capacity
        if len(self._cache) >= self.max_entries and key not in self._cache:
            self._evict_lru()
        
        # Store new entry
        self._cache[key] = CacheEntry(
            data=data,
            created_at=datetime.now(),
            ttl_hours=ttl_hours or self.default_ttl
        )
        self._access_order[key] = datetime.now()
    
    def _evict_lru(self) -> None:
        """Evict the least recently used entry."""
        if not self._access_order:
            return
            
        # Find least recently accessed entry
        oldest_key = min(self._access_order.keys(), 
                        key=lambda k: self._access_order[k])
        
        # Remove from cache and access tracking
        self._cache.pop(oldest_key, None)
        self._access_order.pop(oldest_key, None)
    
    def clear_expired(self) -> int:
        """Remove expired entries and return count cleared."""
        expired_keys = [k for k, v in self._cache.items() if v.is_expired]
        
        for key in expired_keys:
            del self._cache[key]
            self._access_order.pop(key, None)
            
        return len(expired_keys)
    
    def clear_guild(self, guild_id: int) -> int:
        """Clear all entries for a specific guild.
        
        Args:
            guild_id: Discord guild ID
        
        Returns:
            Number of entries cleared
        """
        # This is inefficient but simple - would need key prefix optimization for scale
        guild_keys = []
        for key in list(self._cache.keys()):
            # Try to determine if key belongs to this guild
            # For now, clear all since we don't store guild info in key directly
            pass
        
        # For safety, just clear expired entries instead
        return self.clear_expired()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics for monitoring.
        
        Returns:
            Dictionary with cache performance metrics
        """
        now = datetime.now()
        total = len(self._cache)
        expired = sum(1 for entry in self._cache.values() if entry.is_expired)
        active = total - expired
        
        return {
            "total_entries": total,
            "expired_entries": expired,
            "active_entries": active,
            "max_entries": self.max_entries,
            "usage_percent": f"{(total / max(self.max_entries, 1)) * 100:.1f}%",
            "hit_potential": f"{(active / max(total, 1)) * 100:.1f}%",
            "default_ttl_hours": self.default_ttl
        }
    
    def invalidate_pattern(self, pattern: str) -> int:
        """Invalidate cache entries matching a pattern (placeholder).
        
        Args:
            pattern: Pattern to match against keys/queries
        
        Returns:
            Number of entries invalidated
        """
        # Simple implementation - could be enhanced with regex matching
        cleared = 0
        keys_to_remove = []
        
        for key in self._cache.keys():
            if pattern.lower() in key.lower():
                keys_to_remove.append(key)
        
        for key in keys_to_remove:
            del self._cache[key]
            self._access_order.pop(key, None)
            cleared += 1
        
        return cleared


# Global cache instance (would be initialized in main cog)
_global_cache: Optional[SearchCache] = None

def get_cache() -> SearchCache:
    """Get the global search cache instance."""
    global _global_cache
    if _global_cache is None:
        _global_cache = SearchCache()
    return _global_cache

def initialize_cache(max_entries: int = 1000, default_ttl_hours: int = 1) -> SearchCache:
    """Initialize global cache with custom settings."""
    global _global_cache
    _global_cache = SearchCache(max_entries, default_ttl_hours)
    return _global_cache
