"""
Auto Web Search Integration for SkynetV2

Automatically detects when chat messages need current information and triggers web search
to provide up-to-date context before AI processing.
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
import discord

from .api.base import ChatMessage


class AutoWebSearchIntegration:
    """
    Intelligent system that analyzes chat messages to determine when web search
    should be automatically triggered to provide current information.
    """
    
    def __init__(self, cog):
        self.cog = cog
        
        # Temporal trigger patterns (current events, dates, recent happenings)
        self.temporal_patterns = [
            # Current/recent time references
            r'\b(?:today|now|current|currently|recent|recently|latest|new|newest)\b',
            r'\b(?:this (?:week|month|year)|past (?:week|month|year))\b',
            r'\b(?:what(?:\'s| is) (?:happening|new|the latest))\b',
            
            # News and events
            r'\b(?:news|breaking|announcement|update|development)s?\b',
            r'\b(?:what happened|tell me about).+(?:today|recently|this week)\b',
            
            # Date-specific queries
            r'\b(?:on|from|since|after|before) (?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\w+ \d{1,2}(?:st|nd|rd|th)?)\b',
            r'\btoday(?:\'s| is) date\b',
            
            # Real-time data requests
            r'\b(?:current|live|real[- ]?time) (?:price|weather|score|status|data)\b',
            r'\b(?:stock price|weather|temperature|forecast)\b',
        ]
        
        # Content-specific triggers (things that likely need current info)
        self.content_triggers = [
            # Technology and products
            r'\b(?:latest version|new release|recent update)\b',
            r'\b(?:iPhone|Android|Windows|iOS|macOS|Linux).+(?:latest|new|current|version)\b',
            
            # Companies and business
            r'\b(?:stock|share price|market cap|earnings|revenue)\b',
            r'\b(?:merger|acquisition|IPO|bankruptcy)\b',
            
            # Entertainment
            r'\b(?:latest movie|new show|recent episode|box office)\b',
            r'\b(?:Oscar|Emmy|Grammy|award).+(?:winner|nominee)\b',
            
            # Sports
            r'\b(?:score|game|match|tournament|championship|playoffs)\b',
            r'\b(?:NBA|NFL|MLB|NHL|FIFA|Olympics)\b',
            
            # Politics and world events  
            r'\b(?:election|vote|poll|president|government|policy)\b',
            r'\b(?:war|conflict|crisis|disaster|emergency)\b',
        ]
        
        # Question patterns that often need current info
        self.question_patterns = [
            r'\bwhat(?:\'s| is) (?:the latest|happening|new|going on)\b',
            r'\bhow (?:is|are).+(?:doing|performing|currently)\b',
            r'\bwho (?:won|is winning|leads|is leading)\b',
            r'\bwhen (?:is|was|will be|did).+(?:happen|release|announce)\b',
            r'\bwhere (?:is|are).+(?:now|currently|today)\b',
        ]

    def should_trigger_search(self, message_content: str, config: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Analyze a message to determine if auto web search should be triggered.
        
        Args:
            message_content: The user's message content
            config: Auto web search configuration
            
        Returns:
            (should_search, reason) tuple
        """
        if not config.get('enabled', False):
            return False, "Auto web search is disabled"
            
        content_lower = message_content.lower()
        
        # Check sensitivity level (1=very sensitive, 5=very conservative)
        sensitivity = config.get('sensitivity', 3)
        
        triggers_found = []
        
        # Level 1-5: Check temporal patterns (always check these for current info needs)
        for pattern in self.temporal_patterns:
            if re.search(pattern, content_lower, re.IGNORECASE):
                triggers_found.append(f"temporal: {pattern}")
                
        # Level 1-4: Check content-specific triggers
        if sensitivity <= 4:
            for pattern in self.content_triggers:
                if re.search(pattern, content_lower, re.IGNORECASE):
                    triggers_found.append(f"content: {pattern}")
                    
        # Level 1-3: Check question patterns
        if sensitivity <= 3:
            for pattern in self.question_patterns:
                if re.search(pattern, content_lower, re.IGNORECASE):
                    triggers_found.append(f"question: {pattern}")
                    
        # Level 1-2: Check for custom keywords/phrases
        if sensitivity <= 2:
            custom_keywords = config.get('trigger_keywords', [])
            for keyword in custom_keywords:
                if keyword.lower() in content_lower:
                    triggers_found.append(f"custom: {keyword}")
                    
        # Level 1: Very aggressive - search for any query that might benefit
        if sensitivity == 1:
            # Look for informational queries
            info_patterns = [
                r'\b(?:what|who|when|where|why|how)\b',
                r'\b(?:explain|describe|tell me)\b',
                r'\b(?:compare|versus|vs|difference)\b',
            ]
            for pattern in info_patterns:
                if re.search(pattern, content_lower, re.IGNORECASE):
                    triggers_found.append(f"info: {pattern}")
                    break  # Only add one info trigger
        
        # Determine if we should search
        min_triggers = {1: 1, 2: 1, 3: 1, 4: 2, 5: 2}
        required_triggers = min_triggers.get(sensitivity, 1)
        
        should_search = len(triggers_found) >= required_triggers
        
        if should_search:
            reason = f"Found {len(triggers_found)} triggers (need {required_triggers}): {', '.join(triggers_found[:3])}"
        else:
            reason = f"Found {len(triggers_found)} triggers, need {required_triggers} for sensitivity level {sensitivity}"
            
        return should_search, reason

    async def perform_auto_search(self, message_content: str, guild: discord.Guild, config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Perform automatic web search and return results for context injection.
        
        Args:
            message_content: User's message that triggered search
            guild: Discord guild for configuration
            config: Auto web search configuration
            
        Returns:
            Search results dict or None if search failed
        """
        try:
            # Use existing autosearch classification to determine best search strategy
            mode, params, followups = self.cog._heuristic_classify_autosearch(message_content)
            
            # Limit search scope for auto-search (don't want too much data)
            max_results = config.get('max_results', 5)
            timeout_seconds = config.get('timeout_seconds', 15)
            
            # Modify params for auto-search constraints
            if mode == "search":
                params['limit'] = min(params.get('limit', 5), max_results)
            elif mode == "deep_research":
                # Convert deep research to simple search for auto mode
                mode = "search"
                params = {'query': params.get('query', message_content[:120]), 'limit': max_results}
            elif mode in ["crawl", "scrape_multi"]:
                # Too heavy for auto mode, convert to search
                mode = "search"
                params = {'query': message_content[:120], 'limit': max_results}
                
            # Set timeout (this would need to be implemented in the search providers)
            params['timeout'] = timeout_seconds
            
            # Execute the search using existing autosearch infrastructure
            search_result = await self.cog._tool_run_autosearch(
                guild=guild, 
                query=message_content, 
                execute=True  # Always execute for auto search
            )
            
            return {
                'mode': mode,
                'params': params,
                'result': search_result,
                'timestamp': time.time(),
                'query': message_content[:120]
            }
            
        except Exception as e:
            # Log error but don't break chat flow
            self.cog.error_handler.log_error(e, "auto_web_search", {
                "message": message_content[:100],
                "guild_id": guild.id
            })
            return None

    def format_search_context(self, search_data: Dict[str, Any], message_content: str) -> str:
        """
        Format search results into context that can be injected into AI prompt.
        
        Args:
            search_data: Results from perform_auto_search
            message_content: Original user message
            
        Returns:
            Formatted context string
        """
        if not search_data or not search_data.get('result'):
            return ""
            
        timestamp = datetime.fromtimestamp(search_data['timestamp'])
        
        context = f"""
## Current Web Information (Retrieved {timestamp.strftime('%Y-%m-%d %H:%M:%S')})

**User Query:** {message_content}
**Search Strategy:** {search_data.get('mode', 'search').title()}

**Relevant Current Information:**
{search_data['result']}

---
**Note:** Use this current information to supplement your knowledge. If the search results are relevant to the user's question, incorporate them into your response. If they're not relevant, focus on your training data instead.
"""
        return context.strip()

    def get_config_defaults(self) -> Dict[str, Any]:
        """Get default configuration for auto web search."""
        return {
            'enabled': False,  # Start disabled for safety
            'sensitivity': 3,  # Balanced sensitivity  
            'max_results': 5,  # Limit search results
            'timeout_seconds': 15,  # Max time for search
            'trigger_keywords': [],  # Custom trigger words
            'exclude_patterns': [],  # Patterns to avoid searching
            'min_message_length': 10,  # Don't search very short messages
            'cooldown_seconds': 60,  # Cooldown between auto searches per user
        }

    def get_sensitivity_description(self, level: int) -> str:
        """Get human-readable description of sensitivity levels."""
        descriptions = {
            1: "Very Aggressive - searches for most informational queries",
            2: "Aggressive - includes custom keywords and broad triggers", 
            3: "Balanced - current events, news, dates, and clear info needs (default)",
            4: "Conservative - only obvious current information requests",
            5: "Very Conservative - only explicit temporal/news queries"
        }
        return descriptions.get(level, "Unknown sensitivity level")


class AutoSearchCooldownManager:
    """Manages per-user cooldowns for auto web search to prevent spam."""
    
    def __init__(self):
        self._cooldowns: Dict[str, float] = {}  # user_id -> last_search_time
        
    def can_search(self, user_id: str, cooldown_seconds: int) -> bool:
        """Check if user can perform auto search (not in cooldown)."""
        now = time.time()
        last_search = self._cooldowns.get(user_id, 0)
        return (now - last_search) >= cooldown_seconds
        
    def record_search(self, user_id: str) -> None:
        """Record that user performed an auto search."""
        self._cooldowns[user_id] = time.time()
        
    def cleanup_old_entries(self, max_age_seconds: int = 3600) -> None:
        """Remove old cooldown entries to prevent memory buildup."""
        now = time.time()
        expired = [uid for uid, timestamp in self._cooldowns.items() 
                  if (now - timestamp) > max_age_seconds]
        for uid in expired:
            del self._cooldowns[uid]
