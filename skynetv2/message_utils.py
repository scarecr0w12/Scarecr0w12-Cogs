"""
Message handling utilities for SkynetV2.

Handles long message chunking, conversation context, and Discord message limits.
"""
from __future__ import annotations

import re
import discord
import time
from typing import List, Optional, Tuple, Dict, Any
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


class SmartReplyAnalyzer:
    """
    Analyzes whether the bot should respond in 'all' mode based on conversation context.
    
    Helps prevent the bot from being too chatty by detecting:
    - Direct replies between humans
    - Active human-to-human conversations  
    - Messages that are clearly not meant for the bot
    
    While still allowing responses to:
    - General questions and requests
    - Bot-directed content
    - Messages after periods of inactivity
    """
    
    @staticmethod
    def should_respond_in_all_mode(
        message: discord.Message,
        recent_messages: List[discord.Message],
        bot_user: discord.User,
        smart_config: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """
        Determine if the bot should respond to a message in 'all' mode.
        
        Returns:
            Tuple[bool, str]: (should_respond, reason_for_decision)
        """
        if not smart_config.get("enabled", True):
            return True, "Smart replies disabled - responding as normal 'all' mode"
        
        content = message.content or ""
        sensitivity = smart_config.get("sensitivity", 3)
        
        # Always respond if bot is mentioned
        if bot_user in message.mentions:
            return True, "Bot is mentioned in message"
        
        # Ignore very short messages if configured
        if smart_config.get("ignore_short_messages", True) and len(content.strip()) < 10:
            return False, "Message too short (smart replies ignore short messages)"
        
        # Check if this is a direct reply to another human
        if SmartReplyAnalyzer._is_direct_reply_to_human(message, bot_user):
            return False, "Message is a direct reply to another human"
        
        # Check if this message contains specific mentions to other humans (not bot)
        human_mentions = [mention for mention in message.mentions if mention != bot_user]
        if human_mentions and len(human_mentions) == 1:
            # Single human mention might be directed conversation
            if sensitivity >= 3:  # Balanced or more conservative
                return False, f"Message mentions specific user: {human_mentions[0].display_name}"
        
        # Check for bot-indicating content
        has_bot_indicators = SmartReplyAnalyzer._contains_bot_indicators(content, smart_config)
        if has_bot_indicators:
            return True, "Message contains bot-indicating keywords or patterns"
        
        # Analyze recent conversation context
        context_analysis = SmartReplyAnalyzer._analyze_conversation_context(
            message, recent_messages, bot_user, smart_config
        )
        
        if context_analysis["active_human_conversation"]:
            if sensitivity >= 4:  # Conservative or very conservative
                return False, "Active human-to-human conversation detected"
            elif sensitivity >= 3 and not context_analysis["channel_quiet"]:
                return False, "Recent human conversation activity detected"
        
        # Check question patterns based on sensitivity
        has_question = SmartReplyAnalyzer._appears_to_be_question(content)
        if smart_config.get("require_question_or_keyword", False):
            if not (has_question or has_bot_indicators):
                return False, "No question or bot keywords detected (strict mode)"
        
        # Sensitivity-based decision making
        if sensitivity == 1:  # Very responsive
            return True, "Very responsive mode - responding to most messages"
        elif sensitivity == 2:  # Responsive
            if context_analysis["channel_quiet"] or has_question:
                return True, "Responsive mode - channel quiet or question detected"
            return False, "Responsive mode - no strong indicators to respond"
        elif sensitivity == 3:  # Balanced (default)
            if context_analysis["channel_quiet"] or has_question or has_bot_indicators:
                return True, "Balanced mode - good indicators to respond"
            if context_analysis["recent_bot_activity"]:
                return False, "Balanced mode - bot was recently active"
            return True, "Balanced mode - general message in appropriate context"
        elif sensitivity == 4:  # Conservative
            if has_question or (context_analysis["channel_quiet"] and has_bot_indicators):
                return True, "Conservative mode - clear question or quiet channel with indicators"
            return False, "Conservative mode - no strong indicators to respond"
        else:  # sensitivity == 5, Very conservative
            if has_question and (has_bot_indicators or context_analysis["channel_quiet"]):
                return True, "Very conservative mode - question with clear indicators"
            return False, "Very conservative mode - being very selective"
    
    @staticmethod
    def _is_direct_reply_to_human(message: discord.Message, bot_user: discord.User) -> bool:
        """Check if message is a direct reply to another human (not the bot)."""
        if not message.reference or not message.reference.resolved:
            return False
        
        replied_to_message = message.reference.resolved
        if isinstance(replied_to_message, discord.Message):
            return replied_to_message.author != bot_user and not replied_to_message.author.bot
        
        return False
    
    @staticmethod
    def _contains_bot_indicators(content: str, smart_config: Dict[str, Any]) -> bool:
        """Check if message contains keywords or patterns that suggest it's meant for the bot."""
        content_lower = content.lower()
        
        # Check configured keywords
        keywords = smart_config.get("response_keywords", [])
        for keyword in keywords:
            if keyword.lower() in content_lower:
                return True
        
        # Check for common bot-directed patterns
        bot_patterns = [
            r"\b(help|assist|support)\b",
            r"\b(how to|how do|how can)\b", 
            r"\b(what is|what are|what's)\b",
            r"\b(why is|why are|why does)\b",
            r"\b(when is|when are|when does)\b",
            r"\b(where is|where are|where can)\b",
            r"\b(can you|could you|would you)\b",
            r"\b(please|thanks|thank you)\b",
            r"[?]{1,3}$"  # Ends with question marks
        ]
        
        for pattern in bot_patterns:
            if re.search(pattern, content_lower):
                return True
        
        return False
    
    @staticmethod
    def _appears_to_be_question(content: str) -> bool:
        """Check if message appears to be a question."""
        content_lower = content.lower().strip()
        
        # Ends with question mark
        if content_lower.endswith('?'):
            return True
        
        # Starts with question words
        question_starters = [
            "how", "what", "why", "when", "where", "who", "which",
            "can", "could", "would", "should", "is", "are", "do", "does", "did"
        ]
        
        first_word = content_lower.split()[0] if content_lower.split() else ""
        return first_word in question_starters
    
    @staticmethod
    def _analyze_conversation_context(
        current_message: discord.Message,
        recent_messages: List[discord.Message],
        bot_user: discord.User,
        smart_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Analyze recent conversation context to inform response decisions."""
        now = time.time()
        quiet_time = smart_config.get("quiet_time_seconds", 300)  # 5 minutes default
        
        # Filter recent messages (last 15 messages or 10 minutes, whichever is more)
        cutoff_time = now - 600  # 10 minutes
        relevant_messages = [
            msg for msg in recent_messages[-15:] 
            if msg.created_at.timestamp() > cutoff_time and not msg.author.bot
        ]
        
        # Check for channel quietness
        last_human_message = None
        for msg in reversed(relevant_messages):
            if msg.author != bot_user and not msg.author.bot:
                last_human_message = msg
                break
        
        channel_quiet = (
            last_human_message is None or 
            (now - last_human_message.created_at.timestamp()) > quiet_time
        )
        
        # Detect human-to-human conversation patterns
        recent_human_messages = [
            msg for msg in relevant_messages[-8:] 
            if msg.author != bot_user and not msg.author.bot
        ]
        
        active_human_conversation = False
        if len(recent_human_messages) >= 3:
            # Check for back-and-forth between specific users
            authors = [msg.author.id for msg in recent_human_messages[-6:]]
            unique_authors = set(authors)
            
            if len(unique_authors) == 2:
                # Two people talking back and forth
                active_human_conversation = True
            elif len(unique_authors) <= 3 and len(recent_human_messages) >= 4:
                # Small group active conversation
                recent_times = [msg.created_at.timestamp() for msg in recent_human_messages[-4:]]
                if recent_times[-1] - recent_times[0] < 120:  # 2 minutes of recent activity
                    active_human_conversation = True
        
        # Check recent bot activity
        recent_bot_messages = [
            msg for msg in relevant_messages[-5:]
            if msg.author == bot_user
        ]
        recent_bot_activity = len(recent_bot_messages) > 0
        
        return {
            "channel_quiet": channel_quiet,
            "active_human_conversation": active_human_conversation,
            "recent_bot_activity": recent_bot_activity,
            "recent_message_count": len(relevant_messages),
            "time_since_last_human": (
                now - last_human_message.created_at.timestamp() 
                if last_human_message else float('inf')
            )
        }
