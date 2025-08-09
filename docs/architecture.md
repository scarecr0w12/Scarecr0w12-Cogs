# Architecture Overview

Goal: a clean, testable Red-DiscordBot cog that's easy to extend and safe to operate.

- Cog package: `skynetv2/`
  - `__init__.py`: setup hook (load/unload), version, data paths
  - `skynetv2.py`: main Cog, commands, listeners, Discord UI
  - `config.py`: Config schema, defaults, helpers, validators
  - `markdown_utils.py`: Discord markdown formatting, response formatting, template processing
  - `api/`: provider adapters implementing a common interface
    - `base.py`, `openai.py`, `anthropic.py`, `openrouter.py`, `ollama.py`
  - `tools/`: built-ins + MCP bridge
    - `mcp_client.py`, `web_search.py`, `documents.py`, `images.py`
  - `memory/`: chat history, summaries, vector integration hooks
    - `store.py`, `policies.py`
  - `views/`: buttons/selects/modals
  - `i18n/`: translations

Key patterns

- Dependency inversion: commands call service functions; services call adapters.
- Async, streaming-first design; cancellation safe.
- Strict provider interface for drop-in backends.
- Tool abstraction with registry; safe defaults; approval gates.
- Config layering: global -> guild -> channel -> user.
- Minimal persistence in Config; larger blobs under DataManager path.
- **Discord-First Design**: Rich markdown formatting throughout with Discord-specific syntax support

Request flow (high level)

1) Resolve scope (guild/channel/user, passive vs explicit)
2) Select provider + credentials (precedence + model policy)
3) Merge params and build context (memory + optional RAG) with markdown-enhanced system prompts
4) Plan/execute tools (timeouts, hop budgets)
5) Call provider (stream where supported)
6) Format responses with Discord markdown and persist memory/usage, emit response

See `docs/testing.md` for testing strategy and `docs/rag.md` for memory details.

---

Core components (current implementation)

- **Main Cog** (`skynetv2.py`): Orchestration layer composed from mixins (`memory.py`, `tools.py`, `stats.py`, `listener.py`, `orchestration.py`)
- **Configuration** (`config.py`): Global defaults, guild overrides, pricing, usage, listening, tools, memory, governance policies
- **Markdown System** (`markdown_utils.py`): Discord-specific formatting, response templates, intelligent text processing
- **Providers** (`api/*`): `Provider` interface, OpenAI adapter with executor calls, optional streaming
- **Search Integration**: Configurable search providers (`dummy`, `serp`) with real SerpAPI implementation
- **Tool System**: Registry with ping, websearch tools; extensible design for MCP/LLM agent tools
- **Memory Management**: Per-channel conversation history with configurable pruning and context injection
- **Web Interface** (`web/*`, `webapp/*`): OAuth2 authentication, dashboard, configuration management
- **Statistics & Governance**: Rate limiting, usage tracking, model policies, cost estimation

## Markdown Enhancement System

The markdown system provides comprehensive Discord formatting capabilities:

### DiscordMarkdownFormatter
- Complete Discord markdown syntax support
- Bold, italic, code, quotes, mentions, timestamps
- Hyperlinks and channel/role references
- Code blocks with language highlighting

### ResponseFormatter
- Consistent error/success/info message formatting
- Visual hierarchy with icons and structured presentation
- Markdown-aware text truncation preserving structure
- Template-based response generation

### MarkdownTemplateProcessor
- Advanced template processing for system prompts
- Context injection with variable substitution
- Structured prompt creation with sections and instructions
- Rich formatting guidelines embedded in prompts

### Enhanced User Experience
- Rich system prompts with Discord formatting guidelines
- Consistent command response formatting
- Enhanced variable documentation with examples
- Professional error messaging with clear visual structure

---

Provider interface (`api/base.py`)

All providers implement this interface for drop-in compatibility:

```python
@dataclass
class ChatMessage:
    role: str
    content: str

@dataclass  
class ChatParams:
    model: str
    messages: List[ChatMessage]
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    stream: bool = False

class Provider:
    async def chat(self, params: ChatParams) -> AsyncGenerator[str, None]:
        # Stream response chunks
    
    async def list_models(self) -> List[str]:
        # Available models for this provider
```

Build pattern (`skynetv2.py`)

```python
def build_provider(provider_config: Dict) -> Provider:
    provider_type = provider_config.get("type")
    
    if provider_type == "openai":
        return OpenAIProvider(provider_config)
    elif provider_type == "anthropic":
        return AnthropicProvider(provider_config)
    # ... etc
```

Current provider adapters handle async executor calls to avoid blocking the Discord event loop.

---

Testing approach (see `tests/`)

- Mock provider responses for deterministic chat tests
- Config validation with edge cases (empty keys, malformed JSON)
- Rate limit boundary testing
- Memory pruning simulation
- Tool registry isolation

Integration approach: 
- Start Red instance programmatically
- Load cog + auth with mock provider
- Exercise commands via test bot user
- Validate final config state
