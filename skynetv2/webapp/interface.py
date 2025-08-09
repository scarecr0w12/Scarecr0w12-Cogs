"""Thin wrapper interface delegating to modular route sets.
Original WebInterface will later import and use this version.
"""
from __future__ import annotations
import time
import secrets
import base64
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

    async def _ensure_valid_session_key(self):
        """Validate or regenerate the Fernet session key with enhanced error handling."""
        config = self.cog.config
        key = await config.web_session_key()
        regenerate = False
        
        if not key:
            print("SkynetV2 Web: No session key found; generating new one.")
            regenerate = True
        else:
            try:
                # Ensure it is valid Fernet key (44 char base64, decodes to 32 bytes)
                if not isinstance(key, str) or len(key) != 44:
                    raise ValueError(f"Key must be 44-char string, got {type(key)} len={len(key) if key else 'None'}")
                test_fernet = fernet.Fernet(key.encode())
                print(f"SkynetV2 Web: Using existing valid session key.")
            except Exception as e:
                print(f"SkynetV2 Web: Stored session key invalid ({e}); regenerating.")
                regenerate = True
        
        if regenerate:
            # Clear any existing invalid key first
            try:
                await config.web_session_key.clear()
            except Exception:
                pass
            
            key = fernet.Fernet.generate_key().decode()
            print(f"SkynetV2 Web: Generated new session key (len={len(key)}).")
            try:
                await config.web_session_key.set(key)
                print("SkynetV2 Web: Successfully stored new session key.")
            except Exception as e:
                # Non-fatal; still attempt to use in-memory key
                print(f"SkynetV2 Web: Failed to persist session key ({e}); using ephemeral.")
        
        # Final validation before use  
        try:
            # Test that the key works with Fernet first
            if isinstance(key, str):
                # Key is stored as base64 string - test it works
                test_fernet = fernet.Fernet(key.encode('utf-8'))
                # EncryptedCookieStorage expects the decoded 32 bytes
                self.session_key = base64.urlsafe_b64decode(key)
            else:
                # Key is already bytes - test it works
                test_fernet = fernet.Fernet(key)
                # Decode if it's base64 encoded bytes, otherwise use as-is
                if len(key) == 44:  # base64 encoded
                    self.session_key = base64.urlsafe_b64decode(key)
                else:
                    self.session_key = key
                
            print("SkynetV2 Web: Session key validated for middleware setup.")
        except Exception as e:
            print(f"SkynetV2 Web: Final session key validation failed: {e}")
            # Generate emergency fallback key (generate as bytes, use decoded)
            emergency_key_bytes = fernet.Fernet.generate_key()
            self.session_key = base64.urlsafe_b64decode(emergency_key_bytes.decode())
            print("SkynetV2 Web: Using emergency ephemeral session key.")

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
        
        # Session storage setup (key validation already done in _ensure_valid_session_key)
        try:
            print(f"SkynetV2 Web: Setting up session storage with key type {type(self.session_key)}.")
            # Use compressed cookie storage with smaller max_age to reduce cookie size
            setup(self.app, EncryptedCookieStorage(
                self.session_key, 
                max_age=3600,  # 1 hour instead of 24 to reduce data accumulation
                cookie_name='skynet_session',
                httponly=True,
                secure=True if self.public_url.startswith('https') else False
            ))
            print("SkynetV2 Web: Session middleware setup successful.")
        except Exception as e:
            print(f"SkynetV2 Web: Session middleware setup failed: {e}")
            print(f"SkynetV2 Web: Key details - type: {type(self.session_key)}, len: {len(self.session_key) if self.session_key else 'None'}")
            raise
            
        # Register modular routes
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
