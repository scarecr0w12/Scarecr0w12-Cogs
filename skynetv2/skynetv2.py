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
from .markdown_utils import ResponseFormatter, DiscordMarkdownFormatter, MarkdownParser
from .memory import MemoryMixin
from .tools import ToolsMixin
from .stats import StatsMixin
from .listener import ListenerMixin
from .orchestration import OrchestrationMixin
from .logging_system import log_config_change, log_error_event, log_ai_request
from .error_handler import ErrorHandler
from .web.server import WebServer  # modular web server


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
        # Initialize web interface
        self.web = WebServer(self)  # replaced legacy WebInterface with modular WebServer

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

        # Get provider configuration (guild overrides global)
        provider_config = {}
        if provider_name in gproviders:
            provider_config = gproviders[provider_name].copy()
        
        # Merge with global config for missing keys
        global_config = global_providers.get(provider_name, {})
        for key, value in global_config.items():
            if key not in provider_config and value is not None:
                provider_config[key] = value

        return provider_name, model, provider_config

    def build_provider(self, provider_name: str, config_data: Dict[str, Any]):
        """Build provider instance from configuration data"""
        if provider_name == "openai":
            api_key = config_data.get("api_key")
            if not api_key:
                raise RuntimeError("Missing API key for OpenAI provider")
            return OpenAIProvider(api_key)
        
        elif provider_name == "anthropic":
            from .api.cloud_providers import AnthropicProvider
            api_key = config_data.get("api_key")
            if not api_key:
                raise RuntimeError("Missing API key for Anthropic provider")
            return AnthropicProvider(api_key)
        
        elif provider_name == "groq":
            from .api.cloud_providers import GroqProvider
            api_key = config_data.get("api_key")
            if not api_key:
                raise RuntimeError("Missing API key for Groq provider")
            return GroqProvider(api_key)
        
        elif provider_name == "gemini":
            from .api.cloud_providers import GeminiProvider
            api_key = config_data.get("api_key")
            if not api_key:
                raise RuntimeError("Missing API key for Gemini provider")
            return GeminiProvider(api_key)
        
        elif provider_name == "ollama":
            from .api.local_providers import OllamaProvider
            base_url = config_data.get("base_url", "http://localhost:11434/v1")
            return OllamaProvider(base_url)
        
        elif provider_name == "lmstudio":
            from .api.local_providers import LMStudioProvider
            base_url = config_data.get("base_url", "http://localhost:1234/v1")
            return LMStudioProvider(base_url)
        
        elif provider_name == "localai":
            from .api.local_providers import LocalAIProvider
            base_url = config_data.get("base_url")
            api_key = config_data.get("api_key", "")
            if not base_url:
                raise RuntimeError("Missing base_url for LocalAI provider")
            return LocalAIProvider(base_url, api_key)
        
        elif provider_name == "vllm":
            from .api.local_providers import VLLMProvider
            base_url = config_data.get("base_url")
            api_key = config_data.get("api_key", "")
            if not base_url:
                raise RuntimeError("Missing base_url for vLLM provider")
            return VLLMProvider(base_url, api_key)
        
        elif provider_name == "text_generation_webui":
            from .api.local_providers import TextGenerationWebUIProvider
            base_url = config_data.get("base_url", "http://localhost:5000/v1")
            return TextGenerationWebUIProvider(base_url)
        
        elif provider_name == "openai_compatible":
            from .api.openai_compatible import OpenAICompatibleProvider
            base_url = config_data.get("base_url")
            api_key = config_data.get("api_key", "")
            if not base_url:
                raise RuntimeError("Missing base_url for OpenAI-compatible provider")
            return OpenAICompatibleProvider(api_key, base_url)
        
        raise RuntimeError(f"Unsupported provider: {provider_name}")

    async def _get_provider(self, provider_name: str):
        """Get a provider instance by name."""
        try:
            # Get global provider config
            global_providers = await self.config.providers()
            provider_config = global_providers.get(provider_name.lower())
            
            if not provider_config:
                return None
                
            return self.build_provider(provider_name.lower(), provider_config)
        except Exception:
            return None

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

    async def _models_cached(self, provider_name: str, provider_config: Dict[str, Any]) -> List[str]:
        # Create cache key from provider config
        config_str = str(sorted(provider_config.items()))
        key = (provider_name, config_str)
        now = int(time.time())
        if key in self._model_cache:
            ts, models = self._model_cache[key]
            if now - ts < self._model_cache_ttl:
                return models
        try:
            provider = self.build_provider(provider_name, provider_config)
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
        provider_name, model, provider_config = await self.resolve_provider_and_model(guild)
        try:
            models = await self._models_cached(provider_name, provider_config)
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

    async def _user_is_allowed(self, guild: discord.Guild, user: discord.Member, permission: str) -> bool:
        """Check if user has a specific permission for special operations."""
        # Bot owner always allowed
        if await self.bot.is_owner(user):
            return True
        
        # Special permissions based on type
        if permission == "orchestrate_debug":
            # Debug permissions require manage_guild permission
            return user.guild_permissions.manage_guild
        
        # Default to no permission for unknown permission types
        return False

    # ----------------
    # Prefix commands
    # ----------------

    @commands.group(name="ai")
    @commands.guild_only()
    @commands.bot_has_permissions(send_messages=True)
    async def ai_group(self, ctx: commands.Context):
        """AI assistant commands."""
        if ctx.invoked_subcommand is None:
            return  # avoid duplicate help spam

    @ai_group.command(name="chat")
    @commands.bot_has_permissions(send_messages=True)
    async def ai_chat(self, ctx: commands.Context, *, message: str):
        err = await self._check_and_record_usage(ctx.guild, ctx.channel, ctx.author)
        if err:
            await ctx.send(err)
            return
        provider_name, model, provider_config = await self.resolve_provider_and_model(ctx.guild)
        if not provider_config:
            error_msg = ResponseFormatter.format_error(
                "Provider Not Configured",
                "An AI provider needs to be set up before using chat commands.",
                f"Use `{ctx.prefix}ai provider key set <provider> <key>` to configure a provider."
            )
            await ctx.send(error_msg)
            return
        try:
            provider = self.build_provider(provider_name, provider_config)
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
            base = await self._memory_build_context(ctx.guild, ctx.channel.id, ctx.author)
            
            # Resolve variables in the message
            resolved_message = await self.resolve_prompt_variables(message, ctx.guild, ctx.channel, ctx.author)
            
            chunks = []
            async for chunk in provider.chat(model=model_name, messages=base + [ChatMessage("user", resolved_message)]):
                chunks.append(chunk)
            text = "".join(chunks) or "(no output)"
            last_usage = getattr(provider, "get_last_usage", lambda: None)()
            
            # Log the AI request with usage data
            tokens_used = last_usage.get('total', 0) if last_usage else 0
            await log_ai_request(ctx.guild, ctx.author, ctx.channel, provider_name, model_name, tokens_used)
            
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
        provider_name, model, provider_config = await self.resolve_provider_and_model(ctx.guild)
        if not provider_config:
            error_msg = ResponseFormatter.format_error(
                "Provider Not Configured", 
                "An AI provider needs to be set up before using chat commands.",
                f"Use `{ctx.prefix}ai provider key set <provider> <key>` to configure a provider."
            )
            await ctx.send(error_msg)
            return
        model_name = model["name"] if isinstance(model, dict) else str(model)
        policy_err = await self._is_model_allowed(ctx.guild, provider_name, model_name)
        if policy_err:
            await ctx.send(policy_err)
            return
        try:
            provider = self.build_provider(provider_name, provider_config)
        except Exception as e:
            await ctx.send(f"Provider error: {e}")
            return
        base = await self._memory_build_context(ctx.guild, ctx.channel.id, ctx.author)
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

    @ai_group.command(name="variables")
    async def ai_variables(self, ctx: commands.Context):
        """Show available variables for prompt injection with enhanced formatting."""
        help_text = self.get_available_variables_help(ctx.guild, ctx.author)
        
        # Use enhanced markdown-aware truncation
        if len(help_text) > 1900:
            truncated = ResponseFormatter.truncate_with_markdown(help_text, 1900)
            await ctx.send(truncated)
        else:
            await ctx.send(help_text)

    @ai_group.command(name="modelinfo", aliases=["model-info"])
    async def ai_model_info(self, ctx: commands.Context, model_name: Optional[str] = None):
        """Show information about model capabilities and supported parameters."""
        try:
            if model_name:
                # Show info for specified model - need to determine provider
                provider_name, current_model_dict, provider_config = await self.resolve_provider_and_model(ctx.guild)
                
                from .model_capabilities import get_parameter_help
                help_text = get_parameter_help(model_name, provider_name)
                await ctx.send(help_text)
            else:
                # Show info for current model
                provider_name, model_dict, provider_config = await self.resolve_provider_and_model(ctx.guild)
                
                # Extract actual model name
                if isinstance(model_dict, dict):
                    current_model = model_dict.get("name", "unknown")
                else:
                    current_model = str(model_dict)
                
                from .model_capabilities import get_parameter_help
                help_text = get_parameter_help(current_model, provider_name)
                
                title = f"**Current Model:** {current_model} ({provider_name})\n\n"
                full_text = title + help_text
                
                await ctx.send(full_text)
        except Exception as e:
            await ctx.send(f"❌ Error getting model information: {e}")

    @ai_group.command(name="refresh-models")
    @checks.admin_or_permissions(manage_guild=True)
    async def ai_refresh_models(self, ctx: commands.Context, provider: Optional[str] = None):
        """Refresh available models from AI providers."""
        try:
            if provider:
                # Refresh specific provider
                await self._refresh_provider_models(provider)
                await ctx.send(f"✅ Refreshed models for {provider}")
            else:
                # Refresh all configured providers
                providers = await self.config.providers()
                refreshed = []
                for provider_name in providers:
                    if provider_name in ["default", "serp", "firecrawl"]:
                        continue  # Skip non-AI providers
                    try:
                        await self._refresh_provider_models(provider_name)
                        refreshed.append(provider_name)
                    except Exception as e:
                        await ctx.send(f"⚠️ Failed to refresh {provider_name}: {e}")
                
                if refreshed:
                    await ctx.send(f"✅ Refreshed models for: {', '.join(refreshed)}")
                else:
                    await ctx.send("❌ No providers were successfully refreshed")
        except Exception as e:
            await ctx.send(f"❌ Error refreshing models: {e}")

    @ai_group.command(name="list-models")
    async def ai_list_models(self, ctx: commands.Context, provider: Optional[str] = None):
        """List available models from AI providers."""
        try:
            if provider:
                # List models for specific provider
                available_models = await self.config.available_models()
                models = available_models.get(provider, [])
                if models:
                    models_text = "\n".join(f"• {model}" for model in models[:20])  # Limit to 20
                    if len(models) > 20:
                        models_text += f"\n... and {len(models) - 20} more"
                    await ctx.send(f"**{provider.title()} Models:**\n{models_text}")
                else:
                    await ctx.send(f"❌ No models found for {provider}. Try refreshing first: `{ctx.clean_prefix}ai refresh-models {provider}`")
            else:
                # List models for all providers
                available_models = await self.config.available_models()
                if not available_models:
                    await ctx.send("❌ No models cached. Try refreshing first: `{ctx.clean_prefix}ai refresh-models`")
                    return
                
                lines = []
                for provider_name, models in available_models.items():
                    if models:
                        count = len(models)
                        sample = models[:3]  # Show first 3 models
                        sample_text = ", ".join(sample)
                        if count > 3:
                            sample_text += f", ... ({count - 3} more)"
                        lines.append(f"**{provider_name.title()}:** {sample_text}")
                
                if lines:
                    models_text = "\n".join(lines)
                    await ctx.send(f"**Available Models:**\n{models_text}\n\n💡 Use `{ctx.clean_prefix}ai list-models <provider>` for full list")
                else:
                    await ctx.send("❌ No models found. Try refreshing first: `{ctx.clean_prefix}ai refresh-models`")
        except Exception as e:
            await ctx.send(f"❌ Error listing models: {e}")

    async def _refresh_provider_models(self, provider_name: str) -> None:
        """Refresh models for a specific provider."""
        try:
            # Get provider instance
            provider_obj = await self._get_provider(provider_name)
            if provider_obj is None:
                raise ValueError(f"Provider {provider_name} not configured or unavailable")
            
            # Get available models
            models = await provider_obj.list_models()
            
            # Store in config
            available_models = await self.config.available_models()
            available_models[provider_name] = models
            await self.config.available_models.set(available_models)
            
            # Update timestamp
            models_last_updated = await self.config.models_last_updated()
            models_last_updated[provider_name] = int(time.time())
            await self.config.models_last_updated.set(models_last_updated)
            
        except Exception as e:
            raise Exception(f"Failed to refresh models for {provider_name}: {e}")

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
        if ctx.invoked_subcommand is None:
            return

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
        if ctx.invoked_subcommand is None:
            return

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
        if ctx.invoked_subcommand is None:
            return

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
        if ctx.invoked_subcommand is None:
            return

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
        if ctx.invoked_subcommand is None:
            return

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
        if ctx.invoked_subcommand is None:
            return

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
    channel_group = app_commands.Group(name="channel", description="Per-channel AI listening configuration", parent=ai_slash)

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
        provider_name, model, provider_config = await self.resolve_provider_and_model(interaction.guild)
        if not provider_config:
            await interaction.response.send_message("Provider not configured. Ask an admin to set one.", ephemeral=True)
            return
        try:
            provider = self.build_provider(provider_name, provider_config)
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
        base = await self._memory_build_context(interaction.guild, interaction.channel.id, interaction.user)
        
        # Resolve variables in the message
        resolved_message = await self.resolve_prompt_variables(message, interaction.guild, interaction.channel, interaction.user)
        
        if stream:
            await interaction.response.defer(thinking=True)
            msg = await interaction.followup.send("…")
            buf = ""
            last_edit = 0.0
            try:
                async for chunk in provider.chat(model=model_name, messages=base + [ChatMessage("user", resolved_message)], stream=True):
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
            await self._memory_remember(interaction.guild, interaction.channel.id, resolved_message, buf)
            return
        await interaction.response.defer(thinking=True)
        chunks = []
        async for chunk in provider.chat(model=model_name, messages=base + [ChatMessage("user", resolved_message)]):
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
        await self._memory_remember(interaction.guild, interaction.channel.id, resolved_message, text)
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

    @ai_slash.command(name="variables", description="Show available variables for prompt injection")
    async def slash_variables(self, interaction: discord.Interaction):
        """Show available variables for prompt injection."""
        help_text = self.get_available_variables_help(interaction.guild, interaction.user)
        # Discord interaction responses have stricter limits, so we need to chunk more aggressively
        if len(help_text) > 1800:
            parts = help_text.split('\n\n')
            current_chunk = ""
            await interaction.response.send_message(f"**Variables Help (Part 1):**", ephemeral=True)
            for i, part in enumerate(parts):
                if len(current_chunk + part) > 1800:
                    if current_chunk:
                        await interaction.followup.send(current_chunk, ephemeral=True)
                    current_chunk = part + '\n\n'
                else:
                    current_chunk += part + '\n\n'
            if current_chunk:
                await interaction.followup.send(current_chunk, ephemeral=True)
        else:
            await interaction.response.send_message(help_text, ephemeral=True)

    @ai_slash.command(name="modelinfo", description="Show model capabilities and parameter constraints")
    @app_commands.describe(model_name="Specific model to check (optional, defaults to current model)")
    async def slash_model_info(self, interaction: discord.Interaction, model_name: Optional[str] = None):
        """Show information about model capabilities and supported parameters."""
        try:
            if model_name:
                # Show info for specified model - need to determine provider
                provider_name, current_model_dict, provider_config = await self.resolve_provider_and_model(interaction.guild)
                
                from .model_capabilities import get_parameter_help
                help_text = get_parameter_help(model_name, provider_name)
                await interaction.response.send_message(help_text, ephemeral=True)
            else:
                # Show info for current model
                provider_name, model_dict, provider_config = await self.resolve_provider_and_model(interaction.guild)
                
                # Extract actual model name
                if isinstance(model_dict, dict):
                    current_model = model_dict.get("name", "unknown")
                else:
                    current_model = str(model_dict)
                
                from .model_capabilities import get_parameter_help
                help_text = get_parameter_help(current_model, provider_name)
                
                title = f"**Current Model:** {current_model} ({provider_name})\n\n"
                full_text = title + help_text
                
                await interaction.response.send_message(full_text, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error getting model information: {e}", ephemeral=True)

    @provider_group.command(name="refresh-models", description="Refresh available models from AI providers")
    @app_commands.describe(provider="Specific provider to refresh (leave empty for all)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def slash_refresh_models(self, interaction: discord.Interaction, provider: Optional[str] = None):
        """Refresh available models from AI providers."""
        await interaction.response.defer(ephemeral=True)
        try:
            if provider:
                # Refresh specific provider
                await self._refresh_provider_models(provider)
                await interaction.followup.send(f"✅ Refreshed models for {provider}")
            else:
                # Refresh all configured providers
                providers = await self.config.providers()
                refreshed = []
                for provider_name in providers:
                    if provider_name in ["default", "serp", "firecrawl"]:
                        continue  # Skip non-AI providers
                    try:
                        await self._refresh_provider_models(provider_name)
                        refreshed.append(provider_name)
                    except Exception as e:
                        await interaction.followup.send(f"⚠️ Failed to refresh {provider_name}: {e}")
                
                if refreshed:
                    await interaction.followup.send(f"✅ Refreshed models for: {', '.join(refreshed)}")
                else:
                    await interaction.followup.send("❌ No providers were successfully refreshed")
        except Exception as e:
            await interaction.followup.send(f"❌ Error refreshing models: {e}")

    @provider_group.command(name="list-models", description="List available models from AI providers")
    @app_commands.describe(provider="Specific provider to list models for")
    async def slash_list_models(self, interaction: discord.Interaction, provider: Optional[str] = None):
        """List available models from AI providers."""
        try:
            if provider:
                # List models for specific provider
                available_models = await self.config.available_models()
                models = available_models.get(provider, [])
                if models:
                    models_text = "\n".join(f"• {model}" for model in models[:20])  # Limit to 20
                    if len(models) > 20:
                        models_text += f"\n... and {len(models) - 20} more"
                    await interaction.response.send_message(f"**{provider.title()} Models:**\n{models_text}", ephemeral=True)
                else:
                    await interaction.response.send_message(f"❌ No models found for {provider}. Try refreshing first with `/skynet provider refresh-models {provider}`", ephemeral=True)
            else:
                # List models for all providers
                available_models = await self.config.available_models()
                if not available_models:
                    await interaction.response.send_message("❌ No models cached. Try refreshing first with `/skynet provider refresh-models`", ephemeral=True)
                    return
                
                lines = []
                for provider_name, models in available_models.items():
                    if models:
                        count = len(models)
                        sample = models[:3]  # Show first 3 models
                        sample_text = ", ".join(sample)
                        if count > 3:
                            sample_text += f", ... ({count - 3} more)"
                        lines.append(f"**{provider_name.title()}:** {sample_text}")
                
                if lines:
                    models_text = "\n".join(lines)
                    await interaction.response.send_message(f"**Available Models:**\n{models_text}\n\n💡 Use `/skynet provider list-models <provider>` for full list", ephemeral=True)
                else:
                    await interaction.response.send_message("❌ No models found. Try refreshing first with `/skynet provider refresh-models`", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error listing models: {e}", ephemeral=True)

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
        if ctx.invoked_subcommand is None:
            return

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
        if ctx.invoked_subcommand is None:
            return

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
        if ctx.invoked_subcommand is None:
            return

    @ai_provider.group(name="key")
    async def ai_provider_key(self, ctx: commands.Context):
        """Manage provider API keys."""
        if ctx.invoked_subcommand is None:
            return

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
        
        # Log the configuration change
        await log_config_change(
            ctx.guild if not is_global else None, 
            ctx.author, 
            ctx.channel,
            f"API key set for {provider} ({scope})",
            {"provider": provider.lower(), "scope": scope}
        )

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
        
        # Log the configuration change
        await log_config_change(
            interaction.guild if not global_scope else None, 
            interaction.user, 
            interaction.channel,
            f"API key set for {provider} ({scope})",
            {"provider": provider.lower(), "scope": scope}
        )

    # ----------------
    # Channel Listening Slash Commands
    # ----------------

    @channel_group.command(name="listening_enable", description="Enable AI listening in a channel")
    @app_commands.describe(channel="Channel to enable (default: current channel)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def slash_channel_listening_enable(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        if interaction.guild is None:
            await interaction.response.send_message(ResponseFormatter.format_error(
                "Guild Not Found", 
                "This command must be used within a server.",
                "Please run this command from a channel in the server you want to configure."
            ), ephemeral=True)
            return
        
        target_channel: discord.TextChannel
        if channel is None:
            if not isinstance(interaction.channel, discord.TextChannel):
                await interaction.response.send_message("❌ This command must be used in a text channel or specify a channel.", ephemeral=True)
                return
            target_channel = interaction.channel
        else:
            target_channel = channel
        
        guild = interaction.guild
        channel_id = str(target_channel.id)
        
        async with self.config.guild(guild).channel_listening() as channel_listening:
            if channel_id not in channel_listening:
                channel_listening[channel_id] = {}
            channel_listening[channel_id]['enabled'] = True
            # Set default mode if not already configured
            if 'mode' not in channel_listening[channel_id]:
                channel_listening[channel_id]['mode'] = 'mention'
        
        await interaction.response.send_message(f"✅ AI listening enabled in {target_channel.mention}")

    @channel_group.command(name="listening_disable", description="Disable AI listening in a channel")
    @app_commands.describe(channel="Channel to disable (default: current channel)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def slash_channel_listening_disable(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        if interaction.guild is None:
            await interaction.response.send_message(ResponseFormatter.format_error(
                "Guild Not Found", 
                "This command must be used within a server.",
                "Please run this command from a channel in the server you want to configure."
            ), ephemeral=True)
            return
        
        target_channel: discord.TextChannel
        if channel is None:
            if not isinstance(interaction.channel, discord.TextChannel):
                await interaction.response.send_message("❌ This command must be used in a text channel or specify a channel.", ephemeral=True)
                return
            target_channel = interaction.channel
        else:
            target_channel = channel
        
        guild = interaction.guild
        channel_id = str(target_channel.id)
        
        async with self.config.guild(guild).channel_listening() as channel_listening:
            if channel_id not in channel_listening:
                channel_listening[channel_id] = {}
            channel_listening[channel_id]['enabled'] = False
        
        await interaction.response.send_message(f"❌ AI listening disabled in {target_channel.mention}")

    @channel_group.command(name="mode_set", description="Set listening mode for a channel")
    @app_commands.describe(mode="Listening mode", channel="Channel to configure (default: current channel)")
    @app_commands.choices(mode=[
        app_commands.Choice(name="Mention Only", value="mention"),
        app_commands.Choice(name="Keywords", value="keyword"), 
        app_commands.Choice(name="All Messages", value="all")
    ])
    @app_commands.checks.has_permissions(manage_guild=True)
    async def slash_channel_mode_set(self, interaction: discord.Interaction, mode: str, channel: Optional[discord.TextChannel] = None):
        assert interaction.guild is not None
        
        target_channel: discord.TextChannel
        if channel is None:
            if not isinstance(interaction.channel, discord.TextChannel):
                await interaction.response.send_message("❌ This command must be used in a text channel or specify a channel.", ephemeral=True)
                return
            target_channel = interaction.channel
        else:
            target_channel = channel
        
        guild = interaction.guild
        channel_id = str(target_channel.id)
        
        async with self.config.guild(guild).channel_listening() as channel_listening:
            if channel_id not in channel_listening:
                channel_listening[channel_id] = {}
            channel_listening[channel_id]['mode'] = mode.lower()
            # Enable if not already enabled
            if not channel_listening[channel_id].get('enabled', False):
                channel_listening[channel_id]['enabled'] = True
        
        mode_descriptions = {
            'mention': 'Only respond when bot is mentioned',
            'keyword': 'Respond to messages containing configured keywords',
            'all': 'Respond to all messages in the channel'
        }
        
        await interaction.response.send_message(f"✅ Set listening mode for {target_channel.mention} to `{mode.lower()}`\n"
                                              f"📋 {mode_descriptions[mode.lower()]}")

    @channel_group.command(name="keywords_set", description="Set keywords for channel listening")
    @app_commands.describe(keywords="Comma-separated keywords", channel="Channel to configure (default: current channel)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def slash_channel_keywords_set(self, interaction: discord.Interaction, keywords: str, channel: Optional[discord.TextChannel] = None):
        assert interaction.guild is not None
        
        target_channel: discord.TextChannel
        if channel is None:
            if not isinstance(interaction.channel, discord.TextChannel):
                await interaction.response.send_message("❌ This command must be used in a text channel or specify a channel.", ephemeral=True)
                return
            target_channel = interaction.channel
        else:
            target_channel = channel
        
        guild = interaction.guild
        channel_id = str(target_channel.id)
        
        # Parse keywords
        keyword_list = [k.strip().lower() for k in keywords.split(',') if k.strip()]
        if not keyword_list:
            await interaction.response.send_message("❌ Please provide at least one keyword.", ephemeral=True)
            return
        
        async with self.config.guild(guild).channel_listening() as channel_listening:
            if channel_id not in channel_listening:
                channel_listening[channel_id] = {}
            channel_listening[channel_id]['keywords'] = keyword_list
            # Set mode to keyword if not already configured
            if 'mode' not in channel_listening[channel_id]:
                channel_listening[channel_id]['mode'] = 'keyword'
            # Enable if not already enabled
            if not channel_listening[channel_id].get('enabled', False):
                channel_listening[channel_id]['enabled'] = True
        
        await interaction.response.send_message(f"✅ Set keywords for {target_channel.mention}: `{', '.join(keyword_list)}`\n"
                                              f"💡 Mode automatically set to `keyword`")

    @channel_group.command(name="status", description="Show channel listening configuration")
    @app_commands.describe(channel="Channel to check (default: current channel)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def slash_channel_status(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        assert interaction.guild is not None
        
        target_channel: discord.TextChannel
        if channel is None:
            if not isinstance(interaction.channel, discord.TextChannel):
                await interaction.response.send_message("❌ This command must be used in a text channel or specify a channel.", ephemeral=True)
                return
            target_channel = interaction.channel
        else:
            target_channel = channel
        
        guild = interaction.guild
        channel_id = str(target_channel.id)
        
        # Get channel-specific config
        channel_listening = await self.config.guild(guild).channel_listening()
        channel_config = channel_listening.get(channel_id, {})
        
        # Get global config as fallback
        global_listening = await self.config.guild(guild).listening()
        
        # Determine effective configuration
        enabled = channel_config.get('enabled')
        if enabled is None:
            enabled = global_listening.get('enabled', False)
            source = "global default"
        else:
            source = "channel override"
        
        mode = channel_config.get('mode') or global_listening.get('mode', 'mention')
        keywords = channel_config.get('keywords') or global_listening.get('keywords', [])
        
        embed = discord.Embed(
            title=f"🎧 Channel Listening Status",
            description=f"Configuration for {target_channel.mention}",
            color=0x00FF00 if enabled else 0xFF0000
        )
        
        embed.add_field(
            name="📡 Status",
            value=f"{'✅ Enabled' if enabled else '❌ Disabled'} ({source})",
            inline=True
        )
        
        embed.add_field(
            name="🎯 Mode",
            value=f"`{mode}`",
            inline=True
        )
        
        if mode == 'keyword' and keywords:
            embed.add_field(
                name="🔑 Keywords",
                value=f"`{', '.join(keywords)}`",
                inline=False
            )
        elif mode == 'keyword':
            embed.add_field(
                name="🔑 Keywords",
                value="*None configured*",
                inline=False
            )
        
        embed.add_field(
            name="📋 Mode Descriptions",
            value="• `mention`: Only respond when bot is mentioned\n"
                  "• `keyword`: Respond to messages with keywords\n"
                  "• `all`: Respond to all messages",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed)

    # ----------------
    # Agent Orchestration Commands
    # ----------------
    
    @commands.guild_only()
    @commands.group(name="orchestrate", aliases=["orch"])
    async def orchestrate(self, ctx: commands.Context):
        """Agent tool orchestration commands."""
        if not ctx.invoked_subcommand:
            await ctx.send_help()
    
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

    # ----------------
    # Channel Listening Commands
    # ----------------

    @ai_group.group(name="channel")
    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    async def ai_channel(self, ctx: commands.Context):
        """Per-channel AI listening configuration."""
        if ctx.invoked_subcommand is None:
            return  # avoid duplicate help spam

    @ai_channel.group(name="listening")
    async def ai_channel_listening(self, ctx: commands.Context):
        """Channel-specific listening configuration."""
        if ctx.invoked_subcommand is None:
            return

    @ai_channel_listening.command(name="enable")
    async def ai_channel_listening_enable(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """Enable AI listening in a specific channel."""
        if ctx.guild is None:
            await ctx.send(ResponseFormatter.format_error(
                "Guild Not Found", 
                "This command must be used within a server.",
                "Please run this command from a channel in the server you want to configure."
            ))
            return
            
        if channel is None:
            channel = ctx.channel
        
        guild = ctx.guild
        channel_id = str(channel.id)
        
        async with self.config.guild(guild).channel_listening() as channel_listening:
            if channel_id not in channel_listening:
                channel_listening[channel_id] = {}
            channel_listening[channel_id]['enabled'] = True
            # Set default mode if not already configured
            if 'mode' not in channel_listening[channel_id]:
                channel_listening[channel_id]['mode'] = 'mention'
        
        await ctx.send(f"✅ AI listening enabled in {channel.mention}")

    @ai_channel_listening.command(name="disable")
    async def ai_channel_listening_disable(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """Disable AI listening in a specific channel."""
        if ctx.guild is None:
            await ctx.send(ResponseFormatter.format_error(
                "Guild Not Found", 
                "This command must be used within a server.",
                "Please run this command from a channel in the server you want to configure."
            ))
            return
            
        if channel is None:
            channel = ctx.channel
        
        guild = ctx.guild
        channel_id = str(channel.id)
        
        async with self.config.guild(guild).channel_listening() as channel_listening:
            if channel_id not in channel_listening:
                channel_listening[channel_id] = {}
            channel_listening[channel_id]['enabled'] = False
        
        await ctx.send(f"❌ AI listening disabled in {channel.mention}")

    @ai_channel.group(name="mode")
    async def ai_channel_mode(self, ctx: commands.Context):
        """Channel listening mode configuration."""
        if ctx.invoked_subcommand is None:
            return

    @ai_channel_mode.command(name="set")
    async def ai_channel_mode_set(self, ctx: commands.Context, mode: str, channel: discord.TextChannel = None):
        """Set listening mode for a channel (mention, keyword, all)."""
        if ctx.guild is None:
            await ctx.send(ResponseFormatter.format_error(
                "Guild Not Found", 
                "This command must be used within a server.",
                "Please run this command from a channel in the server you want to configure."
            ))
            return
            
        if channel is None:
            channel = ctx.channel
        
        if mode.lower() not in ['mention', 'keyword', 'all']:
            await ctx.send("❌ Mode must be one of: `mention`, `keyword`, `all`")
            return
        
        guild = ctx.guild
        channel_id = str(channel.id)
        
        async with self.config.guild(guild).channel_listening() as channel_listening:
            if channel_id not in channel_listening:
                channel_listening[channel_id] = {}
            channel_listening[channel_id]['mode'] = mode.lower()
            # Enable if not already enabled
            if not channel_listening[channel_id].get('enabled', False):
                channel_listening[channel_id]['enabled'] = True
        
        mode_descriptions = {
            'mention': 'Only respond when bot is mentioned',
            'keyword': 'Respond to messages containing configured keywords',
            'all': 'Respond to all messages in the channel'
        }
        
        await ctx.send(f"✅ Set listening mode for {channel.mention} to `{mode.lower()}`\n"
                      f"📋 {mode_descriptions[mode.lower()]}")

    @ai_channel.group(name="keywords")
    async def ai_channel_keywords(self, ctx: commands.Context):
        """Channel keyword configuration."""
        if ctx.invoked_subcommand is None:
            return

    @ai_channel_keywords.command(name="set")
    async def ai_channel_keywords_set(self, ctx: commands.Context, keywords: str, channel: discord.TextChannel = None):
        """Set keywords for channel listening (comma-separated)."""
        if ctx.guild is None:
            await ctx.send(ResponseFormatter.format_error(
                "Guild Not Found", 
                "This command must be used within a server.",
                "Please run this command from a channel in the server you want to configure."
            ))
            return
            
        if channel is None:
            channel = ctx.channel
        
        guild = ctx.guild
        channel_id = str(channel.id)
        
        # Parse keywords
        keyword_list = [k.strip().lower() for k in keywords.split(',') if k.strip()]
        if not keyword_list:
            await ctx.send("❌ Please provide at least one keyword.")
            return
        
        async with self.config.guild(guild).channel_listening() as channel_listening:
            if channel_id not in channel_listening:
                channel_listening[channel_id] = {}
            channel_listening[channel_id]['keywords'] = keyword_list
            # Set mode to keyword if not already configured
            if 'mode' not in channel_listening[channel_id]:
                channel_listening[channel_id]['mode'] = 'keyword'
            # Enable if not already enabled
            if not channel_listening[channel_id].get('enabled', False):
                channel_listening[channel_id]['enabled'] = True
        
        await ctx.send(f"✅ Set keywords for {channel.mention}: `{', '.join(keyword_list)}`\n"
                      f"💡 Mode automatically set to `keyword`")

    @ai_channel_keywords.command(name="show")
    async def ai_channel_keywords_show(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """Show current keywords for a channel."""
        if ctx.guild is None:
            await ctx.send(ResponseFormatter.format_error(
                "Guild Not Found", 
                "This command must be used within a server.",
                "Please run this command from a channel in the server you want to configure."
            ))
            return
            
        if channel is None:
            channel = ctx.channel
        
        guild = ctx.guild
        channel_id = str(channel.id)
        
        channel_listening = await self.config.guild(guild).channel_listening()
        channel_config = channel_listening.get(channel_id, {})
        keywords = channel_config.get('keywords', [])
        
        if keywords:
            await ctx.send(f"📋 Keywords for {channel.mention}: `{', '.join(keywords)}`")
        else:
            await ctx.send(f"❌ No keywords configured for {channel.mention}")

    @ai_channel.command(name="status")
    async def ai_channel_status(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """Show current channel listening configuration."""
        if ctx.guild is None:
            await ctx.send(ResponseFormatter.format_error(
                "Guild Not Found", 
                "This command must be used within a server.",
                "Please run this command from a channel in the server you want to configure."
            ))
            return
            
        if channel is None:
            channel = ctx.channel
        
        guild = ctx.guild
        channel_id = str(channel.id)
        
        # Get channel-specific config
        channel_listening = await self.config.guild(guild).channel_listening()
        channel_config = channel_listening.get(channel_id, {})
        
        # Get global config as fallback
        global_listening = await self.config.guild(guild).listening()
        
        # Determine effective configuration
        enabled = channel_config.get('enabled')
        if enabled is None:
            enabled = global_listening.get('enabled', False)
            source = "global default"
        else:
            source = "channel override"
        
        mode = channel_config.get('mode') or global_listening.get('mode', 'mention')
        keywords = channel_config.get('keywords') or global_listening.get('keywords', [])
        
        embed = discord.Embed(
            title=f"🎧 Channel Listening Status",
            description=f"Configuration for {channel.mention}",
            color=0x00FF00 if enabled else 0xFF0000
        )
        
        embed.add_field(
            name="📡 Status",
            value=f"{'✅ Enabled' if enabled else '❌ Disabled'} ({source})",
            inline=True
        )
        
        embed.add_field(
            name="🎯 Mode",
            value=f"`{mode}`",
            inline=True
        )
        
        if mode == 'keyword' and keywords:
            embed.add_field(
                name="🔑 Keywords",
                value=f"`{', '.join(keywords)}`",
                inline=False
            )
        elif mode == 'keyword':
            embed.add_field(
                name="🔑 Keywords",
                value="*None configured*",
                inline=False
            )
        
        embed.add_field(
            name="📋 Mode Descriptions",
            value="• `mention`: Only respond when bot is mentioned\n"
                  "• `keyword`: Respond to messages with keywords\n"
                  "• `all`: Respond to all messages",
            inline=False
        )
        
        # Add provider status
        try:
            provider_name, model, provider_config = await self.resolve_provider_and_model(guild)
            if provider_config:
                embed.add_field(
                    name="🤖 AI Provider Status",
                    value=f"**Provider:** {provider_name}\n**Model:** {model.get('name') if isinstance(model, dict) else model}\n**Status:** ✅ Ready",
                    inline=False
                )
            else:
                embed.add_field(
                    name="🤖 AI Provider Status", 
                    value="**Status:** ❌ No provider configured\nRun `[p]ai provider key set <provider> <key>` to configure.",
                    inline=False
                )
        except Exception as e:
            embed.add_field(
                name="🤖 AI Provider Status",
                value=f"**Status:** ❌ Error: {str(e)}\nCheck your provider configuration.",
                inline=False
            )
        
        # Add quick troubleshooting
        embed.add_field(
            name="🔧 Quick Actions",
            value=f"• Test listening: `{ctx.prefix}ai channel test`\n"
                  f"• Enable: `{ctx.prefix}ai channel listening enable`\n"
                  f"• Set to 'all': `{ctx.prefix}ai channel mode set all`\n"
                  f"• Check providers: `{ctx.prefix}ai model list`",
            inline=False
        )

        await ctx.send(embed=embed)

    @ai_channel.command(name="test")
    async def ai_channel_test(self, ctx: commands.Context, *, test_message: str = "Hello, can you hear me?"):
        """Test if the listening system would respond to a message in this channel."""
        if ctx.guild is None:
            await ctx.send(ResponseFormatter.format_error(
                "Guild Not Found", 
                "This command must be used within a server.",
                "Please run this command from a channel in the server you want to test."
            ))
            return
        
        channel = ctx.channel
        guild = ctx.guild
        
        # Test the should_respond_to_message logic
        channel_id = str(channel.id)
        channel_listening = await self.config.guild(guild).channel_listening()
        channel_config = channel_listening.get(channel_id, {})
        
        # Get global config as fallback
        global_listening = await self.config.guild(guild).listening()
        
        # Determine if listening is enabled
        enabled = channel_config.get('enabled')
        if enabled is None:
            enabled = global_listening.get('enabled', False)
            config_source = "global default"
        else:
            config_source = "channel override"
        
        if not enabled:
            embed = discord.Embed(
                title="🔇 Test Result: Would NOT Respond",
                description=f"Listening is disabled ({config_source})",
                color=0xFF0000
            )
            embed.add_field(name="Test Message", value=f"`{test_message}`", inline=False)
            embed.add_field(name="Solution", value=f"Run `{ctx.prefix}ai channel listening enable` to enable listening", inline=False)
            await ctx.send(embed=embed)
            return
        
        # Check mode and determine if it would trigger
        mode = channel_config.get('mode') or global_listening.get('mode', 'mention')
        keywords = channel_config.get('keywords') or global_listening.get('keywords', [])
        
        would_trigger = False
        trigger_reason = ""
        
        if mode == 'all':
            would_trigger = True
            trigger_reason = "Mode is set to 'all'"
        elif mode == 'mention':
            # Check if bot would be mentioned (simplified check)
            bot_mentioned = f'<@{ctx.bot.user.id}>' in test_message or f'<@!{ctx.bot.user.id}>' in test_message
            if bot_mentioned:
                would_trigger = True
                trigger_reason = "Bot is mentioned in message"
            else:
                trigger_reason = "Bot is not mentioned in message"
        elif mode == 'keyword':
            if keywords:
                found_keywords = [kw for kw in keywords if kw.lower() in test_message.lower()]
                if found_keywords:
                    would_trigger = True
                    trigger_reason = f"Found keywords: {', '.join(found_keywords)}"
                else:
                    trigger_reason = f"No keywords found (looking for: {', '.join(keywords)})"
            else:
                trigger_reason = "No keywords configured"
        
        # Check provider status
        provider_status = "Unknown"
        try:
            provider_name, model, provider_config = await self.resolve_provider_and_model(guild)
            if provider_config:
                provider_status = f"✅ {provider_name} with {model.get('name') if isinstance(model, dict) else model}"
            else:
                provider_status = "❌ No provider configured"
                would_trigger = False  # Can't respond without provider
                trigger_reason += " (Also: No AI provider configured)"
        except Exception as e:
            provider_status = f"❌ Provider error: {str(e)}"
            would_trigger = False
            trigger_reason += f" (Also: Provider error: {str(e)})"
        
        # Build result embed
        color = 0x00FF00 if would_trigger else 0xFF0000
        title = "🎤 Test Result: Would RESPOND" if would_trigger else "🔇 Test Result: Would NOT Respond"
        
        embed = discord.Embed(title=title, color=color)
        embed.add_field(name="Test Message", value=f"`{test_message}`", inline=False)
        embed.add_field(name="Configuration", value=f"**Enabled:** {enabled} ({config_source})\n**Mode:** {mode}", inline=False)
        embed.add_field(name="Trigger Logic", value=trigger_reason, inline=False)
        embed.add_field(name="AI Provider", value=provider_status, inline=False)
        
        if not would_trigger:
            solutions = []
            if not enabled:
                solutions.append(f"• Enable listening: `{ctx.prefix}ai channel listening enable`")
            if mode == 'mention' and 'not mentioned' in trigger_reason:
                solutions.append(f"• Switch to 'all' mode: `{ctx.prefix}ai channel mode set all`")
                solutions.append(f"• Or mention the bot: `@{ctx.bot.user.name} {test_message}`")
            if mode == 'keyword' and 'No keywords found' in trigger_reason:
                solutions.append(f"• Add keywords: `{ctx.prefix}ai channel keywords add <keyword>`")
                solutions.append(f"• Or switch to 'all' mode: `{ctx.prefix}ai channel mode set all`")
            if 'No provider' in provider_status:
                solutions.append(f"• Configure AI: `{ctx.prefix}ai provider key set openai <your-key>`")
            
            if solutions:
                embed.add_field(name="💡 Suggested Solutions", value="\n".join(solutions), inline=False)
        
        await ctx.send(embed=embed)

    # ----------------
    # Web Interface Commands
    # ----------------

    @ai_group.group(name="web")
    @checks.admin_or_permissions(manage_guild=True)
    async def ai_web(self, ctx: commands.Context):
        """Web interface management commands."""
        if ctx.invoked_subcommand is None:
            return  # avoid duplicate help spam

    @ai_web.group(name="token")
    async def ai_web_token(self, ctx: commands.Context):
        """Manage legacy web interface authentication tokens (deprecated).
        
        OAuth2 web login has replaced token auth. These commands are retained for
        backwards compatibility and will be removed in a future release.
        """
        if ctx.invoked_subcommand is None:
            return

    @ai_web_token.command(name="generate")
    async def ai_web_token_generate(self, ctx: commands.Context, hours: Optional[int] = 24):
        """Generate a new web access token. Default expiry: 24 hours."""
        if hours is None:
            hours = 24
            
        if not 1 <= hours <= 168:  # Max 1 week
            await ctx.send("Token expiry must be between 1 and 168 hours (1 week).")
            return

        import secrets
        token = secrets.token_urlsafe(32)
        expires = time.time() + (hours * 3600)

        async with self.config.guild(ctx.guild).web_tokens() as tokens:
            tokens[token] = {
                'created_by': ctx.author.id,
                'created_at': time.time(),
                'expires': expires
            }

        port = getattr(self.web, 'port', 8080)
        url = f"http://localhost:{port}/status/{ctx.guild.id}?token={token}"
        
        await ctx.author.send(f"""**SkynetV2 Web Access Token Generated**

🔗 **URL**: {url}
🕒 **Expires**: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(expires))}
🛡️ **Security**: This token grants read-only access to your guild's SkynetV2 status and configuration.

⚠️ **Keep this URL private!** Anyone with this URL can view your guild's AI usage statistics and configuration.

The web interface is currently accessible only from localhost for security reasons.""")
        
        await ctx.tick()

    @ai_web_token.command(name="list")
    async def ai_web_token_list(self, ctx: commands.Context):
        """List active web tokens for this guild."""
        tokens = await self.config.guild(ctx.guild).web_tokens()
        
        if not tokens:
            await ctx.send("No active web tokens for this guild.")
            return
            
        lines = []
        now = time.time()
        
        for token, data in tokens.items():
            created_by = ctx.guild.get_member(data.get('created_by', 0))
            created_by_name = created_by.display_name if created_by else "Unknown"
            
            expires = data.get('expires', 0)
            if expires > now:
                expires_str = time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(expires))
                lines.append(f"• Token {token[:8]}*** - Created by {created_by_name} - Expires: {expires_str}")
            else:
                lines.append(f"• Token {token[:8]}*** - EXPIRED")
        
        if lines:
            await ctx.send(box("\n".join(lines), "yaml"))
        else:
            await ctx.send("No active tokens found.")

    @ai_web_token.command(name="revoke")
    async def ai_web_token_revoke(self, ctx: commands.Context, token_prefix: str):
        """Revoke a web token by its prefix (first 8 characters)."""
        async with self.config.guild(ctx.guild).web_tokens() as tokens:
            found_token = None
            for token in tokens:
                if token.startswith(token_prefix):
                    found_token = token
                    break
                    
            if found_token:
                del tokens[found_token]
                await ctx.send(f"Revoked token {token_prefix}***")
            else:
                await ctx.send(f"No token found with prefix {token_prefix}")

    @ai_web_token.command(name="cleanup")
    async def ai_web_token_cleanup(self, ctx: commands.Context):
        """Remove all expired tokens."""
        async with self.config.guild(ctx.guild).web_tokens() as tokens:
            now = time.time()
            expired_tokens = [
                token for token, data in tokens.items() 
                if data.get('expires', 0) <= now
            ]
            
            for token in expired_tokens:
                del tokens[token]
                
        if expired_tokens:
            await ctx.send(f"Cleaned up {len(expired_tokens)} expired token(s).")
        else:
            await ctx.send("No expired tokens found.")

    @ai_web.command(name="status")
    async def ai_web_status(self, ctx: commands.Context):
        """Show web interface status."""
        if self.web and self.web.app:
            port = getattr(self.web, 'port', 8080)
            await ctx.send(f"Web interface is running on http://localhost:{port}")
        else:
            await ctx.send("Web interface is not running.")

    @ai_web.group(name="config")
    @checks.is_owner()
    async def ai_web_config(self, ctx: commands.Context):
        """Configure OAuth2 web interface (bot owner only)."""
        if ctx.invoked_subcommand is None:
            return

    @ai_web_config.command(name="oauth")
    async def ai_web_config_oauth(self, ctx: commands.Context):
        """Set Discord OAuth2 application credentials via modal.
        
        Create a Discord application at https://discord.com/developers/applications
        Set the redirect URI to: your_domain/callback
        """
        # Create modal for OAuth2 configuration
        class OAuth2ConfigModal(discord.ui.Modal):
            def __init__(self):
                super().__init__(title="Discord OAuth2 Configuration", timeout=300.0)
                
            client_id = discord.ui.TextInput(
                label="Discord Client ID",
                placeholder="Your Discord application's Client ID",
                min_length=10,
                max_length=25,
                required=True
            )
            
            client_secret = discord.ui.TextInput(
                label="Discord Client Secret", 
                placeholder="Your Discord application's Client Secret",
                min_length=10,
                max_length=50,
                required=True
            )
            
            async def on_submit(self, interaction: discord.Interaction):
                # Validate inputs
                if len(self.client_id.value) < 10 or len(self.client_secret.value) < 10:
                    await interaction.response.send_message(
                        "❌ Invalid client ID or secret. Please check your Discord application settings.",
                        ephemeral=True
                    )
                    return
                    
                # Get the cog instance
                cog = interaction.client.get_cog("SkynetV2")
                if not cog:
                    await interaction.response.send_message(
                        "❌ Could not access cog configuration.",
                        ephemeral=True
                    )
                    return
                    
                # Save configuration
                await cog.config.oauth2.set({
                    "client_id": self.client_id.value.strip(),
                    "client_secret": self.client_secret.value.strip()
                })
                
                await interaction.response.send_message(
                    "✅ OAuth2 credentials configured successfully!\n"
                    f"Next step: Set your public URL with `[p]ai web config url`",
                    ephemeral=True
                )
            
            async def on_error(self, interaction: discord.Interaction, error: Exception):
                await interaction.response.send_message(
                    f"❌ An error occurred: {error}",
                    ephemeral=True
                )
        
        # Create view with modal
        class OAuth2ConfigView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=60.0)
                
            @discord.ui.button(label="Configure OAuth2", style=discord.ButtonStyle.primary, emoji="⚙️")
            async def configure_oauth2(self, interaction: discord.Interaction, button: discord.ui.Button):
                modal = OAuth2ConfigModal()
                await interaction.response.send_modal(modal)
                
        embed = discord.Embed(
            title="🔐 Discord OAuth2 Configuration",
            description="Click the button below to configure your Discord OAuth2 application credentials.",
            color=0x5865F2
        )
        embed.add_field(
            name="📋 Setup Instructions",
            value="1. Go to https://discord.com/developers/applications\n"
                  "2. Create a new application or select existing one\n"
                  "3. Go to OAuth2 section\n"
                  "4. Copy Client ID and Client Secret\n"
                  "5. Add redirect URI: `your_domain/callback`",
            inline=False
        )
        embed.add_field(
            name="🔒 Security Note", 
            value="Your credentials are encrypted and stored securely.",
            inline=False
        )
        
        view = OAuth2ConfigView()
        await ctx.send(embed=embed, view=view)
        
    @ai_web_config.command(name="url")  
    async def ai_web_config_url(self, ctx: commands.Context):
        """Set the public URL for the web interface via modal.
        
        Examples:
        - https://mybot.example.com
        - https://skynet.mydomain.org
        
        This URL will be used for OAuth2 redirect URIs.
        """
        # Create modal for URL configuration
        class URLConfigModal(discord.ui.Modal):
            def __init__(self):
                super().__init__(title="Web Interface Public URL", timeout=300.0)
                
            public_url = discord.ui.TextInput(
                label="Public URL",
                placeholder="https://yourdomain.com (no trailing slash)",
                min_length=10,
                max_length=200,
                required=True
            )
            
            async def on_submit(self, interaction: discord.Interaction):
                url = self.public_url.value.strip()
                
                # Validate URL
                if not url.startswith(('http://', 'https://')):
                    await interaction.response.send_message(
                        "❌ URL must start with http:// or https://",
                        ephemeral=True
                    )
                    return
                    
                # Remove trailing slash
                url = url.rstrip('/')
                
                # Get the cog instance
                cog = interaction.client.get_cog("SkynetV2")
                if not cog:
                    await interaction.response.send_message(
                        "❌ Could not access cog configuration.",
                        ephemeral=True
                    )
                    return
                    
                # Save configuration
                await cog.config.web_public_url.set(url)
                
                await interaction.response.send_message(
                    f"✅ Public URL set to: `{url}`\n\n"
                    f"**Important:** Make sure to set your Discord OAuth2 redirect URI to:\n"
                    f"`{url}/callback`",
                    ephemeral=True
                )
            
            async def on_error(self, interaction: discord.Interaction, error: Exception):
                await interaction.response.send_message(
                    f"❌ An error occurred: {error}",
                    ephemeral=True
                )
        
        # Create view with modal
        class URLConfigView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=60.0)
                
            @discord.ui.button(label="Set Public URL", style=discord.ButtonStyle.primary, emoji="🌐")
            async def configure_url(self, interaction: discord.Interaction, button: discord.ui.Button):
                modal = URLConfigModal()
                await interaction.response.send_modal(modal)
                
        # Get current URL for display
        current_url = await self.config.web_public_url() or "Not set"
        
        embed = discord.Embed(
            title="🌐 Web Interface Public URL",
            description="Set the public URL where your web interface will be accessible.",
            color=0x00D166
        )
        embed.add_field(
            name="Current URL",
            value=f"`{current_url}`",
            inline=False
        )
        embed.add_field(
            name="📋 Requirements",
            value="• Must start with https:// (recommended) or http://\n"
                  "• Should be the domain users will access\n"
                  "• No trailing slash\n"
                  "• Must match your reverse proxy configuration",
            inline=False
        )
        embed.add_field(
            name="🔄 Next Steps",
            value="After setting URL:\n"
                  "1. Configure reverse proxy (Cloudflare, Nginx, etc.)\n"
                  "2. Set Discord OAuth2 redirect URI to: `your_url/callback`\n"
                  "3. Restart web interface: `[p]ai web restart`",
            inline=False
        )
        
        view = URLConfigView()
        await ctx.send(embed=embed, view=view)

    @ai_web_config.command(name="server")
    async def ai_web_config_server(self, ctx: commands.Context):
        """Configure web server host and port via modal.
        
        Default: localhost:8080
        For public access through reverse proxy, use: 0.0.0.0:8080
        """
        # Create modal for server configuration
        class ServerConfigModal(discord.ui.Modal):
            def __init__(self, current_host: str, current_port: int):
                super().__init__(title="Web Server Configuration", timeout=300.0)
                
                # Pre-fill with current values
                self.host_input.default = current_host
                self.port_input.default = str(current_port)
                
            host_input = discord.ui.TextInput(
                label="Host",
                placeholder="localhost (secure) or 0.0.0.0 (allow external)",
                min_length=1,
                max_length=50,
                required=True
            )
            
            port_input = discord.ui.TextInput(
                label="Port",
                placeholder="8080 (default)",
                min_length=2,
                max_length=5,
                required=True
            )
            
            async def on_submit(self, interaction: discord.Interaction):
                host = self.host_input.value.strip()
                port_str = self.port_input.value.strip()
                
                # Validate port
                try:
                    port = int(port_str)
                    if not 1024 <= port <= 65535:
                        await interaction.response.send_message(
                            "❌ Port must be between 1024 and 65535.",
                            ephemeral=True
                        )
                        return
                except ValueError:
                    await interaction.response.send_message(
                        "❌ Port must be a valid number.",
                        ephemeral=True
                    )
                    return
                    
                # Validate host
                if not host:
                    await interaction.response.send_message(
                        "❌ Host cannot be empty.",
                        ephemeral=True
                    )
                    return
                    
                # Get the cog instance
                cog = interaction.client.get_cog("SkynetV2")
                if not cog:
                    await interaction.response.send_message(
                        "❌ Could not access cog configuration.",
                        ephemeral=True
                    )
                    return
                    
                # Save configuration
                await cog.config.web_host.set(host)
                await cog.config.web_port.set(port)
                
                security_note = ""
                if host == "0.0.0.0":
                    security_note = "\n\n⚠️ **Security Note:** Host set to 0.0.0.0 allows external connections. Ensure you have proper reverse proxy and firewall protection."
                
                await interaction.response.send_message(
                    f"✅ Web server configuration updated:\n"
                    f"Host: `{host}`\n"
                    f"Port: `{port}`\n\n"
                    f"**Restart required:** Use `[p]ai web restart` for changes to take effect.{security_note}",
                    ephemeral=True
                )
            
            async def on_error(self, interaction: discord.Interaction, error: Exception):
                await interaction.response.send_message(
                    f"❌ An error occurred: {error}",
                    ephemeral=True
                )
        
        # Create view with modal
        class ServerConfigView(discord.ui.View):
            def __init__(self, current_host: str, current_port: int):
                super().__init__(timeout=60.0)
                self.current_host = current_host
                self.current_port = current_port
                
            @discord.ui.button(label="Configure Server", style=discord.ButtonStyle.primary, emoji="⚙️")
            async def configure_server(self, interaction: discord.Interaction, button: discord.ui.Button):
                modal = ServerConfigModal(self.current_host, self.current_port)
                await interaction.response.send_modal(modal)
                
        # Get current configuration
        current_host = await self.config.web_host() or "localhost"
        current_port = await self.config.web_port() or 8080
        
        embed = discord.Embed(
            title="⚙️ Web Server Configuration",
            description="Configure the host and port for the web interface server.",
            color=0xF39C12
        )
        embed.add_field(
            name="Current Configuration",
            value=f"Host: `{current_host}`\nPort: `{current_port}`",
            inline=False
        )
        embed.add_field(
            name="📋 Host Options",
            value="• `localhost` - Secure, only local access\n"
                  "• `0.0.0.0` - Allow external connections (use with reverse proxy)\n"
                  "• Specific IP - Bind to specific network interface",
            inline=False
        )
        embed.add_field(
            name="🔢 Port Guidelines",
            value="• Range: 1024-65535\n"
                  "• Default: 8080\n"
                  "• Avoid: 80, 443 (reserved for HTTP/HTTPS)\n"
                  "• Check for conflicts with other services",
            inline=False
        )
        embed.add_field(
            name="🔄 After Changes",
            value="Use `[p]ai web restart` to apply new settings.",
            inline=False
        )
        
        view = ServerConfigView(current_host, current_port)
        await ctx.send(embed=embed, view=view)

    @ai_web_config.command(name="show")
    async def ai_web_config_show(self, ctx: commands.Context):
        """Show current web interface configuration and status."""
        
        # Collect all configuration
        oauth_config = await self.config.oauth2()
        public_url = await self.config.web_public_url()
        host = await self.config.web_host() or "localhost"
        port = await self.config.web_port() or 8080
        session_key = await self.config.web_session_key()
        
        # Check OAuth2 configuration status
        oauth2_configured = bool(oauth_config.get("client_id") and oauth_config.get("client_secret"))
        
        # Check if web server is running
        web_running = hasattr(self, 'web') and self.web and self.web.app
        
        # Determine configuration completeness
        config_complete = oauth2_configured and public_url
        
        # Create status embed
        embed = discord.Embed(
            title="🌐 Web Interface Configuration",
            color=0x2ECC71 if config_complete else 0xF39C12
        )
        
        # OAuth2 Status
        oauth2_status = "✅ Configured" if oauth2_configured else "❌ Not configured"
        client_id_display = oauth_config.get('client_id', 'Not set')
        client_secret_display = f"{oauth_config.get('client_secret', '')[:8]}***" if oauth_config.get('client_secret') else 'Not set'
        
        embed.add_field(
            name="🔐 OAuth2 Authentication",
            value=f"**Status:** {oauth2_status}\n"
                  f"Client ID: `{client_id_display}`\n"
                  f"Client Secret: `{client_secret_display}`",
            inline=True
        )
        
        # URL Configuration
        url_status = "✅ Configured" if public_url else "❌ Not configured"
        embed.add_field(
            name="🌍 Public URL",
            value=f"**Status:** {url_status}\n"
                  f"URL: {f'`{public_url}`' if public_url else '`Not set`'}",
            inline=True
        )
        
        # Server Configuration
        embed.add_field(
            name="⚙️ Server Settings",
            value=f"**Host:** `{host}`\n"
                  f"**Port:** `{port}`\n"
                  f"**Session Key:** {'`Generated`' if session_key else '`Auto-generate`'}",
            inline=True
        )
        
        # Web Server Status
        server_status = "🟢 Running" if web_running else "🔴 Stopped"
        embed.add_field(
            name="📡 Web Server",
            value=f"**Status:** {server_status}",
            inline=True
        )
        
        # Configuration Status Summary
        if config_complete:
            status_text = "✅ **Ready** - Web interface is fully configured"
            embed.color = 0x2ECC71
        elif oauth2_configured and not public_url:
            status_text = "⚠️ **Almost Ready** - Set public URL to complete setup"
            embed.color = 0xF39C12
        elif public_url and not oauth2_configured:
            status_text = "⚠️ **Almost Ready** - Configure OAuth2 to complete setup"
            embed.color = 0xF39C12
        else:
            status_text = "❌ **Not Ready** - OAuth2 and public URL required"
            embed.color = 0xE74C3C
            
        embed.add_field(
            name="📋 Overall Status",
            value=status_text,
            inline=False
        )
        
        # Next steps based on configuration state
        next_steps = []
        if not oauth2_configured:
            next_steps.append("1️⃣ Configure OAuth2: `[p]ai web config oauth`")
        if not public_url:
            next_steps.append("2️⃣ Set public URL: `[p]ai web config url`")
        if config_complete and not web_running:
            next_steps.append("3️⃣ Start web server: `[p]ai web start`")
        elif config_complete and web_running:
            next_steps.append("✨ **Ready to use!** Access your web interface at the configured URL")
        
        if next_steps:
            embed.add_field(
                name="🚀 Next Steps" if not config_complete else "🎉 Status",
                value="\n".join(next_steps),
                inline=False
            )
        
        # Add helpful links and tips
        if config_complete:
            embed.add_field(
                name="🔗 Quick Actions",
                value="• **Restart Server:** `[p]ai web restart`\n"
                      "• **View Logs:** `[p]ai web status`\n"
                      "• **Server Settings:** `[p]ai web config server`\n"
                      "• **Reset Config:** `[p]ai web config reset`",
                inline=False
            )
        else:
            embed.add_field(
                name="📚 Setup Help",
                value="• **Discord App:** [Developer Portal](https://discord.com/developers/applications)\n"
                      "• **OAuth2 Setup:** Create application and copy credentials\n"
                      "• **Domain Setup:** Use Cloudflare Tunnel or reverse proxy\n"
                      "• **Redirect URI:** Set to `{your_domain}/callback`",
                inline=False
            )
        
        await ctx.send(embed=embed)

    @ai_web_config.command(name="reset")
    async def ai_web_config_reset(self, ctx: commands.Context):
        """Reset all web interface configuration to defaults via confirmation modal."""
        
        # Create confirmation modal
        class ResetConfigModal(discord.ui.Modal):
            def __init__(self):
                super().__init__(title="Reset Web Configuration", timeout=300.0)
                
            confirmation_input = discord.ui.TextInput(
                label="Type CONFIRM to reset all web configuration",
                placeholder="CONFIRM",
                min_length=7,
                max_length=7,
                required=True,
                style=discord.TextStyle.short
            )
            
            async def on_submit(self, interaction: discord.Interaction):
                if self.confirmation_input.value != "CONFIRM":
                    await interaction.response.send_message(
                        "❌ Confirmation text did not match. Reset cancelled.",
                        ephemeral=True
                    )
                    return
                    
                # Get the cog instance
                cog = interaction.client.get_cog("SkynetV2")
                if not cog:
                    await interaction.response.send_message(
                        "❌ Could not access cog configuration.",
                        ephemeral=True
                    )
                    return
                    
                # Reset all web config
                await cog.config.oauth2.set({"client_id": None, "client_secret": None})
                await cog.config.web_public_url.set(None)
                await cog.config.web_host.set("localhost")
                await cog.config.web_port.set(8080)
                await cog.config.web_session_key.set(None)
                
                await interaction.response.send_message(
                    "✅ **Web configuration reset to defaults:**\n\n"
                    "• Public URL: *Not configured*\n"
                    "• Host: `localhost`\n"
                    "• Port: `8080`\n"
                    "• OAuth2 credentials: *Cleared*\n"
                    "• Session key: *Regenerated*\n\n"
                    "**Next steps:**\n"
                    "1. Configure OAuth2 credentials: `[p]ai web config oauth`\n"
                    "2. Set public URL: `[p]ai web config url`"
                    "3. Restart web server: `[p]ai web restart`",
                    ephemeral=True
                )
            
            async def on_error(self, interaction: discord.Interaction, error: Exception):
                await interaction.response.send_message(
                    f"❌ An error occurred during reset: {error}",
                    ephemeral=True
                )
        
        # Create view with confirmation button
        class ResetConfirmView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=60.0)
                
            @discord.ui.button(label="Reset Configuration", style=discord.ButtonStyle.danger, emoji="🗑️")
            async def reset_config(self, interaction: discord.Interaction, button: discord.ui.Button):
                modal = ResetConfigModal()
                await interaction.response.send_modal(modal)
                
            @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="❌")
            async def cancel_reset(self, interaction: discord.Interaction, button: discord.ui.Button):
                await interaction.response.send_message("Reset cancelled.", ephemeral=True)
                self.stop()
        
        embed = discord.Embed(
            title="🗑️ Reset Web Configuration",
            description="This will reset **ALL** web interface configuration to defaults.",
            color=0xE74C3C
        )
        embed.add_field(
            name="⚠️ What will be reset",
            value="• OAuth2 client credentials\n"
                  "• Public URL setting\n"
                  "• Server host and port\n"
                  "• Session encryption key",
            inline=False
        )
        embed.add_field(
            name="🔄 After Reset",
            value="You'll need to:\n"
                  "1. Reconfigure OAuth2 credentials\n"
                  "2. Set your public URL\n"
                  "3. Restart the web server",
            inline=False
        )
        embed.add_field(
            name="💡 Tip",
            value="Consider backing up your current configuration before resetting.",
            inline=False
        )
        
        view = ResetConfirmView()
        await ctx.send(embed=embed, view=view)

    @ai_web.command(name="restart")
    @checks.is_owner()
    async def ai_web_restart(self, ctx: commands.Context):
        """Restart the web interface server."""
        try:
            if self.web:
                await self.web.stop_server()
                await self.web.start_server()
                await ctx.send("✅ Web interface restarted successfully.")
            else:
                await ctx.send("❌ Web interface is not initialized.")
        except Exception as e:
            await ctx.send(f"❌ Failed to restart web interface: {e}")

    # ----------------
    # Cog Lifecycle
    # ----------------

    async def cog_load(self):
        """Called when the cog is loaded."""
        try:
            await self.web.start_server()
        except Exception as e:
            print(f"Failed to start SkynetV2 web interface: {e}")

    async def cog_unload(self):
        """Called when the cog is unloaded."""
        try:
            if self.web:
                await self.web.stop_server()
        except Exception as e:
            print(f"Error stopping SkynetV2 web interface: {e}")

    # Red automatically handles slash command registration for class-level app_commands.Group
    # No manual tree management needed in cog_load/cog_unload
