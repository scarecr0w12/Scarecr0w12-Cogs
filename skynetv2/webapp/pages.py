"""Page handlers (dashboard, profile, guild views, config)"""
from __future__ import annotations
from aiohttp import web
from aiohttp_session import get_session
from typing import Any, Dict

async def _require_session(request: web.Request):
    session = await get_session(request); user = session.get('user')
    if not user: return None, web.HTTPFound('/')
    return user, None

async def dashboard(request: web.Request):
    webiface = request.app['webiface']
    user, resp = await _require_session(request)
    if resp: return resp
    perms = user.get('permissions', {})
    rows = []
    for gid in perms.get('guilds', []):
        g = webiface.cog.bot.get_guild(int(gid))
        if not g: continue
        rows.append(f"<tr><td>{g.name}</td><td>{g.id}</td><td><a href='/guild/{g.id}'>Open</a></td></tr>")
    body = f"<h1>Skynet Dashboard</h1><div class='card'><p>Logged in as <strong>{user.get('username')}</strong></p></div><div class='card'><h2>Your Guilds</h2><table><tr><th>Name</th><th>ID</th><th></th></tr>{''.join(rows) if rows else '<tr><td colspan=3>(none)</td></tr>'}</table></div>"
    return web.Response(text=_html_base('Dashboard', body), content_type='text/html')

async def profile(request: web.Request):
    user, resp = await _require_session(request)
    if resp: return resp
    perms = user.get('permissions', {})
    body = f"<h1>Profile</h1><div class='card'><p>User: {user.get('username')}#{user.get('discriminator')}</p><p>ID: {user.get('id')}</p><p>Bot Owner: {perms.get('bot_owner')}</p><p>Admin Guilds: {', '.join(perms.get('guild_admin', [])) or '(none)'}" f"</p></div>"
    return web.Response(text=_html_base('Profile', body), content_type='text/html')

async def guild_dashboard(request: web.Request):
    webiface = request.app['webiface']
    user, resp = await _require_session(request)
    if resp: return resp
    try:
        gid = int(request.match_info['guild_id'])
    except ValueError:
        return web.Response(text='Invalid guild id', status=400)
    if str(gid) not in user.get('permissions', {}).get('guilds', []):
        return web.Response(text='Forbidden', status=403)
    guild = webiface.cog.bot.get_guild(gid)
    if not guild:
        return web.Response(text='Guild not found', status=404)
    status = await webiface.get_guild_status(guild)
    tools_lines = ''.join(f"<li>{k}: {'enabled' if v else 'disabled'}</li>" for k,v in status['tools'].items())
    providers = ''.join(f"<li>{k}: {v}</li>" for k,v in status['providers'].items())
    body = f"<h1>Guild: {guild.name}</h1><div class='card'><h2>Providers</h2><ul>{providers}</ul></div><div class='card'><h2>Tools</h2><ul>{tools_lines}</ul></div><div class='card'><a href='/config/{guild.id}'>Configuration View</a></div>"
    return web.Response(text=_html_base(f'Guild {guild.id}', body), content_type='text/html')

async def guild_config(request: web.Request):
    webiface = request.app['webiface']
    user, resp = await _require_session(request)
    if resp: return resp
    try:
        gid = int(request.match_info['guild_id'])
    except ValueError:
        return web.Response(text='Invalid guild id', status=400)
    if str(gid) not in user.get('permissions', {}).get('guilds', []):
        return web.Response(text='Forbidden', status=403)
    guild = webiface.cog.bot.get_guild(gid)
    if not guild:
        return web.Response(text='Guild not found', status=404)
    admin = str(gid) in user.get('permissions', {}).get('guild_admin', []) or user.get('permissions', {}).get('bot_owner')
    rate_limits = await webiface.cog.config.guild(guild).rate_limits()
    providers_cfg = await webiface.cog.config.guild(guild).providers(); global_providers = await webiface.cog.config.providers()
    lines = []
    for prov in ['openai','serp','firecrawl']:
        gk = providers_cfg.get(prov, {}).get('api_key'); globk = global_providers.get(prov, {}).get('api_key')
        if gk: val = 'guild:' + (gk[:8] + '***')
        elif globk: val = 'global:' + (globk[:8] + '***')
        else: val = '(not set)'
        lines.append(f"<tr><td>{prov}</td><td>{val}</td></tr>")
    rl_rows = ''.join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k,v in rate_limits.items())
    body = f"<h1>Configuration - {guild.name}</h1><div class='card'><h2>Providers</h2><table><tr><th>Provider</th><th>Key</th></tr>{''.join(lines)}</table></div><div class='card'><h2>Rate Limits</h2><table><tr><th>Key</th><th>Value</th></tr>{rl_rows}</table></div>" + ("<div class='card'><p>Admin view enabled.</p></div>" if admin else "")
    return web.Response(text=_html_base('Guild Config', body), content_type='text/html')

BASE_STYLE = "body{font-family:Segoe UI,Arial,sans-serif;margin:20px;background:#f5f7fb;color:#222}a{color:#3366cc;text-decoration:none}nav a{margin-right:12px}.card{background:#fff;padding:16px;border-radius:8px;box-shadow:0 2px 6px rgba(0,0,0,0.06);margin:12px 0}table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:6px 8px;border-bottom:1px solid #eee;font-size:14px}th{background:#fafafa}code{background:#eef;padding:2px 4px;border-radius:4px;font-size:90%}"

def _html_base(title: str, body: str) -> str:
    return f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>{title}</title><style>{BASE_STYLE}</style></head><body><nav><a href='/dashboard'>Dashboard</a><a href='/profile'>Profile</a></nav>{body}</body></html>"

def setup(webiface: 'WebInterface'):
    app = webiface.app
    app['webiface'] = webiface
    app.router.add_get('/dashboard', dashboard)
    app.router.add_get('/profile', profile)
    app.router.add_get('/guild/{guild_id}', guild_dashboard)
    app.router.add_get('/config/{guild_id}', guild_config)
