"""
Markdown processing and formatting utilities for SkynetV2.

This module provides tools for:
- Discord markdown formatting
- User input markdown parsing
- Response formatting with Discord markdown
- Template markdown processing
"""

import re
from typing import List, Dict, Any, Optional


class DiscordMarkdownFormatter:
    """Utilities for Discord-specific markdown formatting."""
    
    @staticmethod
    def bold(text: str) -> str:
        """Format text in bold: **text**"""
        return f"**{text}**"
    
    @staticmethod 
    def italic(text: str) -> str:
        """Format text in italic: *text*"""
        return f"*{text}*"
    
    @staticmethod
    def code(text: str) -> str:
        """Format text as inline code: `text`"""
        return f"`{text}`"
    
    @staticmethod
    def code_block(text: str, language: str = "") -> str:
        """Format text as code block: ```lang\ntext\n```"""
        return f"```{language}\n{text}\n```"
    
    @staticmethod
    def quote(text: str) -> str:
        """Format text as quote: > text"""
        lines = text.split('\n')
        return '\n'.join(f"> {line}" for line in lines)
    
    @staticmethod
    def spoiler(text: str) -> str:
        """Format text as spoiler: ||text||"""
        return f"||{text}||"
    
    @staticmethod
    def strikethrough(text: str) -> str:
        """Format text with strikethrough: ~~text~~"""
        return f"~~{text}~~"
    
    @staticmethod
    def underline(text: str) -> str:
        """Format text with underline: __text__"""
        return f"__{text}__"
    
    @staticmethod
    def hyperlink(text: str, url: str) -> str:
        """Create Discord hyperlink: [text](url)"""
        return f"[{text}]({url})"
    
    @staticmethod
    def mention_user(user_id: int) -> str:
        """Create user mention: <@user_id>"""
        return f"<@{user_id}>"
    
    @staticmethod
    def mention_channel(channel_id: int) -> str:
        """Create channel mention: <#channel_id>"""
        return f"<#{channel_id}>"
    
    @staticmethod
    def mention_role(role_id: int) -> str:
        """Create role mention: <@&role_id>"""
        return f"<@&{role_id}>"
    
    @staticmethod
    def timestamp(timestamp: int, format_type: str = "f") -> str:
        """Create Discord timestamp: <t:timestamp:format>"""
        return f"<t:{timestamp}:{format_type}>"


class MarkdownTemplateProcessor:
    """Enhanced template processing with markdown support."""
    
    @staticmethod
    def create_structured_prompt(
        title: str,
        sections: List[Dict[str, str]],
        instructions: List[str],
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create a well-structured markdown prompt.
        
        Args:
            title: Main title for the prompt
            sections: List of {"title": "Section Title", "content": "Section content"}
            instructions: List of instruction strings
            context: Optional context variables to include
        """
        fmt = DiscordMarkdownFormatter()
        parts = []
        
        # Title
        parts.append(f"# {title}\n")
        
        # Sections
        for section in sections:
            parts.append(f"## {section['title']}")
            parts.append(section['content'])
            parts.append("")  # blank line
        
        # Instructions
        if instructions:
            parts.append("## Instructions")
            for i, instruction in enumerate(instructions, 1):
                parts.append(f"{i}. {instruction}")
            parts.append("")
        
        # Context (if provided)
        if context:
            parts.append("## Context")
            for key, value in context.items():
                parts.append(f"- {fmt.bold(key)}: {value}")
        
        return "\n".join(parts)
    
    @staticmethod
    def format_response_guidelines() -> str:
        """Generate Discord markdown response guidelines."""
        fmt = DiscordMarkdownFormatter()
        
        guidelines = f"""## Response Formatting Guidelines

{fmt.bold("Use Discord markdown effectively:")}

- Use {fmt.code("**bold**")} for emphasis and headers
- Use {fmt.code("*italic*")} for subtle emphasis  
- Use {fmt.code("`code`")} for technical terms, commands, and file names
- Use {fmt.code("```code blocks```")} for multi-line code or data
- Use {fmt.code("> quotes")} for highlighting important information
- Use numbered/bulleted lists for step-by-step instructions
- Use {fmt.code("||spoilers||")} sparingly for sensitive information

{fmt.bold("Keep responses:")}
- Concise but informative (aim for under 1500 characters when possible)
- Well-structured with clear sections
- Discord-friendly (avoid excessive line breaks)
- Engaging and helpful

{fmt.bold("Use mentions and references appropriately:")}
- Reference channels with {fmt.mention_channel(123456)}  
- Mention users when directly addressing them
- Use timestamps for time-sensitive information"""
        
        return guidelines


class MarkdownParser:
    """Parse and analyze markdown content from user input."""
    
    # Regex patterns for common markdown elements
    PATTERNS = {
        'bold': re.compile(r'\*\*(.*?)\*\*'),
        'italic': re.compile(r'\*(.*?)\*'),
        'code': re.compile(r'`([^`]+)`'),
        'code_block': re.compile(r'```(\w+)?\n?(.*?)\n?```', re.DOTALL),
        'quote': re.compile(r'^> (.+)', re.MULTILINE),
        'strikethrough': re.compile(r'~~(.*?)~~'),
        'spoiler': re.compile(r'\|\|(.*?)\|\|'),
        'hyperlink': re.compile(r'\[([^\]]+)\]\(([^\)]+)\)'),
        'mention_user': re.compile(r'<@!?(\d+)>'),
        'mention_channel': re.compile(r'<#(\d+)>'),
        'mention_role': re.compile(r'<@&(\d+)>'),
    }
    
    @classmethod
    def extract_elements(cls, text: str) -> Dict[str, List[Dict[str, Any]]]:
        """Extract markdown elements from text."""
        elements = {}
        
        for element_type, pattern in cls.PATTERNS.items():
            matches = []
            for match in pattern.finditer(text):
                match_data = {
                    'content': match.group(0),
                    'start': match.start(),
                    'end': match.end(),
                }
                
                # Add specific data based on element type
                if element_type == 'code_block':
                    match_data['language'] = match.group(1) or ''
                    match_data['code'] = match.group(2)
                elif element_type == 'hyperlink':
                    match_data['text'] = match.group(1)
                    match_data['url'] = match.group(2)
                elif element_type in ['mention_user', 'mention_channel', 'mention_role']:
                    match_data['id'] = int(match.group(1))
                else:
                    match_data['text'] = match.group(1)
                
                matches.append(match_data)
            
            if matches:
                elements[element_type] = matches
        
        return elements
    
    @classmethod
    def strip_markdown(cls, text: str) -> str:
        """Remove markdown formatting from text."""
        # Remove in order of complexity to avoid conflicts
        for pattern in cls.PATTERNS.values():
            text = pattern.sub(lambda m: m.group(1) if len(m.groups()) >= 1 else '', text)
        return text
    
    @classmethod
    def has_formatting(cls, text: str) -> bool:
        """Check if text contains markdown formatting."""
        for pattern in cls.PATTERNS.values():
            if pattern.search(text):
                return True
        return False


class ResponseFormatter:
    """Format AI responses with appropriate Discord markdown."""
    
    @staticmethod
    def format_list(items: List[str], ordered: bool = False) -> str:
        """Format a list with markdown."""
        if ordered:
            return '\n'.join(f"{i}. {item}" for i, item in enumerate(items, 1))
        else:
            return '\n'.join(f"• {item}" for item in items)
    
    @staticmethod
    def format_table(headers: List[str], rows: List[List[str]]) -> str:
        """Format a simple markdown table (Discord compatible)."""
        # Discord doesn't support full markdown tables, so use a simple format
        lines = []
        
        # Header
        header_line = " | ".join(f"**{header}**" for header in headers)
        lines.append(header_line)
        
        # Rows
        for row in rows:
            row_line = " | ".join(str(cell) for cell in row)
            lines.append(row_line)
        
        return '\n'.join(lines)
    
    @staticmethod
    def format_error(title: str, message: str, suggestion: Optional[str] = None) -> str:
        """Format an error message with appropriate markdown."""
        fmt = DiscordMarkdownFormatter()
        
        parts = [f"❌ {fmt.bold(title)}"]
        parts.append(message)
        
        if suggestion:
            parts.append(f"\n💡 {fmt.italic(f'Suggestion: {suggestion}')}")
        
        return '\n'.join(parts)
    
    @staticmethod
    def format_success(title: str, message: str, details: Optional[List[str]] = None) -> str:
        """Format a success message with appropriate markdown."""
        fmt = DiscordMarkdownFormatter()
        
        parts = [f"✅ {fmt.bold(title)}"]
        parts.append(message)
        
        if details:
            parts.append("")
            parts.extend(f"• {detail}" for detail in details)
        
        return '\n'.join(parts)
    
    @staticmethod
    def format_info(title: str, content: str, highlight: Optional[List[str]] = None) -> str:
        """Format an informational message."""
        fmt = DiscordMarkdownFormatter()
        
        parts = [f"ℹ️ {fmt.bold(title)}"]
        parts.append(content)
        
        if highlight:
            parts.append("")
            parts.extend(f"▸ {item}" for item in highlight)
        
        return '\n'.join(parts)
    
    @staticmethod
    def truncate_with_markdown(text: str, max_length: int = 1900) -> str:
        """Truncate text while preserving markdown structure."""
        if len(text) <= max_length:
            return text
        
        # Try to truncate at a paragraph break
        paragraphs = text.split('\n\n')
        truncated = ""
        
        for paragraph in paragraphs:
            if len(truncated + paragraph) <= max_length - 50:  # Reserve space for truncation notice
                truncated += paragraph + '\n\n'
            else:
                break
        
        if truncated:
            return truncated.rstrip() + f"\n\n*[Truncated - {len(text) - len(truncated)} characters omitted]*"
        else:
            # Hard truncation as fallback
            return text[:max_length - 20] + "*[Truncated]*"
