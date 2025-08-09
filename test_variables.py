#!/usr/bin/env python3
"""
Test script for SkynetV2 Variables System
"""

import asyncio
from datetime import datetime

# Mock Discord objects for testing
class MockUser:
    def __init__(self, name="TestUser", user_id=123456789):
        self.name = name
        self.id = user_id
        self.mention = f"<@{user_id}>"

class MockMember:
    def __init__(self, name="TestUser", display_name="Test Nick", user_id=123456789):
        self.name = name
        self.display_name = display_name
        self.id = user_id
        self.mention = f"<@{user_id}>"
        self.joined_at = datetime(2023, 1, 15, 10, 30)

class MockChannel:
    def __init__(self, name="test-channel", channel_id=987654321):
        self.name = name
        self.id = channel_id
        self.mention = f"<#{channel_id}>"

class MockGuild:
    def __init__(self, name="Test Server", guild_id=555444333):
        self.name = name
        self.id = guild_id
        self.member_count = 42
        self._members = {}
    
    def get_member(self, user_id):
        return self._members.get(user_id)
    
    def add_member(self, member):
        self._members[member.id] = member

class MockBot:
    def __init__(self):
        self.user = MockUser("SkynetV2", 111222333)
    
    async def get_valid_prefixes(self, guild):
        return ["!", "$"]

class MockCog:
    def __init__(self):
        self.bot = MockBot()

# Import the variables system
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'skynetv2'))

from skynetv2.orchestration import VariableResolver

async def test_variables():
    """Test the variables system with mock objects."""
    
    # Set up mock objects
    cog = MockCog()
    user = MockUser("Alice", 123456789)
    member = MockMember("Alice", "Ace", 123456789)
    channel = MockChannel("general", 987654321)
    guild = MockGuild("Awesome Server", 555444333)
    guild.add_member(member)
    
    # Create variable resolver
    resolver = VariableResolver(cog)
    
    print("=== SkynetV2 Variables System Test ===\n")
    
    # Test individual variable resolution
    print("Individual Variable Tests:")
    print("-" * 30)
    
    test_vars = [
        "timestamp", "time", "date", "datetime",
        "user_name", "user_display_name", "user_mention", "user_id",
        "server_name", "server_member_count", "channel_name",
        "bot_name", "bot_mention", "command_prefix"
    ]
    
    for var_name in test_vars:
        value = await resolver.resolve_variable(var_name, guild, channel, user)
        print(f"{{{{ {var_name:<20} }}}} -> {value}")
    
    print(f"\n{'='*50}\n")
    
    # Test prompt resolution
    print("Prompt Resolution Tests:")
    print("-" * 30)
    
    test_prompts = [
        "Hello {{user_display_name}}!",
        "Welcome to {{server_name}}, we have {{server_member_count}} members.",
        "Current time: {{time}} on {{date}}",
        "You are in {{channel_mention}}, use {{command_prefix}}help for commands.",
        "{{bot_mention}} says hello to {{user_mention}} at {{datetime}}!",
        "Complex: {{user_display_name}} joined {{server_name}} on {{user_joined}} - it's now {{time}}",
    ]
    
    for prompt in test_prompts:
        resolved = await resolver.resolve_prompt(prompt, guild, channel, user)
        print(f"Original:  {prompt}")
        print(f"Resolved:  {resolved}")
        print()
    
    print(f"{'='*50}\n")
    
    # Test help text generation
    print("Available Variables Help:")
    print("-" * 30)
    help_text = resolver.get_variables_help_text(guild, user)
    print(help_text)

if __name__ == "__main__":
    asyncio.run(test_variables())
