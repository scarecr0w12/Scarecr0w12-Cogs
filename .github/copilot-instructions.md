# Copilot Instructions for SkynetV2 (Red-DiscordBot Cog)

Purpose: Enable AI agents to make small, safe, high-signal changes that match Red and this cog’s patterns.

## Key principles
- **Safety**: No destructive changes; no breaking changes; no new dependencies.
- **Simplicity**: Keep changes small and reviewable; avoid complex logic.
- **Consistency**: Follow existing patterns for commands, config, and provider usage.
- **Documentation**: Update `README.md` and `docs/` for any new features or changes.
- **Testing**: Ensure new features are testable; document testing strategy in `docs/testing.md`.
- **Config**: Use Red’s Config system; document config changes in `docs/configuration.md`.
- **Architecture**: Follow the architecture overview in `docs/architecture.md` for new features.
- **Conventions**: Follow Red’s coding conventions; document any new patterns in `docs/contributing.md`.
## Common tasks
- **Add a new provider**: Implement in `skynetv2/api/<name>.py` using the `Provider` interface; update `build_provider()` in `skynetv2/skynetv2.py`.
- **Add a new command**: Add under `[p]ai` group and mirror under `/ai` group; restrict with `manage_guild` where admin-only; keep outputs under 2000 chars; prefer `ephemeral=True` for setup/status slash replies.
- **Update config**: Edit `skynetv2/config.py` defaults; access via `self.config.guild(guild).<key>` or `self.config.<key>`; for dict updates, use `async with self.config.<scope>.<dict>() as d: d[...] = ...`.
- **Build, run, test**: Load cog with `[p]load skynetv2`; set provider key with `[p]ai provider key set openai <KEY> --global` (or via `/ai key_set`); set model with `[p]ai model set openai gpt-4o-mini`; test chat with `/ai chat "hello"`.
- **Documentation**: Update `README.md` for new features; document commands in `docs/commands.md`; update configuration details in `docs/configuration.md`.
- **Testing**: Document testing strategy in `docs/testing.md`; ensure new features are testable; consider using Red’s test framework.
- **Security**: Never log full API keys; redact secrets; add threat model notes for new tools/integrations; respect rate limits; avoid abusive defaults.
- **Error handling**: Use `ProviderError` for provider-specific errors; keep error messages user-friendly and non-technical; avoid leaking sensitive information.
- **Rate limits**: Implement rate limits in `skynetv2/config.py`; use `self.config.guild(ctx.guild).rate_limits` to access and update limits; document rate limit behavior in `docs/configuration.md`.
- **Usage tracking**: Track usage in `skynetv2/config.py` under `usage`; update after provider calls; document usage tracking in `docs/configuration.md`.
- **Passive listening**: Implement passive listening features in `skynetv2/skynetv2.py`; document commands in `docs/commands.md`; ensure proper permissions and cooldowns are set.
- **Memory management**: Implement memory policies in `skynetv2/memory/`; document memory commands in `docs/commands.md`; ensure memory is cleared or pruned as needed.
- **Localization**: Use `i18n/` for translations; document new strings in `docs/i18n.md`; ensure all user-facing text is localized.
- **Views**: Use `views/` for Discord UI components; document new views in `docs/views.md`; ensure views are accessible and user-friendly.
- **API integration**: Use `api/` for provider adapters; implement a common interface in `api/base.py`; document new providers in `docs/providers.md`; ensure adapters handle errors gracefully and return consistent data formats.

## Big picture (files that matter)
- `skynetv2/`
  - `__init__.py` — registers cog (`SkynetV2`) with Red
  - `skynetv2.py` — main Cog: prefix+slash commands, helpers, provider wiring
  - `config.py` — registers Red `Config` (global defaults + guild overrides)
  - `api/`
    - `base.py` — Provider interface (`Provider.chat(model, messages, ...)`), `ChatMessage`, `ChatParams`
    - `openai.py` — OpenAI adapter; uses OpenAI SDK via `run_in_executor`
- `docs/*` — architecture/commands/config/providers; README has quickstart and roadmap

## Data flow (MVP)
1) User runs `[p]ai ...` or `/ai ...`
2) `resolve_provider_and_model(guild)` merges config (guild > global) and resolves API key
3) `build_provider()` instantiates adapter (OpenAI) and calls `provider.chat(...)`
3) Provider adapter is built (OpenAI for now) and `chat()` is called, yielding text
4) Response sent to Discord (no streaming edits yet)

## Conventions & patterns
- Async-safe SDK usage: heavy/sync SDK calls run via `loop.run_in_executor` to avoid blocking
- Config precedence: guild override > global defaults; secrets at global or guild providers map
- Prefix and Slash parity: mirror subcommands under `commands.Group` and `app_commands.Group`
- Autocomplete: use `provider.list_models()` to populate `/ai model_set` suggestions
- Minimal error messaging: respond in-channel; ephemeral for slash; do not leak keys

## External deps & integration
- Red-DiscordBot 3.5+ APIs (commands, app_commands, Config)
- OpenAI SDK (>=1.0): used via `OpenAI(...).chat.completions.create(**payload)`; listing via `client.models.list()`
- No HTTP servers or long-lived tasks yet; MCP/tools and RAG are planned but not implemented

## Common tasks (do this way)
- Add a new provider:
  - Create `skynetv2/api/<name>.py` implementing `Provider`
  - Update `build_provider()` switch; keep SDK calls off the event loop via executor
- Add a new command:
  - Add under `[p]ai` group and mirror under `/ai` group; restrict with `manage_guild` where admin-only
  - Keep outputs under 2000 chars; prefer `ephemeral=True` for setup/status slash replies
- Update config:
  - Edit `config.py` defaults; access via `self.config.guild(guild).<key>` or `self.config.<key>`
  - For dict updates, use `async with self.config.<scope>.<dict>() as d: d[...] = ...`

## Build, run, test
- Local dev load:
  1) Put this repo under a path added with `[p]addpath /abs/path/to/parent`
  2) `[p]load skynetv2`
  3) Optional: `[p]slash enable` then `[p]slash sync`
- Minimal smoke test:
  - Set key: `[p]ai provider key set openai <KEY> --global` (or via `/ai key_set`)
  - Set model: `[p]ai model set openai gpt-4o-mini`
  - Chat: `/ai chat "hello"`
- No test suite yet; see `docs/testing.md` for intended strategy

## Important files to read before coding
- `skynetv2/skynetv2.py` — commands, helpers, slash wiring
- `skynetv2/api/base.py` — adapter interface
- `skynetv2/api/openai.py` — SDK usage pattern (executor-based)
- `README.md` and `docs/*` — planned features and design constraints

## MCP Tools for use during development
- 'vibe_check' — ensures alignment with development patterns and safety, only used during development. Should be used to verify that changes adhere to the principles outlined in this document. use when making changes to ensure they are safe and consistent with the project's goals.
- 'vibe_learn' — allows the AI to learn from interactions, only used during development.

## Gotchas
- Don’t block the event loop; use `run_in_executor` for SDK calls
- Respect guild vs global credential precedence; check for missing keys before calling providers
- Keep slash commands ephemeral for admin actions and error messages
- Stay under Discord message limits; later we can add pagination or attachments

If anything in this guide seems off or incomplete, leave a note in your PR and ping to refine these rules.
