#!/usr/bin/env python3
"""
Simple test of the Variables System without Discord dependencies
"""

import asyncio
import re
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import Dict, Any, List, Optional

@dataclass
class Variable:
    """Represents a contextual variable that can be injected into prompts."""
    name: str
    description: str
    value_type: str  # "string", "datetime", "user", "channel", "guild"
    category: str = "general"  # general, time, user, server, system
    requires_guild: bool = False
    requires_user: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return asdict(self)

class SimpleVariableResolver:
    """Simple version of the variable resolver for testing."""
    
    def __init__(self):
        self._variables: Dict[str, Variable] = {}
        self._initialize_variables()
    
    def _initialize_variables(self):
        """Initialize available variables."""
        # Time variables
        self._variables["timestamp"] = Variable("timestamp", "Current timestamp in ISO format", "datetime", "time")
        self._variables["time"] = Variable("time", "Current time in HH:MM format", "string", "time")
        self._variables["date"] = Variable("date", "Current date in YYYY-MM-DD format", "string", "time")
        self._variables["datetime"] = Variable("datetime", "Current date and time in readable format", "string", "time")
        
        # User variables  
        self._variables["user_name"] = Variable("user_name", "Username of the current user", "string", "user", requires_user=True)
        self._variables["user_display_name"] = Variable("user_display_name", "Display name (nickname or username) of the current user in the server", "string", "user", requires_user=True, requires_guild=True)
        
        # Server variables
        self._variables["server_name"] = Variable("server_name", "Name of the current Discord server", "string", "server", requires_guild=True)
        self._variables["channel_name"] = Variable("channel_name", "Name of the current channel", "string", "server", requires_guild=True)
        
        # System variables
        self._variables["bot_name"] = Variable("bot_name", "Name of the bot", "string", "system")
        self._variables["command_prefix"] = Variable("command_prefix", "Command prefix for the bot in this server", "string", "system", requires_guild=True)
    
    async def resolve_variable(self, var_name: str, guild=None, channel=None, user=None) -> Optional[str]:
        """Resolve a single variable to its value."""
        if var_name not in self._variables:
            return None
        
        variable = self._variables[var_name]
        
        # Check requirements
        if variable.requires_guild and not guild:
            return f"[{var_name}: requires guild context]"
        if variable.requires_user and not user:
            return f"[{var_name}: requires user context]"
        
        # Time variables
        if var_name == "timestamp":
            return datetime.now().isoformat()
        elif var_name == "time":
            return datetime.now().strftime("%H:%M")
        elif var_name == "date":
            return datetime.now().strftime("%Y-%m-%d")
        elif var_name == "datetime":
            return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Mock user variables
        elif var_name == "user_name" and user:
            return user.get("name", "TestUser")
        elif var_name == "user_display_name" and user and guild:
            return user.get("display_name", user.get("name", "TestUser"))
        
        # Mock server variables
        elif var_name == "server_name" and guild:
            return guild.get("name", "Test Server")
        elif var_name == "channel_name" and channel:
            return channel.get("name", "test-channel")
        
        # Mock system variables
        elif var_name == "bot_name":
            return "SkynetV2"
        elif var_name == "command_prefix" and guild:
            return "!"
        
        return f"[{var_name}: unresolved]"
    
    async def resolve_prompt(self, prompt: str, guild=None, channel=None, user=None) -> str:
        """Resolve all variables in a prompt string."""
        if not prompt:
            return prompt
        
        # Find all variable placeholders: {{variable_name}}
        pattern = r'\{\{([a-zA-Z_][a-zA-Z0-9_]*)\}\}'
        matches = re.findall(pattern, prompt)
        
        resolved_prompt = prompt
        for var_name in matches:
            placeholder = f"{{{{{var_name}}}}}"
            value = await self.resolve_variable(var_name, guild, channel, user)
            if value is not None:
                resolved_prompt = resolved_prompt.replace(placeholder, value)
        
        return resolved_prompt
    
    def get_variables_help_text(self, guild=None, user=None) -> str:
        """Generate help text for available variables."""
        variables = []
        
        for variable in self._variables.values():
            # Check if requirements are met
            if variable.requires_guild and not guild:
                continue
            if variable.requires_user and not user:
                continue
            variables.append(variable)
        
        if not variables:
            return "No variables available in this context."
        
        # Group by category
        categories = {}
        for var in variables:
            if var.category not in categories:
                categories[var.category] = []
            categories[var.category].append(var)
        
        help_text = "**Available Variables:**\n"
        help_text += "Use `{{variable_name}}` in prompts to inject contextual data.\n\n"
        
        for category, vars_list in categories.items():
            help_text += f"**{category.title()} Variables:**\n"
            for var in vars_list:
                help_text += f"• `{{{{{var.name}}}}}` - {var.description}\n"
            help_text += "\n"
        
        help_text += "**Example:** `Hello {{user_display_name}}, the time is {{time}} on {{date}}.`"
        return help_text

async def test_variables():
    """Test the variables system."""
    
    resolver = SimpleVariableResolver()
    
    # Mock objects
    user = {"name": "Alice", "display_name": "Ace"}
    channel = {"name": "general"}
    guild = {"name": "Awesome Server"}
    
    print("=== SkynetV2 Variables System Test ===\n")
    
    # Test individual variables
    print("Individual Variable Tests:")
    print("-" * 30)
    
    test_vars = ["timestamp", "time", "date", "datetime", "user_name", "user_display_name", 
                "server_name", "channel_name", "bot_name", "command_prefix"]
    
    for var_name in test_vars:
        value = await resolver.resolve_variable(var_name, guild, channel, user)
        print(f"{{{{ {var_name:<20} }}}} -> {value}")
    
    print(f"\n{'='*60}\n")
    
    # Test prompt resolution
    print("Prompt Resolution Examples:")
    print("-" * 30)
    
    test_prompts = [
        "Hello {{user_display_name}}!",
        "Welcome to {{server_name}}!",
        "Current time: {{time}} on {{date}}",
        "You are in #{{channel_name}}, use {{command_prefix}}help",
        "{{bot_name}} says hello at {{datetime}}!",
        "Complex: {{user_display_name}} in {{server_name}} at {{time}}",
        "Test unresolved: {{unknown_var}} should show placeholder",
    ]
    
    for prompt in test_prompts:
        resolved = await resolver.resolve_prompt(prompt, guild, channel, user)
        print(f"Original:  {prompt}")
        print(f"Resolved:  {resolved}")
        print()
    
    print(f"{'='*60}\n")
    
    # Test help text
    print("Variables Help Text:")
    print("-" * 30)
    help_text = resolver.get_variables_help_text(guild, user)
    print(help_text)
    
    print(f"\n{'='*60}\n")
    
    # Test context requirements
    print("Context Requirements Test:")
    print("-" * 30)
    
    print("With full context (user, guild, channel):")
    resolved = await resolver.resolve_prompt("{{user_display_name}} in {{server_name}}", guild, channel, user)
    print(f"Result: {resolved}")
    
    print("\nWithout user context:")
    resolved = await resolver.resolve_prompt("{{user_display_name}} in {{server_name}}", guild, channel, None)
    print(f"Result: {resolved}")
    
    print("\nWithout guild context:")
    resolved = await resolver.resolve_prompt("{{user_display_name}} in {{server_name}}", None, channel, user)
    print(f"Result: {resolved}")

if __name__ == "__main__":
    asyncio.run(test_variables())
