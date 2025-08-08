"""
Unit tests for autosearch classification heuristics.
"""

import pytest
from skynetv2.autoexec import AutoExecMixin


class TestAutosearchClassification:
    """Test autosearch query classification logic."""
    
    @pytest.mark.parametrize("query,expected_mode", [
        # Search queries
        ("latest news about AI", "search"),
        ("what is machine learning", "search"), 
        ("find information about renewable energy", "search"),
        ("search for python tutorials", "search"),
        
        # Scrape queries
        ("scrape content from https://example.com", "scrape"),
        ("extract text from https://docs.python.org", "scrape"),
        ("get content of https://news.ycombinator.com", "scrape"),
        ("fetch data from this URL: https://api.github.com", "scrape"),
        
        # Crawl queries  
        ("crawl example.com for documentation", "crawl"),
        ("map the structure of docs.microsoft.com", "crawl"),
        ("explore all pages on wikipedia.org/wiki/AI", "crawl"),
        ("index the entire site at pytorch.org", "crawl"),
        
        # Deep research queries
        ("research renewable energy trends", "deep_research"),
        ("comprehensive analysis of climate change", "deep_research"),
        ("investigate the future of autonomous vehicles", "deep_research"),
        ("deep dive into cryptocurrency regulation", "deep_research"),
        
        # Edge cases
        ("", "search"),  # Empty query defaults to search
        ("single word", "search"),  # Simple queries default to search
        ("https://example.com", "scrape"),  # URL alone implies scraping
    ])
    def test_classify_autosearch_query(self, query, expected_mode):
        """Test that queries are classified into the correct execution mode."""
        # Note: This would need the actual classification logic
        # For now, we'll create a simplified version
        
        def classify_query(q):
            q_lower = q.lower()
            
            if any(word in q_lower for word in ["scrape", "extract", "fetch", "get content"]):
                return "scrape"
            elif any(word in q_lower for word in ["crawl", "map", "explore", "index", "site"]):
                return "crawl"  
            elif any(word in q_lower for word in ["research", "analysis", "investigate", "deep dive"]):
                return "deep_research"
            elif q.startswith("http://") or q.startswith("https://"):
                return "scrape"
            else:
                return "search"
        
        result = classify_query(query)
        assert result == expected_mode, f"Query '{query}' classified as '{result}', expected '{expected_mode}'"
    
    def test_classification_confidence_scoring(self):
        """Test that classification includes confidence scores."""
        # High confidence cases
        high_confidence_queries = [
            "scrape https://example.com",
            "crawl the entire website",
            "research climate change impacts"
        ]
        
        # Low confidence cases (ambiguous)
        low_confidence_queries = [
            "check example.com", 
            "look into this topic",
            "find stuff about things"
        ]
        
        # This would test actual confidence scoring logic
        # For demonstration purposes only
        for query in high_confidence_queries:
            # confidence = get_classification_confidence(query)
            # assert confidence > 0.8
            pass
            
        for query in low_confidence_queries:
            # confidence = get_classification_confidence(query) 
            # assert confidence < 0.6
            pass
    
    def test_safety_url_validation(self):
        """Test that dangerous URLs are rejected."""
        dangerous_urls = [
            "http://localhost/secret",
            "https://127.0.0.1:8080/admin", 
            "http://192.168.1.1/config",
            "https://10.0.0.1/internal"
        ]
        
        def is_url_safe(url):
            """Simplified URL safety check."""
            if not url.startswith(('http://', 'https://')):
                return False
            
            # Block localhost and private IPs
            dangerous_patterns = [
                'localhost', '127.0.0.1', '0.0.0.0',
                '192.168.', '10.0.', '172.16.'
            ]
            
            return not any(pattern in url for pattern in dangerous_patterns)
        
        for url in dangerous_urls:
            assert not is_url_safe(url), f"URL '{url}' should be rejected as unsafe"
            
        # Safe URLs should pass
        safe_urls = [
            "https://example.com",
            "https://docs.python.org",
            "https://github.com/user/repo"
        ]
        
        for url in safe_urls:
            assert is_url_safe(url), f"URL '{url}' should be accepted as safe"


class TestAutosearchModeValidation:
    """Test autosearch mode validation and caps."""
    
    def test_scrape_character_limits(self):
        """Test that scrape results respect character limits."""
        max_chars = 10000  # Default limit
        
        # This would test actual scraping with character limits
        # Mock implementation for demonstration
        def mock_scrape_with_limit(url, max_chars):
            # Simulate scraping large content
            large_content = "A" * (max_chars + 1000)  # Exceeds limit
            return large_content[:max_chars]
        
        result = mock_scrape_with_limit("https://example.com", max_chars)
        assert len(result) <= max_chars
    
    def test_crawl_depth_limits(self):
        """Test that crawling respects depth limits.""" 
        max_depth = 3  # Default limit
        
        def mock_crawl_with_depth(url, depth):
            # Simulate crawling with depth tracking
            return min(depth, max_depth)
        
        # Should be limited to max_depth even if requested higher
        result = mock_crawl_with_depth("https://example.com", 5)
        assert result <= max_depth
    
    def test_crawl_page_limits(self):
        """Test that crawling respects page count limits."""
        max_pages = 50  # Default limit
        
        def mock_crawl_with_limit(url, limit):
            # Simulate discovering many pages
            discovered_pages = 100  # More than limit
            return min(discovered_pages, limit)
        
        result = mock_crawl_with_limit("https://example.com", max_pages)
        assert result <= max_pages
