# Knowledge Base and RAG (Draft)

Simple first, optional advanced recall later.

## Ingestion

- /ai kb add url URL
- /ai kb add file (attachments)
- /ai kb add channel (backfill last N)
- Dedup/versioning; background indexing with progress

## Storage

- Minimal chat history in Config
- Larger docs and vector store under DataManager path
- Backends: Qdrant (first), Chroma, FAISS, pgvector (later)

## Retrieval

- Query = last user message + recent summary
- Filter by guild/channel/user metadata
- Return top-k with score cutoff; preview sources

## Privacy & Ops

- Retention/TTL and pruning; opt-out per channel
- Redact sensitive data where possible
- Rate limit indexing and retrieval
