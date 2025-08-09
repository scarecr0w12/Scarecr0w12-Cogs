# Scarecr0w12-Cogs

> Documentation now lives in the GitHub Wiki. The `docs/` folder is kept as a source snapshot and will auto-sync to the Wiki. Visit: [Project Wiki](https://github.com/Scarecr0w12/Scarecr0w12-Cogs/wiki)

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

- **Multi-Provider AI System**: Support for OpenAI, Anthropic Claude, Groq, Google Gemini, and self-hosted solutions (Ollama, LM Studio, LocalAI, vLLM, Text Generation WebUI)
- **Rich Discord Markdown Integration**: Enhanced system prompts, consistent message formatting, and intelligent markdown processing throughout all interactions
- **Chat (prefix + slash)** with streaming support and provider selection
- **Variables System**: Dynamic prompt injection with 17+ contextual variables (`{{user_name}}`, `{{server_name}}`, `{{time}}`, etc.)
- **Per-Channel Configuration**: Channel-specific listening modes, keywords, and AI behavior overrides
- **Multi-Level Prompting**: Hierarchical prompt system (System → Guild → Member) for personalized AI interactions with rich markdown formatting
- **Advanced Memory System**: Per-channel memory with context building, pruning policies, and conversation history
- **Comprehensive Web Interface**: OAuth2-authenticated management portal with interactive forms and real-time configuration
- **Tool Registry**: Extensible tool system with ping, websearch, and Firecrawl integration
- **Search & Research**: Multi-mode search with real scraping, crawling, and deep research capabilities
- **Rate Limiting & Governance**: Per-user/channel limits, model policies, and usage controls with owner bypass
- **Usage Analytics**: Token tracking, cost estimation, usage statistics, and performance monitoring
- **Passive Listening**: Configurable AI responses via mentions, keywords, or all messages
- **Self-Hosted Support**: Full support for local AI deployments and custom OpenAI-compatible endpoints
- **Professional Management**: Web-based configuration, prompt management, and system administration

### Search & Autosearch Overview

SkynetV2 includes a lightweight heuristic autosearch planner:

1. Classifies a user query (e.g. needs simple search vs. deeper content gathering).
2. Produces an execution plan (mode + caps). Modes: `search`, `scrape`, `crawl`, `deep_research`.
3. (Current state) Executes safe placeholder logic; Firecrawl integration enables real scrape/crawl/deep research when an API key is configured.
4. Optionally auto-scrapes the top result when high-confidence single result (configurable flag).

Safety caps (depth, result limits, total characters) prevent runaway usage. Future work (see `docs/todo.md`) will add a real SERP provider and richer telemetry.

**Quick Start:**

1. Set a key: `[p]ai provider key set openai <KEY> --global`
2. Choose a model: `[p]ai model set openai gpt-4o-mini`
3. Chat: `/skynet chat "hello"` or `[p]ai chat "hello"`

**Documentation:**
- Full Wiki: [Project Wiki](https://github.com/Scarecr0w12/Scarecr0w12-Cogs/wiki)
- [Commands](docs/commands.md)
- [Configuration](docs/configuration.md)
- [Architecture](docs/architecture.md)
- [Web Interface Setup](docs/web-oauth-setup.md)

## Support

If you encounter issues with any of these cogs, please open an issue on this repository.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
