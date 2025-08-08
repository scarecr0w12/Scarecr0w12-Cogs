# Contributing

Thanks for your interest! This project follows a small, reviewable-changes philosophy.

## How to propose changes

1. Open an issue describing the problem or feature (include minimal context and acceptance criteria).
2. Fork + branch per change; keep PRs focused.
3. Add tests when possible; update docs in `README.md` and `docs/`.
4. Run linters/formatters and ensure tests pass.

## Code style

- Python 3.10+
- Type hints required for public functions
- Ruff + Black (88 cols)
- Docstrings for modules and public classes/functions

## Commit/PR

- Conventional commits recommended (feat:, fix:, docs:, chore:, refactor:)
- Link issues in PR description
- Include screenshots/gifs for UI/Discord changes

## Security & privacy

- Never log full API keys; redact secrets
- Add threat model notes for new tools/integrations
- Respect rate limits; avoid abusive defaults
