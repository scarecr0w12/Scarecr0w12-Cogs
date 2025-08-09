# SkynetV2 Variables System

## Overview

The SkynetV2 Variables System allows you to inject contextual information into AI prompts using a simple placeholder syntax. Variables are automatically resolved based on the current Discord context (server, channel, user) and provide dynamic content like timestamps, user information, server details, and system data.

## Usage

Variables use double curly brace syntax: `{{variable_name}}`

**Example:**
```
Hello {{user_display_name}}, welcome to {{server_name}}! The time is {{time}} on {{date}}.
```

**Resolves to:**
```
Hello Ace, welcome to Awesome Server! The time is 14:30 on 2025-08-08.
```

## Available Variables

### Time Variables
- `{{timestamp}}` - Current timestamp in ISO format (e.g., `2025-08-08T14:30:25.123456`)
- `{{time}}` - Current time in HH:MM format (e.g., `14:30`)
- `{{date}}` - Current date in YYYY-MM-DD format (e.g., `2025-08-08`)
- `{{datetime}}` - Current date and time in readable format (e.g., `2025-08-08 14:30:25`)
- `{{weekday}}` - Current day of the week (e.g., `Thursday`)

### User Variables
*Require user context*
- `{{user_name}}` - Discord username (e.g., `alice_123`)
- `{{user_display_name}}` - Server nickname or username (e.g., `Ace` or `alice_123`)
- `{{user_mention}}` - Mentionable user string (e.g., `<@123456789>`)
- `{{user_id}}` - Discord user ID (e.g., `123456789`)
- `{{user_joined}}` - Date when user joined the server (e.g., `2023-01-15`)
- `{{user_created}}` - Date when user's Discord account was created (e.g., `2020-05-10`)
- `{{user_avatar}}` - URL of user's avatar image

### Server Variables
*Require guild/server context*
- `{{server_name}}` - Name of the Discord server (e.g., `Awesome Community`)
- `{{server_id}}` - Discord server ID (e.g., `555444333`)
- `{{server_member_count}}` - Number of members in the server (e.g., `142`)
- `{{server_created}}` - Date when server was created (e.g., `2022-03-20`)
- `{{server_owner}}` - Name of the server owner (e.g., `ServerAdmin`)
- `{{channel_name}}` - Name of the current channel (e.g., `general`)
- `{{channel_id}}` - Discord channel ID (e.g., `987654321`)
- `{{channel_mention}}` - Mentionable channel string (e.g., `<#987654321>`)

### System Variables
- `{{bot_name}}` - Name of the bot (e.g., `SkynetV2`)
- `{{bot_mention}}` - Mentionable bot string (e.g., `<@111222333>`)
- `{{command_prefix}}` - Command prefix for the bot in this server (e.g., `!`)

## Commands

### View Available Variables
```
!ai variables
```
or
```
/ai variables
```

Shows all available variables for your current context, organized by category.

## Context Requirements

Some variables require specific Discord contexts:
- **User Variables**: Need a user to be present (commands, interactions)
- **Server Variables**: Need to be used within a Discord server
- **System Variables**: Available everywhere

If a variable can't be resolved due to missing context, it will show a message like `[variable_name: requires user context]`.

## Integration

Variables are automatically resolved in:
- **AI Chat Commands**: `!ai chat` and `/ai chat`
- **Streaming Chat**: `/ai chat` with streaming enabled
- **Future Features**: Will be integrated into more AI interactions

## Advanced Usage

### Complex Prompts
```
{{user_display_name}}, you've been a member of {{server_name}} since {{user_joined}}. 
Today is {{weekday}}, {{date}} at {{time}}. 
You're currently in {{channel_mention}} - use {{command_prefix}}help if you need assistance!
```

### Conditional Content
Variables gracefully handle missing context, so you can write prompts that work in different situations:
```
Hello {{user_display_name}}! Welcome to {{server_name}}!
```

If used outside a server context, `{{server_name}}` will show `[server_name: requires guild context]` instead of breaking the prompt.

## Technical Details

- Variables are resolved just before sending to the AI provider
- Resolution is case-sensitive: `{{User_Name}}` won't match `{{user_name}}`
- Unknown variables are left as-is in the prompt
- Variable names must start with a letter or underscore, followed by letters, numbers, or underscores
- No nested variables: `{{user_{{type}}}}` won't work

## Examples

### Welcome Message
```
Welcome to {{server_name}}, {{user_display_name}}! 
You joined on {{user_joined}} and we now have {{server_member_count}} members!
```

### Time-Aware Greeting
```
Good day, {{user_display_name}}! It's {{weekday}}, {{time}} on {{date}}.
How can {{bot_name}} help you today?
```

### Context-Rich Prompt
```
You are an AI assistant in the {{server_name}} Discord server. 
The current user is {{user_display_name}} ({{user_mention}}) in the {{channel_name}} channel.
Today is {{weekday}}, {{date}} at {{time}}.
The server has {{server_member_count}} members and was created on {{server_created}}.
Respond helpfully and mention relevant context when appropriate.
```

## Error Handling

- **Unknown Variables**: Left unchanged in the prompt (e.g., `{{unknown_var}}` stays as `{{unknown_var}}`)
- **Missing Context**: Shows descriptive message (e.g., `[user_name: requires user context]`)
- **Resolution Errors**: Shows error indicator (e.g., `[timestamp: error]`)

This ensures prompts remain functional even if variables can't be resolved.
