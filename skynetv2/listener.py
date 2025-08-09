from __future__ import annotations

import time
import discord
from .api.base import ChatMessage
from .logging_system import log_ai_request, log_listening_event, log_rate_limit_hit, log_error_event

class ListenerMixin:
    """Passive on_message logic extracted from main cog."""

    @discord.app_commands.checks.cooldown(1, 0)  # dummy decorator to avoid empty file lint; unused
    async def _noop(self):  # pragma: no cover
        pass

    @property
    def _passive_enabled(self):  # helper if future conditional import
        return True

    @discord.utils.copy_doc
    async def on_message(self, message: discord.Message):  # type: ignore[override]
        if message.author.bot or not message.guild:
            return
        guild = message.guild
        
        print(f"[SkynetV2 Listener] Processing message from {message.author} in #{message.channel.name}")
        
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
                print(f"[SkynetV2 Listener] Global listening disabled or not configured")
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
            print(f"[SkynetV2 Listener] Mode is 'all', triggered=True")
        
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
            chunks = []
            async for chunk in provider.chat(model=model["name"] if isinstance(model, dict) else str(model), messages=[ChatMessage("user", content or "Hello")]):
                chunks.append(chunk)
            text = "".join(chunks) or "(no output)"
            last_usage = getattr(provider, "get_last_usage", lambda: None)()
            
            # Log the AI request with usage info
            model_name = model["name"] if isinstance(model, dict) else str(model)
            tokens_used = last_usage.get('total_tokens', 0) if last_usage else 0
            await log_ai_request(guild, message.author, message.channel, provider_name, model_name, tokens_used)
            if last_usage:
                async with self.config.guild(guild).usage as usage:
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
            
            print(f"[SkynetV2 Listener] Sending response: {text[:100]}...")
            await message.channel.send(text[:2000])
            print(f"[SkynetV2 Listener] Response sent successfully!")
        except Exception as e:
            # Log the exception for debugging instead of silently returning
            import traceback
            print(f"[SkynetV2 Listener] Error processing message: {e}")
            print(traceback.format_exc())
            await log_error_event(guild, message.author, message.channel, f"AI processing error: {str(e)}")
            return
