from __future__ import annotations

from typing import Dict, Any, List, Tuple
import discord
import time
import re
from .search import build_search_provider
from .autoexec import build_autoexec_adapter

# Truncation constants for better Discord UX
MAX_TOOL_OUTPUT_CHARS = 8000  # Configurable limit for tool outputs
MAX_MESSAGE_CHARS = 1900      # Safe Discord message limit with formatting

def truncate_tool_output(content: str, max_chars: int = MAX_TOOL_OUTPUT_CHARS) -> str:
    """Truncate tool output with intelligent summarization for Discord compatibility.
    
    Args:
        content: The content to potentially truncate
        max_chars: Maximum characters allowed (default: 8000)
    
    Returns:
        Original content if under limit, otherwise intelligently truncated content
    """
    if not content or len(content) <= max_chars:
        return content
    
    # Try to truncate at paragraph boundaries first for better readability
    paragraphs = content.split('\n\n')
    truncated = ""
    for para in paragraphs:
        potential_length = len(truncated + para + '\n\n')
        if potential_length <= max_chars - 100:  # Reserve space for truncation notice
            truncated += para + '\n\n'
        else:
            break
    
    if truncated.strip():
        original_length = len(content)
        truncated_length = len(truncated.rstrip())
        omitted = original_length - truncated_length
        return truncated.rstrip() + f"\n\n[Output truncated - {omitted:,} characters omitted for readability]"
    else:
        # Fallback: hard truncation with ellipsis
        safe_limit = max_chars - 60  # Reserve space for truncation notice
        return content[:safe_limit] + "...\n\n[Output truncated - content too large for Discord]"

class ToolsMixin:
    """Tools registry and helper methods.

    Holds the in-memory registry; persistence of enable flags via Config.
    """

    def _init_tool_registry(self):
        # Called by main cog __init__
        self._tool_registry: Dict[str, Dict[str, Any]] = {
            "ping": {"desc": "Health check tool returning 'pong'", "run": self._tool_run_ping},
            "websearch": {"desc": "Dummy web search (placeholder results)", "run": self._tool_run_websearch},
            # New heuristic auto search router (stub planning output + optional search execution)
            "autosearch": {"desc": "Heuristic routing: classify query -> plan (optional: execute search mode)", "run": self._tool_run_autosearch},
            # Website fetch/crawl/research via Firecrawl adapter
            "webfetch": {"desc": "Fetch website content: scrape/crawl/deep_research (uses Firecrawl if configured)", "run": self._tool_run_webfetch},
        }

    async def _check_tool_rate_limits(self, guild: discord.Guild, user: discord.User, tool: str | None = None) -> str | None:
        now = int(time.time())
        rl = await self.config.guild(guild).rate_limits()
        per_user = int(rl.get("tools_per_user_per_min", 4))
        # Override per-tool per-user minute if configured
        gov = await self.config.guild(guild).governance()
        per_user_overrides = (gov or {}).get("tools", {}).get("per_user_minute_overrides", {}) if gov else {}
        if tool and per_user_overrides and tool in per_user_overrides:
            try:
                per_user = int(per_user_overrides[tool])
            except Exception:
                pass
        per_guild = int(rl.get("tools_per_guild_per_min", 30))
        tool_cooldowns: Dict[str, int] = rl.get("tool_cooldowns", {}) or {}
        is_owner = await self.bot.is_owner(user)
        # Governance bypass roles
        gov = await self.config.guild(guild).governance()
        bypass_roles = set((gov or {}).get("bypass", {}).get("cooldown_roles", []) if gov else [])
        member = guild.get_member(user.id) if guild else None
        has_bypass = False
        if member and bypass_roles:
            for r in getattr(member, 'roles', []) or []:
                if getattr(r, 'id', None) in bypass_roles:
                    has_bypass = True
                    break
        if is_owner or has_bypass:
            return None
        # Governance allow/deny tool filter
        if tool and gov:
            allow = gov.get("tools", {}).get("allow") or []
            deny = gov.get("tools", {}).get("deny") or []
            allow_roles = set((gov.get("tools", {}).get("allow_roles") or []))
            deny_roles = set((gov.get("tools", {}).get("deny_roles") or []))
            allow_channels = set((gov.get("tools", {}).get("allow_channels") or []))
            deny_channels = set((gov.get("tools", {}).get("deny_channels") or []))
            # Channel gate
            if hasattr(self, "_current_channel_id") and getattr(self, "_current_channel_id") is not None:
                ch_id = int(getattr(self, "_current_channel_id"))
                if deny_channels and ch_id in deny_channels:
                    return f"Tool '{tool}' is denied in this channel by governance policy."
                if allow_channels and ch_id not in allow_channels:
                    return f"Tool '{tool}' is not allowed in this channel by governance policy."
            # Role gate
            if member:
                member_role_ids = {getattr(r, 'id', None) for r in getattr(member, 'roles', [])}
                if deny_roles and (member_role_ids & deny_roles):
                    return f"Tool '{tool}' is denied for your role by governance policy."
                if allow_roles and not (member_role_ids & allow_roles):
                    return f"Tool '{tool}' is not allowed for your role by governance policy."
            # Global allow/deny
            if deny and tool in deny:
                return f"Tool '{tool}' is denied by governance policy."
            if allow and tool not in allow:
                return f"Tool '{tool}' is not in the allowed tool list."
        # Budget check (tokens) simplistic: compare per_user tokens_total delta in last 24h
        budget = (gov or {}).get("budget", {}) if gov else {}
        per_user_daily_tokens = int(budget.get("per_user_daily_tokens", 0) or 0)
        per_user_daily_cost = float(budget.get("per_user_daily_cost_usd", 0.0) or 0.0)
        # Only enforce if set (>0); cost requires usage.cost and timestamps per user (not tracked yet per day) => skip cost until token daily tracked
        async with self.config.guild(guild).usage() as usage:
            pu = usage.setdefault("per_user", {})
            u = pu.setdefault(str(user.id), {"last_used": 0, "count_1m": 0, "window_start": now, "total": 0, "tokens_total": 0, "tools_count_1m": 0, "tools_window_start": now, "tools_last": {}, "tokens_day_start": now, "tokens_day_total": 0})
            # Reset daily window
            if now - int(u.get("tokens_day_start", now)) >= 86400:
                u["tokens_day_start"], u["tokens_day_total"] = now, 0
            if per_user_daily_tokens and int(u.get("tokens_day_total", 0)) >= per_user_daily_tokens:
                return "Daily token budget reached. Try again tomorrow."
            if now - int(u.get("tools_window_start", now)) >= 60:
                u["tools_window_start"], u["tools_count_1m"] = now, 0
            if now - int(usage.get("tools_guild_window_start", 0)) >= 60:
                usage["tools_guild_window_start"], usage["tools_guild_count_1m"] = now, 0
            if tool:
                tl = u.setdefault("tools_last", {})
                cd = int(tool_cooldowns.get(tool, 0))
                if cd > 0:
                    last_ts = int(tl.get(tool, 0))
                    if now - last_ts < cd:
                        return f"Cooldown for tool '{tool}' active. Try again in {cd - (now - last_ts)}s."
            if int(u.get("tools_count_1m", 0)) >= per_user:
                return "Per-user tool rate limit reached. Try again later."
            if int(usage.get("tools_guild_count_1m", 0)) >= per_guild:
                return "Guild tool rate limit reached. Try again later."
            # Increment counters (persist)
            u["tools_count_1m"] = int(u.get("tools_count_1m", 0)) + 1
            usage["tools_guild_count_1m"] = int(usage.get("tools_guild_count_1m", 0)) + 1
            if tool:
                u.setdefault("tools_last", {})[tool] = now
        return None

    async def _resolve_firecrawl_api_key(self, guild: discord.Guild) -> str | None:
        """Resolve Firecrawl API key with guild > global precedence."""
        # Check guild providers first
        gproviders = await self.config.guild(guild).providers()
        if "firecrawl" in gproviders and gproviders["firecrawl"].get("api_key"):
            return gproviders["firecrawl"]["api_key"]
        else:
            # Fall back to global
            global_providers = await self.config.providers()
            return global_providers.get("firecrawl", {}).get("api_key")

    async def _resolve_search_provider_and_key(self, guild: discord.Guild) -> tuple[str, str | None]:
        """Resolve search provider and API key with guild > global precedence."""
        # Resolve provider kind
        g_search = await self.config.guild(guild).search()
        if g_search and isinstance(g_search, dict):
            kind = g_search.get("provider") or "dummy"
        else:
            global_search = await self.config.search()
            kind = (global_search or {}).get("provider", "dummy") if isinstance(global_search, dict) else "dummy"
        
        # Resolve API key (for providers that need one)
        api_key = None
        if kind == "serp":
            # Check guild providers first
            gproviders = await self.config.guild(guild).providers()
            if "serp" in gproviders and gproviders["serp"].get("api_key"):
                api_key = gproviders["serp"]["api_key"]
            else:
                # Fall back to global
                global_providers = await self.config.providers()
                api_key = global_providers.get("serp", {}).get("api_key")
        
        return kind, api_key

    async def _execute_tool_with_telemetry(self, guild: discord.Guild, tool_name: str, tool_func, *args, **kwargs):
        """Wrapper for tool execution with latency tracking and error handling."""
        start_time = time.perf_counter()
        success = True
        result = None
        try:
            result = await tool_func(*args, **kwargs)
            # Apply intelligent truncation based on configuration
            if isinstance(result, str):
                stretch_cfg = await self.config.guild(guild).stretch()
                truncation_cfg = stretch_cfg.get("truncation", {})
                if truncation_cfg.get("enabled", True):
                    max_chars = truncation_cfg.get("max_tool_output_chars", MAX_TOOL_OUTPUT_CHARS)
                    if len(result) > max_chars:
                        result = truncate_tool_output(result, max_chars)
        except Exception as e:
            success = False
            result = f"Tool error: {type(e).__name__}: {str(e)[:100]}"
        finally:
            end_time = time.perf_counter()
            latency_ms = int((end_time - start_time) * 1000)
            await self._record_tool_usage(guild, tool_name, latency_ms=latency_ms, success=success)
        return result

    async def _record_tool_usage(self, guild: discord.Guild, name: str, latency_ms: int = 0, success: bool = True):
        now = int(time.time())
        async with self.config.guild(guild).usage() as usage:
            usage["tools_total"] = int(usage.get("tools_total", 0)) + 1
            tools_map = usage.setdefault("tools", {})
            t = tools_map.setdefault(name, {
                "count": 0, 
                "last_used": 0,
                "success_count": 0,
                "error_count": 0,
                "latency_ms": {"total": 0, "count": 0, "last": 0}
            })
            t["count"] = int(t.get("count", 0)) + 1
            t["last_used"] = now
            
            # Update success/error counters
            if success:
                t["success_count"] = int(t.get("success_count", 0)) + 1
            else:
                t["error_count"] = int(t.get("error_count", 0)) + 1
            
            # Update latency tracking
            lat = t.setdefault("latency_ms", {"total": 0, "count": 0, "last": 0})
            if latency_ms > 0:
                lat["total"] = int(lat.get("total", 0)) + latency_ms
                lat["count"] = int(lat.get("count", 0)) + 1
                lat["last"] = latency_ms

    # Tool implementations (placeholders)
    async def _tool_run_ping(self, guild: discord.Guild, *_args, user: discord.User | None = None, **_kwargs) -> str:
        if user:
            err = await self._check_tool_rate_limits(guild, user, tool="ping")
            if err:
                return err
        
        async def _ping_impl():
            return "pong"
        
        return await self._execute_tool_with_telemetry(guild, "ping", _ping_impl)

    async def _tool_run_websearch(self, guild: discord.Guild, query: str, topk: int = 5, user: discord.User | None = None, *_args, **_kwargs) -> str:
        if user:
            err = await self._check_tool_rate_limits(guild, user, tool="websearch")
            if err:
                return err
        async def _websearch_impl():
            kind, api_key = await self._resolve_search_provider_and_key(guild)
            provider = build_search_provider(kind=kind, api_key=api_key)
            results = await provider.search(query=query, topk=topk)
            # Increment provider usage telemetry
            async with self.config.guild(guild).usage() as usage:
                sp = usage.setdefault("search_providers", {})
                sp[kind] = int(sp.get(kind, 0)) + 1
            if not results:
                return "(empty query)" if not (query or '').strip() else "(no results)"
            lines = [f"provider: {getattr(provider, 'name', 'unknown')} | query: {query[:60]}"]
            for idx, r in enumerate(results, start=1):
                lines.append(f"{idx}. {r[:160]}")
            return "\n".join(lines)[:1000]
        return await self._execute_tool_with_telemetry(guild, "websearch", _websearch_impl)

    # New: Website fetch tool using Firecrawl adapter
    async def _tool_run_webfetch(self, guild: discord.Guild, mode: str, target: str, depth: int | None = None, limit: int | None = None, user: discord.User | None = None) -> str:
        if user:
            err = await self._check_tool_rate_limits(guild, user, tool="webfetch")
            if err:
                return err
        mode = (mode or "").strip().lower()
        target = (target or "").strip()
        if mode not in {"scrape", "crawl", "deep_research"}:
            return "Unsupported mode. Use one of: scrape, crawl, deep_research"
        if not target:
            return "Target is required (URL for scrape/crawl, or query for deep_research)."

        async def _impl():
            firecrawl_key = await self._resolve_firecrawl_api_key(guild)
            adapter = build_autoexec_adapter(api_key=firecrawl_key)
            # Character cap for safety
            caps = await self.config.guild(guild).autosearch_caps()
            char_cap = int((caps or {}).get("scrape_chars", 4000))
            if mode == "scrape":
                result = await adapter.scrape(target)
                if len(result) > char_cap:
                    result = result[:char_cap] + "..."
                return f"mode: scrape\nurl: {target}\n---\n{result}"
            if mode == "crawl":
                md = max(1, min(3, int(depth or 2)))
                lim = max(5, min(50, int(limit or 20)))
                discovered = await adapter.crawl(target, max_depth=md, limit=lim)
                lines = [f"mode: crawl", f"url: {target}", f"depth: {md}", f"limit: {lim}", "discovered:"]
                for d in (discovered or [])[:10]:
                    lines.append(f"- {d}")
                return "\n".join(lines)
            # deep_research
            dr = await adapter.deep_research(target)
            steps = dr.get("steps", [])
            summary = dr.get("summary") or ""
            if len(summary) > char_cap:
                summary = summary[:char_cap] + "..."
            lines = ["mode: deep_research", f"query: {target}", "steps:"]
            for s in steps[:6]:
                lines.append(f"- {s}")
            if summary:
                lines.append("summary:")
                lines.append(summary)
            return "\n".join(lines)
        return await self._execute_tool_with_telemetry(guild, "webfetch", _impl)

    # New heuristic auto search routing tool (with optional execution of search mode)
    async def _tool_run_autosearch(self, guild: discord.Guild, query: str, user: discord.User | None = None, execute: bool = False, *_args, **_kwargs) -> str:
        """Classify a query and optionally execute the best strategy.
        Modes: search, scrape, crawl, deep_research, scrape_multi (collapsed to scrape batch).
        """
        text = (query or '').strip()
        if not text:
            return "(empty query)"
        mode, params, followups = self._heuristic_classify_autosearch(text)
        plan_lines = [f"mode: {mode}", f"params: {params}"]
        if followups:
            plan_lines.append(f"followups: {', '.join(followups)}")
        plan = "\n".join(plan_lines)
        if not execute:
            # Record classification only
            await self._increment_autosearch_exec(guild, mode="classified")
            return plan
        # Execute path
        result = ""
        try:
            if mode == "search":
                limit = int(params.get("limit", 5))
                q = params.get("query", text)
                result = await self._tool_run_websearch(guild, q, topk=limit, user=user)
                await self._increment_autosearch_exec(guild, mode="search")
            elif mode == "scrape":
                url = params.get("url") or text
                result = await self._tool_run_webfetch(guild, "scrape", url, user=user)
                await self._increment_autosearch_exec(guild, mode="scrape")
            elif mode == "scrape_multi":
                urls_csv = params.get("urls", "")
                urls = [u.strip() for u in urls_csv.split(',') if u.strip()]
                combined: List[str] = []
                for u in urls[:3]:  # limit to 3 for safety
                    out = await self._tool_run_webfetch(guild, "scrape", u, user=user)
                    combined.append(f"### {u}\n{out[:1200]}")
                result = "\n\n".join(combined)
                await self._increment_autosearch_exec(guild, mode="scrape")
            elif mode == "crawl":
                url = params.get("url") or text
                depth = int(params.get("maxDepth", 2))
                limit = int(params.get("limit", 20))
                result = await self._tool_run_webfetch(guild, "crawl", url, limit=limit, depth=depth, user=user)
                await self._increment_autosearch_exec(guild, mode="crawl")
            elif mode == "deep_research":
                q = params.get("query", text)
                result = await self._tool_run_webfetch(guild, "deep_research", q, user=user)
                await self._increment_autosearch_exec(guild, mode="deep_research")
            else:
                result = plan
        except Exception as e:
            result = f"autosearch error: {type(e).__name__}: {str(e)[:120]}"
        return result

    async def _increment_autosearch_exec(self, guild: discord.Guild, mode: str):
        async with self.config.guild(guild).usage() as usage:
            a = usage.setdefault("autosearch", {"classified": 0, "executed": {"search": 0, "scrape": 0, "crawl": 0, "deep_research": 0}})
            ex = a.setdefault("executed", {})
            ex.setdefault(mode, 0)
            ex[mode] = int(ex.get(mode, 0)) + 1

    # Heuristic classifier (pure)
    def _heuristic_classify_autosearch(self, text: str) -> Tuple[str, Dict[str, Any], List[str]]:
        lowered = text.lower()
        urls = self._extract_urls(text)
        analytical_keywords = {"versus", "vs", "compare", "comparison", "impact", "trend", "analysis", "pros and cons", "future", "strategy"}
        crawl_keywords = {"crawl", "site", "all pages", "map", "discover"}
        params: Dict[str, Any] = {}
        followups: List[str] = []
        # Multiple URLs -> multi-scrape plan
        if urls:
            if len(urls) == 1:
                params["url"] = urls[0]
                return "scrape", params, followups
            else:
                params["urls"] = ",".join(urls[:5])
                followups.append("synthesize results")
                return "scrape_multi", params, followups
        # Domain + crawl intent
        domain_match = re.search(r"\b([a-z0-9-]+\.)+[a-z]{2,}\b", text, re.I)
        if domain_match and any(k in lowered for k in crawl_keywords):
            params["url"] = domain_match.group(0)
            depth = 2
            m_depth = re.search(r"depth\s*(\d)", lowered)
            if m_depth:
                depth = max(1, min(3, int(m_depth.group(1))))
            limit = 20
            m_limit = re.search(r"limit\s*(\d{1,3})", lowered)
            if m_limit:
                limit = max(5, min(50, int(m_limit.group(1))))
            params["maxDepth"] = depth
            params["limit"] = limit
            followups.append("extract representative pages")
            return "crawl", params, followups
        # Deep research conditions
        if len(text) > 160 or any(k in lowered for k in analytical_keywords):
            params["query"] = text[:180]
            followups.append("may need multi-source synthesis")
            return "deep_research", params, followups
        # Default search
        limit = 5
        if any(k in lowered for k in {"list", "top", "best", "alternatives"}):
            limit = 8
        params["query"] = text[:120]
        params["limit"] = limit
        # Potential follow-up: single result then scrape
        followups.append("if single high-confidence result -> scrape")
        return "search", params, followups

    def _extract_urls(self, text: str) -> List[str]:
        # Simple URL/host extractor (no validation)
        pattern = re.compile(r"https?://\S+|(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}(?:/\S*)?")
        found = pattern.findall(text)
        # Filter out things that look like sentences ending with a period
        cleaned = []
        for f in found:
            c = f.rstrip('.,;')
            if ' ' in c:
                continue
            # Skip if looks like just a TLD word accidentally (very short)
            if c.count('.') == 0:
                continue
            cleaned.append(c)
        # Deduplicate preserving order
        seen = set()
        uniq = []
        for c in cleaned:
            if c.lower() not in seen:
                seen.add(c.lower())
                uniq.append(c)
        return uniq[:10]

    async def _tool_is_enabled(self, guild: discord.Guild, name: str) -> bool:
        tools_cfg = await self.config.guild(guild).tools()
        enabled = tools_cfg.get("enabled", {})
        return bool(enabled.get(name, False))

    async def _tool_set_enabled(self, guild: discord.Guild, name: str, value: bool):
        async with self.config.guild(guild).tools() as tools_cfg:
            en = tools_cfg.setdefault("enabled", {})
            en[name] = value
