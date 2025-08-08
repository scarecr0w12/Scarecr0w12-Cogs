"""JSON API endpoints split out."""
from __future__ import annotations
from aiohttp import web
from aiohttp_session import get_session

async def _require_session(request: web.Request):
    from aiohttp_session import get_session
    session = await get_session(request); user = session.get('user')
    if not user: return None, web.json_response({'error':'unauthorized'}, status=401)
    return user, None

async def guilds(request: web.Request):
    webiface = request.app['webiface']
    user, resp = await _require_session(request)
    if resp: return resp
    data = []
    for gid in user.get('permissions', {}).get('guilds', []):
        g = webiface.cog.bot.get_guild(int(gid))
        if not g: continue
        data.append({'id': g.id, 'name': g.name, 'admin': gid in user.get('permissions', {}).get('guild_admin', [])})
    return web.json_response({'guilds': data})

async def guild_status(request: web.Request):
    webiface = request.app['webiface']
    user, resp = await _require_session(request)
    if resp: return resp
    try:
        gid = int(request.match_info['guild_id'])
    except ValueError:
        return web.json_response({'error': 'invalid_guild_id'}, status=400)
    if str(gid) not in user.get('permissions', {}).get('guilds', []):
        return web.json_response({'error': 'forbidden'}, status=403)
    guild = webiface.cog.bot.get_guild(gid)
    if not guild:
        return web.json_response({'error': 'not_found'}, status=404)
    status = await webiface.get_guild_status(guild)
    return web.json_response(status)

def setup(webiface: 'WebInterface'):
    app = webiface.app
    app['webiface'] = webiface
    app.router.add_get('/api/guilds', guilds)
    app.router.add_get('/api/status/{guild_id}', guild_status)
