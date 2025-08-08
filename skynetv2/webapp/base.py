"""Shared helpers extracted from WebInterface for modular pages."""
from __future__ import annotations
from aiohttp import web
from aiohttp_session import get_session
from typing import Any, Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from .interface import WebInterface

class BaseViews:
    def __init__(self, webiface: 'WebInterface'):
        self.web = webiface
        self.cog = webiface.cog

    async def require_session(self, request: web.Request):
        session = await get_session(request)
        user = session.get('user')
        if not user:
            return None, web.HTTPFound('/')
        return user, None

    def html_base(self, title: str, body: str) -> web.Response:
        html = f"""<!DOCTYPE html><html><head><meta charset='utf-8'><title>{title}</title>
<style>body{{font-family:Segoe UI,Arial,sans-serif;margin:20px;background:#f5f7fb;color:#222}}a{{color:#3366cc;text-decoration:none}}nav a{{margin-right:12px}}.card{{background:#fff;padding:16px;border-radius:8px;box-shadow:0 2px 6px rgba(0,0,0,0.06);margin:12px 0}}table{{border-collapse:collapse;width:100%}}th,td{{text-align:left;padding:6px 8px;border-bottom:1px solid #eee;font-size:14px}}th{{background:#fafafa}}code{{background:#eef;padding:2px 4px;border-radius:4px;font-size:90%}}</style></head><body>
<nav><a href='/dashboard'>Dashboard</a><a href='/profile'>Profile</a></nav>
{body}</body></html>"""
        return web.Response(text=html, content_type='text/html')

    async def check_guild_access(self, user: Dict[str, Any], guild_id: int) -> bool:
        return str(guild_id) in (user.get('permissions', {}).get('guilds', []))
