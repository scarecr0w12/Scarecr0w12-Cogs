# Configuration

Scopes and precedence: channel > guild > global. Provider credentials at global or guild scope.

## Global Configuration

### Providers
Multi-provider system supporting cloud and self-hosted AI services:

```json
{
  "providers": {
    "openai": {"api_key": "sk-..."},
    "anthropic": {"api_key": "ant-..."},
    "groq": {"api_key": "gsk_..."},
    "gemini": {"api_key": "AIza..."},
    "ollama": {"base_url": "http://localhost:11434/v1"},
    "lmstudio": {"base_url": "http://localhost:1234/v1"},
    "localai": {"base_url": "http://localhost:8080/v1", "api_key": "optional"},
    "vllm": {"base_url": "http://localhost:8000/v1", "api_key": "optional"},
    "text_generation_webui": {"base_url": "http://localhost:5000/v1"},
    "openai_compatible": {"base_url": "custom-endpoint", "api_key": "optional"}
  }
}
```

### Model Configuration
Default provider and model selection:

```json
{
  "model": {
    "provider": "openai",
    "name": "gpt-4o-mini"
  }
}
```

### Parameters
Default chat parameters:

```json
{
  "params": {
    "temperature": 0.7,
    "max_tokens": 512,
    "top_p": 1.0
  }
}
```

### Pricing
Cost estimation mapping (optional):

```json
{
  "pricing": {
    "openai": {
      "gpt-4o-mini": {
        "prompt_per_1k": 0.0,
        "completion_per_1k": 0.0
      }
    },
    "gemini": {
      "gemini-1.5-flash": {
        "prompt_per_1k": 0.0,
        "completion_per_1k": 0.0
      }
    }
  }
}
```

### System Prompts
Global prompt templates (bot owner managed):

```json
{
  "system_prompts": {
    "default": "You are a helpful AI assistant integrated into Discord.",
    "creative": "You are a creative AI assistant. Be imaginative and inspiring.",
    "technical": "You are a technical AI assistant. Provide detailed technical information."
  }
}
```

### Search Configuration
Default search provider:

```json
{
  "search": {
    "provider": "dummy"
  }
}
```

## Guild Configuration

### Basic Settings
- **enabled**: Enable/disable AI functionality for the guild
- **model**: Guild-specific model override
- **params**: Guild-specific parameter overrides (temperature, max_tokens, top_p)

### Multi-Level Prompting
Hierarchical prompt system for personalized AI interactions:

```json
{
  "system_prompts": {
    "guild": "This is a gaming server focused on MMORPGs.",
    "members": {
      "123456789": "This user prefers technical explanations.",
      "987654321": "This user likes casual, friendly responses."
    }
  }
}
```

### Per-Channel Listening
Channel-specific AI behavior overrides:

```json
{
  "channel_listening": {
    "123456789": {
      "enabled": true,
      "mode": "keyword",
      "keywords": ["bot", "ai", "help"]
    },
    "987654321": {
      "enabled": true,
      "mode": "mention"
    }
  }
}
```

**Listening Modes:**
- `mention`: Respond only when bot is mentioned
- `keyword`: Respond to messages containing specified keywords  
- `all`: Respond to all messages in the channel

### Global Listening
Default listening behavior for all channels:

```json
{
  "listening": {
    "enabled": false,
    "mode": "mention",
    "keywords": ["ai", "bot", "help"]
  }
}
```

### Tools Configuration
Tool registry and enable/disable states:

```json
{
  "tools": {
    "enabled": {
      "websearch": true,
      "ping": true,
      "autosearch": false
    }
  }
}
```
- rate_limits (cooldown_sec, per_user_per_min, per_channel_per_min, tools_per_user_per_min, tools_per_guild_per_min, tool_cooldowns: {tool: seconds})
- usage: aggregates and rollups
  - chat_count, last_used
  - tokens: prompt, completion, total
  - cost: usd (estimated when pricing configured)
  - per_user: counts and tokens_total per user (+ tool counters: tools_count_1m, tools_window_start)
  - per_channel: counts and tokens_total per channel
  - tools_total: total tool invocations (all tools)
  - tools: per tool usage map {tool_name: {count, last_used}}
  - tools_guild_window_start / tools_guild_count_1m: rolling 60s window for guild-wide tool invocations
  - autosearch: { classified:int, executed: { search:int, scrape:int, crawl:int, deep_research:int } }
- listening: { enabled, mode, keywords }
- memory: { default_limit, per_channel: { id: { limit, messages[] } }, prune: { max_items:int, max_age_days:int } }
- policy: allow/deny model lists
- search: optional override { provider } else inherits global (providers: dummy, serp, serp-stub)
- autosearch_caps: { scrape_chars, depth, limit } (configured per guild)
  - Autosearch safety caps configurable via guild `autosearch_caps` (scrape_chars, with enforced depth<=3 and limit<=50 in execution). Set `autoscrape_single` true to auto-scrape when exactly one search result.
- governance: { tools: {allow:[], deny:[]}, bypass: { cooldown_roles: [role_ids] }, budget: { per_user_daily_tokens:int, per_user_daily_cost_usd:float } }
- prompts: mapping of prompt_name -> { content, variables[], created, updated, scope } (global + guild scopes; variables auto-extracted by regex `{{var}}`)

### Memory Pruning

Pruning is enforced whenever new messages are remembered:

- Channel limit (pairs) -> trims to `limit * 2` messages (user+assistant)
- prune.max_items -> hard cap on total stored messages across pairs (after channel limit applied)
- prune.max_age_days -> removes oldest messages older than the age cutoff

Set via:

```text
[p]ai memory prune-policy [max_items] [max_age_days]
/ai memory prune_policy max_items? max_age_days?
```

Zero values disable that dimension.

## Channel

- persona (planned)
- memory limit override (per_channel limit)

## User

- persona (planned)

## Notes

- Mixins (`MemoryMixin`, `ToolsMixin`, `StatsMixin`, `ListenerMixin`) consume these config sections; structure stable across refactor.
- Tools must be enabled before invocation; default is disabled until toggled.
- Tool-specific rate limits enforce fairness independently of chat request limits.
- Stats command surfaces comprehensive tool telemetry: usage counts, latency (avg/last ms), success/error rates, per-tool cooldown status, and enhanced autosearch mode distribution alongside chat metrics.
- Autosearch telemetry counts classification volume and executed mode counts (search always implemented, scrape/crawl/deep_research use real Firecrawl when API key configured).
- Autosearch execution adapter selects real Firecrawl integration when API key available, placeholder stub otherwise.
- Firecrawl adapter includes safety checks: blocks internal IP ranges, localhost, and private networks to prevent SSRF attacks.
- Search provider configurable (providers: dummy, serp, serp-stub); inherit or override per guild.
- SERP provider requires API key from SerpAPI (serpapi.com). Configure globally with `[p]ai provider key set serp <key> --global`.
- Firecrawl provider requires API key from Firecrawl (firecrawl.dev). Configure globally with `[p]ai provider key set firecrawl <key> --global`.
- Provider keys stored in global providers config: `{providers: {serp: {api_key: "..."}, firecrawl: {api_key: "..."}, openai: {api_key: "..."}}}`.
- Per-tool cooldowns override generic tool rate window for burst control.
- Memory export limited to last 50 entries per channel segment for brevity/security; admin only.

### Governance

- Tool allow list: if non-empty, only listed tools may run
- Tool deny list: always blocks listed tools (evaluated before allow)
- Cooldown bypass roles: members with any listed role skip tool rate/cooldown limits
- Budget caps: per_user_daily_tokens (0 disables); cost cap placeholder (not enforced yet)

Configured via future commands (phase 2); stored under guild.governance. Enforcement occurs during tool rate limit checks.

## Personas (Planned)

Future persona management system for customizable AI behavior and context.

### Planned Features

- **Persona Profiles**: Predefined personality templates (professional, casual, technical, creative)
- **Custom Instructions**: Guild-specific system prompts and behavior guidelines
- **Context Awareness**: Role-based persona switching and channel-specific personas
- **Memory Integration**: Persona-aware memory retention and context building

### Configuration Placeholder

```yaml
personas:
  default: "assistant"           # Default persona for new conversations
  profiles:
    assistant:                   # Standard helpful assistant
      system_prompt: "You are a helpful AI assistant..."
      temperature: 0.7
      max_tokens: 512
    technical:                   # Technical documentation focus
      system_prompt: "You are a technical documentation expert..."
      temperature: 0.3
      max_tokens: 1024
  channel_overrides: {}          # Channel-specific persona assignments
  role_overrides: {}             # Role-specific persona assignments
```

### Planned Commands

- `[p]ai persona list` - Show available personas
- `[p]ai persona set <name>` - Set default persona for guild
- `[p]ai persona channel <channel> <persona>` - Set channel-specific persona
- `[p]ai persona role <role> <persona>` - Set role-specific persona
- `[p]ai persona create <name>` - Create custom persona
- `[p]ai persona edit <name>` - Modify persona settings

*Note: Persona system is not yet implemented. This section serves as a design placeholder for future development.*

## External API Keys

SkynetV2 integrates with external services for enhanced functionality. Configure API keys using the provider key management commands.

### OpenAI (Required for AI functionality)

```bash
[p]ai provider key set openai YOUR_API_KEY --global
```

- **Purpose**: Core AI chat and completion functionality
- **Scope**: Global only (secrets not stored per-guild)
- **Models**: Access to GPT models (gpt-4, gpt-4o-mini, etc.)
- **Documentation**: [OpenAI API Documentation](https://platform.openai.com/docs)

### SerpAPI (Optional - Web Search)

```bash
[p]ai provider key set serp YOUR_API_KEY --global
[p]ai search set serp  # Enable SERP search provider
```

- **Purpose**: Real web search results for websearch and autosearch tools
- **Alternative**: Uses `dummy` provider with placeholder results if not configured
- **Models**: N/A (search service)
- **Documentation**: [SerpAPI Documentation](https://serpapi.com/search-api)

### Firecrawl (Optional - Web Scraping & Research)

```bash  
[p]ai provider key set firecrawl YOUR_API_KEY --global
```

- **Purpose**: Real web scraping, crawling, and deep research for autosearch execution
- **Alternative**: Returns placeholder results if not configured
- **Capabilities**: Page scraping, site crawling, multi-source research
- **Safety**: Automatically blocks private IP ranges and localhost
- **Documentation**: [Firecrawl API Documentation](https://firecrawl.dev)

### Key Management Best Practices

- **Security**: All API keys are encrypted in Red's config storage
- **Scope**: External API keys must be set at global scope (not per-guild)
- **Display**: Keys are masked in status displays (`sk-...XXXX`)
- **Validation**: Key format validation performed during setup
- **Fallbacks**: Tools gracefully degrade to placeholder behavior when keys unavailable

### Configuration Commands

```bash
# Set API keys
[p]ai provider key set <provider> <key> --global

# Check configured providers (keys masked)
[p]ai provider key status

# Switch providers
[p]ai search set <provider>        # Search provider: dummy, serp
[p]ai model set <provider> <model> # AI model selection
```

## Stretch Features (Optional Enhancements)

### Token-Aware Truncation

Automatically truncates tool outputs that exceed Discord's message limits or configured thresholds.

**Configuration:**
```json
"stretch": {
  "truncation": {
    "enabled": true,
    "max_tool_output_chars": 8000
  }
}
```

**Features:**
- Intelligent truncation at paragraph boundaries when possible
- Preserves readability with truncation notices
- Prevents Discord message failures from oversized responses
- Configurable per-guild limits

### Search Result Caching

Local caching system for search results and tool outputs to improve performance.

**Configuration:**
```json
"stretch": {
  "cache": {
    "enabled": false,
    "max_entries": 1000,
    "ttl_hours": 1
  }
}
```

**Features:**
- Time-based TTL (time-to-live) expiration
- LRU (least recently used) eviction when capacity reached  
- Per-guild result isolation
- Reduces API calls for repeated queries
- Configurable cache size and expiration

### Experimental Features

Advanced features that are work-in-progress or experimental.

**Configuration:**
```json
"stretch": {
  "experimental": {
    "chain_planning": false,
    "localization": false
  }
}
```

**Chain Planning:**
- Multi-step tool execution plans
- Results from one step feed into subsequent steps
- Complex workflow automation
- Currently experimental/placeholder

**Localization:**
- Multi-language support for user-facing messages
- Discord locale detection
- Translation framework foundation
- Currently design-only implementation

### Admin Commands for Stretch Features

```bash
# Check stretch feature status
[p]ai config stretch

# Toggle truncation
[p]ai config stretch truncation <enabled> [max_chars]

# Manage cache
[p]ai config stretch cache <enabled> [max_entries] [ttl_hours]
[p]ai cache stats    # View cache performance metrics
[p]ai cache clear    # Clear cache entries

# Experimental features (admin only)
[p]ai config stretch experimental <feature> <enabled>
```

### Performance Impact

- **Truncation**: Minimal overhead, improves message delivery success
- **Caching**: Reduces API calls, uses local memory (configurable limit)  
- **Experimental**: May have stability/performance implications

### Migration Notes

- Stretch features are backwards compatible
- Default configuration enables truncation, disables caching
- Existing functionality unaffected when stretch features disabled
- Configuration migration handled automatically

## Web Session Security

The web interface uses an encrypted cookie session (Fernet). On startup the cog now validates the stored `web_session_key`:
- Missing / wrong type
- Incorrect length (expected 44 chars base64)
- Fails Fernet construction

If invalid, a new key is generated automatically and stored. A console log line is emitted:
```text
SkynetV2 Web: Generated new session encryption key (previous was missing/invalid).
```
No previous key material is logged. Admins can force regeneration by resetting web config (`[p]ai web config reset`).
