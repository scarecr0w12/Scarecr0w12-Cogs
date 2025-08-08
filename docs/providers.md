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

Notes:

- Normalize errors; add retry for transient failures
- Token accounting best-effort per provider
- Tool calling support where available; noop otherwise
