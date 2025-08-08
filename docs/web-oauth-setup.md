# SkynetV2 Web Interface Setup Guide

## Overview

SkynetV2 now features a Discord OAuth2 web interface that provides role-based access to guild configuration and monitoring. This replaces the legacy token-based system with proper Discord authentication and secure modal-based configuration.

## Features by Role

### Bot Owner
- Access to all guilds where the bot is present
- Global configuration management
- System-wide statistics and monitoring
- OAuth2 application configuration

### Guild Administrator (Manage Server permission)
- Access to guilds they administer
- Guild-specific configuration
- Guild usage statistics and monitoring
- Memory management for their guilds

### Regular Users  
- Read-only access to their personal usage statistics
- View enabled tools and basic guild information
- No configuration capabilities

## Setup Process

### 1. Create Discord Application

1. Go to https://discord.com/developers/applications
2. Click "New Application" and give it a name (e.g., "SkynetV2 Web Interface")
3. Go to the "OAuth2" section
4. Copy the Client ID and Client Secret (you'll need these for step 2)
5. Under "Redirects", add your domain's callback URL: `https://yourdomain.com/callback` (add `http://localhost:8080/callback` as an additional redirect for local testing if desired)

### 2. Configure the Web Interface

**All configuration is now done through secure Discord modals to protect sensitive information:**

```bash
# Configure OAuth2 credentials via secure modal (bot owner only)
[p]ai web config oauth
# Secure modal fields:
# - Discord Application Client ID
# - Discord Application Client Secret

# Set your public domain via modal
[p]ai web config url

# Optional: Configure server host/port via modal
[p]ai web config server

# View comprehensive configuration status
[p]ai web config show
```

### 3. Reverse Proxy Setup

The web interface is designed to work behind a reverse proxy for SSL termination and domain management. Here are some popular options:

#### Option A: Cloudflare Tunnel (Recommended for beginners)

1. Install cloudflared on your server
1. Login: `cloudflared tunnel login`
1. Create tunnel: `cloudflared tunnel create skynetv2`
1. Configure tunnel in `~/.cloudflared/config.yml`:

```yaml
tunnel: your-tunnel-id
credentials-file: /path/to/your-tunnel-credentials.json

ingress:
  - hostname: yourdomain.com
    service: http://localhost:8080
  - service: http_status:404
```

1. Run tunnel: `cloudflared tunnel run skynetv2`

#### Option B: Nginx (For advanced users)

```nginx
server {
    listen 443 ssl http2;
    server_name yourdomain.com;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/private.key;
    
    location / {
        proxy_pass http://localhost:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

#### Option C: Caddy

```caddyfile
yourdomain.com {
    reverse_proxy localhost:8080
}
```

### 4. Complete Setup

```bash
# Restart the web interface to apply changes
[p]ai web restart

# Check status
[p]ai web config show
```

## Access the Interface

1. Visit your configured domain (e.g., `https://yourdomain.com`)
1. Click "Login with Discord"
1. Authorize the application
1. You'll be redirected to your dashboard based on your permissions

## Security Notes

- The web interface only binds to localhost by default for security
- All external access should go through a reverse proxy with HTTPS
- OAuth2 session data is encrypted; credentials never stored in chat logs
- Users can only access guilds where they have appropriate Discord permissions
- Bot owner status is determined by Discord application ownership

## Troubleshooting

### "OAuth2 not configured" Message
- Run `[p]ai web config oauth` and enter credentials in the modal
- Ensure Client ID and Secret are correct

### "Public URL not configured" Message  
- Run `[p]ai web config url` and provide your domain in the modal
- Confirm it matches your reverse proxy configuration

### Login Fails with "Invalid redirect URI"
- Check redirect URIs in developer portal (must include `/callback` exactly)
- Include both production and any localhost testing URIs if needed

### Web Interface Won't Start
- Check for port conflicts: `netstat -tlnp | grep 8080`
- Change port via `[p]ai web config server`
- Review bot console logs for tracebacks

### Users Can't Access Expected Guilds
- Verify the bot is in the guild
- User needs "Manage Server" for admin-level guild actions
- Bot owner has global visibility

## Migration from Token System

The legacy token-based authentication is deprecated but still available for backwards compatibility. To migrate:

1. Set up OAuth2 as described above
2. Users should use the new web interface instead of token URLs
3. Legacy token endpoints return a deprecation notice
4. Tokens can still be managed via `[p]ai web token` commands

## Command Reference

### OAuth2 Configuration (Bot Owner Only)
- `[p]ai web config oauth` – Opens secure modal to set Discord OAuth2 credentials
- `[p]ai web config url` – Opens modal to set public domain
- `[p]ai web config server` – Opens modal to configure host/port
- `[p]ai web config show` – Displays current configuration (embed)
- `[p]ai web config reset` – Opens confirmation modal to reset configuration

### Server Management
- `[p]ai web restart` – Restart web interface
- `[p]ai web status` – Show current status

### Legacy Token Management (Deprecated)
- `[p]ai web token generate [hours]` – Generate legacy token
- `[p]ai web token list` – List active tokens  
- `[p]ai web token revoke <prefix>` – Revoke token
- `[p]ai web token cleanup` – Remove expired tokens

## Development Notes

For development and testing:
- Discord supports `http://localhost` redirect URIs (add explicitly in the developer portal)
- Use a tool like ngrok or Cloudflare Tunnel for temporary public URLs
- Consider a separate development Discord application
