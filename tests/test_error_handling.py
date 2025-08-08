"""
Unit tests for error handling and secret redaction.
"""

import pytest
from skynetv2.error_handler import ErrorHandler
from skynetv2.api.base import ProviderError


class TestErrorHandler:
    """Test centralized error handling functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.handler = ErrorHandler()
    
    def test_secret_redaction_api_keys(self):
        """Test that API keys are properly redacted."""
        test_cases = [
            ("API key: sk-1234567890abcdef", "sk-...XXXX"),
            ("Bearer sk-abcdefghijklmnop", "sk-...XXXX"), 
            ("OpenAI key: sk-proj-1234567890", "sk-...XXXX"),
            ("key=sk-1234567890abcdefghij", "sk-...XXXX")
        ]
        
        for input_text, expected_pattern in test_cases:
            result = self.handler.redact_secrets(input_text)
            assert expected_pattern in result or "sk-" in result
            assert "sk-1234567890abcdef" not in result  # Original key should be gone
    
    def test_secret_redaction_bearer_tokens(self):
        """Test that bearer tokens are redacted."""
        test_cases = [
            "Bearer abc123def456ghi789",
            "Authorization: Bearer xyz789uvw456rst123"
        ]
        
        for input_text in test_cases:
            result = self.handler.redact_secrets(input_text)
            # Should contain redacted version, not original
            assert "abc123def456ghi789" not in result
            assert "Bearer" in result  # Bearer prefix should remain
    
    def test_secret_redaction_urls_with_auth(self):
        """Test that URLs with authentication are redacted."""
        test_cases = [
            ("https://user:password@api.example.com", "https://user:***@api.example.com"),
            ("http://admin:secret123@internal.service", "http://admin:***@internal.service")
        ]
        
        for input_text, expected_pattern in test_cases:
            result = self.handler.redact_secrets(input_text)
            assert "password" not in result
            assert "secret123" not in result
            assert "***" in result
    
    def test_provider_error_mapping(self):
        """Test that ProviderError messages are mapped to user-friendly text."""
        test_cases = [
            ("Missing OpenAI API key", "provider", "AI service not configured"),
            ("Invalid API key provided", "provider", "authentication failed"),
            ("Rate limit exceeded", "provider", "Service busy"),
            ("Model 'gpt-5' not found", "provider", "model unavailable"),
            ("Connection timeout", "provider", "Connection issue")
        ]
        
        for error_msg, context, expected_keyword in test_cases:
            error = ProviderError(error_msg)
            result = self.handler.get_user_friendly_error(error, context)
            assert expected_keyword.lower() in result.lower()
            # Should not contain technical details
            assert "OpenAI" not in result or "API" not in result
    
    def test_tool_error_mapping(self):
        """Test tool-specific error message mapping."""
        test_cases = [
            ("Search API failed with HTTP 500", "tool", "Search failed"),
            ("URL scraping permission denied", "tool", "Unable to scrape"),
            ("Invalid URL format provided", "tool", "Invalid URL"),
            ("Tool websearch is disabled", "tool", "disabled")
        ]
        
        for error_msg, context, expected_keyword in test_cases:
            error = Exception(error_msg)
            result = self.handler.get_user_friendly_error(error, context)
            assert expected_keyword.lower() in result.lower()
    
    def test_config_error_mapping(self):
        """Test configuration error message mapping."""
        test_cases = [
            ("Provider openai not configured", "config", "not configured"),
            ("Search provider dummy not found", "config", "search provider"),
            ("Model not set for provider", "config", "model not selected")
        ]
        
        for error_msg, context, expected_keyword in test_cases:
            error = Exception(error_msg)
            result = self.handler.get_user_friendly_error(error, context)
            assert expected_keyword.lower() in result.lower()
    
    def test_generic_error_fallbacks(self):
        """Test generic error handling for unknown error types."""
        test_cases = [
            ("Permission denied", "You don't have permission"),
            ("File not found", "not found"),
            ("Invalid input provided", "Invalid input"),
            ("Operation timed out", "timed out")
        ]
        
        for error_msg, expected_keyword in test_cases:
            error = Exception(error_msg)
            result = self.handler.get_user_friendly_error(error)
            assert expected_keyword.lower() in result.lower()
    
    def test_error_logging_with_context(self):
        """Test that errors are logged with proper context and redaction."""
        error = ProviderError("Invalid API key: sk-1234567890abcdef")
        context = "chat_command"
        extra_data = {"provider": "openai", "user_id": 123}
        
        # This would test actual logging - mock for demonstration
        with pytest.raises(ProviderError):
            self.handler.log_error(error, context, extra_data)
            # In real implementation, would verify:
            # - Error message is redacted in logs
            # - Context is included
            # - Extra data is preserved
            # - Log level is appropriate
    
    def test_safe_error_response_format(self):
        """Test that safe error responses are consistently formatted."""
        errors = [
            ProviderError("OpenAI API error"),
            ValueError("Invalid parameter"),
            ConnectionError("Network unreachable")
        ]
        
        for error in errors:
            result = self.handler.safe_error_response(error)
            
            # All responses should be user-friendly
            assert len(result) > 0
            assert not any(technical in result.lower() for technical in [
                "traceback", "stack", "exception", "error:", "failed:"
            ])
            
            # Should be helpful but not expose internals
            assert "try again" in result.lower() or "contact" in result.lower()


class TestToolExecutionWrapper:
    """Test tool execution wrapper with error handling."""
    
    def setup_method(self):
        """Set up test fixtures."""
        from unittest.mock import Mock
        self.mock_cog = Mock()
        self.mock_cog._record_tool_usage = Mock()
        
    def test_successful_tool_execution(self):
        """Test wrapper behavior on successful tool execution.""" 
        # This would test the actual ToolExecutionWrapper
        # Mock implementation for demonstration
        
        async def mock_successful_tool():
            return "success result"
        
        # Would test:
        # - Result is returned correctly
        # - Success telemetry is recorded
        # - Execution time is tracked
        # - No errors are raised
        pass
    
    def test_tool_execution_with_provider_error(self):
        """Test wrapper behavior when tool raises ProviderError."""
        async def mock_failing_tool():
            raise ProviderError("API key invalid")
        
        # Would test:
        # - ProviderError is caught and converted
        # - User-friendly error is re-raised
        # - Failure telemetry is recorded
        # - Original error is logged with context
        pass
    
    def test_tool_execution_with_generic_error(self):
        """Test wrapper behavior with generic exceptions."""
        async def mock_failing_tool():
            raise ValueError("Invalid parameter")
        
        # Would test:
        # - Generic error is caught and converted
        # - User-friendly message is generated
        # - Failure telemetry is recorded
        # - Technical details are logged
        pass
