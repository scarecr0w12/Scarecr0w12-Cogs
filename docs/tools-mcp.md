# Tools and MCP

Goal: safe, simple tool calling with powerful integrations.

## Current State

- Registry supports enabling/disabling tools per guild.
- Built-in placeholder tools: `ping`, `websearch` (dummy results only).
- Commands: list, enable, disable, websearch query.
- Search abstraction (`search.py`) with `SearchProvider` interface and `DummySearchProvider` used by websearch tool.

## Planned Built-in Tools

- time: timezone-aware conversions
- calc: simple math
- websearch: Real provider (Tavily/Bing/etc.)
- summarize_url: fetch + summarize with rate limits

## MCP bridge (Planned)

- Discover/enable MCP servers (from config or environment)
- Map MCP tools to internal registry with names/descriptions/schemas
- Approval flow: first-time tool use per guild requires admin approval
- Per-channel tool sets; dry-run mode to preview calls/cost

## Custom tools (Planned)

- Manifest (name, description, input schema, rate-limit, visibility)
- Add via command/wizard or import from URL
- Sandboxed execution where possible; timeouts and budgets
