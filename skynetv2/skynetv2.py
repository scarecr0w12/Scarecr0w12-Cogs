from __future__ import annotations

import asyncio
import io
import json
import time
import logging
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

    # Slash command groups (class-level) so Red registers them under /skynet and /skynet memory
    ai_slash = app_commands.Group(name="skynet", description="AI assistant commands")
    mem_group = app_commands.Group(name="memory", description="Memory controls", parent=ai_slash)

    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("red.skynetv2.cog")
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

    @ai_group.command(name="ask")
    @commands.bot_has_permissions(send_messages=True)
    async def ai_ask(self, ctx: commands.Context, *, message: str):
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
            # Initialize auto web search system
            from .auto_web_search import AutoWebSearchIntegration, AutoSearchCooldownManager
            if not hasattr(self, '_auto_search_integration'):
                self._auto_search_integration = AutoWebSearchIntegration(self)
            if not hasattr(self, '_auto_search_cooldowns'):
                self._auto_search_cooldowns = AutoSearchCooldownManager()
            
            base = await self._memory_build_context(ctx.guild, ctx.channel.id, ctx.author)
            
            # Resolve variables in the message
            resolved_message = await self.resolve_prompt_variables(message, ctx.guild, ctx.channel, ctx.author)
            
            # Auto web search integration - check if we should search for current info
            auto_search_config = await self.config.guild(ctx.guild).auto_web_search()
            search_context = ""
            
            if auto_search_config.get('enabled', False):
                allowed = auto_search_config.get('allowed_commands', ['ask', 'chat', 'chatstream'])
                # Check if command is allowed for auto search
                if 'ask' in allowed or 'chat' in allowed:
                    # Check user cooldown
                    user_id = str(ctx.author.id)
                    cooldown_seconds = auto_search_config.get('cooldown_seconds', 60)
                    
                    if self._auto_search_cooldowns.can_search(user_id, cooldown_seconds):
                        # Check if message should trigger search
                        should_search, search_reason = self._auto_search_integration.should_trigger_search(
                            resolved_message, auto_search_config
                        )
                        
                        if should_search:
                            # Check message length requirement
                            min_length = auto_search_config.get('min_message_length', 10)
                            if len(resolved_message.strip()) >= min_length:
                                try:
                                    # Perform auto search
                                    search_data = await self._auto_search_integration.perform_auto_search(
                                        resolved_message, ctx.guild, auto_search_config
                                    )
                                    
                                    if search_data:
                                        # Format search results as context
                                        search_context = self._auto_search_integration.format_search_context(
                                            search_data, resolved_message
                                        )
                                        
                                        # Record successful search for cooldown
                                        self._auto_search_cooldowns.record_search(user_id)
                                        
                                        # Log auto search activity
                                        self.logger.info(f"Auto web search triggered for user {ctx.author.id} in guild {ctx.guild.id}: {search_reason}")
                                        
                                except Exception as e:
                                    # Log error but don't break chat
                                    self.error_handler.log_error(e, "auto_web_search_chat", {
                                        "user_id": ctx.author.id,
                                        "guild_id": ctx.guild.id,
                                        "message_preview": resolved_message[:100]
                                    })
            
            # Add search context to the conversation if available
            chat_messages = base.copy()
            if search_context:
                # Insert search context as a system message before the user message
                chat_messages.append(ChatMessage("system", search_context))
            
            chat_messages.append(ChatMessage("user", resolved_message))
            
            chunks = []
            async for chunk in provider.chat(model=model_name, messages=chat_messages):
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
            await self._memory_remember(ctx.guild, ctx.channel.id, message, text, user=ctx.author)
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
            
        # Initialize auto web search system
        from .auto_web_search import AutoWebSearchIntegration, AutoSearchCooldownManager
        if not hasattr(self, '_auto_search_integration'):
            self._auto_search_integration = AutoWebSearchIntegration(self)
        if not hasattr(self, '_auto_search_cooldowns'):
            self._auto_search_cooldowns = AutoSearchCooldownManager()
        
        base = await self._memory_build_context(ctx.guild, ctx.channel.id, ctx.author)
        
        # Resolve variables in the message
        resolved_message = await self.resolve_prompt_variables(message, ctx.guild, ctx.channel, ctx.author)
        
        # Auto web search integration for chatstream
        auto_search_config = await self.config.guild(ctx.guild).auto_web_search()
        search_context = ""
        
        if auto_search_config.get('enabled', False):
            # Check if command is allowed for auto search
            if "chatstream" in auto_search_config.get('allowed_commands', ['chat', 'chatstream']):
                # Check user cooldown
                user_id = str(ctx.author.id)
                cooldown_seconds = auto_search_config.get('cooldown_seconds', 60)
                
                if self._auto_search_cooldowns.can_search(user_id, cooldown_seconds):
                    # Check if message should trigger search
                    should_search, search_reason = self._auto_search_integration.should_trigger_search(
                        resolved_message, auto_search_config
                    )
                    
                    if should_search:
                        # Check message length requirement
                        min_length = auto_search_config.get('min_message_length', 10)
                        if len(resolved_message.strip()) >= min_length:
                            try:
                                # Perform auto search
                                search_data = await self._auto_search_integration.perform_auto_search(
                                    resolved_message, ctx.guild, auto_search_config
                                )
                                
                                if search_data:
                                    # Format search results as context
                                    search_context = self._auto_search_integration.format_search_context(
                                        search_data, resolved_message
                                    )
                                    
                                    # Record successful search for cooldown
                                    self._auto_search_cooldowns.record_search(user_id)
                                    
                                    # Log auto search activity
                                    self.logger.info(f"Auto web search triggered for chatstream user {ctx.author.id} in guild {ctx.guild.id}: {search_reason}")
                                    
                            except Exception as e:
                                # Log error but don't break chat
                                self.error_handler.log_error(e, "auto_web_search_chatstream", {
                                    "user_id": ctx.author.id,
                                    "guild_id": ctx.guild.id,
                                    "message_preview": resolved_message[:100]
                                })
        
        # Add search context to the conversation if available
        chat_messages = base.copy()
        if search_context:
            # Insert search context as a system message before the user message
            chat_messages.append(ChatMessage("system", search_context))
        
        chat_messages.append(ChatMessage("user", resolved_message))
        
        msg = await ctx.send("…")
        buf = ""
        last_edit = 0.0
        try:
            async for chunk in provider.chat(model=model_name, messages=chat_messages, stream=True):
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
        await self._memory_remember(ctx.guild, ctx.channel.id, resolved_message, buf, user=ctx.author)

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
        overrides = (tools.get("per_user_minute_overrides", {}) or {})
        if overrides:
            lines.append("per_user_minute_overrides: " + ",".join(f"{k}:{int(v)}" for k, v in overrides.items()))
        else:
            lines.append("per_user_minute_overrides: (none)")
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

    # Register slash chat under the slash command group, not the prefix group
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
        
        # Initialize auto web search system
        from .auto_web_search import AutoWebSearchIntegration, AutoSearchCooldownManager
        if not hasattr(self, '_auto_search_integration'):
            self._auto_search_integration = AutoWebSearchIntegration(self)
        if not hasattr(self, '_auto_search_cooldowns'):
            self._auto_search_cooldowns = AutoSearchCooldownManager()
        
        # Resolve variables in the message
        resolved_message = await self.resolve_prompt_variables(message, interaction.guild, interaction.channel, interaction.user)
        
        # Auto web search integration - check if we should search for current info
        auto_search_config = await self.config.guild(interaction.guild).auto_web_search()
        search_context = ""
        
        if auto_search_config.get('enabled', False):
            # Check if command is allowed for auto search (slash commands count as "chat")
            if "chat" in auto_search_config.get('allowed_commands', ['chat', 'chatstream']):
                # Check user cooldown
                user_id = str(interaction.user.id)
                cooldown_seconds = auto_search_config.get('cooldown_seconds', 60)
                
                if self._auto_search_cooldowns.can_search(user_id, cooldown_seconds):
                    # Check if message should trigger search
                    should_search, search_reason = self._auto_search_integration.should_trigger_search(
                        resolved_message, auto_search_config
                    )
                    
                    if should_search:
                        # Check message length requirement
                        min_length = auto_search_config.get('min_message_length', 10)
                        if len(resolved_message.strip()) >= min_length:
                            try:
                                # Perform auto search
                                search_data = await self._auto_search_integration.perform_auto_search(
                                    resolved_message, interaction.guild, auto_search_config
                                )
                                
                                if search_data:
                                    # Format search results as context
                                    search_context = self._auto_search_integration.format_search_context(
                                        search_data, resolved_message
                                    )
                                    
                                    # Record successful search for cooldown
                                    self._auto_search_cooldowns.record_search(user_id)
                                    
                                    # Log auto search activity
                                    self.logger.info(f"Auto web search triggered for slash chat user {interaction.user.id} in guild {interaction.guild.id}: {search_reason}")
                                    
                            except Exception as e:
                                # Log error but don't break chat
                                self.error_handler.log_error(e, "auto_web_search_slash", {
                                    "user_id": interaction.user.id,
                                    "guild_id": interaction.guild.id,
                                    "message_preview": resolved_message[:100]
                                })
        
        # Add search context to the conversation if available
        chat_messages = base.copy()
        if search_context:
            # Insert search context as a system message before the user message
            chat_messages.append(ChatMessage("system", search_context))
        
        chat_messages.append(ChatMessage("user", resolved_message))
        
        if stream:
            await interaction.response.defer(thinking=True)
            msg = await interaction.followup.send("…")
            buf = ""
            last_edit = 0.0
            try:
                async for chunk in provider.chat(model=model_name, messages=chat_messages, stream=True):
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
            await self._memory_remember(interaction.guild, interaction.channel.id, resolved_message, buf, user=interaction.user)
            return
        await interaction.response.defer(thinking=True)
        chunks = []
        async for chunk in provider.chat(model=model_name, messages=chat_messages):
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
        await self._memory_remember(interaction.guild, interaction.channel.id, resolved_message, text, user=interaction.user)
        await interaction.followup.send(text[:2000])

    # ----------------
    # Memory scope controls (slash)
    # ----------------
    @mem_group.command(name="scope", description="Enable/disable per-user memory and set limits")
    @app_commands.describe(per_user_enabled="Enable per-user memory", per_user_limit="Pairs to keep per user per channel", merge_strategy="append, interleave, or user_first")
    @app_commands.choices(merge_strategy=[
        app_commands.Choice(name="append", value="append"),
        app_commands.Choice(name="interleave", value="interleave"),
        app_commands.Choice(name="user_first", value="user_first"),
    ])
    @app_commands.default_permissions(manage_guild=True)
    async def slash_memory_scope(self, interaction: discord.Interaction, per_user_enabled: Optional[bool] = None, per_user_limit: Optional[int] = None, merge_strategy: Optional[str] = None):
        assert interaction.guild is not None
        async with self.config.guild(interaction.guild).memory() as mem:
            scopes = mem.setdefault("scopes", {"per_user_enabled": False, "per_user_limit": 10, "merge_strategy": "append"})
            if per_user_enabled is not None:
                scopes["per_user_enabled"] = bool(per_user_enabled)
            if per_user_limit is not None:
                scopes["per_user_limit"] = max(0, int(per_user_limit))
            if merge_strategy is not None:
                scopes["merge_strategy"] = str(merge_strategy)
        await interaction.response.send_message("Memory scope updated.", ephemeral=True)

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
