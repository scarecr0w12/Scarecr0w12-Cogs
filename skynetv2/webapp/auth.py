"""Authentication & OAuth related routes."""
from __future__ import annotations
from aiohttp import web, ClientSession
from aiohttp_session import get_session, new_session
from urllib.parse import urlencode
import secrets
from typing import Dict, Any, List

def get_client_ip(request: web.Request) -> str:
    """Get the real client IP address, handling proxies"""
    # Check common proxy headers in order of preference
    forwarded_for = request.headers.get('X-Forwarded-For')
    if forwarded_for:
        # X-Forwarded-For can contain multiple IPs, take the first (original client)
        return forwarded_for.split(',')[0].strip()
    
    real_ip = request.headers.get('X-Real-IP')
    if real_ip:
        return real_ip.strip()
    
    cf_connecting_ip = request.headers.get('CF-Connecting-IP')  # Cloudflare
    if cf_connecting_ip:
        return cf_connecting_ip.strip()
    
    # Fallback to direct connection IP
    return request.remote or 'unknown'

# Import the HTML template function from pages module
def _html_base(title: str, body: str) -> str:
    """HTML template with consistent styling"""
    BASE_STYLE = "body{font-family:Segoe UI,Arial,sans-serif;margin:20px;background:#f5f7fb;color:#222}a{color:#3366cc;text-decoration:none}nav a{margin-right:12px}.card{background:#fff;padding:16px;border-radius:8px;box-shadow:0 2px 6px rgba(0,0,0,0.06);margin:12px 0}table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:6px 8px;border-bottom:1px solid #eee;font-size:14px}th{background:#fafafa}code{background:#eef;padding:2px 4px;border-radius:4px;font-size:90%}"
    return f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>{title}</title><style>{BASE_STYLE}</style></head><body>{body}</body></html>"

async def get_user_permissions(webiface: Any, user_info: Dict, user_guilds: List[Dict]) -> Dict[str, Any]:
    user_id = int(user_info['id'])
    permissions = {'bot_owner': False,'guild_admin': [],'guild_member': [],'guilds': []}
    
    try:
        app_info = await webiface.cog.bot.application_info()
        print(f"SkynetV2 Web: Checking ownership for user {user_id}")
        print(f"SkynetV2 Web: App info - owner: {getattr(app_info, 'owner', None)}, team: {getattr(app_info, 'team', None)}")
        
        # Check if user is bot owner (handle both individual and team ownership)
        is_owner = False
        
        # First check individual ownership
        if hasattr(app_info, 'owner') and app_info.owner and hasattr(app_info.owner, 'id'):
            if user_id == app_info.owner.id:
                is_owner = True
                print(f"SkynetV2 Web: ✅ User is individual bot owner - user: {user_id}, bot owner: {app_info.owner.id}")
        
        # Then check team ownership
        if not is_owner and hasattr(app_info, 'team') and app_info.team:
            print(f"SkynetV2 Web: Checking team ownership - team: {app_info.team.name} ({app_info.team.id})")
            if hasattr(app_info.team, 'members') and app_info.team.members:
                team_member_ids = []
                for member in app_info.team.members:
                    team_member_ids.append(member.id)
                    if user_id == member.id:
                        is_owner = True
                        print(f"SkynetV2 Web: ✅ User is team member - user: {user_id}, role: {getattr(member, 'membership_state', 'unknown')}")
                        break
                if not is_owner:
                    print(f"SkynetV2 Web: ❌ User not in team - user: {user_id}, team members: {team_member_ids}")
            else:
                print(f"SkynetV2 Web: Team has no members or members not accessible")
        
        if is_owner:
            print("SkynetV2 Web: ✅ User confirmed as bot owner - granting full access")
            permissions['bot_owner'] = True
            # For bot owners, store only first 50 guilds to avoid cookie size limits
            bot_guild_ids = [str(g.id) for g in list(webiface.cog.bot.guilds)[:50]]
            permissions['guilds'] = bot_guild_ids
            permissions['guild_admin'] = bot_guild_ids
            return permissions
        else:
            print(f"SkynetV2 Web: ❌ User is not bot owner - user: {user_id}")
    
    except Exception as e:
        print(f"SkynetV2 Web: Error checking bot ownership: {e}")
        import traceback
        traceback.print_exc()
    
    # Process guild permissions for non-owners
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
    # Use styled template from pages module
    body = """
    <div class='card'>
        <h1>SkynetV2 Web Interface</h1>
        <p>Welcome to the SkynetV2 web interface. Please log in with your Discord account to continue.</p>
        <div style='text-align: center; margin-top: 20px;'>
            <a href='/login' style='background: #5865F2; color: white; padding: 12px 24px; border-radius: 6px; text-decoration: none; font-weight: 500;'>
                🔗 Login with Discord
            </a>
        </div>
    </div>
    """
    return web.Response(text=_html_base('SkynetV2 Login', body), content_type='text/html')

async def login(request: web.Request):
    webiface = request.app['webiface']
    client_ip = get_client_ip(request)
    state = secrets.token_urlsafe(32)
    session = await new_session(request)
    session['oauth_state'] = state
    print(f"SkynetV2 Web: Login initiated from {client_ip}")
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
    client_ip = get_client_ip(request)
    code = request.query.get('code'); state = request.query.get('state')
    print(f"SkynetV2 Web: OAuth callback from {client_ip} - code: {'***' if code else None}, state: {'***' if state else None}")
    if not code:
        print(f"SkynetV2 Web: OAuth callback failed from {client_ip} - missing code")
        return web.Response(text='Authorization failed: Missing code', status=400)
    session = await get_session(request)
    stored_state = session.get('oauth_state')
    print(f"SkynetV2 Web: OAuth state check from {client_ip} - provided: {'***' if state else None}, stored: {'***' if stored_state else None}")
    if state != stored_state:
        print(f"SkynetV2 Web: OAuth callback failed from {client_ip} - state mismatch")
        return web.Response(text='Authorization failed: Invalid state', status=400)
    print(f"SkynetV2 Web: OAuth callback from {client_ip} - starting token exchange")
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
            print(f"SkynetV2 Web: Got user info for {user_info.get('username', 'unknown')} from {client_ip}")
            async with client.get('https://discord.com/api/users/@me/guilds', headers=headers) as resp:
                if resp.status != 200: return web.Response(text='Failed to get guild info', status=400)
                user_guilds = await resp.json()
            print(f"SkynetV2 Web: Got {len(user_guilds)} guilds for user from {client_ip}")
    except Exception as e:
        print(f"SkynetV2 Web: OAuth2 error from {client_ip}: {e}")
        return web.Response(text='OAuth2 error occurred. Please try again later.', status=500)
    permissions = await get_user_permissions(webiface, user_info, user_guilds)
    print(f"SkynetV2 Web: User permissions: {permissions}")
    
    # Store minimal session data to avoid cookie size limits
    session_user_data = {
        'id': user_info['id'],
        'username': user_info['username'],
        'discriminator': user_info.get('discriminator','0000'),
        'avatar': user_info.get('avatar'),
        'permissions': permissions
        # Note: Full guild data not stored in session to keep cookie size manageable
        # Guild data can be fetched from bot.guilds when needed
    }
    
    # Debug: Check session data size (permissions already converted to lists in get_user_permissions)
    import json
    try:
        session_size = len(json.dumps(session_user_data))
        print(f"SkynetV2 Web: Session data size: {session_size} bytes")
    except TypeError as e:
        print(f"SkynetV2 Web: Session data serialization error: {e}")
        # Emergency fix - ensure all sets are converted to lists
        if 'permissions' in session_user_data:
            perms = session_user_data['permissions']
            for key, value in perms.items():
                if isinstance(value, set):
                    perms[key] = list(value)
        session_size = len(json.dumps(session_user_data))
        print(f"SkynetV2 Web: Fixed session data size: {session_size} bytes")
    
    session['user'] = session_user_data
    
    # Ensure session is properly saved before redirect
    print(f"SkynetV2 Web: Session data set for {client_ip} - verifying: {session.get('user', {}).get('username', 'NOT_FOUND')}")
    session.changed()  # Force session save
    print(f"SkynetV2 Web: OAuth callback successful for {client_ip} - redirecting to dashboard")
    return web.HTTPFound('/dashboard')

async def logout(request: web.Request):
    session = await get_session(request); session.clear(); return web.HTTPFound('/')

def setup(webiface: Any):
    app = webiface.app
    app['webiface'] = webiface
    app.router.add_get('/', index)
    app.router.add_get('/login', login)
    app.router.add_get('/callback', oauth_callback)
    app.router.add_get('/logout', logout)
