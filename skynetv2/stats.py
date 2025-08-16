from __future__ import annotations

from typing import Dict, Any, Optional
import time
import discord
try:
    from .governance import check_over_budget  # Prefer package-relative
except Exception:
    import importlib
    try:
        # Package-aware import for loaders that don't set __package__ properly
        _gov = importlib.import_module(".governance", package=__package__ or "skynetv2")
        check_over_budget = getattr(_gov, "check_over_budget")
    except Exception as e:
        raise ModuleNotFoundError(
            "Unable to import governance.check_over_budget via package-aware relative import"
        ) from e

class StatsMixin:
    """Stats and usage text builder."""

    def _human_delta(self, seconds: int) -> str:
        return (
            f"{seconds}s" if seconds < 60 else f"{seconds // 60}m" if seconds < 3600 else f"{seconds // 3600}h" if seconds < 86400 else f"{seconds // 86400}d"
        )

    async def _check_and_record_usage(self, guild: discord.Guild, channel: discord.abc.GuildChannel, user: discord.User) -> Optional[str]:
        now = int(time.time())
        rl = await self.config.guild(guild).rate_limits()
        cooldown = int(rl.get("cooldown_sec", 10))
        per_user_per_min = int(rl.get("per_user_per_min", 6))
        per_channel_per_min = int(rl.get("per_channel_per_min", 20))

        # Governance: hard reject when over budget (tokens or USD per effective unit)
        budget_err = await check_over_budget(self, guild)
        if budget_err:
            return budget_err

        is_owner = await self.bot.is_owner(user)
        async with self.config.guild(guild).usage() as usage:
            pu = usage.setdefault("per_user", {})
            pc = usage.setdefault("per_channel", {})
            u = pu.setdefault(str(user.id), {"last_used": 0, "count_1m": 0, "window_start": now, "total": 0, "tokens_total": 0})
            c = pc.setdefault(str(channel.id), {"count_1m": 0, "window_start": now, "total": 0, "tokens_total": 0})

            if now - int(u.get("window_start", now)) >= 60:
                u["window_start"], u["count_1m"] = now, 0
            if now - int(c.get("window_start", now)) >= 60:
                c["window_start"], c["count_1m"] = now, 0

            if not is_owner:
                if now - int(u.get("last_used", 0)) < cooldown:
                    return f"Cooldown active. Try again in {cooldown - (now - int(u.get('last_used', 0)))}s."
                if int(u.get("count_1m", 0)) >= per_user_per_min:
                    return "Per-user rate limit reached. Try again later."
                if int(c.get("count_1m", 0)) >= per_channel_per_min:
                    return "Channel is busy. Try again later."

            u["last_used"] = now
            u["count_1m"] = int(u.get("count_1m", 0)) + 1
            u["total"] = int(u.get("total", 0)) + 1
            c["count_1m"] = int(c.get("count_1m", 0)) + 1
            c["total"] = int(c.get("total", 0)) + 1
            usage["chat_count"] = int(usage.get("chat_count", 0)) + 1
            usage["last_used"] = now
        return None

    async def _build_stats_text(self, guild: discord.Guild, top_n: int = 5) -> str:
        rl = await self.config.guild(guild).rate_limits()
        usage = await self.config.guild(guild).usage()
        cooldown = int(rl.get("cooldown_sec", 10))
        pum = int(rl.get("per_user_per_min", 6))
        pcm = int(rl.get("per_channel_per_min", 20))
        tpu = int(rl.get("tools_per_user_per_min", 4))
        tpg = int(rl.get("tools_per_guild_per_min", 30))
        chat_count = int(usage.get("chat_count", 0))
        last_used = int(usage.get("last_used", 0))
        tokens = usage.get("tokens", {})
        cost = usage.get("cost", {}).get("usd", 0.0)
        tools_total = int(usage.get("tools_total", 0))
        tools_map: Dict[str, Dict[str, Any]] = usage.get("tools", {})
        autosearch = usage.get("autosearch", {})
        now = int(time.time())
        last = self._human_delta(now - last_used) if last_used else "n/a"
        lines = [
            f"Chats: {chat_count} | Last: {last}",
            f"Tokens: prompt={int(tokens.get('prompt', 0))}, completion={int(tokens.get('completion', 0))}, total={int(tokens.get('total', 0))}",
            f"Cost: ${float(cost):.6f}",
            f"Rate: cooldown={cooldown}s, per-user/min={pum}, per-channel/min={pcm}, tools-user/min={tpu}, tools-guild/min={tpg}",
            f"Tools: total={tools_total}, distinct={len(tools_map)}",
        ]
        
        # Enhanced autosearch mode distribution
        if autosearch:
            executed = autosearch.get("executed", {})
            classified_total = int(autosearch.get("classified", 0))
            search_count = int(executed.get("search", 0))
            scrape_count = int(executed.get("scrape", 0))
            crawl_count = int(executed.get("crawl", 0))
            deep_count = int(executed.get("deep_research", 0))
            
            lines.append(f"Autosearch: {classified_total} classified")
            if classified_total > 0:
                distribution = []
                if search_count > 0:
                    distribution.append(f"search:{search_count}")
                if scrape_count > 0:
                    distribution.append(f"scrape:{scrape_count}")
                if crawl_count > 0:
                    distribution.append(f"crawl:{crawl_count}")
                if deep_count > 0:
                    distribution.append(f"deep:{deep_count}")
                
                if distribution:
                    lines.append(f"Executed: {', '.join(distribution)}")
                else:
                    lines.append("Executed: (none)")
        
        if tools_map:
            top_tools = sorted(tools_map.items(), key=lambda kv: int(kv[1].get("count", 0)), reverse=True)[:top_n]
            if top_tools:
                lines.append("Top tools:")
                for name, data in top_tools:
                    count = int(data.get("count", 0))
                    success_count = int(data.get("success_count", 0))
                    error_count = int(data.get("error_count", 0))
                    latency = data.get("latency_ms", {})
                    
                    # Calculate success rate
                    total_attempts = success_count + error_count
                    success_rate = (success_count / total_attempts * 100) if total_attempts > 0 else 0
                    
                    # Calculate average latency
                    avg_latency = 0
                    last_latency = int(latency.get("last", 0))
                    if latency.get("count", 0) > 0:
                        avg_latency = int(latency.get("total", 0)) / int(latency.get("count", 1))
                    
                    line_parts = [f"- {name}: {count}"]
                    if total_attempts > 0:
                        line_parts.append(f"({success_rate:.0f}% ok)")
                    if avg_latency > 0:
                        line_parts.append(f"avg:{avg_latency:.0f}ms")
                    if last_latency > 0:
                        line_parts.append(f"last:{last_latency}ms")
                    
                    lines.append(" ".join(line_parts))
        
        # Display per-tool cooldowns if any are active
        rl = await self.config.guild(guild).rate_limits()
        tool_cooldowns: Dict[str, int] = rl.get("tool_cooldowns", {}) or {}
        if tool_cooldowns:
            lines.append("Tool cooldowns:")
            pu_for_cooldowns = usage.get("per_user", {})
            active_cooldowns = []
            for tool_name, cooldown_sec in tool_cooldowns.items():
                if cooldown_sec > 0:
                    # Check if any user has an active cooldown for this tool
                    max_remaining = 0
                    for user_data in pu_for_cooldowns.values():
                        tools_last = user_data.get("tools_last", {})
                        last_used = int(tools_last.get(tool_name, 0))
                        if last_used > 0:
                            remaining = max(0, cooldown_sec - (now - last_used))
                            max_remaining = max(max_remaining, remaining)
                    
                    status = f"ready" if max_remaining == 0 else f"{max_remaining}s"
                    active_cooldowns.append(f"- {tool_name}: {cooldown_sec}s ({status})")
            
            if active_cooldowns:
                lines.extend(active_cooldowns[:10])  # Limit to top 10 to avoid spam
            else:
                lines.append("- (all tools ready)")
        
        # Enhanced autosearch mode distribution
        if autosearch:
            executed = autosearch.get("executed", {})
            classified_total = int(autosearch.get("classified", 0))
            search_count = int(executed.get("search", 0))
            scrape_count = int(executed.get("scrape", 0))
            crawl_count = int(executed.get("crawl", 0))
            deep_count = int(executed.get("deep_research", 0))
            
            lines.append(f"Autosearch: {classified_total} classified")
            if classified_total > 0:
                distribution = []
                if search_count > 0:
                    distribution.append(f"search:{search_count}")
                if scrape_count > 0:
                    distribution.append(f"scrape:{scrape_count}")
                if crawl_count > 0:
                    distribution.append(f"crawl:{crawl_count}")
                if deep_count > 0:
                    distribution.append(f"deep:{deep_count}")
                
                if distribution:
                    lines.append(f"Executed: {', '.join(distribution)}")
                else:
                    lines.append("Executed: (none)")
        
        pu: Dict[str, Dict[str, Any]] = usage.get("per_user", {})
        if pu:
            top_users = sorted(pu.items(), key=lambda kv: int(kv[1].get("tokens_total", 0)), reverse=True)[:top_n]
            if top_users:
                lines.append("Top users (tokens):")
                for uid, stats in top_users:
                    member = guild.get_member(int(uid))
                    name = member.display_name if member else uid
                    lines.append(f"- {name}: tokens={int(stats.get('tokens_total', 0))}, req={int(stats.get('total', 0))}")
        pc: Dict[str, Dict[str, Any]] = usage.get("per_channel", {})
        if pc:
            top_channels = sorted(pc.items(), key=lambda kv: int(kv[1].get("tokens_total", 0)), reverse=True)[:top_n]
            if top_channels:
                lines.append("Top channels (tokens):")
                for cid, stats in top_channels:
                    chan = guild.get_channel(int(cid))
                    name = f"#{chan.name}" if isinstance(chan, discord.TextChannel) else cid
                    lines.append(f"- {name}: tokens={int(stats.get('tokens_total', 0))}, req={int(stats.get('total', 0))}")
        out = "\n".join(lines)
        return out[:1900]
