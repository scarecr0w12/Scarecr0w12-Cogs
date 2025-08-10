from __future__ import annotations

from typing import List, Dict, Any, cast
import time
import discord # pyright: ignore[reportMissingImports]
from .api.base import ChatMessage
from .markdown_utils import MarkdownTemplateProcessor, DiscordMarkdownFormatter

class MemoryMixin:
    """Memory helper methods for SkynetV2.

    Separated from main cog for clarity; no behavioral changes.
    """
    # The main cog provides: self.config

    async def _memory_get_limit(self, guild: discord.Guild, channel_id: int) -> int:
        s = cast(Any, self)
        mem = await s.config.guild(guild).memory()
        per = mem.get("per_channel", {}).get(str(channel_id), {})
        return int(per.get("limit", mem.get("default_limit", 10)))

    async def _memory_get_messages(self, guild: discord.Guild, channel_id: int) -> List[Dict[str, Any]]:
        s = cast(Any, self)
        mem = await s.config.guild(guild).memory()
        per = mem.get("per_channel", {}).get(str(channel_id), {})
        return list(per.get("messages", []))

    async def _build_system_prompt(self, guild: discord.Guild, user: discord.Member = None, channel: discord.TextChannel = None) -> str:
        """Build hierarchical system prompt with markdown formatting: System > Guild > Member"""
        s = cast(Any, self)
        global_config = await s.config.system_prompts()
        guild_config = await s.config.guild(guild).system_prompts()
        
        # Start with global system prompt (already markdown formatted)
        system_prompt = global_config.get('default', 'You are a helpful AI assistant.')
        
        # Add guild-level context with markdown formatting
        guild_prompt = guild_config.get('guild', '')
        if guild_prompt:
            fmt = DiscordMarkdownFormatter()
            system_prompt += f"\n\n## Guild-Specific Context\n{guild_prompt}"
        
        # Add member-level context with markdown formatting  
        if user:
            member_prompts = guild_config.get('members', {})
            member_prompt = member_prompts.get(str(user.id), '')
            if member_prompt:
                fmt = DiscordMarkdownFormatter()
                system_prompt += f"\n\n## User-Specific Context\n"
                system_prompt += f"**User:** {fmt.mention_user(user.id)} ({user.display_name})\n"
                system_prompt += f"**Instructions:** {member_prompt}"
        
        # Add current Discord context for better responses
        context_info = []
        context_info.append(f"**Server:** {guild.name}")
        context_info.append(f"**Member Count:** {guild.member_count}")
        if hasattr(guild, 'premium_tier') and guild.premium_tier > 0:
            context_info.append(f"**Boost Level:** {guild.premium_tier}")
        
        if context_info:
            system_prompt += f"\n\n## Current Discord Context\n" + "\n".join(context_info)
        
        # **CRITICAL FIX**: Resolve variables in the system prompt
        if hasattr(s, 'resolve_prompt_variables'):
            try:
                system_prompt = await s.resolve_prompt_variables(system_prompt, guild, channel, user)
            except Exception as e:
                # Log error but continue with unresolved prompt
                print(f"[SkynetV2] Error resolving system prompt variables: {e}")
        
        return system_prompt.strip()

    async def _memory_build_context(self, guild: discord.Guild, channel_id: int, user: discord.Member = None) -> List[ChatMessage]:
        s = cast(Any, self)
        mem = await s.config.guild(guild).memory()
        msgs = await self._memory_get_messages(guild, channel_id)
        out: List[ChatMessage] = []
        
        # Get channel object for variable resolution
        channel = guild.get_channel(channel_id) if hasattr(guild, 'get_channel') else None
        
        # Add system prompt as first message
        system_prompt = await self._build_system_prompt(guild, user, channel)
        out.append(ChatMessage(role="system", content=system_prompt))
        
        # Optionally include per-user memory
        scopes = mem.get("scopes", {}) or {}
        per_user_enabled = bool(scopes.get("per_user_enabled", False))
        merge_strategy = (scopes.get("merge_strategy") or "append").lower()  # append|interleave|user_first
        user_msgs: List[Dict[str, Any]] = []
        if per_user_enabled and user is not None:
            udata = (mem.get("per_user", {}) or {}).get(str(user.id), {})
            uper = (udata.get("per_channel", {}) or {}).get(str(channel_id), {})
            user_msgs = list(uper.get("messages", []))
        
        # Add conversation history with optional user-specific thread
        chan_msgs = msgs[-await self._memory_get_limit(guild, channel_id):]
        if user_msgs:
            # Respect per_user_limit for safety
            per_user_limit = int(scopes.get("per_user_limit", 10)) * 2
            user_tail = user_msgs[-per_user_limit:]
            if merge_strategy == "user_first":
                combined = user_tail + chan_msgs
            elif merge_strategy == "interleave":
                combined = []
                i = j = 0
                while i < len(chan_msgs) or j < len(user_tail):
                    if j < len(user_tail):
                        combined.append(user_tail[j]); j += 1
                    if i < len(chan_msgs):
                        combined.append(chan_msgs[i]); i += 1
            else:  # append (default)
                combined = chan_msgs + user_tail
        else:
            combined = chan_msgs
        
        for m in combined:
            role = m.get("role", "user")
            content = m.get("content", "")
            out.append(ChatMessage(role=role, content=content))
        return out

    async def _memory_remember(self, guild: discord.Guild, channel_id: int, user_text: str, assistant_text: str, user: discord.Member | None = None):
        s = cast(Any, self)
        mem = await s.config.guild(guild).memory()
        scopes = mem.get("scopes", {}) or {}
        per_user_enabled = bool(scopes.get("per_user_enabled", False))
        # Write to channel-level memory (always, backwards compatible)
        limit = await self._memory_get_limit(guild, channel_id)
        async with s.config.guild(guild).memory() as mem_edit:
            per = mem_edit.setdefault("per_channel", {}).setdefault(str(channel_id), {})
            messages = per.setdefault("messages", [])
            now = int(time.time())
            messages.append({"role": "user", "content": user_text, "ts": now})
            messages.append({"role": "assistant", "content": assistant_text, "ts": now})
            if len(messages) > (limit * 2):  # user+assistant pairs
                trim = len(messages) - (limit * 2)
                del messages[0:trim]
            # Pruning policy enforcement
            prune_cfg = mem_edit.get("prune", {})  # guild-level prune config
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
            
            # Optionally also write to per-user memory
            if per_user_enabled and user is not None:
                per_user_limit_pairs = int(scopes.get("per_user_limit", 10))
                u = mem_edit.setdefault("per_user", {}).setdefault(str(user.id), {})
                u_per = u.setdefault("per_channel", {}).setdefault(str(channel_id), {})
                u_msgs = u_per.setdefault("messages", [])
                u_msgs.append({"role": "user", "content": user_text, "ts": now})
                u_msgs.append({"role": "assistant", "content": assistant_text, "ts": now})
                # Trim per-user memory by pairs
                max_len = per_user_limit_pairs * 2
                if len(u_msgs) > max_len:
                    del u_msgs[0: len(u_msgs) - max_len]
                # Apply same prune policy by age
                if max_age_days:
                    cutoff2 = now - (max_age_days * 86400)
                    k = 0
                    while k < len(u_msgs) and int(u_msgs[k].get("ts", now)) < cutoff2:
                        k += 1
                    if k > 0:
                        del u_msgs[0:k]
