"""Logging system for SkynetV2 - tracks system and guild events."""
from __future__ import annotations

import asyncio
import json
import time
from collections import deque
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
import discord

class LogEntry:
    """Represents a single log entry."""
    
    def __init__(self, level: str, message: str, guild_id: Optional[int] = None, 
                 user_id: Optional[int] = None, channel_id: Optional[int] = None, 
                 extra_data: Optional[Dict] = None):
        self.timestamp = datetime.now(timezone.utc)
        self.level = level  # INFO, WARNING, ERROR, DEBUG
        self.message = message
        self.guild_id = guild_id
        self.user_id = user_id
        self.channel_id = channel_id
        self.extra_data = extra_data or {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert log entry to dictionary for JSON serialization."""
        return {
            'timestamp': self.timestamp.isoformat(),
            'level': self.level,
            'message': self.message,
            'guild_id': self.guild_id,
            'user_id': self.user_id,
            'channel_id': self.channel_id,
            'extra_data': self.extra_data
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LogEntry':
        """Create log entry from dictionary."""
        entry = cls(
            level=data['level'],
            message=data['message'],
            guild_id=data.get('guild_id'),
            user_id=data.get('user_id'),
            channel_id=data.get('channel_id'),
            extra_data=data.get('extra_data', {})
        )
        entry.timestamp = datetime.fromisoformat(data['timestamp'])
        return entry

class LoggingSystem:
    """In-memory logging system with persistence capabilities."""
    
    def __init__(self, max_entries: int = 10000):
        self.max_entries = max_entries
        self.system_logs: deque = deque(maxlen=max_entries)
        self.guild_logs: Dict[int, deque] = {}  # guild_id -> deque of logs
        self._lock = asyncio.Lock()
    
    async def log(self, level: str, message: str, guild_id: Optional[int] = None, 
                  user_id: Optional[int] = None, channel_id: Optional[int] = None, 
                  extra_data: Optional[Dict] = None):
        """Add a log entry."""
        async with self._lock:
            entry = LogEntry(level, message, guild_id, user_id, channel_id, extra_data)
            
            # Add to system logs
            self.system_logs.append(entry)
            
            # Add to guild-specific logs if guild_id is provided
            if guild_id:
                if guild_id not in self.guild_logs:
                    self.guild_logs[guild_id] = deque(maxlen=1000)  # Smaller limit per guild
                self.guild_logs[guild_id].append(entry)
    
    async def log_info(self, message: str, **kwargs):
        """Log an info message."""
        await self.log("INFO", message, **kwargs)
    
    async def log_warning(self, message: str, **kwargs):
        """Log a warning message."""
        await self.log("WARNING", message, **kwargs)
    
    async def log_error(self, message: str, **kwargs):
        """Log an error message."""
        await self.log("ERROR", message, **kwargs)
    
    async def log_debug(self, message: str, **kwargs):
        """Log a debug message."""
        await self.log("DEBUG", message, **kwargs)
    
    async def get_system_logs(self, limit: int = 100, level_filter: Optional[str] = None) -> List[LogEntry]:
        """Get recent system logs."""
        async with self._lock:
            logs = list(self.system_logs)
            
            if level_filter:
                logs = [log for log in logs if log.level == level_filter]
            
            # Return most recent first
            logs.reverse()
            return logs[:limit]
    
    async def get_guild_logs(self, guild_id: int, limit: int = 100, 
                           level_filter: Optional[str] = None) -> List[LogEntry]:
        """Get recent logs for a specific guild."""
        async with self._lock:
            if guild_id not in self.guild_logs:
                return []
            
            logs = list(self.guild_logs[guild_id])
            
            if level_filter:
                logs = [log for log in logs if log.level == level_filter]
            
            # Return most recent first
            logs.reverse()
            return logs[:limit]
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get logging statistics."""
        async with self._lock:
            total_logs = len(self.system_logs)
            guild_count = len(self.guild_logs)
            
            # Count by level
            level_counts = {}
            for log in self.system_logs:
                level_counts[log.level] = level_counts.get(log.level, 0) + 1
            
            return {
                'total_logs': total_logs,
                'guild_count': guild_count,
                'level_counts': level_counts,
                'oldest_log': self.system_logs[0].timestamp.isoformat() if self.system_logs else None,
                'newest_log': self.system_logs[-1].timestamp.isoformat() if self.system_logs else None
            }

# Global logging instance
_global_logger: Optional[LoggingSystem] = None

def get_logger() -> LoggingSystem:
    """Get the global logging instance."""
    global _global_logger
    if _global_logger is None:
        _global_logger = LoggingSystem()
    return _global_logger

# Convenience functions
async def log_info(message: str, **kwargs):
    """Log an info message."""
    await get_logger().log_info(message, **kwargs)

async def log_warning(message: str, **kwargs):
    """Log a warning message."""
    await get_logger().log_warning(message, **kwargs)

async def log_error(message: str, **kwargs):
    """Log an error message."""
    await get_logger().log_error(message, **kwargs)

async def log_debug(message: str, **kwargs):
    """Log a debug message."""
    await get_logger().log_debug(message, **kwargs)

# Event logging functions for specific SkynetV2 events
async def log_ai_request(guild: discord.Guild, user: discord.User, channel: discord.TextChannel, 
                        provider: str, model: str, tokens_used: int = 0):
    """Log an AI request."""
    await log_info(
        f"AI request from {user.name} in #{channel.name}",
        guild_id=guild.id,
        user_id=user.id,
        channel_id=channel.id,
        extra_data={
            'type': 'ai_request',
            'provider': provider,
            'model': model,
            'tokens_used': tokens_used
        }
    )

async def log_listening_event(guild: discord.Guild, channel: discord.TextChannel, 
                             mode: str, triggered: bool, user: discord.User):
    """Log a passive listening event."""
    await log_info(
        f"Listening event in #{channel.name}: mode={mode}, triggered={triggered}",
        guild_id=guild.id,
        user_id=user.id,
        channel_id=channel.id,
        extra_data={
            'type': 'listening_event',
            'mode': mode,
            'triggered': triggered
        }
    )

async def log_config_change(guild: discord.Guild, user: discord.User, 
                           setting: str, old_value: Any, new_value: Any):
    """Log a configuration change."""
    await log_info(
        f"Config changed by {user.name}: {setting} = {new_value}",
        guild_id=guild.id,
        user_id=user.id,
        extra_data={
            'type': 'config_change',
            'setting': setting,
            'old_value': str(old_value),
            'new_value': str(new_value)
        }
    )

async def log_rate_limit_hit(guild: discord.Guild, user: discord.User, 
                            channel: discord.TextChannel, limit_type: str):
    """Log a rate limit being hit."""
    await log_warning(
        f"Rate limit hit for {user.name} in #{channel.name}: {limit_type}",
        guild_id=guild.id,
        user_id=user.id,
        channel_id=channel.id,
        extra_data={
            'type': 'rate_limit_hit',
            'limit_type': limit_type
        }
    )

async def log_error_event(guild: Optional[discord.Guild], error: Exception, 
                         context: str, user: Optional[discord.User] = None):
    """Log an error event."""
    await log_error(
        f"Error in {context}: {str(error)}",
        guild_id=guild.id if guild else None,
        user_id=user.id if user else None,
        extra_data={
            'type': 'error_event',
            'context': context,
            'error_type': type(error).__name__,
            'error_message': str(error)
        }
    )


# Convenience functions for accessing logs
async def get_system_logs(limit: int = 50) -> List[LogEntry]:
    """Get system-wide logs."""
    return await get_logger().get_system_logs(limit)

async def get_guild_logs(guild_id: int, limit: int = 50) -> List[LogEntry]:
    """Get logs for a specific guild."""
    return await get_logger().get_guild_logs(guild_id, limit)
