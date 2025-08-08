"""
Test configuration and fixtures for SkynetV2.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock


@pytest.fixture
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_bot():
    """Mock Discord bot instance."""
    bot = Mock()
    bot.get_guild = Mock(return_value=None)
    return bot


@pytest.fixture
def mock_guild():
    """Mock Discord guild."""
    guild = Mock()
    guild.id = 123456789
    guild.name = "Test Guild"
    return guild


@pytest.fixture
def mock_user():
    """Mock Discord user."""
    user = Mock()
    user.id = 987654321
    user.name = "TestUser"
    return user


@pytest.fixture
def mock_channel():
    """Mock Discord channel."""
    channel = Mock()
    channel.id = 456789123
    channel.name = "test-channel"
    return channel


@pytest.fixture
def mock_config():
    """Mock Red config system."""
    config = AsyncMock()
    
    # Default config structure
    config.providers.return_value = {}
    config.model.return_value = {"provider": "openai", "name": "gpt-4o-mini"}
    config.guild.return_value.enabled.return_value = True
    
    return config


class MockRedBotConfig:
    """Mock Red-DiscordBot config system for testing."""
    
    def __init__(self):
        self._data = {}
    
    def guild(self, guild):
        guild_data = self._data.setdefault(f"guild_{guild.id}", {})
        return MockConfigGroup(guild_data)
    
    def global_config(self):
        global_data = self._data.setdefault("global", {})
        return MockConfigGroup(global_data)


class MockConfigGroup:
    """Mock config group with async context support."""
    
    def __init__(self, data):
        self._data = data
    
    async def __call__(self):
        return self._data
    
    def __getattr__(self, name):
        return MockConfigGroup(self._data.setdefault(name, {}))
    
    async def __aenter__(self):
        return self._data
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass
