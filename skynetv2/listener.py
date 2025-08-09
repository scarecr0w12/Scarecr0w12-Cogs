from __future__ import annotations

import time
import discord
from .api.base import ChatMessage

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
        
        # Check per-channel listening configuration first
        channel_listening_config = await self.config.guild(guild).channel_listening()
        channel_id = str(message.channel.id)
        
        # Channel-specific override
        if channel_id in channel_listening_config:
            channel_config = channel_listening_config[channel_id]
            if not channel_config.get("enabled", False):
                return
            listening = channel_config
        else:
            # Fall back to global guild listening config
            listening = await self.config.guild(guild).listening()
            if not listening or not listening.get("enabled", False):
                return
        
        mode = listening.get("mode", "mention")
        content = message.content or ""
        try:
            prefixes = await self.bot.get_prefix(message)
            if any(content.startswith(p) for p in prefixes if isinstance(p, str)):
                return
        except Exception:
            pass
        triggered = False
        if mode == "mention":
            if self.bot.user and self.bot.user.mentioned_in(message):
                triggered = True
                content = content.replace(self.bot.user.mention, "").strip()
        elif mode == "keyword":
            keywords = [k.lower() for k in listening.get("keywords", []) if k]
            lc = content.lower()
            if any(k in lc for k in keywords):
                triggered = True
        elif mode == "all":
            triggered = True
        if not triggered:
            return
        err = await self._check_and_record_usage(guild, message.channel, message.author)
        if err:
            return
        provider_name, model, provider_config = await self.resolve_provider_and_model(guild)
        if not provider_config:
            return
        try:
            provider = self.build_provider(provider_name, provider_config)
        except Exception:
            return
        try:
            chunks = []
            async for chunk in provider.chat(model=model["name"] if isinstance(model, dict) else str(model), messages=[ChatMessage("user", content or "Hello")]):
                chunks.append(chunk)
            text = "".join(chunks) or "(no output)"
            last_usage = getattr(provider, "get_last_usage", lambda: None)()
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
            await message.channel.send(text[:2000])
        except Exception:
            return
