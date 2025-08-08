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
        
    async def initialize_config(self):
        """Initialize web interface configuration."""
        # Get or generate session encryption key
        config = self.cog.config
        key = await config.web_session_key()
        if not key:
            key = fernet.Fernet.generate_key().decode()
            await config.web_session_key.set(key)
        self.session_key = key.encode()
        
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
        
        # Setup session middleware
        setup(self.app, EncryptedCookieStorage(self.session_key, max_age=86400))
        
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
        """Determine user permissions based on Discord roles."""
        user_id = int(user_info['id'])
        permissions = {
            'bot_owner': False,
            'guild_admin': [],
            'guild_member': [],
            'guilds': []
        }
        
        # Check if bot owner
        app_info = await self.cog.bot.application_info()
        if user_id == app_info.owner.id:
            permissions['bot_owner'] = True
            # Bot owner has access to all bot guilds
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
                
    async def stop_server(self):
        """Stop the web server."""
        if self.site:
            await self.site.stop()
            self.site = None
            
        if self.runner:
            await self.runner.cleanup()
            self.runner = None
            
        self.app = None
        
    async def handle_cors(self, request: web.Request):
        """Handle CORS preflight requests."""
        if request.method == 'OPTIONS':
            return web.Response(
                headers={
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
                    'Access-Control-Allow-Headers': 'Content-Type',
                }
            )
        return web.Response(status=404)
        
    async def index(self, request: web.Request):
        """Simple index page."""
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>SkynetV2 Web Interface</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }
                .container { max-width: 800px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
                h1 { color: #333; border-bottom: 2px solid #007acc; padding-bottom: 10px; }
                .info { background: #e7f3ff; padding: 15px; border-radius: 5px; margin: 20px 0; }
                pre { background: #f8f8f8; padding: 10px; border-radius: 5px; overflow-x: auto; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>SkynetV2 Web Interface</h1>
                <div class="info">
                    <p>This is the SkynetV2 web interface MVP. To view guild status:</p>
                    <pre>1. Generate a token: [p]ai web token generate
2. Visit: /status/{guild_id}?token={your_token}</pre>
                </div>
                <p>Available endpoints:</p>
                <ul>
                    <li><code>/status/{guild_id}?token={token}</code> - Guild status page</li>
                </ul>
            </div>
        </body>
        </html>
        """
        return web.Response(text=html, content_type='text/html')
        
    async def guild_status(self, request: web.Request):
        """Guild status page with authentication."""
        guild_id = request.match_info['guild_id']
        token = request.query.get('token')
        
        if not token:
            return web.Response(text='Missing token parameter', status=400)
            
        # Validate guild and token
        try:
            guild_id_int = int(guild_id)
            guild = self.cog.bot.get_guild(guild_id_int)
            if not guild:
                return web.Response(text='Guild not found', status=404)
                
            # Check token
            if not await self.validate_token(guild, token):
                return web.Response(text='Invalid or expired token', status=401)
                
        except ValueError:
            return web.Response(text='Invalid guild ID', status=400)
            
        # Generate status page
        try:
            status_data = await self.get_guild_status(guild)
            html = await self.render_status_page(guild, status_data)
            return web.Response(text=html, content_type='text/html')
            
        except Exception as e:
            return web.Response(text=f'Error generating status: {e}', status=500)
            
    async def validate_token(self, guild: discord.Guild, token: str) -> bool:
        """Validate authentication token for guild."""
        tokens = await self.cog.config.guild(guild).web_tokens()
        
        # Check if token exists and hasn't expired
        if token in tokens:
            token_data = tokens[token]
            expires = token_data.get('expires', 0)
            if time.time() < expires:
                return True
            else:
                # Clean up expired token
                async with self.cog.config.guild(guild).web_tokens() as tokens_dict:
                    del tokens_dict[token]
                    
        return False
        
    async def get_guild_status(self, guild: discord.Guild) -> Dict[str, Any]:
        """Collect guild status information."""
        config = self.cog.config.guild(guild)
        
        # Rate limits
        rate_limits = await config.rate_limits()
        
        # Usage stats
        usage = await config.usage()
        
        # Tools
        tools_status = {}
        for tool_name in self.cog._tool_registry.keys():
            tools_status[tool_name] = await self.cog._tool_is_enabled(guild, tool_name)
            
        # Provider status
        providers = await config.providers()
        global_providers = await self.cog.config.providers()
        
        provider_status = {}
        for provider in ['openai', 'serp', 'firecrawl']:
            guild_key = providers.get(provider, {}).get('api_key')
            global_key = global_providers.get(provider, {}).get('api_key')
            
            if guild_key:
                provider_status[provider] = f"guild:{guild_key[:8]}***"
            elif global_key:
                provider_status[provider] = f"global:{global_key[:8]}***"
            else:
                provider_status[provider] = "not configured"
                
        # Memory info
        memory = await config.memory()
        per_channel = memory.get('per_channel', {})
        memory_info = {}
        for ch_id, data in per_channel.items():
            msg_count = len(data.get('messages', []))
            if msg_count > 0:
                memory_info[ch_id] = msg_count
                
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
        
    async def render_status_page(self, guild: discord.Guild, data: Dict[str, Any]) -> str:
        """Render the HTML status page."""
        
        # Format usage stats
        usage = data['usage']
        tokens = usage.get('tokens', {})
        cost = usage.get('cost', {})
        
        # Format memory info
        memory_channels = []
        for ch_id, count in data['memory'].items():
            try:
                channel = guild.get_channel(int(ch_id))
                name = channel.name if channel else f"Unknown ({ch_id})"
                memory_channels.append(f"{name}: {count} messages")
            except:
                memory_channels.append(f"Channel {ch_id}: {count} messages")
                
        memory_text = "<br>".join(memory_channels) if memory_channels else "No stored messages"
        
        # Format tools
        tools_list = []
        for tool, enabled in data['tools'].items():
            status = "✅ Enabled" if enabled else "❌ Disabled"
            tools_list.append(f"{tool}: {status}")
            
        tools_text = "<br>".join(tools_list)
        
        # Format providers
        providers_list = []
        for provider, status in data['providers'].items():
            providers_list.append(f"{provider}: {status}")
            
        providers_text = "<br>".join(providers_list)
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>SkynetV2 - {data['guild_name']} Status</title>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                body {{ 
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
                    margin: 0; 
                    padding: 20px; 
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                }}
                .container {{ 
                    max-width: 1200px; 
                    margin: 0 auto; 
                    background: white; 
                    padding: 30px; 
                    border-radius: 12px; 
                    box-shadow: 0 8px 32px rgba(0,0,0,0.1);
                }}
                h1 {{ 
                    color: #2c3e50; 
                    border-bottom: 3px solid #3498db; 
                    padding-bottom: 10px; 
                    margin-bottom: 30px;
                }}
                .stats-grid {{ 
                    display: grid; 
                    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); 
                    gap: 20px; 
                    margin: 20px 0;
                }}
                .stat-card {{ 
                    background: #f8f9fa; 
                    padding: 20px; 
                    border-radius: 8px; 
                    border-left: 4px solid #3498db;
                }}
                .stat-card h3 {{ 
                    margin-top: 0; 
                    color: #2c3e50;
                }}
                .stat-value {{ 
                    font-size: 1.5em; 
                    font-weight: bold; 
                    color: #e74c3c;
                }}
                .info-section {{ 
                    background: #ecf0f1; 
                    padding: 15px; 
                    border-radius: 5px; 
                    margin: 15px 0;
                }}
                .timestamp {{ 
                    text-align: right; 
                    color: #7f8c8d; 
                    font-size: 0.9em; 
                    margin-top: 20px;
                }}
                pre {{ 
                    background: #2c3e50; 
                    color: #ecf0f1; 
                    padding: 15px; 
                    border-radius: 5px; 
                    overflow-x: auto;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🤖 SkynetV2 Status: {data['guild_name']}</h1>
                
                <div class="stats-grid">
                    <div class="stat-card">
                        <h3>📊 Usage Statistics</h3>
                        <p>Total Tokens: <span class="stat-value">{tokens.get('total', 0):,}</span></p>
                        <p>Prompt Tokens: <span class="stat-value">{tokens.get('prompt', 0):,}</span></p>
                        <p>Completion Tokens: <span class="stat-value">{tokens.get('completion', 0):,}</span></p>
                        <p>Estimated Cost: <span class="stat-value">${cost.get('usd', 0.0):.4f}</span></p>
                    </div>
                    
                    <div class="stat-card">
                        <h3>⚙️ Rate Limits</h3>
                        <p>Cooldown: <span class="stat-value">{data['rate_limits'].get('cooldown_sec', 10)}s</span></p>
                        <p>Per User/Min: <span class="stat-value">{data['rate_limits'].get('per_user_per_min', 6)}</span></p>
                        <p>Per Channel/Min: <span class="stat-value">{data['rate_limits'].get('per_channel_per_min', 20)}</span></p>
                        <p>Tools/User/Min: <span class="stat-value">{data['rate_limits'].get('tools_per_user_per_min', 4)}</span></p>
                    </div>
                </div>
                
                <div class="info-section">
                    <h3>🔧 Tools Status</h3>
                    <p>{tools_text}</p>
                </div>
                
                <div class="info-section">
                    <h3>🔐 Providers</h3>
                    <p>{providers_text}</p>
                </div>
                
                <div class="info-section">
                    <h3>💾 Memory Status</h3>
                    <p>{memory_text}</p>
                </div>
                
                <div class="info-section">
                    <h3>ℹ️ Guild Info</h3>
                    <p>Guild ID: {data['guild_id']}</p>
                    <p>Members: {data['member_count']}</p>
                </div>
                
                <div class="timestamp">
                    Generated at: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(data['generated_at']))}
                </div>
            </div>
        </body>
        </html>
        """
        
        return html
