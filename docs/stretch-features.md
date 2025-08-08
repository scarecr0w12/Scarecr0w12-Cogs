# Stretch Features Implementation Plan

This document outlines the implementation approach for stretch features in SkynetV2.
These features enhance the user experience but are not critical for core functionality.

## 1. Token-Aware Truncation

### Current Approach
- Discord messages have a 2000 character limit
- Long AI responses are automatically chunked and sent as multiple messages
- Tool outputs are returned as-is, which could be very large

### Enhancement Implementation
```python
# In skynetv2/tools.py - Add truncation utility

MAX_TOOL_OUTPUT_CHARS = 8000  # Configurable limit for tool outputs
MAX_MESSAGE_CHARS = 1900      # Safe Discord message limit with formatting

def truncate_tool_output(content: str, max_chars: int = MAX_TOOL_OUTPUT_CHARS) -> str:
    """Truncate tool output with intelligent summarization."""
    if len(content) <= max_chars:
        return content
    
    # Try to truncate at paragraph boundaries first
    paragraphs = content.split('\n\n')
    truncated = ""
    for para in paragraphs:
        if len(truncated + para) <= max_chars - 100:  # Reserve space for truncation notice
            truncated += para + '\n\n'
        else:
            break
    
    if truncated:
        return truncated.rstrip() + f"\n\n[Output truncated - {len(content) - len(truncated)} characters omitted]"
    else:
        # Fallback: hard truncation with ellipsis
        return content[:max_chars - 50] + "... [Output truncated]"
```

### Configuration Integration
```python
# Add to config.py
@dataclass
class TruncationConfig:
    """Settings for output truncation."""
    tool_output_max_chars: int = 8000
    message_max_chars: int = 1900
    enable_smart_truncation: bool = True
```

## 2. Local Search Result Cache

### Design Principles
- Time-based TTL (e.g., 1 hour for search results)
- LRU eviction when memory limits reached
- Per-guild caching to avoid cross-contamination
- Configurable cache size and TTL

### Implementation Approach
```python
# In skynetv2/search_cache.py (new file)
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Optional, Any
import hashlib

@dataclass
class CacheEntry:
    """Single cache entry with metadata."""
    data: Any
    created_at: datetime
    ttl_hours: int = 1
    
    @property 
    def is_expired(self) -> bool:
        return datetime.now() > self.created_at + timedelta(hours=self.ttl_hours)

class SearchCache:
    """Local cache for search results and tool outputs."""
    
    def __init__(self, max_entries: int = 1000, default_ttl_hours: int = 1):
        self._cache: Dict[str, CacheEntry] = {}
        self.max_entries = max_entries
        self.default_ttl = default_ttl_hours
    
    def _make_key(self, query: str, provider: str, guild_id: int) -> str:
        """Generate cache key from query parameters."""
        key_data = f"{guild_id}:{provider}:{query}"
        return hashlib.sha256(key_data.encode()).hexdigest()[:16]
    
    def get(self, query: str, provider: str, guild_id: int) -> Optional[Any]:
        """Retrieve cached result if available and not expired."""
        key = self._make_key(query, provider, guild_id)
        entry = self._cache.get(key)
        
        if not entry or entry.is_expired:
            if entry:  # Clean up expired entry
                del self._cache[key]
            return None
            
        return entry.data
    
    def set(self, query: str, provider: str, guild_id: int, data: Any, ttl_hours: Optional[int] = None) -> None:
        """Store result in cache with TTL."""
        key = self._make_key(query, provider, guild_id)
        
        # Evict oldest entries if at capacity
        if len(self._cache) >= self.max_entries:
            oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k].created_at)
            del self._cache[oldest_key]
        
        self._cache[key] = CacheEntry(
            data=data,
            created_at=datetime.now(),
            ttl_hours=ttl_hours or self.default_ttl
        )
    
    def clear_expired(self) -> int:
        """Remove expired entries and return count cleared."""
        expired_keys = [k for k, v in self._cache.items() if v.is_expired]
        for key in expired_keys:
            del self._cache[key]
        return len(expired_keys)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        now = datetime.now()
        total = len(self._cache)
        expired = sum(1 for entry in self._cache.values() if entry.is_expired)
        
        return {
            "total_entries": total,
            "expired_entries": expired,
            "active_entries": total - expired,
            "cache_hit_potential": f"{((total - expired) / max(total, 1)) * 100:.1f}%"
        }
```

## 3. Chain Planning (Multi-Message Tool Plans)

### Concept
- Allow AI to plan multi-step tool executions
- Each step can use results from previous steps
- Experimental feature behind configuration flag

### Implementation Stub
```python
# In skynetv2/chain_planning.py (new file)
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from enum import Enum

class PlanStepStatus(Enum):
    PENDING = "pending"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"

@dataclass
class PlanStep:
    """Single step in a multi-step execution plan."""
    step_id: str
    tool_name: str
    parameters: Dict[str, Any]
    depends_on: List[str] = None  # Other step IDs this depends on
    status: PlanStepStatus = PlanStepStatus.PENDING
    result: Optional[Any] = None
    error: Optional[str] = None

@dataclass 
class ExecutionPlan:
    """Multi-step tool execution plan."""
    plan_id: str
    steps: List[PlanStep]
    created_by: int  # User ID
    guild_id: int
    channel_id: int
    status: str = "pending"
    
class ChainPlanner:
    """Experimental chain planning for multi-tool workflows."""
    
    def __init__(self, config):
        self.config = config
        self.active_plans: Dict[str, ExecutionPlan] = {}
    
    async def create_plan(self, user_id: int, guild_id: int, channel_id: int, 
                         steps: List[Dict[str, Any]]) -> str:
        """Create a new execution plan."""
        # Implementation would parse step definitions
        # Validate tool availability and parameters
        # Return plan ID for tracking
        raise NotImplementedError("Chain planning is experimental - not yet implemented")
    
    async def execute_plan(self, plan_id: str) -> List[Any]:
        """Execute plan steps in dependency order."""
        # Implementation would:
        # 1. Resolve step dependencies
        # 2. Execute steps in order
        # 3. Pass results between steps
        # 4. Handle failures gracefully
        raise NotImplementedError("Chain planning is experimental - not yet implemented")
```

## 4. Localization Framework

### Approach
- String externalization for user-facing messages
- Language detection from Discord locale
- Fallback to English for missing translations

### Implementation Stub
```python
# In skynetv2/localization.py (new file)
from typing import Dict, Optional
import json
from pathlib import Path

class LocalizationManager:
    """Manages localized strings for user-facing messages."""
    
    def __init__(self, locale_dir: str = "locales"):
        self.locale_dir = Path(locale_dir)
        self.translations: Dict[str, Dict[str, str]] = {}
        self.default_locale = "en"
        self._load_translations()
    
    def _load_translations(self):
        """Load translation files from locale directory."""
        # Stub - would load JSON files like en.json, es.json, etc.
        self.translations["en"] = {
            "error.provider_unavailable": "AI service temporarily unavailable. Please try again.",
            "error.rate_limited": "You're sending requests too quickly. Please wait {seconds} seconds.",
            "error.invalid_model": "Invalid model '{model}'. Use `/ai models` to see available options.",
            "tool.search.no_results": "No search results found for '{query}'.",
            "governance.denied_tool": "Tool '{tool}' is not allowed in this server.",
            "stats.title": "🤖 SkynetV2 Statistics",
            "memory.export_complete": "Memory export complete. Check your DMs.",
        }
    
    def get_string(self, key: str, locale: Optional[str] = None, **kwargs) -> str:
        """Get localized string with parameter substitution."""
        locale = locale or self.default_locale
        
        # Get translation from requested locale, fallback to English
        translations = self.translations.get(locale, self.translations[self.default_locale])
        template = translations.get(key, key)  # Fallback to key if translation missing
        
        # Simple parameter substitution
        try:
            return template.format(**kwargs)
        except KeyError:
            return template  # Return as-is if formatting fails
    
    def get_user_locale(self, user_id: int) -> str:
        """Determine user's preferred locale (stub)."""
        # Would integrate with Discord API to get user locale
        # For now, return default
        return self.default_locale

# Global instance (would be initialized in main cog)
_localization = LocalizationManager()

def get_localized_string(key: str, locale: Optional[str] = None, **kwargs) -> str:
    """Convenience function for getting localized strings."""
    return _localization.get_string(key, locale, **kwargs)
```

## Implementation Priority

1. **Token-Aware Truncation** - Most immediately useful, prevents message failures
2. **Search Result Cache** - Performance improvement, reduces API calls
3. **Localization Framework** - Foundation for future international support  
4. **Chain Planning** - Advanced feature, experimental implementation

## Configuration Integration

```python
# Add to config.py StretchConfig section
@dataclass
class StretchConfig:
    """Optional/experimental feature configuration."""
    
    # Truncation settings
    enable_smart_truncation: bool = True
    max_tool_output_chars: int = 8000
    
    # Cache settings  
    enable_search_cache: bool = True
    cache_max_entries: int = 1000
    cache_ttl_hours: int = 1
    
    # Experimental features
    enable_chain_planning: bool = False
    enable_localization: bool = False
    default_locale: str = "en"
```

## Testing Approach

- Unit tests for truncation logic with various content types
- Cache tests for TTL expiration, LRU eviction, key generation
- Integration tests for configuration loading
- Manual testing for user experience improvements

## Documentation Updates

- Add stretch features section to configuration.md
- Update commands.md with any new admin commands
- Add troubleshooting section for cache/truncation issues
- Update README with optional feature descriptions
