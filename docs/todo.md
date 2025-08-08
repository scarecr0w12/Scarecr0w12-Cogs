# Backlog / TODO

Guiding principles: safety (no breaking changes), simplicity (small PRs), consistency (follow existing patterns), documentation + vibe_check after each task.

Legend:

- [ ] Open
- [x] Done (when completed)

After finishing each top-level task (or meaningful subtask), run a vibe_check to validate alignment, then optionally record a vibe_learn entry.

## 1. Autosearch Execution

- [ ] Implement execution layer for modes returned by `autosearch` (search, scrape, crawl, deep_research).
- [x] Add internal adapter abstraction (e.g., FirecrawlAdapter placeholder) so future real integration is isolated.
- [x] Enforce safety caps (maxDepth ≤ 3, limit ≤ 50, total scraped chars ≤ configurable cap).
- [x] Auto-scrape top search result if single high-confidence match (optional flag).
- [x] Record mode-specific usage (e.g., increment `autosearch_search`, etc., or extend plan metadata).
- [x] Update docs (commands, configuration) and changelog.
- [x] vibe_check (placeholder execution complete; real provider integration pending in later tasks)

## 2. Real Search Provider (SERP API)

- [x] Implement `search_serp.py` provider (key in providers map, executor pattern like OpenAI).
- [x] Key set command pattern (reuse provider key set) + validation (generic provider key commands already support `serp`).
- [x] Error handling (network timeout, quota) -> clean user message (`[serp-error]` prefixed lines).
- [x] Update provider list docs + README.
- [x] Add usage telemetry (per search provider counts under `usage.search_providers`).
- [x] vibe_check

## 3. Firecrawl Integration (Optional Next)

- [x] Create adapter (search/scrape/crawl/deep_research wrappers).
- [x] Config keys: global api_key, optional guild override; safety: deny internal IP ranges.
- [x] Map autosearch modes -> adapter calls when execution enabled.
- [ ] Rate limit integration (tool reuse; maybe distinct tool names like `firecrawl_crawl`).
- [x] Threat model + docs update.
- [ ] vibe_check

## 4. Stats & Telemetry Enhancements

- [ ] Add latency tracking per tool (avg/last ms).
- [ ] Add success/error counters per tool.
- [ ] Display per-tool cooldowns in stats (optional section).
- [ ] Surface autosearch mode distribution (counts per classified mode).
- [ ] Update stats docs.
- [ ] vibe_check

## 5. Governance Additions

- [ ] Daily/weekly cost budget caps (abort calls if exceeding). Config + docs.
- [ ] Tool allow/deny lists per role/channel.
- [ ] Per-tool per-user minute cap (override of global tool window).
- [ ] Cooldown override permission (e.g., roles bypass?).
- [ ] vibe_check

## 6. Memory & Chat Improvements

- [ ] Export memory command (DM or attachment) with redaction safeguard.
- [ ] Clear memory (channel) command with confirmation.
- [ ] Configurable memory pruning policy (FIFO vs size/time-based).
- [ ] Persona scaffolding (channel/user placeholders) docs stub.
- [ ] vibe_check

## 7. Agent / Tool Orchestration

- [ ] Define internal tool call schema (JSON) for future automatic invocation.
- [ ] Add debug command to simulate provider function-call style output.
- [ ] Prepare mapping from tool schema -> run functions.
- [ ] Document architecture changes.
- [ ] vibe_check

## 8. Documentation & Lint Hygiene

- [ ] Resolve README MD032 blank line list warnings (or add markdownlint config to ignore).
- [ ] Add architecture section describing search/autosearch pipeline.
- [ ] Add configuration doc section for future external keys (SERP/Firecrawl placeholders).
- [ ] Consolidate error message patterns into docs snippet.
- [ ] vibe_check

## 9. Error Handling Polish

- [ ] Centralize ProviderError raising + mapping to user-safe phrases.
- [ ] Wrap tool executions with try/except to mark failures in telemetry.
- [ ] Redact secrets from trace logs (confirm no leaks).
- [ ] vibe_check

## 10. Testing Scaffold

- [ ] Draft manual test matrix (docs/testing.md) for new features (autosearch execution, provider fallback).
- [ ] Add simple automated tests (if Red test harness feasible) for classification heuristics.
- [ ] CI note (future) placeholder.
- [ ] vibe_check

## 11. Roadmap Alignment

- [ ] Update docs/roadmap.md to reflect completed autosearch (planning) and upcoming execution phase.
- [ ] Mark tasks moved from roadmap into active backlog as done/merged.
- [ ] vibe_check

## 12. Nice-to-Have / Stretch

- [ ] Token-aware truncation for tool outputs beyond Discord limit (pagination or file).
- [ ] Local cache for external search results (TTL) to reduce calls.
- [ ] Multi-message tool plans (chain planning) experimental flag.
- [ ] Localization pass for new strings (i18n docs update).
- [ ] vibe_check

---

## 13. Model Policy & Provider UX

- [ ] Add commands: `[p]ai modelpolicy allow add/remove <provider> <model>` (guild + global variants).
- [ ] Add commands: `[p]ai modelpolicy deny add/remove <provider> <model>`.
- [ ] Slash equivalents under `/skynet modelpolicy ...`.
- [ ] Command to list resolved model policy (allow, deny, effective) with cache hit stats.
- [ ] Command to clear model list cache (`model cache flush`).
- [ ] Docs section (configuration + commands) for model policies.
- [ ] Telemetry: count policy denials.
- [ ] vibe_check

## 14. Governance UX & Reliability

- [ ] Ensure governance group returns help instead of silent exit when no subcommand (prefix & slash help improvements).
- [ ] Add explicit error message when lacking `manage_guild` on governance commands (currently fallback to main help risk).
- [ ] Validate tool names in allow/deny (warn if unknown rather than silently accepting typo).
- [ ] Add command to show *effective* tool availability after allow/deny + enable/disable + per-role overrides.
- [ ] Governance policy export/import (YAML) with confirmation.
- [ ] Budget enforcement hook in `_check_and_record_usage` (currently placeholder for cost tokens).
- [ ] vibe_check

## 15. Web Interface Hardening

- [x] Basic guild list/status endpoints with permission checks.
- [x] Add health/status endpoint with minimal info (no secrets) for monitoring.
- [ ] Session key auto-rotation command.
- [ ] CSRF token for form POST endpoints (if any future forms).
- [ ] Rate limiting on web API endpoints (simple in-memory leaky bucket per IP/user id).
- [ ] Log auth failures (redacted) with counter in telemetry.
- [ ] TLS / reverse proxy deployment guide expansion (security notes).
- [ ] Access audit log (who viewed config / performed actions) stored short-term.
- [ ] vibe_check

## 16. Security & Safety Enhancements

- [ ] Firecrawl URL validation: block file://, localhost, RFC1918, link-shortener expansion.
- [ ] Add configurable allowed TLD whitelist for scraping (optional mode).
- [ ] Add configurable max cumulative scrape bytes per invocation.
- [ ] Add provider timeout configuration (per provider) with sane defaults.
- [ ] Implement structured error codes for user messages (e.g., GOV_DENIED, RATE_LIMIT, PROVIDER_FAIL).
- [ ] Threat model doc section updates (attack surfaces: web, scraping, tool exec).
- [ ] vibe_check

## 17. Tool Registry Improvements

- [ ] Add tool metadata: `version`, `category`, `admin_only` surfaced in list/stats.
- [ ] Per-tool detailed info command (description, cooldown, success rate, last latency).
- [ ] Tool disable reason (store optional reason; show in list).
- [ ] Tool dependency validation (warn if enabling tool missing provider key).
- [ ] Tool schema cache invalidation after enable/disable.
- [ ] vibe_check

## 18. Telemetry Deep Dive

- [ ] Histogram buckets for latency (p50/p90/p99 calculation) – simple aggregation.
- [ ] Error classification counters (timeout, auth, quota, other).
- [ ] Daily roll-up snapshot (store yesterday summary for quick compare).
- [ ] Top models used section in stats.
- [ ] Optional anonymized hash for users to allow privacy-friendly per-user stats.
- [ ] vibe_check

## 19. Memory System Extensions

- [ ] Channel memory size warning when 80% of cap reached.
- [ ] Memory search (simple substring) command.
- [ ] Memory redact command (remove entries containing a token).
- [ ] Persona config scaffolding (per guild/channel) + injection into context.
- [ ] Vector store integration placeholder interface (no dependency yet) – docs only or stub class.
- [ ] vibe_check

## 20. Orchestration Execution Phase

- [ ] Implement actual tool execution from structured plan (currently simulation only).
- [ ] Add safety budget: max sequential tool calls, max total chars.
- [ ] Add dry-run plan preview command.
- [ ] Add plan validation diagnostics (missing required params, unknown tools).
- [ ] Persist last plan per channel for re-run.
- [ ] vibe_check

## 21. Testing Expansion

- [ ] Tests for governance allow/deny logic and effective tool resolution.
- [ ] Tests for model policy allow/deny precedence.
- [ ] Tests for rate limit overrides per tool.
- [ ] Tests for autosearch execution safety caps (mock Firecrawl adapter).
- [ ] Tests for orchestration schema generation stability (snapshot tests).
- [ ] Tests for memory pruning policies (age + max items).
- [ ] vibe_check

## 22. Documentation Gaps

- [ ] Add missing docs for web OAuth2 modal-driven setup (link from README already present – expand details).
- [ ] Add governance policy examples (YAML export sample).
- [ ] Add troubleshooting section: common errors + error codes mapping.
- [ ] Add performance tuning tips (cooldowns, memory limits, pruning).
- [ ] Add security checklist (keys, role permissions, web exposure).
- [ ] Update README with Search & Autosearch Overview anchor link.
- [ ] vibe_check

## 23. Internationalization (i18n)

- [ ] Centralize user-facing strings (pass through placeholder i18n function).
- [ ] Add docs/i18n.md describing translation workflow.
- [ ] Provide baseline `en-US` catalog.
- [ ] Mark governance & tool messages for extraction.
- [ ] vibe_check

## 24. Performance / Resource Management

- [ ] Async executor pool sizing config (max workers for provider calls).
- [ ] Cache eviction strategy for model list if memory footprint grows.
- [ ] Optional disabling of memory storage for specific channels.
- [ ] Lazy-load web server only if enabled via config.
- [ ] Lightweight health metric (recent errors count) for status command.
- [ ] vibe_check

## 25. Cleanup & Refactors

- [ ] Consolidate duplicate helper logic in chat vs chatstream (token accounting repeated).
- [ ] Extract token/cost update into helper function (DRY).
- [ ] Normalize group command patterns (consistent help output when missing subcommand).
- [ ] Rename any legacy placeholder names (e.g., serp-stub) to consistent naming.
- [ ] Type hints for all public methods (mypy / pyright friendliness pass).
- [ ] Remove obsolete commented code blocks.
- [ ] vibe_check

---
Process reminder: Complete one cluster -> update docs/changelog -> run vibe_check -> commit.

## Newly Identified Gaps (Aug 2025 Audit Summary)

High-impact clusters to prioritize next (suggested order):
1. Governance UX & Model Policy (Sections 13 & 14) – improves admin control reliability.
2. Error Handling Polish (Section 9) – centralizes user-safe messaging.
3. Telemetry Enhancements (Sections 4 & 18) – observability for production.
4. Firecrawl & Search Providers (Sections 2 & 3) – unlocks real autosearch execution.
5. Orchestration Execution (Section 20) – enables agent automation beyond simulation.
