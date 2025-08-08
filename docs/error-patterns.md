# Error Message Patterns

Guidelines for consistent, user-friendly error handling across SkynetV2.

## Error Types

### Provider Errors (`ProviderError`)

**Pattern**: Technical provider issues that need user-safe translation
```python
# Good - user-friendly
await ctx.send("AI service unavailable. Please try again later.")

# Bad - too technical  
await ctx.send(f"Provider error: {e}")
```

**Common Cases**:
- Missing API keys → "AI service not configured. Contact admin."
- Rate limits → "Service busy. Please wait a moment and try again."
- Invalid models → "Selected model unavailable. Try a different model."
- Network errors → "Connection issue. Please try again."

### Configuration Errors

**Pattern**: Missing or invalid configuration
```python
# Good
await ctx.send("Search provider not configured. Use `[p]ai search set <provider>`")

# Bad
await ctx.send("Error: search provider None not found")
```

### Permission Errors

**Pattern**: Access denied or governance violations
```python
# Good
await ctx.send("You don't have permission to use this tool.")
await ctx.send("Daily usage limit exceeded. Try again tomorrow.")

# Bad  
await ctx.send("Error: user not in bypass_roles list")
```

### Tool Execution Errors

**Pattern**: Tool-specific failures during execution
```python
# Good
await ctx.send("Search failed. Please check your query and try again.")
await ctx.send("Unable to scrape that URL. It may be blocked or unavailable.")

# Bad
await ctx.send(f"HTTP 403 Forbidden on URL {url}")
```

## Error Response Formats

### Command Errors (Prefix Commands)
```python
try:
    result = await some_operation()
    await ctx.send(f"Success: {result}")
except ProviderError as e:
    await ctx.send("AI service issue. Please try again or contact admin.")
except Exception as e:
    logger.error(f"Unexpected error in {ctx.command}: {e}")
    await ctx.send("Something went wrong. Please try again.")
```

### Slash Command Errors (Interactions)
```python
try:
    result = await some_operation()
    await interaction.response.send_message(f"Success: {result}")
except ProviderError as e:
    await interaction.response.send_message(
        "AI service issue. Please try again or contact admin.", 
        ephemeral=True
    )
except Exception as e:
    logger.error(f"Unexpected error in slash command: {e}")
    await interaction.response.send_message(
        "Something went wrong. Please try again.", 
        ephemeral=True
    )
```

### Streaming Response Errors
```python
msg = await ctx.send("Thinking...")
try:
    # streaming response
    await msg.edit(content=final_content)
except Exception as e:
    await msg.edit(content="Response interrupted. Please try again.")
```

## Security Guidelines

### Information Disclosure
- **Never** include API keys, tokens, or internal paths in error messages
- **Avoid** exposing internal service names or technical details  
- **Mask** sensitive data: `"API key: sk-...XXXX"`

### User-Safe Patterns
```python
# Good - safe and helpful
"Configuration missing. Contact server admin."
"Service temporarily unavailable."
"Invalid input format. Please check and try again."

# Bad - exposes internals
f"Missing key in config.providers.openai.api_key"
f"HTTP 401 from api.openai.com/v1/chat/completions"  
f"Database connection failed at localhost:5432"
```

## Consistent Message Categories

### Success Messages
- Brief, action-oriented: `"Model updated to gpt-4o-mini"`
- Include relevant details: `"Exported 45 memory items"`

### Warning Messages  
- Clear implications: `"This will clear all memory. Use 'true' to confirm."`
- Suggest alternatives: `"Tool disabled. Enable with '[p]ai tools enable <tool>'"`

### Error Messages
- Immediate cause: `"Search query cannot be empty"`
- Next steps: `"Try '[p]help ai search' for usage examples"`
- No blame: `"Unable to process request"` vs `"You provided invalid input"`

### Info Messages
- Context-appropriate: `"🔒 = Admin only"` (in tool listings)
- Ephemeral for admins: `"Set OpenAI API key (guild scope)"` 

## Implementation Checklist

- [ ] Use `ProviderError` for provider-specific issues
- [ ] Keep slash command errors ephemeral  
- [ ] Log technical details, show user-friendly messages
- [ ] Include next steps in error messages where helpful
- [ ] Mask sensitive information in all outputs
- [ ] Test error paths with real scenarios
- [ ] Document error conditions in command help
