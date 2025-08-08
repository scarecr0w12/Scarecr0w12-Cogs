# Provider Adapters (Draft)

Common interface (async):

- list_models() -> capabilities
- chat(messages, tools?, params?) -> stream or result
- embed(texts) -> vectors

Adapters planned:

- OpenAI (official SDK)
- Anthropic
- OpenRouter
- Google (Gemini)
- Ollama (local)

Search Providers:

- Dummy (placeholder deterministic responses)
- SERP (SerpAPI web search) — requires API key set via `[p]ai provider key set serp <KEY> --global` or guild scope
- Firecrawl (adapter implemented: search, scrape, crawl, deep_research; requires API key; blocks private/internal IPs for safety)

Notes:

- Normalize errors; add retry for transient failures
- Token accounting best-effort per provider
- Tool calling support where available; noop otherwise
- Search providers follow a minimal interface returning list[str] snippets (first 160–200 chars)

## Firecrawl Threat Model (Summary)

- SSRF Mitigation: Blocks localhost, private (RFC1918), link-local, and IPv6 unique-local ranges before any request.
- Depth & Scope Limits: Crawl depth hard-capped (≤3) and page limit (≤50) enforced prior to API call.
- Content Caps: Autosearch execution enforces character caps on aggregated scrape output to prevent oversized Discord responses.
- Fallback Behavior: If no API key configured, placeholder adapter returns stub results (no network calls).
- URL Sanitization: Basic hostname/IP parsing before execution; unsafe targets rejected with `[scrape:blocked]` / `[crawl:blocked]` tags.
