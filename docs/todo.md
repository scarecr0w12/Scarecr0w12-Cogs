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

- [ ] Implement `search_serp.py` provider (key in providers map, executor pattern like OpenAI).
- [ ] Key set command pattern (reuse provider key set) + validation.
- [ ] Error handling (network timeout, quota) -> clean user message.
- [ ] Update provider list docs + README.
- [ ] Add usage telemetry (per search provider counts if needed).
- [ ] vibe_check

## 3. Firecrawl Integration (Optional Next)

- [ ] Create adapter (search/scrape/crawl/deep_research wrappers).
- [ ] Config keys: global api_key, optional guild override; safety: deny internal IP ranges.
- [ ] Map autosearch modes -> adapter calls when execution enabled.
- [ ] Rate limit integration (tool reuse; maybe distinct tool names like `firecrawl_crawl`).
- [ ] Threat model + docs update.
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
Process reminder: Complete one cluster -> update docs/changelog -> run vibe_check -> commit.
