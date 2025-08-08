"""
Centralized error handling for SkynetV2.

Provides consistent error mapping, secret redaction, and user-friendly messaging.
"""

import logging
import re
from typing import Optional, Dict, Any

from .api.base import ProviderError

logger = logging.getLogger(__name__)


class ErrorHandler:
    """Centralized error handling and message translation."""
    
    # User-friendly error mappings
    PROVIDER_ERROR_MAPPING = {
        "missing.*api.*key": "AI service not configured. Contact server admin.",
        "invalid.*api.*key": "AI service authentication failed. Contact server admin.", 
        "rate.*limit": "Service busy. Please wait a moment and try again.",
        "quota.*exceeded": "Service quota exceeded. Please try again later.",
        "model.*not.*found": "Selected model unavailable. Try a different model.",
        "connection.*error": "Connection issue. Please try again.",
        "timeout": "Request timed out. Please try again.",
        "insufficient.*funds": "Service account needs funding. Contact server admin.",
        "context.*length": "Message too long. Please shorten your request.",
    }
    
    TOOL_ERROR_MAPPING = {
        "search.*failed": "Search failed. Please check your query and try again.",
        "scraping.*failed": "Unable to scrape that URL. It may be blocked or unavailable.",
        "url.*invalid": "Invalid URL provided. Please check the URL format.",
        "permission.*denied": "You don't have permission to use this tool.",
        "rate.*limit": "Tool usage limit reached. Please wait before trying again.",
        "disabled": "Tool is currently disabled. Enable it with '[p]ai tools enable <tool>'",
    }
    
    CONFIG_ERROR_MAPPING = {
        "provider.*not.*configured": "AI provider not configured. Use '[p]ai provider key set <provider> <key>'",
        "search.*provider.*not.*found": "Search provider not configured. Use '[p]ai search set <provider>'",
        "model.*not.*set": "AI model not selected. Use '[p]ai model set <provider> <model>'",
    }
    
    @classmethod
    def redact_secrets(cls, text: str) -> str:
        """Redact sensitive information from text."""
        if not isinstance(text, str):
            return str(text)
        
        # Redact API keys (various formats)
        text = re.sub(r'(sk-[a-zA-Z0-9]{20,})', r'\1'[:8] + '...' + r'\1'[-4:] if len(r'\1') > 12 else 'sk-...XXXX', text)
        text = re.sub(r'(key["\']?\s*[:=]\s*["\']?)([a-zA-Z0-9]{20,})', r'\1' + r'\2'[:4] + '...' + r'\2'[-4:] if len(r'\2') > 8 else r'\1...XXXX', text)
        
        # Redact bearer tokens
        text = re.sub(r'(Bearer\s+)([a-zA-Z0-9+/]{20,})', r'\1' + r'\2'[:8] + '...' + r'\2'[-4:], text, re.IGNORECASE)
        
        # Redact URLs with auth
        text = re.sub(r'(https?://[^@\s]*:)([^@\s]+)(@)', r'\1***\3', text)
        
        # Redact credit card numbers (basic pattern)
        text = re.sub(r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b', '****-****-****-****', text)
        
        return text
    
    @classmethod
    def get_user_friendly_error(cls, error: Exception, context: str = "general") -> str:
        """Convert exception to user-friendly message."""
        error_text = str(error).lower()
        
        # Check for provider errors first
        if isinstance(error, ProviderError) or context == "provider":
            for pattern, message in cls.PROVIDER_ERROR_MAPPING.items():
                if re.search(pattern, error_text, re.IGNORECASE):
                    return message
            return "AI service issue. Please try again or contact admin."
        
        # Check for tool errors
        if context == "tool":
            for pattern, message in cls.TOOL_ERROR_MAPPING.items():
                if re.search(pattern, error_text, re.IGNORECASE):
                    return message
            return "Tool execution failed. Please try again."
        
        # Check for config errors
        if context == "config":
            for pattern, message in cls.CONFIG_ERROR_MAPPING.items():
                if re.search(pattern, error_text, re.IGNORECASE):
                    return message
            return "Configuration issue. Check setup and try again."
        
        # Generic error mapping
        if "permission" in error_text:
            return "You don't have permission for this action."
        elif "not found" in error_text:
            return "Requested item not found. Please check and try again."
        elif "invalid" in error_text:
            return "Invalid input. Please check your request and try again."
        elif "timeout" in error_text:
            return "Operation timed out. Please try again."
        
        # Default fallback
        return "Something went wrong. Please try again."
    
    @classmethod
    def log_error(cls, error: Exception, context: str = "", extra_data: Optional[Dict[str, Any]] = None):
        """Log error with proper redaction and context."""
        # Redact error message and traceback
        error_msg = cls.redact_secrets(str(error))
        
        log_data = {
            "error_type": type(error).__name__,
            "context": context,
            "message": error_msg
        }
        
        if extra_data:
            # Redact any sensitive data in extra_data
            redacted_extra = {}
            for key, value in extra_data.items():
                if isinstance(value, str):
                    redacted_extra[key] = cls.redact_secrets(value)
                else:
                    redacted_extra[key] = value
            log_data.update(redacted_extra)
        
        logger.error(f"Error in {context}: {error_msg}", extra=log_data)
    
    @classmethod
    def safe_error_response(cls, error: Exception, context: str = "general", 
                          include_type: bool = False) -> str:
        """Get safe error response for user display."""
        user_msg = cls.get_user_friendly_error(error, context)
        
        if include_type and not isinstance(error, ProviderError):
            # Only include error type for non-provider errors to avoid leaking provider internals
            error_type = type(error).__name__
            if error_type not in ["ValueError", "TypeError", "AttributeError"]:
                user_msg += f" ({error_type})"
        
        return user_msg


class ToolExecutionWrapper:
    """Wrapper for tool execution with telemetry and error handling."""
    
    def __init__(self, cog):
        self.cog = cog
        self.error_handler = ErrorHandler()
    
    async def execute_with_error_handling(self, tool_name: str, tool_func, *args, **kwargs):
        """Execute tool function with comprehensive error handling and telemetry."""
        import time
        
        start_time = time.perf_counter()
        success = False
        result = None
        error_msg = None
        
        try:
            # Execute the tool function
            result = await tool_func(*args, **kwargs)
            success = True
            return result
            
        except ProviderError as e:
            error_msg = self.error_handler.safe_error_response(e, "provider")
            self.error_handler.log_error(e, f"tool:{tool_name}", {
                "tool": tool_name,
                "args_count": len(args),
                "kwargs_keys": list(kwargs.keys())
            })
            raise Exception(error_msg) from e
            
        except Exception as e:
            error_msg = self.error_handler.safe_error_response(e, "tool")
            self.error_handler.log_error(e, f"tool:{tool_name}", {
                "tool": tool_name,
                "args_count": len(args),
                "kwargs_keys": list(kwargs.keys())
            })
            raise Exception(error_msg) from e
            
        finally:
            # Record telemetry regardless of success/failure
            execution_time_ms = int((time.perf_counter() - start_time) * 1000)
            
            if hasattr(self.cog, '_record_tool_usage'):
                # Extract guild from args/kwargs for telemetry
                guild = None
                if args and hasattr(args[0], 'guild'):
                    guild = args[0].guild
                elif 'guild' in kwargs:
                    guild = kwargs['guild']
                elif 'ctx' in kwargs and hasattr(kwargs['ctx'], 'guild'):
                    guild = kwargs['ctx'].guild
                
                if guild:
                    await self.cog._record_tool_usage(
                        guild=guild,
                        tool_name=tool_name,
                        latency_ms=execution_time_ms,
                        success=success
                    )
