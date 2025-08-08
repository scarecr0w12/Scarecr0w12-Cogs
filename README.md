# Scarecr0w12-Cogs

A collection of AI-powered cogs for Red-DiscordBot.

## Installation

To add this repository to your Red-DiscordBot instance:

```bash
[p]repo add Scarecr0w12-Cogs https://github.com/Scarecr0w12/Scarecr0w12-Cogs
```

## Available Cogs

### SkynetV2

AI assistant cog focused on usability, governance, and extensibility.

**Installation:**
```bash
[p]cog install Scarecr0w12-Cogs skynetv2
```

**Features:**
- Chat (prefix + slash) with streaming support
- Provider abstraction (OpenAI implemented)  
- Per-channel memory window with show/prune/export/clear + prune policy (max items / max age)
- Tool registry (ping + dummy websearch) with enable/disable
- Search abstraction (configurable provider: `dummy`, `serp` stub; guild override)
- Tool-specific rate limits + general cooldown / per-user / per-channel limits (owner bypass)
- Usage stats: chats, tokens, cost estimate, top users/channels, tool usage & top tools
- Cost estimation (editable pricing map)
- Passive listening modes (mention / keyword / all) groundwork
- Model policy allow/deny lists
- Diagnostics and model list caching
- Modular mixins (memory, tools, stats, listener) for maintainability
- Agent tool orchestration with JSON schemas for AI automation
- Heuristic autosearch tool (classifies query -> plan; executes search + real scrape/crawl/deep research via Firecrawl when API key configured, placeholder otherwise; optional autoscrape single result)

**Quick Start:**
1. Set a key: `[p]ai provider key set openai <KEY> --global`
2. Choose a model: `[p]ai model set openai gpt-4o-mini`
3. Chat: `/ai chat "hello"`

**Documentation:**
- [Commands](docs/commands.md)
- [Configuration](docs/configuration.md)
- [Architecture](docs/architecture.md)

## Support

If you encounter issues with any of these cogs, please open an issue on this repository.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
