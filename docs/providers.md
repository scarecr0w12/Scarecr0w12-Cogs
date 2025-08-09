# Provider Adapters

## Supported Providers

### Cloud Providers

#### OpenAI
- **API Key Required**: Yes
- **Models**: GPT-4o, GPT-4o-mini, GPT-3.5-turbo, etc.
- **Features**: Chat, streaming, function calling, usage tracking
- **Setup**: Set API key via `[p]ai provider key set openai <KEY> --global`

#### Anthropic Claude
- **API Key Required**: Yes  
- **Models**: Claude 3.5 Sonnet, Claude 3.5 Haiku, Claude 3 Opus, etc.
- **Features**: Chat, streaming, tool use, usage tracking
- **Setup**: Set API key via `[p]ai provider key set anthropic <KEY> --global`

#### Groq
- **API Key Required**: Yes
- **Models**: Llama 3, Mixtral, Gemma, etc. (high-speed inference)
- **Features**: Chat, streaming, ultra-fast responses
- **Setup**: Set API key via `[p]ai provider key set groq <KEY> --global`

#### Google Gemini
- **API Key Required**: Yes
- **Models**: Gemini 1.5 Pro, Gemini 1.5 Flash, Gemini 1.0 Pro
- **Features**: Chat, streaming, multimodal support, usage tracking
- **Setup**: 
  1. Get API key from [Google AI Studio](https://makersuite.google.com/app/apikey)
  2. Set via `[p]ai provider key set gemini <KEY> --global`
  3. Install dependency: `pip install google-generativeai>=0.3.0`

### Self-Hosted/Local Providers

#### Ollama
- **API Key Required**: No
- **Default URL**: http://localhost:11434/v1
- **Models**: Any model installed in Ollama
- **Features**: Chat, streaming, local inference
- **Setup**: Install Ollama, then configure base URL if needed

#### LM Studio  
- **API Key Required**: No
- **Default URL**: http://localhost:1234/v1
- **Models**: Any model loaded in LM Studio
- **Features**: Chat, streaming, OpenAI-compatible API
- **Setup**: Start LM Studio server, load a model

#### LocalAI
- **API Key Required**: Optional
- **Base URL**: Required
- **Models**: Various open-source models
- **Features**: Chat, streaming, embeddings, TTS
- **Setup**: Deploy LocalAI instance, configure URL

#### vLLM
- **API Key Required**: Optional
- **Base URL**: Required
- **Models**: High-performance LLM serving
- **Features**: Chat, streaming, batched inference
- **Setup**: Deploy vLLM server with OpenAI-compatible API

#### Text Generation WebUI
- **API Key Required**: No
- **Default URL**: http://localhost:5000/v1
- **Models**: Any model loaded in the WebUI
- **Features**: Chat, streaming, extensive model support
- **Setup**: Start WebUI with `--api` flag

#### OpenAI-Compatible
- **API Key Required**: Optional
- **Base URL**: Required
- **Models**: Any OpenAI-compatible API
- **Features**: Chat, streaming, tool calling
- **Setup**: Configure for any OpenAI-compatible endpoint

## Common Interface

Common interface (async):

- list_models() -> capabilities
- chat(messages, tools?, params?) -> stream or result
- embed(texts) -> vectors

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
