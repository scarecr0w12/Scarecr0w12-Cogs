# Commands Reference

Implemented commands (prefix + slash mirrors where noted).

## Chat

- /ai chat message:string stream?:bool
- [p]ai chat message
- [p]ai chatstream message (streaming prefix variant)

## Tools

- /ai tools list
- /ai tools enable name:string
- /ai tools disable name:string
- /ai websearch query:string (records tool usage telemetry; subject to tool rate limits)
- /ai autosearch query:string execute?:bool (heuristic classification; executes search mode and stub executions for other modes)
- [p]ai tools list|enable|disable `name`
- [p]ai websearch `query`
- [p]ai autosearch `query [--exec]` (append --exec to run execution; non-search modes are stubbed)
- [p]ai (internal ping tool via registry but no direct command; callable from future agent flow)

## Search Provider

- /ai search show
- /ai search set provider:string (use 'inherit' to reset; providers: dummy, serp, serp-stub)
- [p]ai search show
- [p]ai search set <provider|inherit> (providers: dummy, serp, serp-stub)

## Provider Keys

- /ai provider key_set provider:string key:string global_scope?:bool
- [p]ai provider key set <provider> <key> [--global]
- [p]ai provider key show

Supported providers: openai, serp, firecrawl

## Memory

- /ai memory show limit?:int
- /ai memory prune limit?:int
- /ai memory export user_id?:int (ephemeral; DM alternative via prefix)
- /ai memory clear (clears all guild memory)
- /ai memory prune_policy max_items?:int max_age_days?:int
- [p]ai memory show [limit]
- [p]ai memory prune [limit]
- [p]ai memory export [user_id]
- [p]ai memory clear true (requires explicit true)
- [p]ai memory prune-policy [max_items] [max_age_days]

## Stats & Rate Limits

- /ai stats top?:int
- [p]ai stats [top]
- /ai rate show
- /ai rate set cooldown_sec?:int per_user_per_min?:int per_channel_per_min?:int tools_per_user_per_min?:int tools_per_guild_per_min?:int tool?:string tool_cooldown_sec?:int
- [p]ai rate show
- [p]ai rate set [cooldown_sec] [per_user_per_min] [per_channel_per_min] [tools_per_user_per_min] [tools_per_guild_per_min] [tool] [tool_cooldown_sec]

## Passive Listening (planned/partially implemented via config)

Listening enable/disable and mode commands will be surfaced in future updates; internal config keys already exist.

## Notes

- Streaming via `/ai chat stream:true` or `[p]ai chatstream`.
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
