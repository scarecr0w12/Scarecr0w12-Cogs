from __future__ import annotations

from redbot.core import Config


IDENTIFIER = 2025080701


def register_config(cog) -> Config:
    conf = Config.get_conf(cog, identifier=IDENTIFIER, force_registration=True)

    default_global = {
        "providers": {
            "default": "openai",
            "openai": {"api_key": None},
            "serp": {"api_key": None},
            "firecrawl": {"api_key": None},
        },
        "model": {"provider": "openai", "name": "gpt-4o-mini"},
        "params": {"temperature": 0.7, "max_tokens": 512, "top_p": 1.0},
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
        # Prompt templates (global scope): name -> {content:str, variables:list[str], created:int, updated:int, scope:'global'}
        "prompts": {},
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
        },
        # Autosearch safety caps (chars for aggregated scrape outputs) + behavior flags
        "autosearch_caps": {"scrape_chars": 4000, "autoscrape_single": False},
        "listening": {"enabled": False, "mode": "mention", "keywords": []},
        "tools": {"enabled": {}},
        # Added pruning policy (max_items hard cap across messages list; max_age_days age trimming on write)
        "memory": {"default_limit": 10, "per_channel": {}, "prune": {"max_items": 400, "max_age_days": 30}},
        # Governance: tool allow/deny lists, cooldown bypass roles, simple per-user daily budget caps (0 disables)
        "governance": {"tools": {"allow": [], "deny": [], "per_user_minute_overrides": {}}, "bypass": {"cooldown_roles": []}, "budget": {"per_user_daily_tokens": 0, "per_user_daily_cost_usd": 0.0}},
        "policy": {"models": {"allow": {}, "deny": {}}},
        "search": None,
        # Stretch features: token truncation, cache, experimental features
        "stretch": {"truncation": {"enabled": True, "max_tool_output_chars": 8000}, "cache": {"enabled": False, "max_entries": 1000, "ttl_hours": 1}, "experimental": {"chain_planning": False, "localization": False}},
        # Web interface authentication tokens
        "web_tokens": {},
        # Prompt templates (guild scope): name -> {content:str, variables:list[str], created:int, updated:int, scope:'guild'}
        "prompts": {},
    }

    conf.register_global(**default_global)
    conf.register_guild(**default_guild)
    return conf
