# Testing Strategy

## Overview

SkynetV2 uses a layered testing approach combining automated unit tests, integration tests, and comprehensive manual testing matrices for complex AI interactions.

## Unit Testing

### Provider Adapters
- Mock HTTP responses and streaming
- Error handling (network, authentication, rate limits)
- Token usage parsing and tracking
- Model listing and validation

### Configuration System
- Config merge precedence (channel > guild > global)
- Model policy matcher with wildcards
- Provider key management and masking
- Governance policy enforcement

### Memory Management
- Sliding window behavior
- Pruning policies (max items, age limits)
- Export/import functionality
- Channel-specific memory isolation

### Search & Autosearch
- Query classification heuristics
- Provider fallback behavior
- Safety checks (URL validation, IP blocking)
- Result processing and formatting

### Tool System
- Registry management and discovery
- Rate limiting enforcement
- Telemetry tracking (latency, success/error rates)
- Schema generation for orchestration

### Error Handling
- ProviderError mapping to user-friendly messages
- Secret redaction in logs and responses
- Context-aware error classification
- Exception chain preservation

## Integration Testing

### End-to-End Workflows
- Complete chat flow with mocked providers
- Tool execution with rate limit interaction
- Passive listening across different trigger modes
- Memory persistence across restarts

### Cross-Component Integration
- Governance system with tool execution
- Telemetry collection across all operations
- Search provider fallback chains
- Orchestration schema generation and execution

### Load Testing
- Concurrent chat requests
- Rate limit boundary testing
- Memory pruning under load
- Tool cooldown enforcement

## Manual Testing Matrix

### Core Setup & Configuration

| Test Case | Steps | Expected Result | Status |
|-----------|-------|-----------------|--------|
| **Initial Setup** | `[p]load skynetv2` | Cog loads without errors | ⏳ |
| **API Key Config** | `[p]ai provider key set openai <KEY> --global` | Key stored, masked in display | ⏳ |
| **Model Selection** | `[p]ai model set openai gpt-4o-mini` | Model configured, shows in status | ⏳ |
| **Guild Override** | Set guild-specific model/provider | Guild settings override global | ⏳ |

### Core Chat Functionality

| Test Case | Steps | Expected Result | Status |
|-----------|-------|-----------------|--------|
| **Basic Chat** | `/ai chat "Hello, how are you?"` | AI responds appropriately | ⏳ |
| **Streaming Chat** | `[p]ai chatstream "Tell me a story"` | Response streams incrementally | ⏳ |
| **Long Response** | Chat with complex query | Response truncated at 2000 chars | ⏳ |
| **No API Key** | Remove API key, attempt chat | Clear error message about missing key | ⏳ |

### Search Integration

| Test Case | Steps | Expected Result | Status |
|-----------|-------|-----------------|--------|
| **Search Config** | `[p]ai search set dummy` | Search provider changed | ⏳ |
| **Basic Search** | `[p]ai websearch query:"latest news"` | Returns formatted results | ⏳ |
| **SERP Integration** | Set SERP API key, test search | Real web results returned | ⏳ |
| **Search Fallback** | Invalid SERP key, test search | Falls back to dummy provider | ⏳ |

### Autosearch System

| Test Case | Steps | Expected Result | Status |
|-----------|-------|-----------------|--------|
| **Query Classification** | `/ai autosearch query:"compare products" execute:false` | Shows classified intent (search/scrape/etc) | ⏳ |
| **Search Execution** | Enable execution, test search query | Real search with results | ⏳ |
| **Scrape Execution** | Test URL scraping query with Firecrawl | Page content extracted | ⏳ |
| **Safety Checks** | Try localhost URL | Request blocked with error | ⏳ |
| **No Firecrawl Key** | Test without API key | Placeholder execution responses | ⏳ |

### Tool Management

| Test Case | Steps | Expected Result | Status |
|-----------|-------|-----------------|--------|
| **Tool Discovery** | `[p]ai tools list` | Shows available tools with status | ⏳ |
| **Enable/Disable** | `[p]ai tools enable/disable websearch` | Tool status updates correctly | ⏳ |
| **Rate Limiting** | Rapid tool calls | Rate limits enforced, clear error messages | ⏳ |
| **Admin Tools** | Test admin-only tools as non-admin | Permission denied with clear message | ⏳ |

### Orchestration System

| Test Case | Steps | Expected Result | Status |
|-----------|-------|-----------------|--------|
| **Schema Generation** | `[p]ai orchestrate schema` | JSON schema file generated | ⏳ |
| **Tool Listing** | `[p]ai orchestrate tools` | Categorized tool list with permissions | ⏳ |
| **Simulation** | `[p]ai orch sim ping {}` | Simulated execution result | ⏳ |
| **Permission Check** | Non-admin simulate restricted tool | Permission denied | ⏳ |

### Governance System

| Test Case | Steps | Expected Result | Status |
|-----------|-------|-----------------|--------|
| **Tool Allow List** | Set allow list, test excluded tool | Tool blocked with clear message | ⏳ |
| **Bypass Roles** | Set bypass role, test rate limits | Bypassed for allowed users | ⏳ |
| **Daily Budgets** | Set token budget, exceed limit | Budget enforced with reset next day | ⏳ |
| **Per-tool Overrides** | Custom rate limits per tool | Individual limits respected | ⏳ |

### Memory System

| Test Case | Steps | Expected Result | Status |
|-----------|-------|-----------------|--------|
| **Memory Persistence** | Multiple chats, check retention | Context maintained across messages | ⏳ |
| **Pruning Policy** | `[p]ai memory prune-policy 10 1` | Old messages pruned automatically | ⏳ |
| **Memory Export** | `/ai memory export` | Export file with recent messages | ⏳ |
| **Memory Clear** | `[p]ai memory clear true` | All memory cleared with confirmation | ⏳ |

### Telemetry & Stats

| Test Case | Steps | Expected Result | Status |
|-----------|-------|-----------------|--------|
| **Usage Tracking** | Various operations, check `/ai stats` | Accurate counts and metrics | ⏳ |
| **Latency Metrics** | Tool usage, check latency display | Average and last execution times | ⏳ |
| **Success Rates** | Mix of successful/failed operations | Accurate success rate percentages | ⏳ |
| **Cost Tracking** | Set pricing, monitor cost estimates | Cost calculations match usage | ⏳ |

### Error Handling

| Test Case | Steps | Expected Result | Status |
|-----------|-------|-----------------|--------|
| **Invalid API Key** | Set bad key, attempt chat | User-friendly error message | ⏳ |
| **Network Issues** | Simulate connection problems | Graceful error handling | ⏳ |
| **Rate Limit Hit** | Exceed provider rate limits | Clear explanation of rate limiting | ⏳ |
| **Secret Redaction** | Check logs for exposed keys | No sensitive data in user-facing errors | ⏳ |

### Passive Listening

| Test Case | Steps | Expected Result | Status |
|-----------|-------|-----------------|--------|
| **Mention Mode** | Enable mention mode, mention bot | Bot responds appropriately | ⏳ |
| **Keyword Mode** | Set keywords, send matching message | Bot responds to keyword triggers | ⏳ |
| **All Mode** | Enable all mode (carefully!) | Bot responds to all messages | ⏳ |
| **Rate Limit Respect** | Rapid messages with listening on | Rate limits still enforced | ⏳ |

## Automated Testing

### Classification Heuristics Tests

```python
def test_autosearch_classification():
    \"\"\"Test autosearch query classification accuracy.\"\"\"
    test_cases = [
        ("latest news about AI", "search"),
        ("scrape content from https://example.com", "scrape"),
        ("crawl example.com for documentation", "crawl"),
        ("research renewable energy trends", "deep_research")
    ]
    
    for query, expected_mode in test_cases:
        result = classify_autosearch_query(query)
        assert result["mode"] == expected_mode
```

### Provider Error Handling Tests

```python
def test_error_handler_secret_redaction():
    \"\"\"Test that sensitive information is properly redacted.\"\"\"
    test_cases = [
        ("API key: sk-1234567890abcdef", "API key: sk-...XXXX"),
        ("Bearer abc123xyz789", "Bearer abc123...789"),
        ("https://user:pass@api.com", "https://user:***@api.com")
    ]
    
    handler = ErrorHandler()
    for input_text, expected in test_cases:
        result = handler.redact_secrets(input_text)
        assert expected in result
```

### Memory Pruning Tests

```python
def test_memory_pruning_policies():
    \"\"\"Test memory pruning behavior with different policies.\"\"\"
    # Test max_items enforcement
    # Test max_age_days enforcement  
    # Test interaction between policies
    pass
```

## CI/CD Placeholder

```yaml
# .github/workflows/test.yml (future implementation)
name: SkynetV2 Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          pip install pytest pytest-asyncio pytest-cov
          pip install -e .
      - name: Run tests
        run: pytest tests/ --cov=skynetv2
      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

## Testing Tools

### Required Dependencies
```bash
pip install pytest pytest-asyncio pytest-cov
pip install aioresponses  # For mocking HTTP requests
pip install freezegun     # For time-based testing
```

### Test Structure
```
tests/
├── unit/
│   ├── test_providers.py
│   ├── test_config.py
│   ├── test_memory.py
│   ├── test_autosearch.py
│   └── test_error_handling.py
├── integration/
│   ├── test_chat_flow.py
│   ├── test_tool_execution.py
│   └── test_governance.py
└── conftest.py  # Test fixtures
```

## Test Execution

### Running Tests
```bash
# Run all tests
pytest tests/

# Run specific test categories
pytest tests/unit/
pytest tests/integration/

# Run with coverage
pytest --cov=skynetv2 --cov-report=html
```

### Manual Test Execution
1. Set up test environment with API keys
2. Execute test matrix systematically 
3. Document results and issues
4. Update test cases based on findings

Note: Manual testing requires active OpenAI, SERP, and Firecrawl API keys for complete coverage.
