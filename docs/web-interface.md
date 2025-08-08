# Web Interface (OAuth2 Dashboard)

SkynetV2 includes an optional OAuth2-based web interface providing authenticated dashboard and JSON API endpoints. The legacy token endpoint remains deprecated for backwards compatibility.

## Current Features

- Discord OAuth2 login (identify + guilds scope)
- Dashboard listing accessible guilds (member/admin distinction)
- Admin-only guild config placeholder page (read-only for now)
- JSON API endpoints:
  - `GET /api/guilds` (authorized guilds + admin flag)
  - `GET /api/status/{guild_id}` (masked provider key presence + tool/config summary)
  - `GET /api/health` (uptime, guild_count, version)
- Session key auto-validation & regeneration (invalid Fernet keys repaired on startup)
- Masked provider key display (first/last 4 chars)

## Setup

1. Configure OAuth2 credentials:
```
[p]ai web config oauth <client_id> <client_secret>
[p]ai web config url <public_base_url>   # e.g. https://bot.example.com
```
2. (Re)load or start the cog; web server will bind `host` + `port` from config (defaults: localhost:8080)
3. Visit `https://discord.com/oauth2/authorize?client_id=<client_id>&redirect_uri=<public_base_url>/callback&response_type=code&scope=identify%20guilds` (handled automatically via `/login`)

## Security Model

| Aspect | Current | Notes |
|--------|---------|-------|
| Auth | Discord OAuth2 | Sessions stored in encrypted cookie |
| Session Key | Fernet (44 char base64) | Auto-regenerated if invalid |
| HTTPS | External / reverse proxy | Terminate TLS before bot process |
| CSRF | Not yet (no write POST) | Planned when write endpoints added |
| Rate limiting | Not yet | Planned leaky bucket per IP/user |
| Audit log | Not yet | Planned short-term access log |

### Session Key Rotation (Planned)
Internal helper `rotate_session_key()` exists; a command wrapper will be added in a future hardening task (Section 15).

## API Responses

`GET /api/guilds`
```json
{
  "guilds": [
    {"id": "123", "name": "Example", "member_count": 42, "is_admin": true}
  ]
}
```

`GET /api/status/{guild_id}`
```json
{
  "id": "123",
  "name": "Example",
  "member_count": 42,
  "model": "gpt-4o-mini",
  "providers_global": {"openai": "abcd…wxyz", "serp": "(not set)", "firecrawl": "(not set)"},
  "providers_overrides": [],
  "tools_enabled_count": 3,
  "tool_usage_kinds": 2
}
```

`GET /api/health`
```json
{"ok": true, "uptime_s": 120, "guild_count": 5, "version": "unknown"}
```

## Legacy Token Endpoint

Deprecated endpoint `/status/{guild_id}?token=...` remains (HTTP 410 message) and will be removed after governance confirmation. Remove any stored tokens from earlier MVP.

## Roadmap (Section 15 Backlog)
- Session key rotation command (admin-only) + invalidation notice
- CSRF token framework (form + header injection) when first POST write route ships
- Per-IP/user in-memory rate limiting for `/api/*`
- Auth failure logging + telemetry counter
- Access audit log (viewer + timestamp + endpoint)
- TLS / reverse proxy deployment hardening guide

## Troubleshooting
- Repeated invalid session key messages: confirm Red config storage is writable; key should be 44 chars (base64) and decode to 32 bytes.
- OAuth2 redirect mismatch: ensure public URL matches Discord application redirect URI exactly.
- 401 on APIs: session expired or not logged in; re-authorize via `/login`.
- Empty guild list: bot not in listed guilds or missing `guilds` scope consent.

## Deployment Notes
Use a reverse proxy (nginx/Caddy) to terminate TLS and forward only required paths. Deny unexpected methods until write endpoints exist.
