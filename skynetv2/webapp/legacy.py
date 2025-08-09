"""Legacy token-based status endpoint for backwards compatibility."""
from __future__ import annotations
from aiohttp import web
import time
from typing import Dict, Any
import discord

async def validate_token(webiface: 'WebInterface', guild: discord.Guild, token: str) -> bool:
    tokens = await webiface.cog.config.guild(guild).web_tokens()
    if token in tokens:
        data = tokens[token]; exp = data.get('expires', 0)
        if time.time() < exp:
            return True
        # cleanup
        async with webiface.cog.config.guild(guild).web_tokens() as td:
            td.pop(token, None)
    return False

async def render_status_page(webiface: 'WebInterface', guild: discord.Guild, data: Dict[str, Any]) -> str:
    usage = data['usage']; tokens = usage.get('tokens', {}); cost = usage.get('cost', {})
    tools_text = '<br>'.join(f"{k}: {'✅ Enabled' if v else '❌ Disabled'}" for k,v in data['tools'].items())
    providers_text = '<br>'.join(f"{k}: {v}" for k,v in data['providers'].items())
    memory_text = 'No stored messages'
    if data['memory']:
        parts = []
        for ch_id, count in data['memory'].items():
            ch = guild.get_channel(int(ch_id)) if guild else None
            name = ch.name if ch else f"Channel {ch_id}"
            parts.append(f"{name}: {count} messages")
        memory_text = '<br>'.join(parts)
    return f"""<!DOCTYPE html><html><head><meta charset='utf-8'><title>SkynetV2 - {data['guild_name']} Status</title><style>body{{font-family:Segoe UI,Arial,sans-serif;margin:0;padding:20px;background:linear-gradient(135deg,#667eea,#764ba2);color:#222}}.container{{max-width:1000px;margin:0 auto;background:#fff;padding:30px;border-radius:12px;box-shadow:0 8px 32px rgba(0,0,0,.1)}}h1{{margin-top:0}}</style></head><body><div class='container'><h1>🤖 SkynetV2 Status: {data['guild_name']}</h1><h3>Usage</h3><p>Total Tokens: {tokens.get('total',0):,}<br>Prompt: {tokens.get('prompt',0):,}<br>Completion: {tokens.get('completion',0):,}<br>Est. Cost: ${cost.get('usd',0.0):.4f}</p><h3>Rate Limits</h3><pre>{data['rate_limits']}</pre><h3>Tools</h3><p>{tools_text}</p><h3>Providers</h3><p>{providers_text}</p><h3>Memory</h3><p>{memory_text}</p><p>Guild ID: {data['guild_id']} • Members: {data['member_count']}</p><p style='font-size:12px;color:#555'>Generated at {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(data['generated_at']))}</p></div></body></html>"""

async def legacy_status(request: web.Request):
    webiface = request.app['webiface']
    guild_id = request.match_info['guild_id']; token = request.query.get('token')
    if not token:
        return web.Response(text='Missing token parameter', status=400)
    try:
        gid = int(guild_id)
    except ValueError:
        return web.Response(text='Invalid guild ID', status=400)
    guild = webiface.cog.bot.get_guild(gid)
    if not guild:
        return web.Response(text='Guild not found', status=404)
    if not await validate_token(webiface, guild, token):
        return web.Response(text='Invalid or expired token', status=401)
    try:
        status_data = await webiface.get_guild_status(guild)
        html = await render_status_page(webiface, guild, status_data)
        return web.Response(text=html, content_type='text/html')
    except Exception as e:
        return web.Response(text=f'Error generating status: {e}', status=500)

def setup(webiface: 'WebInterface'):
    app = webiface.app
    app['webiface'] = webiface
    app.router.add_get('/status/{guild_id}', legacy_status)
