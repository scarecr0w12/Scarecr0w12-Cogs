# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- (none)

### Changed
- (none)

### Fixed
- (none)

## [1.4.0] - 2025-08-08

### Added
- Real SERP search provider (`search_serp.py`) replacing inline stub logic with external adapter and fallback.
- Per-search-provider usage telemetry map (`usage.search_providers`) tracking invocation counts.
- Firecrawl adapter scaffold (`firecrawl.py`) with search/scrape/crawl/deep_research async methods and internal IP blocking.
- OAuth2 web API endpoints: `/api/guilds` (authorized guild list), `/api/status/{guild_id}` (guild status payload), `/api/health` (minimal health info).

### Changed
- Refactored `search.py` to dynamically import SERP provider and retain stub fallback.
- Provider docs updated to reflect implemented Firecrawl adapter.
- Web interface now validates & auto-regenerates invalid Fernet session keys (more robust startup) and exposes internal helper for future session key rotation.

### Fixed
- Enhanced session key validation with detailed error handling and automatic recovery from corrupted keys.
- Improved user-facing error clarity for SERP failures (standard `[serp-error]` prefix).

## [1.3.0] - 2025-08-08

### Added
- Prompt templates web module: CRUD pages (`/prompts`, `/prompts/new`, `/prompts/{name}`, `/prompts/{name}/generate`) with variable extraction and generation preview (global + guild scope)

### Changed
- Modular web interface now registers prompts module (non-fatal load)

### Fixed
- (none)

## [1.2.0] - 2025-08-08

### Added

- Initial OAuth2 web dashboard pages: `/dashboard`, `/guild/{guild_id}`, `/profile` after Discord login
- Guild configuration view (`/config/{guild_id}`) with admin-only access and masked provider key display
- JSON API endpoints: `/api/guilds` (authorized guild list + permissions), `/api/status/{guild_id}` (status payload used by legacy page)
- Session key auto-validation & regeneration (invalid/missing Fernet key repaired on startup)

### Changed

- Re-enabled web route wiring for future expansion with guarded permission checks
- Legacy `/status/{guild_id}` continues to function (tokens) while OAuth2 flow preferred

### Fixed

- Prevent crash on restart due to malformed `web_session_key` by validating and regenerating

## [1.3.0] - 2025-08-08

### Added
- Prompt templates web module: CRUD pages (`/prompts`, `/prompts/new`, `/prompts/{name}`, `/prompts/{name}/generate`) with variable extraction and generation preview (global + guild scope)

### Changed
- Modular web interface now registers prompts module (non-fatal load)

### Fixed
- (none)

## [1.1.0] - 2025-08-08

### Added

- Modal-based web configuration workflow (OAuth2, URL, server settings, reset confirmation)
- Rich status dashboard for web config show command

### Changed

- Breaking: Replaced parameter-based web config commands with modal interactions
- Documentation updated (commands, setup guide, configuration)

### Fixed

- Improved validation and prevented sensitive credential exposure in chat history

## [1.0.0] - 2025-08-08

### Added

- Initial public release of SkynetV2 cog for Red-DiscordBot
- Multi-provider AI chat system with OpenAI support
- Tool registry with ping and websearch tools (prefix + slash commands)
- Per-channel memory management with configurable limits and pruning policies
- Comprehensive rate limiting system (per-user, per-channel, per-tool)
- Usage statistics and telemetry tracking (tokens, costs, tool usage)
- Search abstraction layer with dummy and SERP stub providers
- Autosearch tool with heuristic query classification and execution modes
- Passive listening capabilities (mention/keyword/all modes)
- Model policy enforcement (allow/deny lists)
- Cost estimation with configurable pricing maps
- Streaming chat responses with edit throttling
- Tool-specific cooldowns and governance controls
- Modular architecture with separate mixins for maintainability
- Comprehensive configuration system with guild-level overrides
- Full documentation suite including architecture, commands, and configuration guides

### Changed

- Consolidated all development work into stable 1.0.0 release

### Fixed

- All development-phase issues resolved for stable release

## [0.0.7] - 2025-08-06

### Added

- Dummy `websearch` tool and commands (prefix + slash) guarded by enable flag.
- Tool management commands: list, enable, disable (prefix + slash).

### Changed

- Documentation updates for tools milestone planning.

### Fixed

- None.

## [0.0.6] - 2025-08-05

### Added

- Reintroduced stats and rate control commands (prefix + slash).
- Expanded usage stats (tokens, cost, per-user/channel rollups).

### Changed

- Refined cost estimation logic and token aggregation.

### Fixed

- Missing governance commands after refactor.

## [0.0.5] - 2025-08-04

### Added

- Streaming chat (prefix+slash) with edit throttling.
- Passive listening modes (mention/keyword/all) with memory context.

### Changed

- Improved memory pruning and context assembly.

### Fixed

- Minor formatting issues in responses.

## [0.0.4] - 2025-08-03

### Added

- Token accounting & cost estimation.
- Model list caching with TTL.

### Changed

- Usage tracking extended with per-user/channel tokens.

### Fixed

- Resolved minor error handling regressions.

## [0.0.3] - 2025-08-02

### Added

- Rate limiting (cooldown, per-user/min, per-channel/min) with owner bypass.
- Usage counters and stats aggregation.

### Changed

- Consolidated provider resolution precedence logic.

### Fixed

- Corrected policy allow/deny evaluation edge cases.

## [0.0.2] - 2025-08-01

### Added

- Memory system (per-channel pairs) with show/prune.
- Policy enforcement (allow/deny model lists).

### Changed

- Improved error messages for missing keys/policy blocks.

### Fixed

- Handling of empty model config.

## [0.0.1] - 2025-07-31

### Added

- Initial cog scaffold with OpenAI provider, chat command (prefix + slash), config, and documentation set.
