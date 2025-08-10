from __future__ import annotations

import time
import discord
from redbot.core import commands  # Import commands for the listener decorator
from .api.base import ChatMessage
from .logging_system import log_ai_request, log_listening_event, log_rate_limit_hit, log_error_event
from .message_utils import MessageChunker, ConversationManager, SmartReplyAnalyzer

print("🚀 [SkynetV2] NEW LISTENER CODE LOADED WITH CONVERSATION SYSTEM v1.2.3")

class ListenerMixin:
    """Passive on_message logic extracted from main cog."""

    @discord.app_commands.checks.cooldown(1, 0)  # dummy decorator to avoid empty file lint; unused
    async def _noop(self):  # pragma: no cover
        pass

    @property
    def _passive_enabled(self):  # helper if future conditional import
        return True

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):  # type: ignore[override]
        if message.author.bot or not message.guild:
            return
        guild = message.guild
        
        print(f"🚨 [SkynetV2 Listener v1.2.3] PROCESSING MESSAGE: '{message.content}' from {message.author.display_name} in #{message.channel.name}")
        
        # Check if the cog is enabled for this guild
        cog_enabled = await self.config.guild(guild).enabled()
        print(f"[SkynetV2 Listener] Cog enabled for guild: {cog_enabled}")
        if not cog_enabled:
            print(f"[SkynetV2 Listener] SkynetV2 cog disabled for guild {guild.name}")
            return
        
        # Check per-channel listening configuration first
        channel_listening_config = await self.config.guild(guild).channel_listening()
        channel_id = str(message.channel.id)
        
        print(f"[SkynetV2 Listener] Channel listening config: {channel_listening_config}")
        
        # Channel-specific override
        if channel_id in channel_listening_config:
            channel_config = channel_listening_config[channel_id]
            print(f"[SkynetV2 Listener] Found channel-specific config: {channel_config}")
            if not channel_config.get("enabled", False):
                print(f"[SkynetV2 Listener] Channel listening disabled for {message.channel.name}")
                return
            listening = channel_config
        else:
            # Fall back to global guild listening config
            listening = await self.config.guild(guild).listening()
            print(f"[SkynetV2 Listener] Using global listening config: {listening}")
            if not listening or not listening.get("enabled", False):
                print(f"[SkynetV2 Listener] Global listening disabled or not configured - enabled: {listening.get('enabled', 'NOT SET') if listening else 'NO CONFIG'}")
                return
        
        mode = listening.get("mode", "mention")
        print(f"[SkynetV2 Listener] Listening mode: {mode}")
        content = message.content or ""
        try:
            prefixes = await self.bot.get_prefix(message)
            if any(content.startswith(p) for p in prefixes if isinstance(p, str)):
                print(f"[SkynetV2 Listener] Message starts with command prefix, ignoring")
                return
        except Exception:
            pass
        triggered = False
        if mode == "mention":
            print(f"[SkynetV2 Listener] Checking mention mode...")
            if self.bot.user and self.bot.user.mentioned_in(message):
                triggered = True
                content = content.replace(self.bot.user.mention, "").strip()
                print(f"[SkynetV2 Listener] Bot mentioned, triggered=True")
        elif mode == "keyword":
            keywords = [k.lower() for k in listening.get("keywords", []) if k]
            lc = content.lower()
            print(f"[SkynetV2 Listener] Checking keywords: {keywords} in '{lc}'")
            if any(k in lc for k in keywords):
                triggered = True
                print(f"[SkynetV2 Listener] Keyword matched, triggered=True")
        elif mode == "all":
            triggered = True
            print(f"[SkynetV2 Listener] Mode is 'all', checking smart replies...")
            
            # Use smart replies to determine if we should actually respond
            smart_config = await self.config.guild(guild).smart_replies()
            
            # Get recent messages for context analysis (last 20 messages)
            try:
                recent_messages = []
                async for msg in message.channel.history(limit=20, before=message):
                    recent_messages.insert(0, msg)  # Insert at beginning to maintain order
            except Exception as e:
                print(f"[SkynetV2 Listener] Warning: Could not fetch recent messages: {e}")
                recent_messages = []
            
            should_respond, reason = SmartReplyAnalyzer.should_respond_in_all_mode(
                message, recent_messages, self.bot.user, smart_config
            )
            
            if not should_respond:
                triggered = False
                print(f"[SkynetV2 Listener] Smart reply decided NOT to respond: {reason}")
            else:
                print(f"[SkynetV2 Listener] Smart reply decided TO respond: {reason}")
        
        # Log the listening event
        await log_listening_event(guild, message.channel, mode, triggered, message.author)
        
        print(f"[SkynetV2 Listener] Final triggered status: {triggered}")
        if not triggered:
            print(f"[SkynetV2 Listener] Not triggered, returning")
            return
        print(f"[SkynetV2 Listener] Checking usage limits...")
        err = await self._check_and_record_usage(guild, message.channel, message.author)
        if err:
            print(f"[SkynetV2 Listener] Usage limit exceeded: {err}")
            await log_rate_limit_hit(guild, message.author, message.channel, str(err))
            return
        
        print(f"[SkynetV2 Listener] Resolving provider and model...")
        provider_name, model, provider_config = await self.resolve_provider_and_model(guild)
        if not provider_config:
            print(f"[SkynetV2 Listener] No provider config available")
            return
        
        print(f"[SkynetV2 Listener] Building provider: {provider_name}")
        try:
            provider = self.build_provider(provider_name, provider_config)
        except Exception as e:
            print(f"[SkynetV2 Listener] Failed to build provider: {e}")
            return
        
        print(f"[SkynetV2 Listener] Sending message to AI provider...")
        try:
            # Keep typing indicator visible until we send the response
            async with message.channel.typing():
                from typing import Any, cast
                s = cast(Any, self)
                # Clean up content for mentions
                processed_content = content
                if mode == "mention" and getattr(s, 'bot', None) and getattr(s.bot, 'user', None):
                    processed_content = ConversationManager.extract_mention_content(message, s.bot.user)
                
                # Auto web search integration for passive listening
                from .auto_web_search import AutoWebSearchIntegration, AutoSearchCooldownManager
                if not hasattr(s, '_auto_search_integration'):
                    s._auto_search_integration = AutoWebSearchIntegration(self)
                if not hasattr(s, '_auto_search_cooldowns'):
                    s._auto_search_cooldowns = AutoSearchCooldownManager()
                
                auto_search_config = await s.config.guild(guild).auto_web_search()
                search_context = ""
                
                if auto_search_config.get('enabled', False):
                    # Check if current listening mode is allowed for auto search
                    if mode in auto_search_config.get('allowed_modes', ['mention', 'keyword', 'all']):
                        # Check user cooldown
                        user_id = str(message.author.id)
                        cooldown_seconds = auto_search_config.get('cooldown_seconds', 60)
                        
                        if s._auto_search_cooldowns.can_search(user_id, cooldown_seconds):
                            # Check if message should trigger search
                            should_search, search_reason = s._auto_search_integration.should_trigger_search(
                                processed_content, auto_search_config
                            )
                            
                            if should_search:
                                # Check message length requirement
                                min_length = auto_search_config.get('min_message_length', 10)
                                if len(processed_content.strip()) >= min_length:
                                    try:
                                        # Perform auto search
                                        search_data = await s._auto_search_integration.perform_auto_search(
                                            processed_content, guild, auto_search_config
                                        )
                                        
                                        if search_data:
                                            # Format search results as context
                                            search_context = s._auto_search_integration.format_search_context(
                                                search_data, processed_content
                                            )
                                            
                                            # Record successful search for cooldown
                                            s._auto_search_cooldowns.record_search(user_id)
                                            
                                            print(f"[SkynetV2 Listener] Auto web search triggered: {search_reason}")
                                            
                                    except Exception as e:
                                        # Log error but don't break listener
                                        print(f"[SkynetV2 Listener] Auto search error: {e}")
                
                # Always use conversation memory for consistent behavior across all modes
                print(f"[SkynetV2 Listener] Building conversation context with memory...")
                messages = await s._memory_build_context(guild, message.channel.id, message.author)
                
                # Add search context if available
                if search_context:
                    messages.append(ChatMessage("system", search_context))
                
                # Add current message to context
                messages.append(ChatMessage("user", processed_content or "Hello"))
                
                # Send to AI provider
                chunks = []
                async for chunk in provider.chat(model=model["name"] if isinstance(model, dict) else str(model), messages=messages):
                    chunks.append(chunk)
                text = "".join(chunks) or "(no output)"
                
                # Log the AI request with usage info
                last_usage = getattr(provider, "get_last_usage", lambda: None)()
                model_name = model["name"] if isinstance(model, dict) else str(model)
                tokens_used = last_usage.get('total', 0) if last_usage else 0
                await log_ai_request(guild, message.author, message.channel, provider_name, model_name, tokens_used)
                
                # Update usage statistics
                if last_usage:
                    async with s.config.guild(guild).usage() as usage:
                        t = usage.setdefault("tokens", {"prompt": 0, "completion": 0, "total": 0})
                        t["prompt"] = int(t.get("prompt", 0)) + int(last_usage.get("prompt", 0))
                        t["completion"] = int(t.get("completion", 0)) + int(last_usage.get("completion", 0))
                        t["total"] = int(t.get("total", 0)) + int(last_usage.get("total", 0))
                        pu = usage.setdefault("per_user", {})
                        pc = usage.setdefault("per_channel", {})
                        u = pu.setdefault(str(message.author.id), {"last_used": int(time.time()), "count_1m": 1, "window_start": int(time.time()), "total": 1, "tokens_total": 0})
                        c = pc.setdefault(str(message.channel.id), {"count_1m": 1, "window_start": int(time.time()), "total": 1, "tokens_total": 0})
                        u["tokens_total"] = int(u.get("tokens_total", 0)) + int(last_usage.get("total", 0))
                        c["tokens_total"] = int(c.get("tokens_total", 0)) + int(last_usage.get("total", 0))
                
                # Store conversation in memory (always, for all modes)
                print(f"[SkynetV2 Listener] Storing conversation in memory...")
                await s._memory_remember(guild, message.channel.id, processed_content or "Hello", text, user=message.author)
                
                # Send response using smart message handling
                print(f"[SkynetV2 Listener] Sending response with smart chunking: {len(text)} characters...")
                sent_messages = await MessageChunker.send_long_message(message.channel, text, reference=message)
                print(f"[SkynetV2 Listener] Response sent as {len(sent_messages)} message(s)!")
            
        except Exception as e:
            # Log the exception for debugging instead of silently returning
            import traceback
            print(f"[SkynetV2 Listener] Error processing message: {e}")
            print(traceback.format_exc())
            await log_error_event(guild, message.author, message.channel, f"AI processing error: {str(e)}")
            return
