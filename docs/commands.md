# Commands Reference

Implemented commands (prefix + slash mirrors where noted).

**Note**: Slash commands use `/skynet` instead of `/ai` to avoid conflicts.

## Markdown Enhancements

SkynetV2 now includes comprehensive Discord markdown formatting throughout all responses:

- **Rich System Prompts**: Enhanced with structured markdown formatting and Discord-specific guidelines
- **Consistent Message Formatting**: Error, success, and info messages with visual hierarchy
- **Discord-Aware Formatting**: Proper use of `**bold**`, `*italic*`, `code`, code blocks, quotes, links, and mentions
- **Intelligent Truncation**: Markdown-aware text processing that preserves formatting structure
- **Variable Documentation**: Enhanced `[p]ai variables` command with rich markdown formatting and examples

## Chat

- /skynet chat message:string stream?:bool
- [p]ai chat message
- [p]ai chatstream message (streaming prefix variant)

## Provider Management

### Provider Configuration
- /skynet provider list (show all configured providers)
- /skynet provider set provider:string model:string (set active provider and model)
- [p]ai provider list
- [p]ai provider set <provider> <model>

### API Key Management  
- /skynet provider key set provider:string key:string global?:bool
- /skynet provider key show provider:string
- /skynet provider key remove provider:string global?:bool
- [p]ai provider key set <provider> <key> [--global]
- [p]ai provider key show <provider>
- [p]ai provider key remove <provider> [--global]

### Supported Providers
- **Cloud**: OpenAI, Anthropic, Groq, Google Gemini
- **Self-Hosted**: Ollama, LM Studio, LocalAI, vLLM, Text Generation WebUI
- **Generic**: OpenAI-Compatible (for custom endpoints)

## Model Management

- /skynet model list provider?:string
- /skynet model set provider:string model:string
- [p]ai model list [provider]
- [p]ai model set <provider> <model>

## Per-Channel Configuration

- /skynet channel listening enable/disable
- /skynet channel mode set mode:string (mention/keyword/all)  
- /skynet channel keywords set keywords:string
- [p]ai channel listening enable|disable
- [p]ai channel mode set <mention|keyword|all>
- [p]ai channel keywords set <keyword1,keyword2,...>

## Multi-Level Prompting

### System Prompts (Bot Owner Only)
- /skynet system prompt set template:string
- [p]ai system prompt set <template>

### Guild Prompts (Admin Only)
- /skynet guild prompt set prompt:string
- /skynet guild prompt show
- /skynet guild prompt clear
- [p]ai guild prompt set <prompt>
- [p]ai guild prompt show|clear

### Member Prompts (Admin Only)
- /skynet member prompt set user:User prompt:string
- /skynet member prompt show user:User
- /skynet member prompt clear user:User
- [p]ai member prompt set <@user> <prompt>
- [p]ai member prompt show|clear <@user>

## Tools

- /skynet tools list
- /skynet tools enable name:string
- /skynet tools disable name:string
- /skynet websearch query:string (records tool usage telemetry; subject to tool rate limits)
- /skynet autosearch query:string execute?:bool (heuristic classification; executes search mode and stub executions for other modes)
- /skynet webfetch mode:string target:string limit?:int depth?:int
- [p]ai tools list|enable|disable `name`
- [p]ai websearch `query`
- [p]ai autosearch `query [--exec]` (append --exec to run execution; non-search modes are stubbed)
- [p]ai webfetch `<mode> <target> [limit] [depth]`
- [p]ai (internal ping tool via registry but no direct command; callable from future agent flow)

Webfetch modes:
- `scrape` – Fetch and summarize a single page.
- `crawl` – Crawl from a start URL (depth<=3, limit<=50) and list discovered URLs plus brief notes.
- `deep_research` – Multi-source research on a query using the configured adapter.

Notes:
- Requires Firecrawl API key for real scraping/crawling; otherwise returns placeholders. Set with `[p]ai provider key set firecrawl <KEY> --global`.
- Output is truncated to fit Discord limits and configured stretch.truncation caps.
- Tool invocations respect governance and rate limits; results may be cached for up to 1 hour.

## Search Provider

- /skynet search show
- /skynet search set provider:string (use 'inherit' to reset; providers: dummy, serp, serp-stub)
- [p]ai search show
- [p]ai search set <provider|inherit> (providers: dummy, serp, serp-stub)

## Provider Keys

- /skynet provider key_set provider:string key:string global_scope?:bool
- [p]ai provider key set <provider> <key> [--global]
- [p]ai provider key show

Supported providers: openai, serp, firecrawl

## Memory

- /skynet memory show limit?:int
- /skynet memory prune limit?:int
- /skynet memory export user_id?:int (ephemeral; DM alternative via prefix)
- /skynet memory clear (clears all guild memory)
- /skynet memory prune_policy max_items?:int max_age_days?:int
- /skynet memory scope per_user_enabled?:bool per_user_limit?:int merge_strategy?:append|interleave|user_first
- [p]ai memory show [limit]
- [p]ai memory prune [limit]
- [p]ai memory export [user_id]
- [p]ai memory clear true (requires explicit true)
- [p]ai memory prune-policy [max_items] [max_age_days]

## Stats & Rate Limits

- /skynet stats top?:int
- [p]ai stats [top]
- /skynet rate show
- /skynet rate set cooldown_sec?:int per_user_per_min?:int per_channel_per_min?:int tools_per_user_per_min?:int tools_per_guild_per_min?:int tool?:string tool_cooldown_sec?:int
- [p]ai rate show
- [p]ai rate set [cooldown_sec] [per_user_per_min] [per_channel_per_min] [tools_per_user_per_min] [tools_per_guild_per_min] [tool] [tool_cooldown_sec]

## Passive Listening (planned/partially implemented via config)

Listening enable/disable and mode commands will be surfaced in future updates; internal config keys already exist.

## Notes

- Streaming via `/skynet chat stream:true` or `[p]ai chatstream`.
- Tool commands require the tool to be enabled (`ai tools enable <name>`).
- Tool usage telemetry stored under guild usage.tools (total & per_tool counters) and governed by tool-specific rate limits.
- Stats output now includes tool usage summary with latency tracking, success/error rates, and top tools by count.
- Enhanced autosearch mode distribution showing classification vs execution counts.
- Per-tool cooldown visibility showing current status and remaining time.
- Output truncated at 2000 characters to fit Discord limits.
- Search provider can be overridden per guild; providers: dummy, serp, serp-stub.
- SERP provider requires API key from SerpAPI (serpapi.com). Set with `[p]ai provider key set serp <key>`.
- Firecrawl provider requires API key from Firecrawl (firecrawl.dev). Set with `[p]ai provider key set firecrawl <key>`.
- Provider keys can be set at guild or global level (--global flag).
- Tool rate governance includes per-minute caps and optional per-tool cooldowns (set via rate set with tool + tool_cooldown_sec).
- `autosearch` executes search + real scrape/crawl/deep_research when Firecrawl API key is configured (placeholder execution otherwise); enable autoscrape_single to auto-scrape a lone result.
- Memory pruning: enforced on write using configured channel limit and guild prune policy (max_items, max_age_days). Export limited to last 50 messages per channel segment.

## Web Interface

Optional web interface for guild status and configuration viewing.

### `[p]ai web`

Web interface management commands (requires Manage Guild permission).

#### `[p]ai web token generate [hours]`

Generate a new web access token.

- **hours**: Token expiry time (1-168 hours, default: 24)
- Token sent via DM with access URL
- Keep URL private - provides access to guild statistics

#### `[p]ai web token list`

List all active web tokens for the current guild.

- Shows token prefix, creator, creation date, and expiry
- Use prefixes to identify tokens for revocation

#### `[p]ai web token revoke <prefix>`

Revoke a web token by its prefix.

- **prefix**: First few characters of the token to revoke
- Token becomes immediately invalid

#### `[p]ai web token cleanup`

Remove all expired web tokens from the current guild.

- Cleans up storage by removing old tokens
- No effect on active tokens

#### `[p]ai web status`

Show web interface status and configuration.

- Displays server port and running status
- Shows active token count

## Web Interface

SkynetV2 includes a Discord OAuth2 web interface with role-based permissions.

Session encryption key is auto-validated on restart; invalid/missing keys are regenerated silently (see configuration docs). Dashboard / profile / API endpoints are planned; current MVP exposes legacy token status endpoint plus OAuth2 login flow (future routes commented out in code).

### OAuth2 Configuration (Bot Owner Only)
- `[p]ai web config oauth` - **Configure Discord OAuth2 credentials via secure modal**
  - Interactive modal form for client ID and client secret
  - Embedded setup instructions and validation
  - Secure credential entry (no chat history)

- `[p]ai web config url` - **Set public domain via modal**
  - Interactive form with URL validation
  - Support for custom domains and Cloudflare setup
  - Automatic redirect URI guidance

- `[p]ai web config server` - **Configure server host/port via modal**
  - Interactive form with validation (default: localhost:8080)
  - Security warnings for external binding (0.0.0.0)
  - Port range validation (1024-65535)

- `[p]ai web config show` - **Display comprehensive configuration status**
  - Visual status dashboard with color-coded indicators
  - Configuration completeness assessment
  - Next steps and quick action links
  - Setup help and troubleshooting guides

- `[p]ai web config reset` - **Reset configuration with confirmation workflow**
  - Interactive confirmation modal requiring "CONFIRM" text
  - Safe destructive action protection
  - Clear explanation of what will be reset

### Server Management
- `[p]ai web restart` - Restart web interface server (bot owner only)
- `[p]ai web status` - Show web interface status

### Legacy Token System (Deprecated)
- `[p]ai web token generate [hours]` - Generate legacy access token (24h default)
- `[p]ai web token list` - List active tokens for guild
- `[p]ai web token revoke <prefix>` - Revoke token by prefix
- `[p]ai web token cleanup` - Remove expired tokens

**Note**: OAuth2 authentication is now the preferred method with modal-based configuration for improved security and user experience. All sensitive credentials are entered through Discord modals to prevent exposure in chat history. See [Web OAuth Setup Guide](web-oauth-setup.md) for configuration instructions.

## Orchestration Commands

Agent tool orchestration for AI automation and structured tool calls.

### `[p]ai orchestrate` / `[p]ai orch`

Tool orchestration group commands.

#### `[p]ai orchestrate tools` / `[p]ai orch list`

List available tools for orchestration with categories and permissions.

- Shows tools grouped by category (General, Search, etc.)
- 🔒 indicates admin-only tools
- Respects tool enablement and user permissions

#### `[p]ai orchestrate schema [tool_name]`

Show JSON schema for orchestration tools.

- **Without tool_name**: Exports all tool schemas to JSON file
- **With tool_name**: Shows specific tool schema inline or as file if large
- Schemas include parameter definitions, types, requirements
- Used by AI agents for structured tool discovery and execution

#### `[p]ai orchestrate simulate <tool_name> [parameters]`

Simulate a tool call for debugging (requires orchestrate_debug permission).

- **tool_name**: Name of tool to simulate
- **parameters**: JSON parameters (default: `{}`)
- Returns simulated execution result with call details
- Example: `[p]ai orch sim websearch {"query": "test search"}`
- Used for development and testing tool call structures

## Prompt Templates (Web Only)

Management currently via web dashboard (`/prompts`). Future CLI/Discord commands may expose list/fill/generate functions.
