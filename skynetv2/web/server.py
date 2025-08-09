"""Web server wrapper exposing start/stop used by cog.
Bridges to modular webapp WebInterface implementation.
"""
from __future__ import annotations
from typing import Optional, Any

try:
    from ..webapp.interface import WebInterface
except Exception:  # fallback if module not present
    WebInterface = None  # type: ignore

class WebServer:
    def __init__(self, cog):
        self.cog = cog
        impl_cls: Any = WebInterface  # type: ignore
        self._impl = impl_cls(cog) if impl_cls else None

    # Backwards compatibility property accessors
    @property
    def app(self):  # legacy code checks self.web.app
        return getattr(self._impl, 'app', None)

    @property
    def host(self):  # optional exposure
        return getattr(self._impl, 'host', None)

    @property
    def port(self):  # optional exposure
        return getattr(self._impl, 'port', None)

    @property
    def public_url(self):  # optional exposure
        return getattr(self._impl, 'public_url', None)

    async def start(self):
        if self._impl:
            await self._impl.start_server()

    async def stop(self):
        if self._impl:
            await self._impl.stop_server()

    # Backwards compatibility aliases (original code expected start_server/stop_server on self.web)
    async def start_server(self):  # called by existing cog code
        await self.start()

    async def stop_server(self):  # called by existing cog code
        await self.stop()

    # Optional passthrough for status helper if needed elsewhere
    async def get_guild_status(self, guild):  # type: ignore
        if self._impl and hasattr(self._impl, 'get_guild_status'):
            return await self._impl.get_guild_status(guild)
        return {}
