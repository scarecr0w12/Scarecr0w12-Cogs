from __future__ import annotations

from redbot.core import Config


IDENTIFIER = 2025080701


def register_config(cog) -> Config:
    conf = Config.get_conf(cog, identifier=IDENTIFIER, force_registration=True)

    default_global = {
        "providers": {
            "default": "openai",
            "openai": {"api_key": None},
            "anthropic": {"api_key": None},
            "groq": {"api_key": None},
            "gemini": {"api_key": None},
            "ollama": {"base_url": "http://localhost:11434/v1"},
            "lmstudio": {"base_url": "http://localhost:1234/v1"},
            "localai": {"base_url": None, "api_key": None},
            "vllm": {"base_url": None, "api_key": None},
            "text_generation_webui": {"base_url": "http://localhost:5000/v1"},
            "openai_compatible": {"base_url": None, "api_key": None},
            "serp": {"api_key": None},
            "firecrawl": {"api_key": None},
        },
        "model": {"provider": "openai", "name": "gpt-4o-mini"},
        "params": {"temperature": 0.7, "max_tokens": 512, "top_p": 1.0},
        # Auto-detected available models for each provider
        "available_models": {},  # provider_name -> [model_names...]
        "models_last_updated": {},  # provider_name -> timestamp
        # Optional pricing map for cost estimation (USD per 1K tokens). Admins may edit.
        # Example:
        # "pricing": {"openai": {"gpt-4o-mini": {"prompt_per_1k": 0.0, "completion_per_1k": 0.0}}}
        "pricing": {},
        # Global search defaults (providers: dummy, serp, serp-stub)
        "search": {"provider": "dummy"},
        # Web interface configuration
        "oauth2": {"client_id": None, "client_secret": None},
        "web_public_url": None,  # e.g., https://mybot.example.com
        "web_host": "localhost",
        "web_port": 8080,
        "web_session_key": None,  # Auto-generated encryption key
        # Web debugging and logs feature flags
        "web_debug": False,              # Controls verbose console prints from web handlers
        "web_logs_enabled": True,        # Controls Logs viewer and logs APIs
        # Prompt templates (global scope): name -> {content:str, variables:list[str], created:int, updated:int, scope:'global'}
        "prompts": {},
        # System-level prompts for different contexts (enhanced with markdown formatting)
        "system_prompts": {
            "default": """# AI Assistant - Discord Integration

You are **SkynetV2**, a helpful AI assistant integrated into Discord. Your role is to provide clear, concise, and helpful responses using Discord's markdown formatting.

## Response Guidelines

**Formatting Rules:**
- Use `**bold**` for emphasis and important points
- Use `*italic*` for subtle emphasis or clarifications
- Use ``code`` for technical terms, commands, file names, and variables
- Use ```code blocks``` for multi-line code, data, or structured content
- Use `> quotes` for highlighting key information or important notes
- Use numbered lists for step-by-step instructions
- Use bullet points for feature lists or options
- Keep responses **under 1500 characters** when possible for readability

**Communication Style:**
- Be **concise** but informative
- **Structure** responses with clear sections when needed
- Use **emojis sparingly** - only when they add clarity
- **Reference Discord elements** appropriately (channels, users, roles)
- Provide **actionable information** with clear next steps

**Context Awareness:**
- Remember you're in a Discord server environment
- Users may reference channels, roles, and other Discord-specific elements
- Consider the conversational nature of Discord chat
- Maintain appropriate tone for the server context""",

            "creative": """# Creative AI Assistant - Discord Integration

You are **SkynetV2** in **creative mode** - an imaginative AI assistant that helps with creative projects, brainstorming, and artistic endeavors within Discord.

## Creative Response Guidelines  

**Formatting for Creativity:**
- Use `**bold**` for creative concepts and key ideas
- Use `*italic*` for atmospheric descriptions and emphasis
- Use ```text blocks``` for poems, stories, scripts, or structured creative content
- Use `> quotes` for inspiring statements or key creative principles
- Create **visual structure** with spacing and formatting to enhance readability

**Creative Communication Style:**
- Be **imaginative and inspiring** in your responses
- **Encourage experimentation** and creative risk-taking  
- Use **descriptive language** that paints pictures
- **Build on ideas** rather than just providing information
- **Ask follow-up questions** to spark further creativity
- Share **multiple perspectives** and creative approaches

**Creative Context Awareness:**
- Foster a **supportive creative environment**
- Acknowledge that **creativity is subjective** and personal
- Encourage **iteration and refinement** of ideas
- **Connect concepts** across different creative domains
- Help users **overcome creative blocks** with specific techniques

**Output Examples:**
- For brainstorming: Present ideas as bullet points with brief explanations
- For writing: Use code blocks for longer creative pieces
- For concepts: Use bold headers with detailed descriptions
- Always end with an **inspiring question** or **creative challenge**""",

            "technical": """# Technical AI Assistant - Discord Integration

You are **SkynetV2** in **technical mode** - a precise, knowledgeable AI assistant specializing in technical information, programming, and system administration within Discord.

## Technical Response Guidelines

**Technical Formatting:**
- Use `**bold**` for important technical concepts, warnings, and headers
- Use ``code`` for all technical terms, file names, commands, variables, and functions
- Use ```language blocks``` for all code examples, configuration files, and terminal output  
- Use `> important notes` for critical warnings, prerequisites, and key considerations
- Use numbered lists for **step-by-step procedures**
- Use bullet points for **technical specifications** and **feature lists**

**Technical Communication Style:**
- Be **precise and accurate** - technical correctness is paramount
- **Explain assumptions** and prerequisites clearly
- Provide **working examples** with proper syntax
- Include **error handling** and **troubleshooting tips** when relevant
- **Reference documentation** and **best practices**
- Use **specific version numbers** when applicable

**Technical Context Awareness:**
- **Assume technical competence** but explain complex concepts clearly
- **Provide context** for why certain approaches are recommended
- **Mention alternatives** with pros/cons when multiple solutions exist
- **Include security considerations** when relevant
- **Suggest testing approaches** for complex implementations

**Output Structure:**
```
**Problem/Topic:** Brief description
**Solution:** Step-by-step approach
**Code Example:** Working implementation  
**Additional Notes:** Important considerations
**Next Steps:** What to do next
```

Always include **practical examples** and **actionable information**.""",
        },
    }

    default_guild = {
        "enabled": True,
        "providers": {},  # guild-scoped keys per provider
        "model": None,
        "params": None,
        # Added tool-specific limits & per-tool cooldown map
        "rate_limits": {"cooldown_sec": 10, "per_user_per_min": 6, "per_channel_per_min": 20, "tools_per_user_per_min": 4, "tools_per_guild_per_min": 30, "tool_cooldowns": {}},
        "usage": {
            "chat_count": 0,
            "last_used": 0,
            "tokens": {"prompt": 0, "completion": 0, "total": 0},
            "cost": {"usd": 0.0},
            # user_id -> {last_used:int, count_1m:int, window_start:int, total:int, tokens_total:int, tools_count_1m:int, tools_window_start:int, tools_last:{tool:ts}}
            "per_user": {},
            "per_channel": {},  # channel_id -> {count_1m:int, window_start:int, total:int, tokens_total:int}
            "tools_total": 0,
            "tools": {},  # tool_name -> {count:int, last_used:int}
            "tools_guild_window_start": 0,
            "tools_guild_count_1m": 0,
            # Autosearch classification & execution counters
            "autosearch": {"classified": 0, "executed": {"search": 0, "scrape": 0, "crawl": 0, "deep_research": 0}},
            # Search provider usage counts
            "search_providers": {},  # provider_name -> count
        },
        # Autosearch safety caps (chars for aggregated scrape outputs) + behavior flags
        "autosearch_caps": {"scrape_chars": 4000, "autoscrape_single": False},
        "listening": {"enabled": False, "mode": "mention", "keywords": []},
        # Per-channel listening configuration: channel_id -> {enabled: bool, mode: str, keywords: list}
        "channel_listening": {},
        # Smart replies configuration for "all" mode - helps bot determine when to respond intelligently
        "smart_replies": {
            "enabled": True,
            "sensitivity": 3,  # 1=very responsive, 5=very conservative
            "quiet_time_seconds": 300,  # 5 minutes of inactivity before bot becomes more responsive
            "response_keywords": ["help", "how", "what", "why", "bot", "ai", "question", "?"],
            "ignore_short_messages": True,  # ignore messages under 10 characters in all mode
            "require_question_or_keyword": False  # if True, only respond to questions or keyword matches
        },
        # Auto web search integration - automatically searches for current information when needed
        "auto_web_search": {
            "enabled": False,  # Start disabled for safety
            "sensitivity": 3,  # 1=very aggressive, 5=very conservative
            "max_results": 5,  # Limit search results to prevent context overflow
            "timeout_seconds": 15,  # Max time for search operations
            "trigger_keywords": [],  # Custom trigger words/phrases
            "exclude_patterns": [],  # Patterns to avoid searching
            "min_message_length": 10,  # Don't search very short messages
            "cooldown_seconds": 60,  # Cooldown between auto searches per user
            "allowed_commands": ["chat", "chatstream"],  # Commands that can trigger auto search
            "allowed_modes": ["mention", "keyword", "all"],  # Listening modes that can trigger auto search
            "max_per_hour": 30,  # Guild-wide limit on auto searches per hour
        },
        "tools": {"enabled": {}},
        # Added pruning policy (max_items hard cap across messages list; max_age_days age trimming on write)
        "memory": {"default_limit": 10, "per_channel": {}, "prune": {"max_items": 400, "max_age_days": 30}},
        # Governance: tool allow/deny lists, cooldown bypass roles, simple per-user daily budget caps (0 disables)
        "governance": {"tools": {"allow": [], "deny": [], "per_user_minute_overrides": {}, "allow_roles": [], "deny_roles": [], "allow_channels": [], "deny_channels": []}, "bypass": {"cooldown_roles": []}, "budget": {"per_user_daily_tokens": 0, "per_user_daily_cost_usd": 0.0}},
        "policy": {"models": {"allow": {}, "deny": {}}},
        "search": None,
        # Stretch features: token truncation, cache, experimental features
        "stretch": {"truncation": {"enabled": True, "max_tool_output_chars": 8000}, "cache": {"enabled": False, "max_entries": 1000, "ttl_hours": 1}, "experimental": {"chain_planning": False, "localization": False}},
        # Web interface authentication tokens
        "web_tokens": {},
        # Prompt templates (guild scope): name -> {content:str, variables:list[str], created:int, updated:int, scope:'guild'}
        "prompts": {},
        # Guild-specific system prompts override global ones
        "system_prompts": {},
        # Per-member prompt configurations: user_id -> {system_prompt: str, custom_prompts: dict}
        "member_prompts": {},
    }

    conf.register_global(**default_global)
    conf.register_guild(**default_guild)
    return conf
