"""Thin wrapper interface delegating to modular route sets.
Original WebInterface will later import and use this version.
"""
from __future__ import annotations
import time
import secrets
from typing import Optional, Dict, Any, List
from aiohttp import web, ClientSession
from aiohttp_session import setup
from aiohttp_session.cookie_storage import EncryptedCookieStorage
from cryptography import fernet
import discord

class WebInterface:  # Partial; only startup + shared existing methods moved gradually
    def __init__(self, cog):
        self.cog = cog
        self.app: Optional[web.Application] = None
        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None
        self.port = 8080
        self.host = 'localhost'
        self.public_url = None
        self.client_id = None
        self.client_secret = None
        self.session_key = None

    async def _regenerate_session_key(self):
        new_key = fernet.Fernet.generate_key().decode()
        await self.cog.config.web_session_key.set(new_key)
        self.session_key = new_key.encode()
        print("SkynetV2 Web: Auto-regenerated invalid/mismatched session key.")

    async def _ensure_valid_session_key(self):
        """Validate or regenerate the Fernet session key (robust)."""
        attempts = 0
        while attempts < 3:
            key = await self.cog.config.web_session_key()
            if isinstance(key, str):
                key = key.strip()  # remove accidental whitespace/newlines
            if not key or not isinstance(key, str):
                await self._regenerate_session_key(); attempts += 1; continue
            if len(key) != 44:
                await self._regenerate_session_key(); attempts += 1; continue
            try:
                fernet.Fernet(key.encode())  # validate
                self.session_key = key.encode()
                if attempts > 0:
                    print("SkynetV2 Web: Session key validated after regeneration attempts.")
                return
            except Exception:
                await self._regenerate_session_key(); attempts += 1
        # If we reach here, something is wrong with regeneration logic/environment
        raise RuntimeError("SkynetV2 Web: Failed to establish a valid session key after retries.")

    async def initialize_config(self):
        config = self.cog.config
        # robust key load
        await self._ensure_valid_session_key()
        oauth_config = await config.oauth2()
        self.client_id = oauth_config.get('client_id')
        self.client_secret = oauth_config.get('client_secret')
        self.public_url = await config.web_public_url()
        self.host = await config.web_host() or 'localhost'
        self.port = await config.web_port() or 8080

    async def start_server(self):
        if self.app is not None:
            return
        await self.initialize_config()
        if not self.client_id or not self.client_secret:
            print("SkynetV2 Web: Discord OAuth2 not configured.")
            return
        if not self.public_url:
            print("SkynetV2 Web: Public URL not configured.")
            return
        self.app = web.Application()
        # session storage with key auto-repair fallback
        try:
            setup(self.app, EncryptedCookieStorage(self.session_key, max_age=86400))
        except Exception as e:
            print(f"SkynetV2 Web: Initial session storage setup failed ({e}); regenerating key.")
            try:
                await self._regenerate_session_key()
                setup(self.app, EncryptedCookieStorage(self.session_key, max_age=86400))
            except Exception as e2:
                print(f"SkynetV2 Web: Failed to initialize session storage after regeneration: {e2}")
                return
        # defer route registration to package init
        from . import auth, pages, api  # noqa
        auth.setup(self)
        pages.setup(self)
        api.setup(self)
        # legacy token endpoint
        from . import legacy  # noqa
        legacy.setup(self)
        # prompts (new prompt templates CRUD)
        try:
            from . import prompts  # noqa
            prompts.setup(self)
        except Exception as e:  # safety: do not crash whole server if prompts fail
            print(f"SkynetV2 Web: Failed to load prompts module: {e}")
        try:
            self.runner = web.AppRunner(self.app)
            await self.runner.setup()
            self.site = web.TCPSite(self.runner, self.host, self.port)
            await self.site.start()
            print(f"SkynetV2 web interface started on http://{self.host}:{self.port}")
            if self.public_url:
                print(f"Public URL configured: {self.public_url}")
        except OSError as e:
            if getattr(e, 'errno', None) == 98:
                self.port += 1
                if self.port > 8090:
                    raise RuntimeError("Could not find available port for web interface")
                await self.start_server()
            else:
                raise

    async def stop_server(self):
        if self.site:
            await self.site.stop(); self.site = None
        if self.runner:
            await self.runner.cleanup(); self.runner = None
        self.app = None

    # ---- Status helpers migrated from legacy web.py ----
    async def get_guild_status(self, guild: discord.Guild) -> Dict[str, Any]:
        """Collect guild status information (ported)."""
        config = self.cog.config.guild(guild)
        rate_limits = await config.rate_limits()
        usage = await config.usage()
        tools_status = {}
        for tool_name in self.cog._tool_registry.keys():
            try:
                tools_status[tool_name] = await self.cog._tool_is_enabled(guild, tool_name)
            except Exception:
                tools_status[tool_name] = False
        providers = await config.providers()
        global_providers = await self.cog.config.providers()
        provider_status: Dict[str, str] = {}
        for provider in ['openai', 'serp', 'firecrawl']:
            guild_key = providers.get(provider, {}).get('api_key')
            global_key = global_providers.get(provider, {}).get('api_key')
            if guild_key:
                provider_status[provider] = f"guild:{guild_key[:8]}***"
            elif global_key:
                provider_status[provider] = f"global:{global_key[:8]}***"
            else:
                provider_status[provider] = "not configured"
        memory = await config.memory()
        per_channel = memory.get('per_channel', {})
        memory_info: Dict[str, int] = {}
        for ch_id, data in per_channel.items():
            try:
                msg_count = len(data.get('messages', []))
                if msg_count > 0:
                    memory_info[ch_id] = msg_count
            except Exception:
                continue
        return {
            'guild_name': guild.name,
            'guild_id': guild.id,
            'member_count': guild.member_count,
            'rate_limits': rate_limits,
            'usage': usage,
            'tools': tools_status,
            'providers': provider_status,
            'memory': memory_info,
            'generated_at': time.time(),
        }
