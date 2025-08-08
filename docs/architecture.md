# Architecture Overview

Goal: a clean, testable Red-DiscordBot cog that's easy to extend and safe to operate.

- Cog package: `skynetv2/`
  - `__init__.py`: setup hook (load/unload), version, data paths
  - `skynetv2.py`: main Cog, commands, listeners, Discord UItecture Overview

Goal: a clean, testable Red-DiscordBot cog that’s easy to extend and safe to operate.

- Cog package: `aiassistant/`
  - `__init__.py`: setup hook (load/unload), version, data paths
  - `aiassistant.py`: main Cog, commands, listeners, Discord UI
  - `config.py`: Config schema, defaults, helpers, validators
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

Request flow (high level)

1) Resolve scope (guild/channel/user, passive vs explicit)
2) Select provider + credentials (precedence + model policy)
3) Merge params and build context (memory + optional RAG)
4) Plan/execute tools (timeouts, hop budgets)
5) Call provider (stream where supported)
6) Persist memory/usage, emit response

See `docs/testing.md` for testing strategy and `docs/rag.md` for memory details.

---

Core components (current implementation)

- **Main Cog** (`skynetv2.py`): Orchestration layer composed from mixins (`memory.py`, `tools.py`, `stats.py`, `listener.py`, `orchestration.py`)
- **Configuration** (`config.py`): Global defaults, guild overrides, pricing, usage, listening, tools, memory, governance policies
- **Providers** (`api/*`): `Provider` interface, OpenAI adapter with executor calls, optional streaming
- **Search Integration**: Configurable search providers (`dummy`, `serp`) with real SerpAPI implementation
- **Autosearch System** (`autoexec.py`): Query classification and execution orchestration with Firecrawl integration
- **Firecrawl Adapter** (`firecrawl.py`): Real scraping/crawling/research capabilities with safety checks
- **Tool Orchestration** (`orchestration.py`): Schema-driven tool calls for AI agent automation
- **Memory Management** (`memory.py`): Sliding window with pruning policies and admin controls
- **Governance System**: Rate limiting, tool access control, daily budgets, bypass roles
- **Telemetry** (`stats.py`): Usage tracking, latency metrics, success rates, cost estimation
- **Documentation** (`docs/*`): Commands, configuration, architecture, roadmap, testing guides
- **Web Modules** (`webapp/`): auth (OAuth2), pages (dashboard/config), api (JSON endpoints), legacy (token status), prompts (template CRUD + generation)

Key flows

1) Invocation (prefix/slash/listener)
   - Rate checks and counters update
   - Resolve provider/model/key (guild > global)
   - Provider.chat called, yielding text (streaming optional)
   - Tokens captured (if available) and accumulated; cost estimated via pricing
   - Response clipped to 2000 chars and sent

2) Tool Execution Pipeline
   - Tool discovery through registry (ToolsMixin)
   - Governance enforcement: allow/deny lists, bypass roles, daily budgets
   - Rate limiting per tool with configurable overrides
   - Execution with telemetry tracking (latency, success/failure rates)
   - Results logged for stats and debugging

3) Search & Autosearch Pipeline  
   - **Search Provider Resolution**: Configurable provider (`dummy`, `serp`) with guild fallback
   - **Autosearch Classification**: Query analysis to determine strategy (search/scrape/crawl/deep research)
   - **Execution Orchestration**: Real execution via Firecrawl adapter when API key present, placeholder otherwise
   - **Content Retrieval**: Scraping with safety checks (blocked private IPs), crawling with depth limits, deep research combining multiple sources
   - **Result Processing**: Content extraction, formatting, and safety validation before response

4) Agent Tool Orchestration
   - **Schema Generation**: JSON schemas for available tools enable AI agent discovery
   - **Tool Call Processing**: Structured JSON tool invocations with parameter validation
   - **Execution Mapping**: Tool calls routed through existing tool registry with governance enforcement
   - **Result Tracking**: Comprehensive logging of tool calls, execution times, and success rates

5) Autocomplete
   - Model list fetched via provider and cached in-memory for a short TTL

6) Passive listening
   - Modes: mention, keyword, all
   - Uses same rate limits and provider flow; does not respond to commands

Extensibility

- **Add Providers**: Implement new providers via `api/<name>.py` following the Provider interface
- **Add Search Providers**: Create new search implementations in the search provider registry
- **Add Tools**: Register tools via `ToolsMixin` with automatic schema generation for orchestration
- **Add Autosearch Modes**: Extend classification and execution patterns in autosearch system
- **Extend Memory**: Enhance via `MemoryMixin` with potential future vector store integration
- **Add Governance Rules**: Extend config schema and enforcement logic for new access controls
- **Tool Orchestration**: AI agents can discover and execute tools through JSON schemas automatically

Safety & Governance

- **Execution Safety**: Do not block the event loop; use `run_in_executor` for long operations
- **Access Control**: Owner bypass for rate limits, governance policies for tool access
- **Data Protection**: Masked key displays, minimal error messages, secret redaction
- **Resource Management**: Rate limiting, daily token budgets, per-tool overrides
- **Content Safety**: IP address blocking for scraping, URL validation, content filtering
- **Permission Integration**: Bypass roles, admin-only operations, guild-scoped configurations
