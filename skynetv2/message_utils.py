"""
Message handling utilities for SkynetV2.

Handles long message chunking, conversation context, and Discord message limits.
"""
from __future__ import annotations

import re
import discord
from typing import List, Optional, Tuple
import io

class MessageChunker:
    """Handles intelligent message chunking for Discord's 2000 character limit."""
    
    MAX_MESSAGE_LENGTH = 2000
    MAX_FILE_SIZE = 8 * 1024 * 1024  # 8MB limit for Discord files
    
    @classmethod
    def chunk_message(cls, text: str, max_length: int = MAX_MESSAGE_LENGTH) -> List[str]:
        """
        Split a message into chunks that fit Discord's character limit.
        
        Tries to split on natural boundaries (sentences, paragraphs, code blocks)
        rather than arbitrary character counts.
        """
        if len(text) <= max_length:
            return [text]
        
        chunks = []
        remaining = text
        
        while remaining:
            if len(remaining) <= max_length:
                chunks.append(remaining)
                break
            
            # Try to find a good split point
            chunk = remaining[:max_length]
            split_point = cls._find_split_point(chunk)
            
            if split_point > 0:
                # Split at the good point
                chunks.append(remaining[:split_point].rstrip())
                remaining = remaining[split_point:].lstrip()
            else:
                # Fallback: split at max length with continuation indicator
                chunks.append(chunk + "...")
                remaining = "..." + remaining[max_length:]
        
        return [chunk for chunk in chunks if chunk.strip()]
    
    @classmethod
    def _find_split_point(cls, text: str) -> int:
        """Find the best point to split text, preferring natural boundaries."""
        # Try to split on paragraph breaks
        match = re.search(r'\n\s*\n', text[::-1])  # Search backwards
        if match:
            return len(text) - match.start()
        
        # Try to split on sentence endings
        match = re.search(r'[.!?]\s+', text[::-1])
        if match and match.start() > 50:  # Don't split too early
            return len(text) - match.start()
        
        # Try to split on code block boundaries  
        match = re.search(r'```\n', text[::-1])
        if match:
            return len(text) - match.start()
        
        # Try to split on line breaks
        match = re.search(r'\n', text[::-1])
        if match and match.start() > 50:
            return len(text) - match.start()
        
        # Try to split on word boundaries
        match = re.search(r'\s', text[::-1])
        if match and match.start() > 50:
            return len(text) - match.start()
        
        return 0  # No good split point found
    
    @classmethod
    async def send_long_message(cls, channel: discord.abc.Messageable, content: str, 
                               reference: Optional[discord.Message] = None) -> List[discord.Message]:
        """
        Send a potentially long message, handling chunking and file uploads as needed.
        
        For very long messages, creates a text file attachment instead of multiple messages.
        """
        if not content or not content.strip():
            return []
        
        content = content.strip()
        
        # If message is short enough, send normally
        if len(content) <= cls.MAX_MESSAGE_LENGTH:
            try:
                msg = await channel.send(content, reference=reference)
                return [msg]
            except discord.HTTPException:
                # Fallback if reference fails
                msg = await channel.send(content)
                return [msg]
        
        # If message is very long, consider using a file attachment
        if len(content) > cls.MAX_MESSAGE_LENGTH * 3:
            return await cls._send_as_file(channel, content, reference)
        
        # Otherwise, chunk the message
        chunks = cls.chunk_message(content)
        sent_messages = []
        
        for i, chunk in enumerate(chunks):
            try:
                # Only use reference for the first message
                msg_ref = reference if i == 0 else None
                msg = await channel.send(chunk, reference=msg_ref)
                sent_messages.append(msg)
            except discord.HTTPException as e:
                # If sending fails, log and continue
                print(f"[MessageChunker] Failed to send chunk {i+1}/{len(chunks)}: {e}")
        
        return sent_messages
    
    @classmethod
    async def _send_as_file(cls, channel: discord.abc.Messageable, content: str,
                           reference: Optional[discord.Message] = None) -> List[discord.Message]:
        """Send content as a text file attachment."""
        try:
            # Create file object
            file_content = content.encode('utf-8')
            if len(file_content) > cls.MAX_FILE_SIZE:
                # Truncate if too large
                file_content = file_content[:cls.MAX_FILE_SIZE - 100]
                file_content += b"\n\n[Content truncated due to size limit]"
            
            file = discord.File(
                io.BytesIO(file_content),
                filename="response.txt",
                description="AI response (too long for message)"
            )
            
            msg = await channel.send(
                "📄 **Response attached as file** (content was too long for a message)",
                file=file,
                reference=reference
            )
            return [msg]
            
        except discord.HTTPException as e:
            print(f"[MessageChunker] Failed to send file attachment: {e}")
            # Fallback to chunked messages
            chunks = cls.chunk_message(content, cls.MAX_MESSAGE_LENGTH)
            sent_messages = []
            for i, chunk in enumerate(chunks[:5]):  # Limit to 5 chunks as fallback
                try:
                    msg_ref = reference if i == 0 else None
                    msg = await channel.send(chunk, reference=msg_ref)
                    sent_messages.append(msg)
                except discord.HTTPException:
                    break
            return sent_messages


class ConversationManager:
    """Manages conversation context and threading for more natural interactions."""
    
    @staticmethod
    def should_include_context(message: discord.Message, listening_mode: str) -> bool:
        """
        Determine if we should include conversation context based on the trigger type.
        
        Memory is now always included for all modes to maintain conversation continuity.
        """
        # Always include context for all modes to ensure consistent memory behavior
        return True
    
    @staticmethod
    def format_message_reference(message: discord.Message) -> str:
        """Format a message for inclusion in conversation context."""
        author_name = message.author.display_name
        content = message.content or "[no text content]"
        
        # Truncate very long messages in context
        if len(content) > 200:
            content = content[:197] + "..."
        
        return f"**{author_name}:** {content}"
    
    @staticmethod
    def extract_mention_content(message: discord.Message, bot_user: discord.User) -> str:
        """Extract content from a message that mentions the bot, cleaning up the mention."""
        content = message.content or ""
        
        # Remove bot mention from content
        if bot_user:
            content = content.replace(f"<@{bot_user.id}>", "").replace(f"<@!{bot_user.id}>", "")
        
        # Clean up extra whitespace
        content = re.sub(r'\s+', ' ', content).strip()
        
        # If content is empty after removing mention, provide default
        if not content:
            content = "Hello"
        
        return content
