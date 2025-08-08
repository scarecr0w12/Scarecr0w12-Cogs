from __future__ import annotations

import asyncio
import io
import json
import time
from typing import Optional, Tuple, List, Dict, Any

import discord # type: ignore
from redbot.core import app_commands, commands, checks # pyright: ignore[reportMissingImports]
from redbot.core.utils.chat_formatting import box # pyright: ignore[reportMissingImports]
from redbot.core.utils.predicates import MessagePredicate # pyright: ignore[reportMissingImports]

from .config import register_config
from .api.base import ChatMessage
from .api.openai import OpenAIProvider
from .memory import MemoryMixin
from .tools import ToolsMixin
from .stats import StatsMixin
from .listener import ListenerMixin
from .orchestration import OrchestrationMixin
from .error_handler import ErrorHandler


class SkynetV2(ToolsMixin, MemoryMixin, StatsMixin, ListenerMixin, OrchestrationMixin, commands.Cog):
    """SkynetV2: AI assistant for Red-DiscordBot (MVP)."""

    def __init__(self, bot):
        self.bot = bot
        self.config = register_config(self)
        # simple in-memory cache for model lists: key=(provider, api_key)
        self._model_cache: dict[Tuple[str, str], Tuple[int, List[str]]] = {}
        self._model_cache_ttl: int = 300
        # Initialize error handler
        self.error_handler = ErrorHandler()
        # Initialize tool registry via mixin helper
        self._init_tool_registry()
        # Initialize orchestration system
        self._init_orchestration()

    # ----------------
    # Provider resolution & models
    # ----------------

    def _human_delta(self, seconds: int) -> str:  # kept for backward compatibility; StatsMixin also defines
        return super()._human_delta(seconds)  # type: ignore

    async def resolve_provider_and_model(self, guild: discord.Guild):
        gmodel = await self.config.guild(guild).model()
        default_model = await self.config.model()
        model = gmodel or default_model

        gproviders = await self.config.guild(guild).providers()
        global_providers = await self.config.providers()
        default_provider_name = global_providers.get("default", "openai")
        provider_name = (model.get("provider") if isinstance(model, dict) else None) or default_provider_name

        api_key = None
        if provider_name in gproviders and gproviders[provider_name].get("api_key"):
            api_key = gproviders[provider_name]["api_key"]
        else:
            api_key = global_providers.get(provider_name, {}).get("api_key")

        return provider_name, model, api_key

    def build_provider(self, provider_name: str, api_key: Optional[str]):
        if provider_name == "openai":
            if not api_key:
                raise RuntimeError("Missing API key for openai provider")
            return OpenAIProvider(api_key)
        raise RuntimeError(f"Unsupported provider: {provider_name}")

    async def _estimate_and_record_cost(self, guild: discord.Guild, provider: str, model_name: str, prompt_tokens: int, completion_tokens: int):
        pricing = await self.config.pricing()
        prov_map = pricing.get(provider, {})
        m = prov_map.get(model_name, {})
        in_cost = float(m.get("prompt_per_1k", 0.0)) * (prompt_tokens / 1000.0)
        out_cost = float(m.get("completion_per_1k", 0.0)) * (completion_tokens / 1000.0)
        delta = round(in_cost + out_cost, 6)
        if delta:
            async with self.config.guild(guild).usage() as usage:
                c = usage.setdefault("cost", {"usd": 0.0})
                c["usd"] = float(c.get("usd", 0.0)) + float(delta)

    async def _models_cached(self, provider_name: str, api_key: Optional[str]) -> List[str]:
        if not api_key:
            return []
        key = (provider_name, api_key)
        now = int(time.time())
        if key in self._model_cache:
            ts, models = self._model_cache[key]
            if now - ts < self._model_cache_ttl:
                return models
        try:
            provider = self.build_provider(provider_name, api_key)
            models = await provider.list_models()
            self._model_cache[key] = (now, models)
            return models
        except Exception:
            return []

    async def _is_model_allowed(self, guild: discord.Guild, provider: str, model_name: str) -> Optional[str]:
        policy = (await self.config.guild(guild).policy()) or {}
        models = policy.get("models", {})
        allow = models.get("allow", {}).get(provider, [])
        deny = models.get("deny", {}).get(provider, [])
        if model_name in deny:
            return "Model is denied by policy."
        if allow and model_name not in allow:
            return "Model is not in the allowed list."
        return None

    # ----------------
    # Autocomplete helpers
    # ----------------

    async def _ac_provider(self, interaction: discord.Interaction, current: str):
        providers = ["openai"]
        return [app_commands.Choice(name=p, value=p) for p in providers if current.lower() in p]

    async def _ac_model(self, interaction: discord.Interaction, current: str):
        guild = interaction.guild
        if guild is None:
            return []
        provider_name, model, api_key = await self.resolve_provider_and_model(guild)
        try:
            models = await self._models_cached(provider_name, api_key)
        except Exception:
            models = [model["name"]] if isinstance(model, dict) and model.get("name") else []
        current_l = current.lower()
        suggestions = [m for m in models if current_l in m.lower()][:25]
        return [app_commands.Choice(name=m, value=m) for m in suggestions]

    # ----------------
    # Governance helpers
    # ----------------
    async def _gov_get(self, guild: discord.Guild) -> dict:
        return await self.config.guild(guild).governance()

    async def _gov_update(self, guild: discord.Guild, mutate):
        async with self.config.guild(guild).governance() as gov:
            mutate(gov)

    # ----------------
    # Prefix commands
    # ----------------

    @commands.group(name="ai")
    @commands.guild_only()
    @commands.bot_has_permissions(send_messages=True)
    async def ai_group(self, ctx: commands.Context):
        """AI assistant commands."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help()

    @ai_group.command(name="chat")
    @commands.bot_has_permissions(send_messages=True)
    async def ai_chat(self, ctx: commands.Context, *, message: str):
        err = await self._check_and_record_usage(ctx.guild, ctx.channel, ctx.author)
        if err:
            await ctx.send(err)
            return
        provider_name, model, api_key = await self.resolve_provider_and_model(ctx.guild)
        if not api_key:
            await ctx.send("No API key configured. Use `[p]ai provider key set <provider> <key>`.")
            return
        try:
            provider = self.build_provider(provider_name, api_key)
        except Exception as e:
            error_msg = self.error_handler.safe_error_response(e, "provider")
            self.error_handler.log_error(e, "chat_command", {"provider": provider_name})
            await ctx.send(error_msg)
            return
        model_name = model["name"] if isinstance(model, dict) else str(model)
        policy_err = await self._is_model_allowed(ctx.guild, provider_name, model_name)
        if policy_err:
            await ctx.send(policy_err)
            return
        async with ctx.typing():
            base = await self._memory_build_context(ctx.guild, ctx.channel.id)
            chunks = []
            async for chunk in provider.chat(model=model_name, messages=base + [ChatMessage("user", message)]):
                chunks.append(chunk)
            text = "".join(chunks) or "(no output)"
            last_usage = getattr(provider, "get_last_usage", lambda: None)()
            if last_usage:
                epoch_now = int(time.time())
                async with self.config.guild(ctx.guild).usage() as usage:
                    t = usage.setdefault("tokens", {"prompt": 0, "completion": 0, "total": 0})
                    t["prompt"] = int(t.get("prompt", 0)) + int(last_usage.get("prompt", 0))
                    t["completion"] = int(t.get("completion", 0)) + int(last_usage.get("completion", 0))
                    t["total"] = int(t.get("total", 0)) + int(last_usage.get("total", 0))
                    pu = usage.setdefault("per_user", {})
                    pc = usage.setdefault("per_channel", {})
                    u = pu.setdefault(str(ctx.author.id), {"last_used": 0, "count_1m": 0, "window_start": int(time.time()), "total": 0, "tokens_total": 0})
                    pc.setdefault(str(ctx.channel.id), {"count_1m": 0, "window_start": int(time.time()), "total": 0, "tokens_total": 0})
                    u["tokens_total"] = int(u.get("tokens_total", 0)) + int(last_usage.get("total", 0))
                    # Daily token tracking (epoch based)
                    if epoch_now - int(u.get("tokens_day_start", epoch_now)) >= 86400:
                        u["tokens_day_start"], u["tokens_day_total"] = epoch_now, 0
                    u["tokens_day_total"] = int(u.get("tokens_day_total", 0)) + int(last_usage.get("total", 0))
            await self._memory_remember(ctx.guild, ctx.channel.id, message, text)
        await ctx.send(text[:2000])

    @ai_group.command(name="chatstream")
    @commands.bot_has_permissions(send_messages=True)
    async def ai_chatstream(self, ctx: commands.Context, *, message: str):
        err = await self._check_and_record_usage(ctx.guild, ctx.channel, ctx.author)
        if err:
            await ctx.send(err)
            return
        provider_name, model, api_key = await self.resolve_provider_and_model(ctx.guild)
        if not api_key:
            await ctx.send("No API key configured. Use `[p]ai provider key set <provider> <key>`.")
            return
        model_name = model["name"] if isinstance(model, dict) else str(model)
        policy_err = await self._is_model_allowed(ctx.guild, provider_name, model_name)
        if policy_err:
            await ctx.send(policy_err)
            return
        try:
            provider = self.build_provider(provider_name, api_key)
        except Exception as e:
            await ctx.send(f"Provider error: {e}")
            return
        base = await self._memory_build_context(ctx.guild, ctx.channel.id)
        msg = await ctx.send("…")
        buf = ""
        last_edit = 0.0
        try:
            async for chunk in provider.chat(model=model_name, messages=base + [ChatMessage("user", message)], stream=True):
                if not chunk:
                    continue
                buf += chunk
                perf_now = time.perf_counter()
                if len(buf) >= 2000:
                    buf = buf[:1995] + "…"
                    await msg.edit(content=buf)
                    break
                if perf_now - last_edit > 0.5 or len(buf) - len(msg.content or "") > 200:
                    await msg.edit(content=buf)
                    last_edit = perf_now
            if (msg.content or "") != buf:
                await msg.edit(content=buf or "(no output)")
        except Exception as e:
            await msg.edit(content=f"Error: {e}")
            return
        last_usage = getattr(provider, "get_last_usage", lambda: None)()
        if last_usage:
            epoch_now = int(time.time())
            async with self.config.guild(ctx.guild).usage() as usage:
                t = usage.setdefault("tokens", {"prompt": 0, "completion": 0, "total": 0})
                t["prompt"] = int(t.get("prompt", 0)) + int(last_usage.get("prompt", 0))
                t["completion"] = int(t.get("completion", 0)) + int(last_usage.get("completion", 0))
                t["total"] = int(t.get("total", 0)) + int(last_usage.get("total", 0))
                pu = usage.setdefault("per_user", {})
                usage.setdefault("per_channel", {})
                u = pu.setdefault(str(ctx.author.id), {"last_used": 0, "count_1m": 0, "window_start": int(time.time()), "total": 0, "tokens_total": 0})
                u["tokens_total"] = int(u.get("tokens_total", 0)) + int(last_usage.get("total", 0))
                if epoch_now - int(u.get("tokens_day_start", epoch_now)) >= 86400:
                    u["tokens_day_start"], u["tokens_day_total"] = epoch_now, 0
                u["tokens_day_total"] = int(u.get("tokens_day_total", 0)) + int(last_usage.get("total", 0))
            await self._estimate_and_record_cost(ctx.guild, provider_name, model_name, int(last_usage.get("prompt", 0)), int(last_usage.get("completion", 0)))
        await self._memory_remember(ctx.guild, ctx.channel.id, message, buf)

    @ai_group.command(name="websearch")
    async def ai_websearch(self, ctx: commands.Context, *, query: str):
        if not await self._tool_is_enabled(ctx.guild, "websearch"):
            await ctx.send("Tool 'websearch' is disabled. Enable with `[p]ai tools enable websearch`.")
            return
        err = await self._check_and_record_usage(ctx.guild, ctx.channel, ctx.author)
        if err:
            await ctx.send(err)
            return
        text = await self._tool_run_websearch(guild=ctx.guild, query=query, user=ctx.author)
        await ctx.send(text[:1900] or "(no results)")

    @ai_group.command(name="autosearch")
    async def ai_autosearch(self, ctx: commands.Context, *, query: str):
        """Heuristically classify query -> search/scrape/crawl/deep_research (planning only, use --exec to run search)."""
        execute = False
        if query.endswith(" --exec"):
            execute = True
            query = query[:-7].strip()
        if not await self._tool_is_enabled(ctx.guild, "autosearch"):
            await ctx.send("Tool 'autosearch' is disabled. Enable with `[p]ai tools enable autosearch`.")
            return
        err = await self._check_and_record_usage(ctx.guild, ctx.channel, ctx.author)
        if err:
            await ctx.send(err)
            return
        plan = await self._tool_run_autosearch(guild=ctx.guild, query=query, user=ctx.author, execute=execute)
        await ctx.send(box(plan[:1800], "yaml"))

    @ai_group.command(name="stats")
    @checks.admin_or_permissions(manage_guild=True)
    async def ai_stats(self, ctx: commands.Context, top: Optional[int] = 5):
        text = await self._build_stats_text(ctx.guild, top_n=int(top or 5))
        await ctx.send(box(text, "yaml"))

    @ai_group.group(name="rate")
    @checks.admin_or_permissions(manage_guild=True)
    async def ai_rate(self, ctx: commands.Context):
        """View or set rate limits."""
        if not ctx.invoked_subcommand:
            await ctx.send_help()

    @ai_rate.command(name="show")
    async def ai_rate_show(self, ctx: commands.Context):
        rl = await self.config.guild(ctx.guild).rate_limits()
        tool_cds = rl.get('tool_cooldowns', {}) or {}
        lines = [
            f"cooldown_sec: {int(rl.get('cooldown_sec', 10))}",
            f"per_user_per_min: {int(rl.get('per_user_per_min', 6))}",
            f"per_channel_per_min: {int(rl.get('per_channel_per_min', 20))}",
            f"tools_per_user_per_min: {int(rl.get('tools_per_user_per_min', 4))}",
            f"tools_per_guild_per_min: {int(rl.get('tools_per_guild_per_min', 30))}",
        ]
        if tool_cds:
            lines.append("tool_cooldowns:")
            for k,v in tool_cds.items():
                lines.append(f"  {k}: {int(v)}")
        await ctx.send(box("\n".join(lines), "yaml"))

    @ai_rate.command(name="set")
    async def ai_rate_set(self, ctx: commands.Context, cooldown_sec: Optional[int] = None, per_user_per_min: Optional[int] = None, per_channel_per_min: Optional[int] = None, tools_per_user_per_min: Optional[int] = None, tools_per_guild_per_min: Optional[int] = None, tool: Optional[str] = None, tool_cooldown_sec: Optional[int] = None):
        async with self.config.guild(ctx.guild).rate_limits() as rl:
            if cooldown_sec is not None:
                rl["cooldown_sec"] = int(cooldown_sec)
            if per_user_per_min is not None:
                rl["per_user_per_min"] = int(per_user_per_min)
            if per_channel_per_min is not None:
                rl["per_channel_per_min"] = int(per_channel_per_min)
            if tools_per_user_per_min is not None:
                rl["tools_per_user_per_min"] = int(tools_per_user_per_min)
            if tools_per_guild_per_min is not None:
                rl["tools_per_guild_per_min"] = int(tools_per_guild_per_min)
            if tool and tool_cooldown_sec is not None:
                cds = rl.setdefault('tool_cooldowns', {})
                if tool_cooldown_sec <= 0:
                    cds.pop(tool, None)
                else:
                    cds[tool] = int(tool_cooldown_sec)
        await ctx.tick()

    # ----------------
    # Governance commands (prefix)
    # ----------------

    @ai_group.group(name="governance")
    @checks.admin_or_permissions(manage_guild=True)
    async def ai_governance(self, ctx: commands.Context):
        """Governance policy controls."""
        if not ctx.invoked_subcommand:
            await ctx.send_help()

    @ai_governance.command(name="show")
    async def ai_governance_show(self, ctx: commands.Context):
        gov = await self._gov_get(ctx.guild)
        lines = []
        tools = gov.get("tools", {}) if gov else {}
        bypass = gov.get("bypass", {}) if gov else {}
        budget = gov.get("budget", {}) if gov else {}
        lines.append("tools_allow: " + ",".join(tools.get("allow", [])))
        lines.append("tools_deny: " + ",".join(tools.get("deny", [])))
        lines.append("per_user_minute_overrides: " + (",".join(f"{k}:{v}" for k,v in (tools.get("per_user_minute_overrides", {}) or {}).items()) or "(none)"))
        lines.append("bypass_cooldown_roles: " + (",".join(str(r) for r in bypass.get("cooldown_roles", [])) or "(none)"))
        lines.append(f"budget_per_user_daily_tokens: {int(budget.get('per_user_daily_tokens', 0))}")
        await ctx.send(box("\n".join(lines), "yaml"))

    @ai_governance.group(name="allow")
    async def ai_governance_allow(self, ctx: commands.Context):
        """Manage allowed tools list."""
        if not ctx.invoked_subcommand:
            await ctx.send_help()

    @ai_governance_allow.command(name="add")
    async def ai_governance_allow_add(self, ctx: commands.Context, tool: str):
        await self._gov_update(ctx.guild, lambda g: g.setdefault("tools", {}).setdefault("allow", []).append(tool) if tool not in g.setdefault("tools", {}).setdefault("allow", []) else None)
        await ctx.tick()

    @ai_governance_allow.command(name="remove")
    async def ai_governance_allow_remove(self, ctx: commands.Context, tool: str):
        await self._gov_update(ctx.guild, lambda g: g.setdefault("tools", {}).setdefault("allow", []).remove(tool) if tool in g.setdefault("tools", {}).setdefault("allow", []) else None)
        await ctx.tick()

    @ai_governance.group(name="deny")
    async def ai_governance_deny(self, ctx: commands.Context):
        """Manage denied tools list."""
        if not ctx.invoked_subcommand:
            await ctx.send_help()

    @ai_governance_deny.command(name="add")
    async def ai_governance_deny_add(self, ctx: commands.Context, tool: str):
        await self._gov_update(ctx.guild, lambda g: g.setdefault("tools", {}).setdefault("deny", []).append(tool) if tool not in g.setdefault("tools", {}).setdefault("deny", []) else None)
        await ctx.tick()

    @ai_governance_deny.command(name="remove")
    async def ai_governance_deny_remove(self, ctx: commands.Context, tool: str):
        await self._gov_update(ctx.guild, lambda g: g.setdefault("tools", {}).setdefault("deny", []).remove(tool) if tool in g.setdefault("tools", {}).setdefault("deny", []) else None)
        await ctx.tick()

    @ai_governance.group(name="bypass")
    async def ai_governance_bypass(self, ctx: commands.Context):
        """Manage cooldown bypass roles."""
        if not ctx.invoked_subcommand:
            await ctx.send_help()

    @ai_governance_bypass.command(name="addrole")
    async def ai_governance_bypass_add(self, ctx: commands.Context, role: discord.Role):
        await self._gov_update(ctx.guild, lambda g: g.setdefault("bypass", {}).setdefault("cooldown_roles", []).append(role.id) if role.id not in g.setdefault("bypass", {}).setdefault("cooldown_roles", []) else None)
        await ctx.tick()

    @ai_governance_bypass.command(name="removerole")
    async def ai_governance_bypass_remove(self, ctx: commands.Context, role: discord.Role):
        await self._gov_update(ctx.guild, lambda g: g.setdefault("bypass", {}).setdefault("cooldown_roles", []).remove(role.id) if role.id in g.setdefault("bypass", {}).setdefault("cooldown_roles", []) else None)
        await ctx.tick()

    @ai_governance.group(name="override")
    async def ai_governance_override(self, ctx: commands.Context):
        """Per-tool per-user minute cap overrides."""
        if not ctx.invoked_subcommand:
            await ctx.send_help()

    @ai_governance_override.command(name="set")
    async def ai_governance_override_set(self, ctx: commands.Context, tool: str, per_minute: int):
        await self._gov_update(ctx.guild, lambda g: g.setdefault("tools", {}).setdefault("per_user_minute_overrides", {}).update({tool: int(per_minute)}))
        await ctx.tick()

    @ai_governance_override.command(name="clear")
    async def ai_governance_override_clear(self, ctx: commands.Context, tool: str):
        await self._gov_update(ctx.guild, lambda g: g.setdefault("tools", {}).setdefault("per_user_minute_overrides", {}).pop(tool, None))
        await ctx.tick()

    @ai_governance.group(name="budget")
    async def ai_governance_budget(self, ctx: commands.Context):
        """Budget caps."""
        if not ctx.invoked_subcommand:
            await ctx.send_help()

    @ai_governance_budget.command(name="settokens")
    async def ai_governance_budget_settokens(self, ctx: commands.Context, per_user_daily_tokens: int):
        await self._gov_update(ctx.guild, lambda g: g.setdefault("budget", {}).update({"per_user_daily_tokens": max(0, int(per_user_daily_tokens))}))
        await ctx.tick()

    # ----------------
    # Slash commands
    # ----------------

    ai_slash = app_commands.Group(name="skynet", description="AI assistant commands")
    
    # All slash command groups defined at class level
    governance_group = app_commands.Group(name="governance", description="Governance controls", parent=ai_slash)
    mem_group = app_commands.Group(name="memory", description="Memory controls", parent=ai_slash)
    rate_group = app_commands.Group(name="rate", description="Rate limit controls", parent=ai_slash)
    tools_group = app_commands.Group(name="tools", description="Tool management", parent=ai_slash)
    search_group = app_commands.Group(name="search", description="Search provider controls", parent=ai_slash)
    provider_group = app_commands.Group(name="provider", description="Provider management", parent=ai_slash)

    @governance_group.command(name="show", description="Show governance policy")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def slash_governance_show(self, interaction: discord.Interaction):
        assert interaction.guild is not None
        gov = await self._gov_get(interaction.guild)
        tools = gov.get("tools", {}) if gov else {}
        bypass = gov.get("bypass", {}) if gov else {}
        budget = gov.get("budget", {}) if gov else {}
        lines = [
            "tools_allow: " + ",".join(tools.get("allow", [])),
            "tools_deny: " + ",".join(tools.get("deny", [])),
            "per_user_minute_overrides: " + (",".join(f"{k}:{v}" for k,v in (tools.get("per_user_minute_overrides", {}) or {}).items()) or "(none)"),
            "bypass_cooldown_roles: " + (",".join(str(r) for r in bypass.get("cooldown_roles", [])) or "(none)"),
            f"budget_per_user_daily_tokens: {int(budget.get('per_user_daily_tokens', 0))}",
        ]
        await interaction.response.send_message(box("\n".join(lines), "yaml"), ephemeral=True)

    @governance_group.command(name="allow_add", description="Add allowed tool")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def slash_governance_allow_add(self, interaction: discord.Interaction, tool: str):
        assert interaction.guild is not None
        await self._gov_update(interaction.guild, lambda g: g.setdefault("tools", {}).setdefault("allow", []).append(tool) if tool not in g.setdefault("tools", {}).setdefault("allow", []) else None)
        await interaction.response.send_message("Added.", ephemeral=True)

    @governance_group.command(name="allow_remove", description="Remove allowed tool")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def slash_governance_allow_remove(self, interaction: discord.Interaction, tool: str):
        assert interaction.guild is not None
        await self._gov_update(interaction.guild, lambda g: g.setdefault("tools", {}).setdefault("allow", []).remove(tool) if tool in g.setdefault("tools", {}).setdefault("allow", []) else None)
        await interaction.response.send_message("Removed.", ephemeral=True)

    @governance_group.command(name="deny_add", description="Add denied tool")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def slash_governance_deny_add(self, interaction: discord.Interaction, tool: str):
        assert interaction.guild is not None
        await self._gov_update(interaction.guild, lambda g: g.setdefault("tools", {}).setdefault("deny", []).append(tool) if tool not in g.setdefault("tools", {}).setdefault("deny", []) else None)
        await interaction.response.send_message("Added.", ephemeral=True)

    @governance_group.command(name="deny_remove", description="Remove denied tool")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def slash_governance_deny_remove(self, interaction: discord.Interaction, tool: str):
        assert interaction.guild is not None
        await self._gov_update(interaction.guild, lambda g: g.setdefault("tools", {}).setdefault("deny", []).remove(tool) if tool in g.setdefault("tools", {}).setdefault("deny", []) else None)
        await interaction.response.send_message("Removed.", ephemeral=True)

    @governance_group.command(name="bypass_addrole", description="Add cooldown bypass role")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def slash_governance_bypass_add(self, interaction: discord.Interaction, role: discord.Role):
        assert interaction.guild is not None
        await self._gov_update(interaction.guild, lambda g: g.setdefault("bypass", {}).setdefault("cooldown_roles", []).append(role.id) if role.id not in g.setdefault("bypass", {}).setdefault("cooldown_roles", []) else None)
        await interaction.response.send_message("Added.", ephemeral=True)

    @governance_group.command(name="bypass_removerole", description="Remove cooldown bypass role")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def slash_governance_bypass_removerole(self, interaction: discord.Interaction, role: discord.Role):
        assert interaction.guild is not None
        await self._gov_update(interaction.guild, lambda g: g.setdefault("bypass", {}).setdefault("cooldown_roles", []).remove(role.id) if role.id in g.setdefault("bypass", {}).setdefault("cooldown_roles", []) else None)
        await interaction.response.send_message("Removed.", ephemeral=True)

    @governance_group.command(name="override_set", description="Set per-user/min override for a tool")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def slash_governance_override_set(self, interaction: discord.Interaction, tool: str, per_minute: int):
        assert interaction.guild is not None
        await self._gov_update(interaction.guild, lambda g: g.setdefault("tools", {}).setdefault("per_user_minute_overrides", {}).update({tool: int(per_minute)}))
        await interaction.response.send_message("Override set.", ephemeral=True)

    @governance_group.command(name="override_clear", description="Clear per-user/min override for a tool")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def slash_governance_override_clear(self, interaction: discord.Interaction, tool: str):
        assert interaction.guild is not None
        await self._gov_update(interaction.guild, lambda g: g.setdefault("tools", {}).setdefault("per_user_minute_overrides", {}).pop(tool, None))
        await interaction.response.send_message("Override cleared.", ephemeral=True)

    @governance_group.command(name="budget_settokens", description="Set per-user daily token budget")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def slash_governance_budget_settokens(self, interaction: discord.Interaction, per_user_daily_tokens: int):
        assert interaction.guild is not None
        await self._gov_update(interaction.guild, lambda g: g.setdefault("budget", {}).update({"per_user_daily_tokens": max(0, int(per_user_daily_tokens))}))
        await interaction.response.send_message("Budget updated.", ephemeral=True)

    @ai_slash.command(name="chat", description="Chat once with the configured model")
    @app_commands.describe(message="Your message to the assistant", stream="Stream partial output (edits message)")
    async def slash_chat(self, interaction: discord.Interaction, message: str, stream: Optional[bool] = False):
        assert interaction.guild is not None
        err = await self._check_and_record_usage(interaction.guild, interaction.channel, interaction.user)
        if err:
            await interaction.response.send_message(err, ephemeral=True)
            return
        provider_name, model, api_key = await self.resolve_provider_and_model(interaction.guild)
        if not api_key:
            await interaction.response.send_message("No API key configured. Ask an admin to set one.", ephemeral=True)
            return
        try:
            provider = self.build_provider(provider_name, api_key)
        except Exception as e:
            error_msg = self.error_handler.safe_error_response(e, "provider")
            self.error_handler.log_error(e, "slash_chat", {"provider": provider_name})
            await interaction.response.send_message(error_msg, ephemeral=True)
            return
        model_name = model["name"] if isinstance(model, dict) else str(model)
        policy_err = await self._is_model_allowed(interaction.guild, provider_name, model_name)
        if policy_err:
            await interaction.response.send_message(policy_err, ephemeral=True)
            return
        base = await self._memory_build_context(interaction.guild, interaction.channel.id)
        if stream:
            await interaction.response.defer(thinking=True)
            msg = await interaction.followup.send("…")
            buf = ""
            last_edit = 0.0
            try:
                async for chunk in provider.chat(model=model_name, messages=base + [ChatMessage("user", message)], stream=True):
                    if not chunk:
                        continue
                    buf += chunk
                    perf_now = time.perf_counter()
                    if len(buf) >= 2000:
                        buf = buf[:1995] + "…"
                        await msg.edit(content=buf)
                        break
                    if perf_now - last_edit > 0.5 or len(buf) - len(msg.content or "") > 200:
                        await msg.edit(content=buf)
                        last_edit = perf_now
                if (msg.content or "") != buf:
                    await msg.edit(content=buf or "(no output)")
            except Exception as e:
                await msg.edit(content=f"Error: {e}")
                return
            last_usage = getattr(provider, "get_last_usage", lambda: None)()
            if last_usage:
                epoch_now = int(time.time())
                async with self.config.guild(interaction.guild).usage() as usage:
                    t = usage.setdefault("tokens", {"prompt": 0, "completion": 0, "total": 0})
                    t["prompt"] = int(t.get("prompt", 0)) + int(last_usage.get("prompt", 0))
                    t["completion"] = int(t.get("completion", 0)) + int(last_usage.get("completion", 0))
                    t["total"] = int(t.get("total", 0)) + int(last_usage.get("total", 0))
                    pu = usage.setdefault("per_user", {})
                    usage.setdefault("per_channel", {})
                    u = pu.setdefault(str(interaction.user.id), {"last_used": 0, "count_1m": 0, "window_start": int(time.time()), "total": 0, "tokens_total": 0})
                    u["tokens_total"] = int(u.get("tokens_total", 0)) + int(last_usage.get("total", 0))
                    if epoch_now - int(u.get("tokens_day_start", epoch_now)) >= 86400:
                        u["tokens_day_start"], u["tokens_day_total"] = epoch_now, 0
                    u["tokens_day_total"] = int(u.get("tokens_day_total", 0)) + int(last_usage.get("total", 0))
                await self._estimate_and_record_cost(interaction.guild, provider_name, model_name, int(last_usage.get("prompt", 0)), int(last_usage.get("completion", 0)))
            await self._memory_remember(interaction.guild, interaction.channel.id, message, buf)
            return
        await interaction.response.defer(thinking=True)
        chunks = []
        async for chunk in provider.chat(model=model_name, messages=base + [ChatMessage("user", message)]):
            chunks.append(chunk)
        text = "".join(chunks) or "(no output)"
        last_usage = getattr(provider, "get_last_usage", lambda: None)()
        if last_usage:
            epoch_now = int(time.time())
            async with self.config.guild(interaction.guild).usage() as usage:
                t = usage.setdefault("tokens", {"prompt": 0, "completion": 0, "total": 0})
                t["prompt"] = int(t.get("prompt", 0)) + int(last_usage.get("prompt", 0))
                t["completion"] = int(t.get("completion", 0)) + int(last_usage.get("completion", 0))
                t["total"] = int(t.get("total", 0)) + int(last_usage.get("total", 0))
                pu = usage.setdefault("per_user", {})
                usage.setdefault("per_channel", {})
                u = pu.setdefault(str(interaction.user.id), {"last_used": 0, "count_1m": 0, "window_start": int(time.time()), "total": 0, "tokens_total": 0})
                u["tokens_total"] = int(u.get("tokens_total", 0)) + int(last_usage.get("total", 0))
                if epoch_now - int(u.get("tokens_day_start", epoch_now)) >= 86400:
                    u["tokens_day_start"], u["tokens_day_total"] = epoch_now, 0
                u["tokens_day_total"] = int(u.get("tokens_day_total", 0)) + int(last_usage.get("total", 0))
            await self._estimate_and_record_cost(interaction.guild, provider_name, model_name, int(last_usage.get("prompt", 0)), int(last_usage.get("completion", 0)))
        await self._memory_remember(interaction.guild, interaction.channel.id, message, text)
        await interaction.followup.send(text[:2000])

    @ai_slash.command(name="autosearch", description="Heuristic classify query -> mode + params (optionally execute search)")
    @app_commands.describe(query="Input to classify", execute="Execute search if mode=search")
    async def slash_autosearch(self, interaction: discord.Interaction, query: str, execute: Optional[bool] = False):
        assert interaction.guild is not None
        if not await self._tool_is_enabled(interaction.guild, "autosearch"):
            await interaction.response.send_message("Tool 'autosearch' is disabled. Enable with `[p]ai tools enable autosearch`.", ephemeral=True)
            return
        err = await self._check_and_record_usage(interaction.guild, interaction.channel, interaction.user)
        if err:
            await interaction.response.send_message(err, ephemeral=True)
            return
        plan = await self._tool_run_autosearch(guild=interaction.guild, query=query, user=interaction.user, execute=bool(execute))
        await interaction.response.send_message(box(plan[:1800], "yaml"))

    # Memory management slash commands

    @mem_group.command(name="show", description="Show recent memory entries for this channel")
    @app_commands.describe(limit="Number of pairs to show")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def slash_memory_show(self, interaction: discord.Interaction, limit: Optional[int] = None):
        assert interaction.guild is not None
        msgs = await self._memory_get_messages(interaction.guild, interaction.channel.id)
        lim = limit if limit is not None else await self._memory_get_limit(interaction.guild, interaction.channel.id)
        view = msgs[-lim * 2:]
        lines = []
        for m in view[-10:]:
            role = m.get("role", "?")
            content = (m.get("content", "") or "").replace("`", "\u0060")
            lines.append(f"{role}: {content[:120]}")
        await interaction.response.send_message(box("\n".join(lines) if lines else "(empty)", "yaml"), ephemeral=True)

    @mem_group.command(name="prune", description="Set limit and prune memory for this channel")
    @app_commands.describe(limit="New memory size (pairs) for this channel")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def slash_memory_prune(self, interaction: discord.Interaction, limit: Optional[int] = None):
        assert interaction.guild is not None
        async with self.config.guild(interaction.guild).memory() as mem:
            per = mem.setdefault("per_channel", {}).setdefault(str(interaction.channel.id), {})
            if limit is not None:
                per["limit"] = int(limit)
            msgs = per.setdefault("messages", [])
            l = int(per.get("limit", mem.get("default_limit", 10))) * 2
            if len(msgs) > l:
                del msgs[0: len(msgs) - l]
        await interaction.response.send_message("Memory updated.", ephemeral=True)

    @mem_group.command(name="export", description="DM export of recent memory (per channel)")
    @app_commands.describe(user_id="Filter messages starting with mention of user id (simple heuristic)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def slash_memory_export(self, interaction: discord.Interaction, user_id: Optional[int] = None):
        assert interaction.guild is not None
        mem = await self.config.guild(interaction.guild).memory()
        out_lines: List[str] = []
        per_channel = mem.get("per_channel", {})
        for ch_id, data in per_channel.items():
            msgs = data.get("messages", [])
            if user_id:
                filtered = []
                for m in msgs:
                    if m.get("role") == "user" and m.get("content", "").startswith(f"<@{user_id}>"):
                        filtered.append(m)
                    elif m.get("role") == "assistant":
                        filtered.append(m)
            else:
                filtered = msgs
            if not filtered:
                continue
            out_lines.append(f"channel: {ch_id}")
            for m in filtered[-50:]:
                role = m.get("role", "?")
                content = (m.get("content", "") or "").replace("`", "\u0060")
                ts = int(m.get("ts", 0))
                out_lines.append(f"- {role} @ {ts}: {content[:160]}")
        text = "\n".join(out_lines) if out_lines else "(no memory)"
        await interaction.response.send_message(box(text[:1900], "yaml"), ephemeral=True)

    @mem_group.command(name="clear", description="Clear all stored memory for guild")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def slash_memory_clear(self, interaction: discord.Interaction):
        assert interaction.guild is not None
        async with self.config.guild(interaction.guild).memory() as mem:
            mem["per_channel"] = {}
        await interaction.response.send_message("Memory cleared.", ephemeral=True)

    @mem_group.command(name="prune_policy", description="Set pruning policy (max_items / max_age_days)")
    @app_commands.describe(max_items="Hard cap on stored messages", max_age_days="Age cap in days (0=disable)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def slash_memory_prune_policy(self, interaction: discord.Interaction, max_items: Optional[int] = None, max_age_days: Optional[int] = None):
        assert interaction.guild is not None
        async with self.config.guild(interaction.guild).memory() as mem:
            prune = mem.setdefault("prune", {"max_items": 400, "max_age_days": 30})
            if max_items is not None:
                prune["max_items"] = max(0, int(max_items))
            if max_age_days is not None:
                prune["max_age_days"] = max(0, int(max_age_days))
        await interaction.response.send_message("Prune policy updated.", ephemeral=True)

    @ai_slash.command(name="stats", description="Show AI usage stats for this server")
    @app_commands.describe(top="Top N users/channels to list")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def slash_stats(self, interaction: discord.Interaction, top: Optional[int] = 5):
        assert interaction.guild is not None
        text = await self._build_stats_text(interaction.guild, top_n=int(top or 5))
        await interaction.response.send_message(box(text, "yaml"), ephemeral=True)

    # Rate limit slash commands

    @rate_group.command(name="show", description="Show current rate limits")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def slash_rate_show(self, interaction: discord.Interaction):
        assert interaction.guild is not None
        rl = await self.config.guild(interaction.guild).rate_limits()
        tool_cds = rl.get('tool_cooldowns', {}) or {}
        parts = [
            f"cooldown_sec: {int(rl.get('cooldown_sec', 10))}",
            f"per_user_per_min: {int(rl.get('per_user_per_min', 6))}",
            f"per_channel_per_min: {int(rl.get('per_channel_per_min', 20))}",
            f"tools_per_user_per_min: {int(rl.get('tools_per_user_per_min', 4))}",
            f"tools_per_guild_per_min: {int(rl.get('tools_per_guild_per_min', 30))}",
        ]
        if tool_cds:
            parts.append("tool_cooldowns:")
            for k,v in tool_cds.items():
                parts.append(f"  {k}: {int(v)}")
        await interaction.response.send_message(box("\n".join(parts), "yaml"), ephemeral=True)

    @rate_group.command(name="set", description="Set rate limits")
    @app_commands.describe(cooldown_sec="Cooldown in seconds", per_user_per_min="Per-user requests per minute", per_channel_per_min="Per-channel requests per minute", tools_per_user_per_min="Per-user tool invocations per minute", tools_per_guild_per_min="Per-guild tool invocations per minute", tool="Tool name for a specific cooldown", tool_cooldown_sec="Cooldown seconds for that tool (0 or negative to clear)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def slash_rate_set(self, interaction: discord.Interaction, cooldown_sec: Optional[int] = None, per_user_per_min: Optional[int] = None, per_channel_per_min: Optional[int] = None, tools_per_user_per_min: Optional[int] = None, tools_per_guild_per_min: Optional[int] = None, tool: Optional[str] = None, tool_cooldown_sec: Optional[int] = None):
        assert interaction.guild is not None
        async with self.config.guild(interaction.guild).rate_limits() as rl:
            if cooldown_sec is not None:
                rl["cooldown_sec"] = int(cooldown_sec)
            if per_user_per_min is not None:
                rl["per_user_per_min"] = int(per_user_per_min)
            if per_channel_per_min is not None:
                rl["per_channel_per_min"] = int(per_channel_per_min)
            if tools_per_user_per_min is not None:
                rl["tools_per_user_per_min"] = int(tools_per_user_per_min)
            if tools_per_guild_per_min is not None:
                rl["tools_per_guild_per_min"] = int(tools_per_guild_per_min)
            if tool and tool_cooldown_sec is not None:
                cds = rl.setdefault('tool_cooldowns', {})
                if tool_cooldown_sec <= 0:
                    cds.pop(tool, None)
                else:
                    cds[tool] = int(tool_cooldown_sec)
        await interaction.response.send_message("Rate limits updated.", ephemeral=True)

    @ai_group.group(name="tools")
    @checks.admin_or_permissions(manage_guild=True)
    async def ai_tools(self, ctx: commands.Context):
        """Manage AI tools (enable/disable/list)."""
        if not ctx.invoked_subcommand:
            await ctx.send_help()

    @ai_tools.command(name="list")
    async def ai_tools_list(self, ctx: commands.Context):
        lines = []
        for name, meta in sorted(self._tool_registry.items()):
            enabled = await self._tool_is_enabled(ctx.guild, name)
            lines.append(f"{name}: {'on' if enabled else 'off'} - {meta.get('desc','')}")
        await ctx.send(box("\n".join(lines) if lines else "(no tools)", "yaml"))

    @ai_tools.command(name="enable")
    async def ai_tools_enable(self, ctx: commands.Context, name: str):
        if name not in self._tool_registry:
            await ctx.send("Unknown tool.")
            return
        await self._tool_set_enabled(ctx.guild, name, True)
        await ctx.tick()

    @ai_tools.command(name="disable")
    async def ai_tools_disable(self, ctx: commands.Context, name: str):
        if name not in self._tool_registry:
            await ctx.send("Unknown tool.")
            return
        await self._tool_set_enabled(ctx.guild, name, False)
        await ctx.tick()

    # Tools management slash commands

    @tools_group.command(name="list", description="List available tools and status")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def slash_tools_list(self, interaction: discord.Interaction):
        assert interaction.guild is not None
        lines = []
        for name, meta in sorted(self._tool_registry.items()):
            enabled = await self._tool_is_enabled(interaction.guild, name)
            lines.append(f"{name}: {'on' if enabled else 'off'} - {meta.get('desc','')}")
        # Append usage summary if exists
        usage = await self.config.guild(interaction.guild).usage()
        tools_usage = usage.get("tools", {})
        if tools_usage:
            lines.append("")
            lines.append("Tool usage:")
            for n, data in sorted(tools_usage.items(), key=lambda kv: int(kv[1].get('count', 0)), reverse=True):
                lines.append(f"- {n}: {int(data.get('count', 0))}")
        await interaction.response.send_message(box("\n".join(lines) if lines else "(no tools)", "yaml"), ephemeral=True)

    @tools_group.command(name="enable", description="Enable a tool")
    @app_commands.describe(name="Tool name")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def slash_tools_enable(self, interaction: discord.Interaction, name: str):
        assert interaction.guild is not None
        if name not in self._tool_registry:
            await interaction.response.send_message("Unknown tool.", ephemeral=True)
            return
        await self._tool_set_enabled(interaction.guild, name, True)
        await interaction.response.send_message("Enabled.", ephemeral=True)

    @tools_group.command(name="disable", description="Disable a tool")
    @app_commands.describe(name="Tool name")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def slash_tools_disable(self, interaction: discord.Interaction, name: str):
        assert interaction.guild is not None
        if name not in self._tool_registry:
            await interaction.response.send_message("Unknown tool.", ephemeral=True)
            return
        await self._tool_set_enabled(interaction.guild, name, False)
        await interaction.response.send_message("Disabled.", ephemeral=True)

    @ai_group.group(name="search")
    @checks.admin_or_permissions(manage_guild=True)
    async def ai_search(self, ctx: commands.Context):
        """Search provider controls."""
        if not ctx.invoked_subcommand:
            await ctx.send_help()

    @ai_search.command(name="show")
    async def ai_search_show(self, ctx: commands.Context):
        g = await self.config.guild(ctx.guild).search()
        glob = await self.config.search()
        g_kind = (g or {}).get("provider") if isinstance(g, dict) else None
        glob_kind = (glob or {}).get("provider") if isinstance(glob, dict) else "dummy"
        if g_kind:
            await ctx.send(box(f"guild_provider: {g_kind}\ninherit_global: false", "yaml"))
        else:
            await ctx.send(box(f"guild_provider: (inherit)\nresolved: {glob_kind}", "yaml"))

    @ai_search.command(name="set")
    async def ai_search_set(self, ctx: commands.Context, provider: str | None):
        if provider is None or provider.lower() in {"inherit", "default"}:
            await self.config.guild(ctx.guild).search.set(None)
            await ctx.tick()
            return
        if provider.lower() not in {"dummy", "serp", "serp-stub"}:
            await ctx.send("Unsupported search provider.")
            return
        await self.config.guild(ctx.guild).search.set({"provider": provider.lower()})
        await ctx.tick()

    # Search provider slash commands

    @search_group.command(name="show", description="Show search provider configuration")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def slash_search_show(self, interaction: discord.Interaction):
        assert interaction.guild is not None
        g = await self.config.guild(interaction.guild).search()
        glob = await self.config.search()
        g_kind = (g or {}).get("provider") if isinstance(g, dict) else None
        glob_kind = (glob or {}).get("provider") if isinstance(glob, dict) else "dummy"
        if g_kind:
            text = f"guild_provider: {g_kind}\ninherit_global: false"
        else:
            text = f"guild_provider: (inherit)\nresolved: {glob_kind}"
        await interaction.response.send_message(box(text, "yaml"), ephemeral=True)

    @search_group.command(name="set", description="Set guild search provider (dummy/serp/serp-stub or inherit)")
    @app_commands.describe(provider="Provider name (dummy, serp, serp-stub) or 'inherit'")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def slash_search_set(self, interaction: discord.Interaction, provider: str):
        assert interaction.guild is not None
        if provider.lower() in {"inherit", "default"}:
            await self.config.guild(interaction.guild).search.set(None)
            await interaction.response.send_message("Search provider reset to inherit.", ephemeral=True)
            return
        if provider.lower() not in {"dummy", "serp", "serp-stub"}:
            await interaction.response.send_message("Unsupported search provider.", ephemeral=True)
            return
        await self.config.guild(interaction.guild).search.set({"provider": provider.lower()})
        await interaction.response.send_message("Search provider updated.", ephemeral=True)

    @ai_group.group(name="provider")
    @checks.admin_or_permissions(manage_guild=True)
    async def ai_provider(self, ctx: commands.Context):
        """Provider management commands."""
        if not ctx.invoked_subcommand:
            await ctx.send_help()

    @ai_provider.group(name="key")
    async def ai_provider_key(self, ctx: commands.Context):
        """Manage provider API keys."""
        if not ctx.invoked_subcommand:
            await ctx.send_help()

    @ai_provider_key.command(name="set")
    async def ai_provider_key_set(self, ctx: commands.Context, provider: str, key: str, global_flag: Optional[str] = None):
        """Set API key for a provider. Use --global for server-wide key."""
        if provider.lower() not in {"openai", "serp", "firecrawl"}:
            await ctx.send("Unsupported provider. Supported: openai, serp, firecrawl")
            return
        
        is_global = global_flag and global_flag.lower() == "--global"
        
        if is_global:
            async with self.config.providers() as providers:
                providers.setdefault(provider.lower(), {})["api_key"] = key
        else:
            async with self.config.guild(ctx.guild).providers() as providers:
                providers.setdefault(provider.lower(), {})["api_key"] = key
        
        scope = "global" if is_global else "guild"
        await ctx.send(f"Set {provider} API key ({scope}). Key: {key[:8]}{'*' * (len(key) - 8)}")

    @ai_provider_key.command(name="show")
    async def ai_provider_key_show(self, ctx: commands.Context):
        """Show configured API keys (redacted)."""
        guild_providers = await self.config.guild(ctx.guild).providers()
        global_providers = await self.config.providers()
        
        lines = []
        for provider in ["openai", "serp", "firecrawl"]:
            g_key = guild_providers.get(provider, {}).get("api_key")
            global_key = global_providers.get(provider, {}).get("api_key")
            
            if g_key:
                lines.append(f"{provider}: guild={g_key[:8]}{'*' * max(0, len(g_key) - 8)}")
            elif global_key:
                lines.append(f"{provider}: global={global_key[:8]}{'*' * max(0, len(global_key) - 8)}")
            else:
                lines.append(f"{provider}: (not set)")
        
        await ctx.send(box("\n".join(lines), "yaml"))

    # Provider management slash commands
    
    @provider_group.command(name="key_set", description="Set provider API key")
    @app_commands.describe(provider="Provider name", key="API key", global_scope="Set globally (default: guild only)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def slash_provider_key_set(self, interaction: discord.Interaction, provider: str, key: str, global_scope: Optional[bool] = False):
        assert interaction.guild is not None
        if provider.lower() not in {"openai", "serp", "firecrawl"}:
            await interaction.response.send_message("Unsupported provider. Supported: openai, serp, firecrawl", ephemeral=True)
            return
        
        if global_scope:
            async with self.config.providers() as providers:
                providers.setdefault(provider.lower(), {})["api_key"] = key
        else:
            async with self.config.guild(interaction.guild).providers() as providers:
                providers.setdefault(provider.lower(), {})["api_key"] = key
        
        scope = "global" if global_scope else "guild"
        await interaction.response.send_message(f"Set {provider} API key ({scope}).", ephemeral=True)

    # ----------------
    # Agent Orchestration Commands
    # ----------------
    
    @commands.guild_only()
    @commands.group(name="orchestrate", aliases=["orch"])
    async def orchestrate(self, ctx: commands.Context):
        """Agent tool orchestration commands."""
        if not ctx.invoked_subcommand:
            await self._send_help_embed(ctx, "orchestrate")
    
    @orchestrate.command(name="tools", aliases=["list"])
    async def orchestrate_tools(self, ctx: commands.Context):
        """List available tools for orchestration."""
        try:
            tools = self.orchestrator.get_available_tools(ctx.guild, ctx.author)
            
            if not tools:
                return await ctx.send("No tools available for orchestration.")
            
            embed = discord.Embed(title="Available Orchestration Tools", color=0x00ff00)
            
            by_category = {}
            for tool in tools:
                category = tool.category.title()
                if category not in by_category:
                    by_category[category] = []
                by_category[category].append(tool)
            
            for category, cat_tools in by_category.items():
                tool_list = []
                for tool in cat_tools:
                    admin_mark = " 🔒" if tool.admin_only else ""
                    tool_list.append(f"`{tool.name}`{admin_mark}")
                embed.add_field(name=category, value=" • ".join(tool_list), inline=False)
            
            embed.set_footer(text="🔒 = Admin only")
            await ctx.send(embed=embed)
            
        except Exception as e:
            error_msg = self.error_handler.safe_error_response(e, "tool")
            self.error_handler.log_error(e, "orchestrate_tools")
            await ctx.send(error_msg)
    
    @orchestrate.command(name="schema")
    async def orchestrate_schema(self, ctx: commands.Context, tool_name: Optional[str] = None):
        """Show JSON schema for orchestration tools."""
        try:
            if tool_name:
                # Show specific tool schema
                tools = self.orchestrator.get_available_tools(ctx.guild, ctx.author)
                tool = next((t for t in tools if t.name == tool_name.lower()), None)
                if not tool:
                    return await ctx.send(f"Tool '{tool_name}' not found or not available.")
                
                schema = tool.to_json_schema()
                content = f"```json\n{json.dumps(schema, indent=2)}\n```"
                
                if len(content) > 1900:
                    # Too long, create a file
                    file_content = json.dumps(schema, indent=2)
                    file = discord.File(io.StringIO(file_content), filename=f"{tool_name}_schema.json")
                    await ctx.send(f"Schema for `{tool_name}`:", file=file)
                else:
                    await ctx.send(f"Schema for `{tool_name}`:\n{content}")
            else:
                # Show all tools schema
                schemas = self.orchestrator.get_tools_json_schema(ctx.guild, ctx.author)
                if not schemas:
                    return await ctx.send("No tools available for orchestration.")
                
                file_content = json.dumps(schemas, indent=2)
                file = discord.File(io.StringIO(file_content), filename="orchestration_schemas.json")
                await ctx.send("All available tool schemas:", file=file)
                
        except Exception as e:
            error_msg = self.error_handler.safe_error_response(e, "tool")
            self.error_handler.log_error(e, "orchestrate_schema")
            await ctx.send(error_msg)
    
    @orchestrate.command(name="simulate", aliases=["sim"])
    async def orchestrate_simulate(self, ctx: commands.Context, tool_name: str, *, parameters: str = "{}"):
        """Simulate a tool call for debugging (JSON parameters)."""
        if not await self._user_is_allowed(ctx.guild, ctx.author, "orchestrate_debug"):
            return await ctx.send("You don't have permission to simulate tool calls.")
        
        try:
            # Parse parameters
            try:
                params = json.loads(parameters)
            except json.JSONDecodeError:
                return await ctx.send("Invalid JSON parameters. Example: `{\"query\": \"test search\"}`")
            
            # Simulate the call
            result = self.orchestrator.simulate_tool_call(tool_name, params)
            
            if len(result) > 1900:
                file = discord.File(io.StringIO(result), filename=f"simulation_{tool_name}.json")
                await ctx.send(f"Simulation result for `{tool_name}`:", file=file)
            else:
                await ctx.send(f"Simulation result:\n```json\n{result}\n```")
                
        except Exception as e:
            error_msg = self.error_handler.safe_error_response(e, "tool")
            self.error_handler.log_error(e, "orchestrate_simulate")
            await ctx.send(error_msg)

    # ----------------
    # Utility Methods
    # ----------------
    
    def _mask_key(self, key: str) -> str:
        """Mask sensitive API keys for display."""
        return self.error_handler.redact_secrets(key)

    # Red automatically handles slash command registration for class-level app_commands.Group
    # No manual tree management needed in cog_load/cog_unload
