# Web Interface (MVP)

SkynetV2 includes an optional web interface that provides read-only access to guild configuration and usage statistics.

## Features

- **Guild Status Dashboard**: View current configuration, usage stats, and provider status
- **Token-based Authentication**: Secure access with generated tokens
- **Read-only Access**: No configuration changes possible through web interface
- **Local Access Only**: Currently limited to localhost for security

## Setup

### 1. Start the Web Interface

The web interface starts automatically when the cog loads. It will find an available port starting from 8080.

### 2. Generate Access Token

Guild administrators can generate web access tokens:

```
[p]ai web token generate [hours]
```

- `hours`: Token expiry in hours (1-168, default: 24)
- Token will be sent via DM with the access URL
- Keep the URL private - anyone with it can view your guild's stats

### 3. Access the Interface

Visit the URL provided in your DM:
```
http://localhost:8080/status/{guild_id}?token={your_token}
```

## Available Information

The web interface displays:

### Usage Statistics
- Total tokens consumed (prompt, completion, total)
- Estimated costs in USD
- Chat activity metrics

### Configuration
- Current rate limits
- Tool status (enabled/disabled)
- Provider configuration status
- Memory usage by channel

### Guild Information
- Guild name and member count
- Generation timestamp

## Security Considerations

### Current MVP Limitations
- **Localhost only**: Interface binds to `localhost` only
- **No HTTPS**: Not required for localhost access
- **Token-based auth**: Simple bearer token authentication
- **Read-only**: No write operations supported

### Token Management

```bash
# List active tokens
[p]ai web token list

# Revoke specific token (by prefix)
[p]ai web token revoke {token_prefix}

# Clean up expired tokens
[p]ai web token cleanup

# Check web interface status
[p]ai web status
```

### Best Practices
1. **Short token lifespans**: Use shorter expiry times for sensitive guilds
2. **Regular cleanup**: Remove expired tokens periodically
3. **Monitor access**: Check token list for unexpected entries
4. **Secure environment**: Ensure bot hosting environment is secure

## Commands Reference

### Token Management
| Command | Description | Permission |
|---------|-------------|------------|
| `[p]ai web token generate [hours]` | Generate new access token | Manage Guild |
| `[p]ai web token list` | List active tokens | Manage Guild |
| `[p]ai web token revoke <prefix>` | Revoke token by prefix | Manage Guild |
| `[p]ai web token cleanup` | Remove expired tokens | Manage Guild |
| `[p]ai web status` | Show web interface status | Manage Guild |

## Troubleshooting

### Web Interface Not Starting
- Check console for port conflicts
- Interface will try ports 8080-8090
- Ensure no other services are using these ports

### Token Issues
- Tokens expire after specified time
- Use `[p]ai web token cleanup` to remove expired tokens
- Check token prefix matches when revoking

### Access Issues
- Ensure URL is accessed from the same machine running the bot
- Check that token hasn't expired
- Verify guild ID in URL matches your guild

## Future Enhancements

The current implementation is an MVP. Planned improvements include:
- HTTPS support for remote access
- Discord OAuth2 integration
- Configuration editing through web interface
- Real-time updates and WebSocket support
- Advanced charts and analytics
- Multi-guild management interface

## Technical Notes

### Architecture
- Built on `aiohttp` framework
- Integrates with Red's Config system
- Async/await throughout
- Automatic lifecycle management

### Configuration Storage
Web tokens are stored in Red's config under:
```
guild.web_tokens: {
    "token_string": {
        "created_by": user_id,
        "created_at": timestamp,
        "expires": timestamp
    }
}
```

### Performance
- Minimal overhead when not accessed
- Efficient config queries
- No background tasks or polling
- Graceful shutdown handling
