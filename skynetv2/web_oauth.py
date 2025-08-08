"""
Web interface for SkynetV2 cog - OAuth2 implementation.
Provides Discord OAuth2 authentication with role-based permissions.
"""
from __future__ import annotations

import asyncio
import json
import secrets
import time
import base64
import hashlib
from urllib.parse import urlencode, parse_qs
from typing import Optional, Dict, Any, List
from aiohttp import web, ClientSession
from aiohttp_session import setup, get_session, new_session
from aiohttp_session.cookie_storage import EncryptedCookieStorage
from cryptography import fernet
from redbot.core import Config
import discord


class WebInterface:
    """Discord OAuth2 web interface for SkynetV2."""
    
    def __init__(self, cog):
        self.cog = cog
        self.app: Optional[web.Application] = None
        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None
        self.port = 8080  # Configurable port
        self.host = 'localhost'  # Configurable host
        self.public_url = None  # For OAuth2 redirect URI
        self.client_id = None
        self.client_secret = None
        self.session_key = None
        self._owner_id = None  # cache bot owner id
        self._start_time = time.time()
    
    async def initialize_config(self):
        """Initialize web interface configuration (validates session key)."""
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
            self.session_key = key.encode()
            test_storage = fernet.Fernet(self.session_key)
            print("SkynetV2 Web: Session key validated for middleware setup.")
        except Exception as e:
            print(f"SkynetV2 Web: Final session key validation failed: {e}")
            # Generate emergency fallback key
            self.session_key = fernet.Fernet.generate_key()
            print("SkynetV2 Web: Using emergency ephemeral session key.")
        
        # Load OAuth2 configuration
        oauth_config = await config.oauth2()
        self.client_id = oauth_config.get('client_id')
        self.client_secret = oauth_config.get('client_secret')
        self.public_url = await config.web_public_url()
        
        # Load server configuration
        self.host = await config.web_host() or 'localhost'
        self.port = await config.web_port() or 8080
        
    async def start_server(self):
        """Start the OAuth2 web server."""
        if self.app is not None:
            return  # Already running
            
        await self.initialize_config()
        
        # Validate OAuth2 configuration
        if not self.client_id or not self.client_secret:
            print("SkynetV2 Web: Discord OAuth2 not configured. Use [p]ai web config oauth commands.")
            return
            
        if not self.public_url:
            print("SkynetV2 Web: Public URL not configured. Use [p]ai web config url command.")
            return
            
        self.app = web.Application()
        
        # Setup session middleware with error handling
        try:
            print(f"SkynetV2 Web: Setting up session storage with key type {type(self.session_key)}.")
            setup(self.app, EncryptedCookieStorage(self.session_key, max_age=86400))
            print("SkynetV2 Web: Session middleware setup successful.")
        except Exception as e:
            print(f"SkynetV2 Web: Session middleware setup failed: {e}")
            print(f"SkynetV2 Web: Key details - type: {type(self.session_key)}, len: {len(self.session_key) if self.session_key else 'None'}")
            raise
        
        # Add routes
        self.setup_routes()
        
        try:
            self.runner = web.AppRunner(self.app)
            await self.runner.setup()
            
            self.site = web.TCPSite(self.runner, self.host, self.port)
            await self.site.start()
            
            print(f"SkynetV2 web interface started on http://{self.host}:{self.port}")
            if self.public_url:
                print(f"Public URL configured: {self.public_url}")
            
        except OSError as e:
            if e.errno == 98:  # Address already in use
                # Try next port
                self.port += 1
                if self.port > 8090:
                    raise RuntimeError("Could not find available port for web interface")
                await self.start_server()
            else:
                raise
                
    def setup_routes(self):
        """Setup web application routes."""
        # Authentication routes
        self.app.router.add_get('/', self.index)
        self.app.router.add_get('/login', self.login)
        self.app.router.add_get('/callback', self.oauth_callback)
        self.app.router.add_get('/logout', self.logout)
        
        # Dashboard routes
        self.app.router.add_get('/dashboard', self.dashboard)
        self.app.router.add_get('/guild/{guild_id}', self.guild_dashboard)
        self.app.router.add_get('/profile', self.user_profile)
        
        # Configuration routes (admin only)
        self.app.router.add_get('/config/{guild_id}', self.guild_config)
        self.app.router.add_post('/config/{guild_id}', self.update_guild_config)
        
        # API routes
        self.app.router.add_get('/api/guilds', self.api_guilds)
        self.app.router.add_get('/api/status/{guild_id}', self.api_guild_status)
        self.app.router.add_get('/api/health', self.api_health)
        
        # Legacy token endpoint for backwards compatibility
        self.app.router.add_get('/status/{guild_id}', self.legacy_guild_status)
                
    async def stop_server(self):
        """Stop the web server."""
        if self.site:
            await self.site.stop()
            self.site = None
            
        if self.runner:
            await self.runner.cleanup()
            self.runner = None
            
        self.app = None
        
    # Authentication handlers
    
    async def index(self, request: web.Request):
        """Landing page with login/dashboard redirect."""
        session = await get_session(request)
        user = session.get('user')
        
        if user:
            # Redirect to dashboard if logged in
            return web.HTTPFound('/dashboard')
            
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>SkynetV2 Web Interface</title>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                body { 
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
                    margin: 0; 
                    padding: 20px; 
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                }
                .login-container { 
                    max-width: 400px; 
                    background: white; 
                    padding: 40px; 
                    border-radius: 12px; 
                    box-shadow: 0 8px 32px rgba(0,0,0,0.1);
                    text-align: center;
                }
                h1 { color: #2c3e50; margin-bottom: 30px; }
                .login-btn {
                    display: inline-block;
                    background: #7289da;
                    color: white;
                    padding: 12px 24px;
                    border-radius: 6px;
                    text-decoration: none;
                    font-weight: bold;
                    margin: 10px 0;
                }
                .login-btn:hover { background: #5b6eae; }
                .info { 
                    background: #e7f3ff; 
                    padding: 15px; 
                    border-radius: 5px; 
                    margin: 20px 0; 
                    font-size: 14px;
                }
            </style>
        </head>
        <body>
            <div class="login-container">
                <h1>🤖 SkynetV2</h1>
                <div class="info">
                    <p>Discord OAuth2 Web Interface</p>
                    <p>Manage your AI assistant settings with proper Discord authentication.</p>
                </div>
                <a href="/login" class="login-btn">Login with Discord</a>
            </div>
        </body>
        </html>
        """
        return web.Response(text=html, content_type='text/html')
        
    async def login(self, request: web.Request):
        """Initiate Discord OAuth2 flow."""
        # Generate state parameter for security
        state = secrets.token_urlsafe(32)
        session = await new_session(request)
        session['oauth_state'] = state
        
        # Discord OAuth2 parameters
        params = {
            'client_id': self.client_id,
            'redirect_uri': f"{self.public_url}/callback",
            'response_type': 'code',
            'scope': 'identify guilds',
            'state': state
        }
        
        discord_url = f"https://discord.com/api/oauth2/authorize?{urlencode(params)}"
        return web.HTTPFound(discord_url)
        
    async def oauth_callback(self, request: web.Request):
        """Handle OAuth2 callback from Discord."""
        code = request.query.get('code')
        state = request.query.get('state')
        
        if not code:
            return web.Response(text='Authorization failed: Missing code', status=400)
            
        session = await get_session(request)
        expected_state = session.get('oauth_state')
        
        if not state or state != expected_state:
            return web.Response(text='Authorization failed: Invalid state', status=400)
            
        # Exchange code for access token
        try:
            async with ClientSession() as client:
                # Get access token
                token_data = {
                    'client_id': self.client_id,
                    'client_secret': self.client_secret,
                    'grant_type': 'authorization_code',
                    'code': code,
                    'redirect_uri': f"{self.public_url}/callback",
                }
                
                async with client.post('https://discord.com/api/oauth2/token', data=token_data) as resp:
                    if resp.status != 200:
                        return web.Response(text='Failed to get access token', status=400)
                    token_info = await resp.json()
                    
                access_token = token_info['access_token']
                
                # Get user information
                headers = {'Authorization': f'Bearer {access_token}'}
                async with client.get('https://discord.com/api/users/@me', headers=headers) as resp:
                    if resp.status != 200:
                        return web.Response(text='Failed to get user info', status=400)
                    user_info = await resp.json()
                    
                # Get user guilds
                async with client.get('https://discord.com/api/users/@me/guilds', headers=headers) as resp:
                    if resp.status != 200:
                        return web.Response(text='Failed to get guild info', status=400)
                    user_guilds = await resp.json()
                    
        except Exception as e:
            return web.Response(text=f'OAuth2 error: {e}', status=500)
            
        # Determine user permissions
        permissions = await self.get_user_permissions(user_info, user_guilds)
        
        # Store user session
        session['user'] = {
            'id': user_info['id'],
            'username': user_info['username'],
            'discriminator': user_info.get('discriminator', '0000'),
            'avatar': user_info.get('avatar'),
            'permissions': permissions,
            'guilds': [g for g in user_guilds if str(g['id']) in permissions.get('guilds', [])]
        }
        
        return web.HTTPFound('/dashboard')
        
    async def logout(self, request: web.Request):
        """Logout and clear session."""
        session = await get_session(request)
        session.clear()
        return web.HTTPFound('/')
        
    async def get_user_permissions(self, user_info: Dict, user_guilds: List[Dict]) -> Dict[str, Any]:
        """Determine user permissions based on Discord roles (cached owner id)."""
        user_id = int(user_info['id'])
        permissions = {
            'bot_owner': False,
            'guild_admin': [],
            'guild_member': [],
            'guilds': []
        }
        # Cache owner id to avoid repeated API calls
        if self._owner_id is None:
            try:
                app_info = await self.cog.bot.application_info()
                self._owner_id = app_info.owner.id  # type: ignore[attr-defined]
            except Exception:
                self._owner_id = -1
        if user_id == self._owner_id:
            permissions['bot_owner'] = True
            bot_guilds = [str(g.id) for g in self.cog.bot.guilds]
            permissions['guilds'] = bot_guilds
            permissions['guild_admin'] = bot_guilds
            return permissions
            
        # Check guild permissions
        bot_guild_ids = {g.id for g in self.cog.bot.guilds}
        
        for guild_info in user_guilds:
            guild_id = guild_info['id']
            
            # Only include guilds where the bot is present
            if int(guild_id) not in bot_guild_ids:
                continue
                
            permissions['guilds'].append(str(guild_id))
            permissions['guild_member'].append(str(guild_id))
            
            # Check for admin permissions (Manage Server)
            user_perms = guild_info.get('permissions', 0)
            if user_perms & 0x00000020:  # MANAGE_GUILD permission
                permissions['guild_admin'].append(str(guild_id))
                
        return permissions
        
    # Dashboard handlers
    
    async def dashboard(self, request: web.Request):
        """Main dashboard page."""
        session = await get_session(request)
        user = session.get('user')
        
        if not user:
            return web.HTTPFound('/login')
            
        permissions = user['permissions']
        
        # Generate dashboard content based on permissions
        dashboard_html = await self.render_dashboard(user)
        return web.Response(text=dashboard_html, content_type='text/html')
        
    async def render_dashboard(self, user: Dict) -> str:
        """Render the main dashboard HTML."""
        permissions = user['permissions']
        guilds = user['guilds']
        
        guild_cards = []
        for guild in guilds:
            guild_obj = self.cog.bot.get_guild(int(guild['id']))
            if not guild_obj:
                continue
                
            is_admin = str(guild['id']) in permissions['guild_admin']
            admin_badge = "🛡️ Admin" if is_admin else "👤 Member"
            
            guild_cards.append(f"""
                <div class="guild-card">
                    <h3>{guild_obj.name}</h3>
                    <p>{admin_badge} • {guild_obj.member_count} members</p>
                    <div class="guild-actions">
                        <a href="/guild/{guild['id']}" class="btn btn-primary">View Dashboard</a>
                        {f'<a href="/config/{guild["id"]}" class="btn btn-secondary">Configure</a>' if is_admin else ''}
                    </div>
                </div>
            """)
            
        guild_grid = "\n".join(guild_cards) if guild_cards else "<p>No accessible guilds found.</p>"
        
        # Bot owner features
        owner_section = ""
        if permissions['bot_owner']:
            owner_section = """
                <div class="owner-section">
                    <h2>🔧 Bot Owner Controls</h2>
                    <div class="owner-actions">
                        <a href="/global-stats" class="btn btn-warning">Global Statistics</a>
                        <a href="/global-config" class="btn btn-warning">Global Configuration</a>
                    </div>
                </div>
            """
            
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>SkynetV2 Dashboard</title>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                body {{ 
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
                    margin: 0; 
                    padding: 0;
                    background: #f5f7fa;
                }}
                .header {{
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 20px 0;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                }}
                .header-content {{
                    max-width: 1200px;
                    margin: 0 auto;
                    padding: 0 20px;
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                }}
                .user-info {{
                    display: flex;
                    align-items: center;
                    gap: 15px;
                }}
                .avatar {{
                    width: 40px;
                    height: 40px;
                    border-radius: 50%;
                    background: rgba(255,255,255,0.2);
                }}
                .container {{
                    max-width: 1200px;
                    margin: 30px auto;
                    padding: 0 20px;
                }}
                .guild-grid {{
                    display: grid;
                    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
                    gap: 20px;
                    margin: 20px 0;
                }}
                .guild-card {{
                    background: white;
                    padding: 20px;
                    border-radius: 10px;
                    box-shadow: 0 4px 15px rgba(0,0,0,0.1);
                    border-left: 4px solid #3498db;
                }}
                .guild-actions {{
                    margin-top: 15px;
                }}
                .btn {{
                    display: inline-block;
                    padding: 8px 16px;
                    border-radius: 5px;
                    text-decoration: none;
                    font-size: 14px;
                    margin-right: 10px;
                    margin-bottom: 5px;
                }}
                .btn-primary {{ background: #3498db; color: white; }}
                .btn-secondary {{ background: #95a5a6; color: white; }}
                .btn-warning {{ background: #f39c12; color: white; }}
                .owner-section {{
                    background: #fff3cd;
                    border: 1px solid #ffeaa7;
                    border-radius: 8px;
                    padding: 20px;
                    margin: 20px 0;
                }}
                .logout-btn {{
                    background: #e74c3c;
                    color: white;
                    padding: 8px 16px;
                    border-radius: 5px;
                    text-decoration: none;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <div class="header-content">
                    <h1>🤖 SkynetV2 Dashboard</h1>
                    <div class="user-info">
                        <span>Welcome, {user['username']}#{user['discriminator']}</span>
                        <a href="/logout" class="logout-btn">Logout</a>
                    </div>
                </div>
            </div>
            
            <div class="container">
                {owner_section}
                
                <h2>Your Guilds</h2>
                <div class="guild-grid">
                    {guild_grid}
                </div>
            </div>
        </body>
        </html>
        """
        
        return html
        
    async def rotate_session_key(self):
        """Rotate session key (call requires restart to invalidate old cookies)."""
        new_key = fernet.Fernet.generate_key().decode()
        try:
            await self.cog.config.web_session_key.set(new_key)
            self.session_key = new_key.encode()
            print("SkynetV2 Web: Session key rotated. Restart web server to apply fully.")
        except Exception as e:
            print(f"SkynetV2 Web: Failed to rotate session key: {e}")
    
    # Additional placeholder methods for completeness
    async def guild_dashboard(self, request: web.Request):
        """Guild-specific dashboard."""
        return web.Response(text="Guild dashboard - TODO", content_type='text/plain')
        
    async def user_profile(self, request: web.Request):
        """User profile page."""
        return web.Response(text="User profile - TODO", content_type='text/plain')
        
    async def guild_config(self, request: web.Request):
        """Guild configuration page (admin only)."""
        session = await get_session(request)
        user = session.get('user')
        if not user:
            return web.HTTPFound('/login')
        guild_id = request.match_info.get('guild_id')
        perms = user['permissions']
        if guild_id not in perms.get('guild_admin', []):
            return web.Response(text="Forbidden", status=403)
        guild = self.cog.bot.get_guild(int(guild_id))
        if not guild:
            return web.Response(text="Guild not found", status=404)
        html = f"<h1>Config: {guild.name}</h1><p>Configuration editing UI pending.</p>"
        return web.Response(text=html, content_type='text/html')
    
    async def update_guild_config(self, request: web.Request):
        """Update guild configuration (not yet implemented)."""
        return web.Response(text="Not implemented", status=501)
    
    # Helpers
    def _mask_key(self, key: str | None) -> str:
        if not key:
            return "(not set)"
        if len(key) < 8:
            return key[:2] + "…"
        return f"{key[:4]}…{key[-4:]}"
    
    def _guild_accessible(self, guild_id: str, permissions: Dict[str, Any]) -> bool:
        return permissions.get('bot_owner') or guild_id in permissions.get('guilds', [])
    
    # API endpoints
    async def api_guilds(self, request: web.Request):
        """API: List accessible guilds with basic info."""
        session = await get_session(request)
        user = session.get('user')
        if not user:
            return web.json_response({'error': 'unauthorized'}, status=401)
        perms = user['permissions']
        data = []
        for g in self.cog.bot.guilds:
            sgid = str(g.id)
            if not self._guild_accessible(sgid, perms):
                continue
            data.append({
                'id': sgid,
                'name': g.name,
                'member_count': g.member_count,
                'is_admin': sgid in perms.get('guild_admin', [])
            })
        return web.json_response({'guilds': data})
    
    async def api_guild_status(self, request: web.Request):
        """API: Guild status details (basic telemetry + config presence)."""
        session = await get_session(request)
        user = session.get('user')
        if not user:
            return web.json_response({'error': 'unauthorized'}, status=401)
        guild_id = request.match_info.get('guild_id')
        perms = user['permissions']
        if not guild_id or not self._guild_accessible(guild_id, perms):
            return web.json_response({'error': 'forbidden'}, status=403)
        guild = self.cog.bot.get_guild(int(guild_id))
        if not guild:
            return web.json_response({'error': 'not_found'}, status=404)
        # Fetch minimal config data
        providers_global = await self.cog.config.providers()
        g_providers = await self.cog.config.guild(guild).providers()
        model_cfg = await self.cog.config.guild(guild).model()
        enabled_tools = await self.cog.config.guild(guild).tools()
        usage = await self.cog.config.guild(guild).usage()
        tools_usage = len((usage or {}).get('tools', {})) if usage else 0
        provider_keys = {
            'openai': self._mask_key(providers_global.get('openai', {}).get('api_key')),
            'serp': self._mask_key(providers_global.get('serp', {}).get('api_key')),
            'firecrawl': self._mask_key(providers_global.get('firecrawl', {}).get('api_key')),
        }
        guild_provider_overrides = [p for p, v in (g_providers or {}).items() if v.get('api_key')]
        status = {
            'id': guild_id,
            'name': guild.name,
            'member_count': guild.member_count,
            'model': model_cfg or '(inherit)',
            'providers_global': provider_keys,
            'providers_overrides': guild_provider_overrides,
            'tools_enabled_count': sum(1 for v in (enabled_tools or {}).get('enabled', {}).values() if v),
            'tool_usage_kinds': tools_usage,
        }
        return web.json_response(status)
    
    async def api_health(self, request: web.Request):
        """API: Minimal health/status endpoint (no secrets)."""
        uptime = int(time.time() - self._start_time)
        guild_count = len(self.cog.bot.guilds)
        version = getattr(self.cog, '__version__', 'unknown')
        return web.json_response({
            'ok': True,
            'uptime_s': uptime,
            'guild_count': guild_count,
            'version': version,
        })
    
    async def legacy_guild_status(self, request: web.Request):
        """Legacy token-based guild status (backwards compatibility)."""
        return web.Response(text="Legacy endpoint - use OAuth2 interface", status=410)
