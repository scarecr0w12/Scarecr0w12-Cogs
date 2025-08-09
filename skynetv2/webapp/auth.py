"""Authentication & OAuth related routes."""
from __future__ import annotations
from aiohttp import web, ClientSession
from aiohttp_session import get_session, new_session
from urllib.parse import urlencode
import secrets
from typing import Dict, Any, List

async def get_user_permissions(webiface: 'WebInterface', user_info: Dict, user_guilds: List[Dict]) -> Dict[str, Any]:
    user_id = int(user_info['id'])
    permissions = {'bot_owner': False,'guild_admin': [],'guild_member': [],'guilds': []}
    app_info = await webiface.cog.bot.application_info()
    if user_id == app_info.owner.id:
        permissions['bot_owner'] = True
        bot_guilds = [str(g.id) for g in webiface.cog.bot.guilds]
        permissions['guilds'] = bot_guilds
        permissions['guild_admin'] = bot_guilds
        return permissions
    bot_guild_ids = {g.id for g in webiface.cog.bot.guilds}
    for guild_info in user_guilds:
        gid = guild_info['id']
        if int(gid) not in bot_guild_ids:
            continue
        permissions['guilds'].append(str(gid))
        permissions['guild_member'].append(str(gid))
        if guild_info.get('permissions', 0) & 0x00000020:
            permissions['guild_admin'].append(str(gid))
    return permissions

async def index(request: web.Request):
    webiface = request.app['webiface']
    session = await get_session(request)
    if session.get('user'):
        return web.HTTPFound('/dashboard')
    # kept minimal, could be imported from legacy
    return web.Response(text="<html><body><h1>SkynetV2</h1><a href='/login'>Login with Discord</a></body></html>", content_type='text/html')

async def login(request: web.Request):
    webiface = request.app['webiface']
    state = secrets.token_urlsafe(32)
    session = await new_session(request)
    session['oauth_state'] = state
    params = {
        'client_id': webiface.client_id,
        'redirect_uri': f"{webiface.public_url}/callback",
        'response_type': 'code',
        'scope': 'identify guilds',
        'state': state
    }
    return web.HTTPFound(f"https://discord.com/api/oauth2/authorize?{urlencode(params)}")

async def oauth_callback(request: web.Request):
    webiface = request.app['webiface']
    code = request.query.get('code'); state = request.query.get('state')
    print(f"SkynetV2 Web: OAuth callback - code: {'***' if code else None}, state: {'***' if state else None}")
    if not code:
        print("SkynetV2 Web: OAuth callback failed - missing code")
        return web.Response(text='Authorization failed: Missing code', status=400)
    session = await get_session(request)
    stored_state = session.get('oauth_state')
    print(f"SkynetV2 Web: OAuth state check - provided: {'***' if state else None}, stored: {'***' if stored_state else None}")
    if state != stored_state:
        print("SkynetV2 Web: OAuth callback failed - state mismatch")
        return web.Response(text='Authorization failed: Invalid state', status=400)
    print("SkynetV2 Web: OAuth callback - starting token exchange")
    try:
        async with ClientSession() as client:
            token_data = {'client_id': webiface.client_id,'client_secret': webiface.client_secret,'grant_type': 'authorization_code','code': code,'redirect_uri': f"{webiface.public_url}/callback"}
            async with client.post('https://discord.com/api/oauth2/token', data=token_data) as resp:
                if resp.status != 200: return web.Response(text='Failed to get access token', status=400)
                token_info = await resp.json()
            access_token = token_info['access_token']
            headers = {'Authorization': f'Bearer {access_token}'}
            async with client.get('https://discord.com/api/users/@me', headers=headers) as resp:
                if resp.status != 200: return web.Response(text='Failed to get user info', status=400)
                user_info = await resp.json()
            print(f"SkynetV2 Web: Got user info for {user_info.get('username', 'unknown')}")
            async with client.get('https://discord.com/api/users/@me/guilds', headers=headers) as resp:
                if resp.status != 200: return web.Response(text='Failed to get guild info', status=400)
                user_guilds = await resp.json()
            print(f"SkynetV2 Web: Got {len(user_guilds)} guilds for user")
    except Exception as e:
        print(f"SkynetV2 Web: OAuth2 error: {e}")
        return web.Response(text='OAuth2 error occurred. Please try again later.', status=500)
    permissions = await get_user_permissions(webiface, user_info, user_guilds)
    print(f"SkynetV2 Web: User permissions: {permissions}")
    session['user'] = {'id': user_info['id'],'username': user_info['username'],'discriminator': user_info.get('discriminator','0000'),'avatar': user_info.get('avatar'),'permissions': permissions,'guilds': [g for g in user_guilds if str(g['id']) in permissions.get('guilds', [])]}
    print(f"SkynetV2 Web: OAuth callback successful - redirecting to dashboard")
    return web.HTTPFound('/dashboard')

async def logout(request: web.Request):
    session = await get_session(request); session.clear(); return web.HTTPFound('/')

def setup(webiface: 'WebInterface'):
    app = webiface.app
    app['webiface'] = webiface
    app.router.add_get('/', index)
    app.router.add_get('/login', login)
    app.router.add_get('/callback', oauth_callback)
    app.router.add_get('/logout', logout)
