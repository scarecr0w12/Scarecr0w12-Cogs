from __future__ import annotations

from typing import List, Dict, Any
import time
import discord # pyright: ignore[reportMissingImports]
from .api.base import ChatMessage

class MemoryMixin:
    """Memory helper methods for SkynetV2.

    Separated from main cog for clarity; no behavioral changes.
    """
    # The main cog provides: self.config

    async def _memory_get_limit(self, guild: discord.Guild, channel_id: int) -> int:
        mem = await self.config.guild(guild).memory()
        per = mem.get("per_channel", {}).get(str(channel_id), {})
        return int(per.get("limit", mem.get("default_limit", 10)))

    async def _memory_get_messages(self, guild: discord.Guild, channel_id: int) -> List[Dict[str, Any]]:
        mem = await self.config.guild(guild).memory()
        per = mem.get("per_channel", {}).get(str(channel_id), {})
        return list(per.get("messages", []))

    async def _build_system_prompt(self, guild: discord.Guild, user: discord.Member = None) -> str:
        """Build hierarchical system prompt: System > Guild > Member"""
        global_config = await self.config.system_prompts()
        guild_config = await self.config.guild(guild).system_prompts()
        
        # Start with global system prompt
        system_prompt = global_config.get('system', 'You are a helpful AI assistant.')
        
        # Add guild-level prompt if configured
        guild_prompt = guild_config.get('guild', '')
        if guild_prompt:
            system_prompt += f"\n\nGuild Context: {guild_prompt}"
        
        # Add member-level prompt if user provided and configured
        if user:
            member_prompts = guild_config.get('members', {})
            member_prompt = member_prompts.get(str(user.id), '')
            if member_prompt:
                system_prompt += f"\n\nUser Context: {member_prompt}"
        
        return system_prompt.strip()

    async def _memory_build_context(self, guild: discord.Guild, channel_id: int, user: discord.Member = None) -> List[ChatMessage]:
        msgs = await self._memory_get_messages(guild, channel_id)
        out: List[ChatMessage] = []
        
        # Add system prompt as first message
        system_prompt = await self._build_system_prompt(guild, user)
        out.append(ChatMessage(role="system", content=system_prompt))
        
        # Add conversation history
        for m in msgs[-await self._memory_get_limit(guild, channel_id):]:
            role = m.get("role", "user")
            content = m.get("content", "")
            out.append(ChatMessage(role=role, content=content))
        return out

    async def _memory_remember(self, guild: discord.Guild, channel_id: int, user_text: str, assistant_text: str):
        limit = await self._memory_get_limit(guild, channel_id)
        async with self.config.guild(guild).memory() as mem:
            per = mem.setdefault("per_channel", {}).setdefault(str(channel_id), {})
            messages = per.setdefault("messages", [])
            now = int(time.time())
            messages.append({"role": "user", "content": user_text, "ts": now})
            messages.append({"role": "assistant", "content": assistant_text, "ts": now})
            if len(messages) > (limit * 2):  # user+assistant pairs
                trim = len(messages) - (limit * 2)
                del messages[0:trim]
            # Pruning policy enforcement
            prune_cfg = mem.get("prune", {})  # guild-level prune config
            if not prune_cfg:
                prune_cfg = {}
            max_items = int(prune_cfg.get("max_items", 0))
            max_age_days = int(prune_cfg.get("max_age_days", 0))
            if max_items and len(messages) > max_items:
                del messages[0: len(messages) - max_items]
            if max_age_days:
                cutoff = now - (max_age_days * 86400)
                idx = 0
                while idx < len(messages) and int(messages[idx].get("ts", now)) < cutoff:
                    idx += 1
                if idx > 0:
                    del messages[0:idx]
