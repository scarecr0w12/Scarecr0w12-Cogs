"""Page handlers (dashboard, profile, guild views, config)"""
from __future__ import annotations
from aiohttp import web
from aiohttp_session import get_session
from typing import Any, Dict

async def _require_session(request: web.Request):
    session = await get_session(request); user = session.get('user')
    print(f"SkynetV2 Web: Session check - user present: {user is not None}")
    if not user: 
        print("SkynetV2 Web: Session check failed - redirecting to login")
        return None, web.HTTPFound('/')
    return user, None

async def dashboard(request: web.Request):
    webiface = request.app['webiface']
    user, resp = await _require_session(request)
    print(f"SkynetV2 Web: Dashboard accessed - user: {user.get('username') if user else None}")
    if resp: 
        print("SkynetV2 Web: Dashboard - no session, redirecting to login")
        return resp
    perms = user.get('permissions', {})
    
    # Get overall bot statistics
    total_guilds = len(webiface.cog.bot.guilds)
    accessible_guilds = len(perms.get('guilds', []))
    admin_guilds = len(perms.get('guild_admin', []))
    is_bot_owner = perms.get('bot_owner', False)
    
    # Build guild table with enhanced information
    rows = []
    for gid in perms.get('guilds', []):
        g = webiface.cog.bot.get_guild(int(gid))
        if not g: continue
        
        # Get guild status
        try:
            config = webiface.cog.config.guild(g)
            enabled = await config.enabled()
            listening_cfg = await config.listening()
            listening_enabled = listening_cfg.get('enabled', False)
        except:
            enabled = True
            listening_enabled = False
        
        is_admin = str(gid) in perms.get('guild_admin', [])
        admin_badge = '<span class="status-badge status-enabled">Admin</span>' if is_admin else '<span class="status-badge status-disabled">Member</span>'
        status_badge = '<span class="status-badge status-enabled">Active</span>' if enabled else '<span class="status-badge status-disabled">Disabled</span>'
        listening_badge = '<span class="status-badge status-enabled">Listening</span>' if listening_enabled else ''
        
        action_buttons = f'''
            <a href="/guild/{g.id}" class="button secondary">Dashboard</a>
            {f'<a href="/config/{g.id}" class="button">Configure</a>' if is_admin else ''}
        '''
        
        rows.append(f"""
            <tr>
                <td><strong>{g.name}</strong><br><small>{g.member_count} members</small></td>
                <td>{admin_badge}</td>
                <td>{status_badge} {listening_badge}</td>
                <td>{action_buttons}</td>
            </tr>
        """)
    
    guild_table = f"""
        <table>
            <tr><th>Guild</th><th>Role</th><th>Status</th><th>Actions</th></tr>
            {''.join(rows) if rows else '<tr><td colspan="4">(no accessible guilds)</td></tr>'}
        </table>
    """
    
    # Quick stats card
    stats_card = f"""
    <div class='card'>
        <h2>Overview</h2>
        <div class='form-row'>
            <div>
                <strong>Accessible Guilds:</strong> {accessible_guilds}
                <br><small>Admin on {admin_guilds} guilds</small>
            </div>
            <div>
                <strong>Bot Status:</strong> {'Bot Owner' if is_bot_owner else 'User'}
                <br><small>Total bot guilds: {total_guilds}</small>
            </div>
        </div>
    </div>
    """
    
    # Quick actions for bot owners
    owner_actions = ""
    if is_bot_owner:
        owner_actions = f"""
        <div class='card'>
            <h2>Bot Owner Actions</h2>
            <button onclick="location.href='/global-config'" class="secondary">🌐 Global Configuration</button>
            <button onclick="location.href='/bot-stats'" class="secondary">📊 Bot Statistics</button>
            <button onclick="location.href='/logs'" class="secondary">📋 View Logs</button>
        </div>
        """
    
    body = f"""
    <h1>SkynetV2 Dashboard</h1>
    <div class='card'>
        <p>Welcome back, <strong>{user.get('username')}</strong>!</p>
        <p>Manage your SkynetV2 bot configuration across your Discord servers.</p>
    </div>
    
    {stats_card}
    {owner_actions}
    
    <div class='card'>
        <h2>Your Guilds</h2>
        {guild_table}
    </div>
    """
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
    
    is_admin = str(gid) in user.get('permissions', {}).get('guild_admin', []) or user.get('permissions', {}).get('bot_owner')
    status = await webiface.get_guild_status(guild)
    
    # Get current configuration
    config = webiface.cog.config.guild(guild)
    enabled = await config.enabled()
    listening_config = await config.listening()
    tools_config = await config.tools()
    rate_limits = await config.rate_limits()
    
    # Quick status overview
    status_color = 'enabled' if enabled else 'disabled'
    listening_status = 'enabled' if listening_config.get('enabled') else 'disabled'
    
    # Tools status with toggles (admin only)
    tools_html = ""
    if is_admin:
        tools_html = f"""
        <div class='card'>
            <h2>Tools Configuration</h2>
            <div class='form-group'>
                <div class='form-row'>
                    <label>Enable/Disable Bot:</label>
                    <div class='toggle {"on" if enabled else ""}' onclick='toggleSetting({gid}, "enabled", {str(not enabled).lower()})'></div>
                    <span class='status-badge status-{status_color}'>{status_color.title()}</span>
                </div>
            </div>
            <div class='form-group'>
                <div class='form-row'>
                    <label>Passive Listening:</label>
                    <div class='toggle {"on" if listening_config.get("enabled") else ""}' onclick='toggleSetting({gid}, "listening_enabled", {str(not listening_config.get("enabled", False)).lower()})'></div>
                    <span class='status-badge status-{listening_status}'>{listening_status.title()}</span>
                </div>
            </div>
            <div class='form-group'>
                <label>Available Tools:</label>
        """
        
        # List available tools with toggles
        available_tools = ['web_search', 'firecrawl_scrape', 'firecrawl_deep_research', 'memory_management']
        for tool in available_tools:
            tool_enabled = tools_config.get('enabled', {}).get(tool, True)
            tool_status = 'enabled' if tool_enabled else 'disabled'
            tools_html += f"""
                <div class='form-row'>
                    <label>{tool.replace('_', ' ').title()}:</label>
                    <div class='toggle {"on" if tool_enabled else ""}' onclick='toggleSetting({gid}, "tool_{tool}", {str(not tool_enabled).lower()})'></div>
                    <span class='status-badge status-{tool_status}'>{tool_status.title()}</span>
                </div>
            """
        tools_html += "</div></div>"
    else:
        # Read-only view for non-admins
        tools_status = ''.join(f"<li>{k.replace('_', ' ').title()}: {'enabled' if v else 'disabled'}</li>" for k,v in tools_config.get('enabled', {}).items())
        tools_html = f"""
        <div class='card'>
            <h2>Tools Status</h2>
            <ul>{tools_status if tools_status else '<li>Default tools enabled</li>'}</ul>
        </div>
        """
    
    # Provider status
    providers = ''.join(f"<li>{k}: {v}</li>" for k,v in status['providers'].items())
    
    # Quick actions
    actions_html = ""
    if is_admin:
        actions_html = f"""
        <div class='card'>
            <h2>Quick Actions</h2>
            <button onclick="location.href='/config/{gid}'">⚙️ Full Configuration</button>
            <button onclick="location.href='/test/{gid}'" class="secondary">🧪 Test AI Chat</button>
            <button onclick="location.href='/usage/{gid}'" class="secondary">📊 Usage Statistics</button>
        </div>
        """
    
    body = f"""
    <h1>Guild: {guild.name}</h1>
    <div class='card'>
        <h2>Status Overview</h2>
        <p><strong>Bot Status:</strong> <span class='status-badge status-{status_color}'>{status_color.title()}</span></p>
        <p><strong>Member Count:</strong> {guild.member_count}</p>
        <p><strong>Your Role:</strong> {'Administrator' if is_admin else 'Member'}</p>
    </div>
    
    <div class='card'>
        <h2>AI Providers</h2>
        <ul>{providers}</ul>
    </div>
    
    {tools_html}
    {actions_html}
    """
    return web.Response(text=_html_base(f'Guild {guild.name}', body), content_type='text/html')

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
    
    if not admin:
        return web.Response(text='Admin access required', status=403)
    
    # Get current configuration
    config = webiface.cog.config.guild(guild)
    rate_limits = await config.rate_limits()
    providers_cfg = await config.providers()
    global_providers = await webiface.cog.config.providers()
    model_cfg = await config.model()
    params_cfg = await config.params()
    listening_cfg = await config.listening()
    autosearch_caps = await config.autosearch_caps()
    
    # Provider configuration form
    providers_form = """
    <div class='card'>
        <h2>AI Provider API Keys</h2>
        <form id='providers-form' action='/api/guild/{}/config/providers' method='POST'>
    """.format(gid)
    
    for prov in ['openai', 'serp', 'firecrawl']:
        gk = providers_cfg.get(prov, {}).get('api_key')
        globk = global_providers.get(prov, {}).get('api_key')
        current_val = gk[:12] + '***' if gk else (globk[:12] + '*** (global)' if globk else '')
        
        providers_form += f"""
            <div class='form-group'>
                <label for='{prov}_key'>{prov.title()} API Key:</label>
                <input type='password' id='{prov}_key' name='{prov}_key' placeholder='{"Current: " + current_val if current_val else "Enter API key"}' />
                <small>Leave blank to keep current key{" (using global)" if globk and not gk else ""}</small>
            </div>
        """
    
    providers_form += """
            <button type='button' onclick='submitForm("providers-form")'>Save API Keys</button>
        </form>
    </div>
    """
    
    # Model configuration form
    global_model = await webiface.cog.config.model()
    current_model = model_cfg or global_model
    
    model_form = f"""
    <div class='card'>
        <h2>AI Model Configuration</h2>
        <form id='model-form' action='/api/guild/{gid}/config/model' method='POST'>
            <div class='form-group'>
                <label for='provider'>Provider:</label>
                <select id='provider' name='provider'>
                    <option value='openai' {'selected' if current_model.get('provider') == 'openai' else ''}>OpenAI</option>
                </select>
            </div>
            <div class='form-group'>
                <label for='model_name'>Model:</label>
                <select id='model_name' name='model_name'>
                    <option value='gpt-4o-mini' {'selected' if current_model.get('name') == 'gpt-4o-mini' else ''}>GPT-4o Mini</option>
                    <option value='gpt-4o' {'selected' if current_model.get('name') == 'gpt-4o' else ''}>GPT-4o</option>
                    <option value='gpt-4-turbo' {'selected' if current_model.get('name') == 'gpt-4-turbo' else ''}>GPT-4 Turbo</option>
                </select>
            </div>
            <button type='button' onclick='submitForm("model-form")'>Save Model Settings</button>
        </form>
    </div>
    """
    
    # Parameters configuration
    global_params = await webiface.cog.config.params()
    current_params = params_cfg or global_params
    
    params_form = f"""
    <div class='card'>
        <h2>AI Parameters</h2>
        <form id='params-form' action='/api/guild/{gid}/config/params' method='POST'>
            <div class='form-row'>
                <div class='form-group'>
                    <label for='temperature'>Temperature:</label>
                    <input type='number' id='temperature' name='temperature' min='0' max='2' step='0.1' value='{current_params.get("temperature", 0.7)}' />
                </div>
                <div class='form-group'>
                    <label for='max_tokens'>Max Tokens:</label>
                    <input type='number' id='max_tokens' name='max_tokens' min='50' max='4000' value='{current_params.get("max_tokens", 512)}' />
                </div>
            </div>
            <div class='form-group'>
                <label for='top_p'>Top P:</label>
                <input type='number' id='top_p' name='top_p' min='0' max='1' step='0.1' value='{current_params.get("top_p", 1.0)}' />
            </div>
            <button type='button' onclick='submitForm("params-form")'>Save Parameters</button>
        </form>
    </div>
    """
    
    # Rate limits configuration
    rate_limits_form = f"""
    <div class='card'>
        <h2>Rate Limits</h2>
        <form id='rate-limits-form' action='/api/guild/{gid}/config/rate_limits' method='POST'>
            <div class='form-row'>
                <div class='form-group'>
                    <label for='cooldown_sec'>Cooldown (seconds):</label>
                    <input type='number' id='cooldown_sec' name='cooldown_sec' min='1' max='300' value='{rate_limits.get("cooldown_sec", 10)}' />
                </div>
                <div class='form-group'>
                    <label for='per_user_per_min'>Per User/Min:</label>
                    <input type='number' id='per_user_per_min' name='per_user_per_min' min='1' max='100' value='{rate_limits.get("per_user_per_min", 6)}' />
                </div>
            </div>
            <div class='form-row'>
                <div class='form-group'>
                    <label for='per_channel_per_min'>Per Channel/Min:</label>
                    <input type='number' id='per_channel_per_min' name='per_channel_per_min' min='1' max='200' value='{rate_limits.get("per_channel_per_min", 20)}' />
                </div>
                <div class='form-group'>
                    <label for='tools_per_user_per_min'>Tools Per User/Min:</label>
                    <input type='number' id='tools_per_user_per_min' name='tools_per_user_per_min' min='1' max='20' value='{rate_limits.get("tools_per_user_per_min", 4)}' />
                </div>
            </div>
            <button type='button' onclick='submitForm("rate-limits-form")'>Save Rate Limits</button>
        </form>
    </div>
    """
    
    # Passive listening configuration
    listening_form = f"""
    <div class='card'>
        <h2>Passive Listening</h2>
        <form id='listening-form' action='/api/guild/{gid}/config/listening' method='POST'>
            <div class='form-group'>
                <label for='listening_mode'>Mode:</label>
                <select id='listening_mode' name='mode'>
                    <option value='mention' {'selected' if listening_cfg.get("mode") == 'mention' else ''}>Mention Only</option>
                    <option value='keyword' {'selected' if listening_cfg.get("mode") == 'keyword' else ''}>Keywords</option>
                    <option value='all' {'selected' if listening_cfg.get("mode") == 'all' else ''}>All Messages</option>
                </select>
            </div>
            <div class='form-group'>
                <label for='keywords'>Keywords (comma separated):</label>
                <input type='text' id='keywords' name='keywords' value='{", ".join(listening_cfg.get("keywords", []))}' />
            </div>
            <button type='button' onclick='submitForm("listening-form")'>Save Listening Settings</button>
        </form>
    </div>
    """
    
    body = f"""
    <h1>Configuration - {guild.name}</h1>
    <div style='margin-bottom: 20px;'>
        <button onclick='location.href="/guild/{gid}"' class='secondary'>← Back to Guild Dashboard</button>
    </div>
    
    {providers_form}
    {model_form}
    {params_form}
    {rate_limits_form}
    {listening_form}
    """
    
    return web.Response(text=_html_base('Guild Configuration', body), content_type='text/html')

# API handlers for form submissions
async def handle_toggle(request: web.Request):
    """Handle toggle switches (enable/disable features)"""
    webiface = request.app['webiface']
    user, resp = await _require_session(request)
    if resp: return web.json_response({'success': False, 'error': 'Not logged in'})
    
    try:
        gid = int(request.match_info['guild_id'])
        guild = webiface.cog.bot.get_guild(gid)
        if not guild:
            return web.json_response({'success': False, 'error': 'Guild not found'})
        
        # Check permissions
        is_admin = str(gid) in user.get('permissions', {}).get('guild_admin', []) or user.get('permissions', {}).get('bot_owner')
        if not is_admin:
            return web.json_response({'success': False, 'error': 'Admin access required'})
        
        data = await request.json()
        setting = data.get('setting')
        value = data.get('value')
        
        config = webiface.cog.config.guild(guild)
        
        if setting == 'enabled':
            await config.enabled.set(value)
        elif setting == 'listening_enabled':
            async with config.listening() as listening:
                listening['enabled'] = value
        elif setting.startswith('tool_'):
            tool_name = setting[5:]  # Remove 'tool_' prefix
            async with config.tools() as tools:
                if 'enabled' not in tools:
                    tools['enabled'] = {}
                tools['enabled'][tool_name] = value
        else:
            return web.json_response({'success': False, 'error': f'Unknown setting: {setting}'})
        
        return web.json_response({'success': True})
    except Exception as e:
        return web.json_response({'success': False, 'error': str(e)})

async def handle_providers_config(request: web.Request):
    """Handle provider API key configuration"""
    webiface = request.app['webiface']
    user, resp = await _require_session(request)
    if resp: return web.json_response({'success': False, 'error': 'Not logged in'})
    
    try:
        gid = int(request.match_info['guild_id'])
        guild = webiface.cog.bot.get_guild(gid)
        if not guild:
            return web.json_response({'success': False, 'error': 'Guild not found'})
        
        # Check permissions
        is_admin = str(gid) in user.get('permissions', {}).get('guild_admin', []) or user.get('permissions', {}).get('bot_owner')
        if not is_admin:
            return web.json_response({'success': False, 'error': 'Admin access required'})
        
        data = await request.json()
        config = webiface.cog.config.guild(guild)
        
        async with config.providers() as providers:
            for provider in ['openai', 'serp', 'firecrawl']:
                key = data.get(f'{provider}_key', '').strip()
                if key:  # Only update if key is provided
                    if provider not in providers:
                        providers[provider] = {}
                    providers[provider]['api_key'] = key
        
        return web.json_response({'success': True})
    except Exception as e:
        return web.json_response({'success': False, 'error': str(e)})

async def handle_model_config(request: web.Request):
    """Handle AI model configuration"""
    webiface = request.app['webiface']
    user, resp = await _require_session(request)
    if resp: return web.json_response({'success': False, 'error': 'Not logged in'})
    
    try:
        gid = int(request.match_info['guild_id'])
        guild = webiface.cog.bot.get_guild(gid)
        if not guild:
            return web.json_response({'success': False, 'error': 'Guild not found'})
        
        # Check permissions
        is_admin = str(gid) in user.get('permissions', {}).get('guild_admin', []) or user.get('permissions', {}).get('bot_owner')
        if not is_admin:
            return web.json_response({'success': False, 'error': 'Admin access required'})
        
        data = await request.json()
        config = webiface.cog.config.guild(guild)
        
        model_config = {
            'provider': data.get('provider', 'openai'),
            'name': data.get('model_name', 'gpt-4o-mini')
        }
        
        await config.model.set(model_config)
        return web.json_response({'success': True})
    except Exception as e:
        return web.json_response({'success': False, 'error': str(e)})

async def handle_params_config(request: web.Request):
    """Handle AI parameters configuration"""
    webiface = request.app['webiface']
    user, resp = await _require_session(request)
    if resp: return web.json_response({'success': False, 'error': 'Not logged in'})
    
    try:
        gid = int(request.match_info['guild_id'])
        guild = webiface.cog.bot.get_guild(gid)
        if not guild:
            return web.json_response({'success': False, 'error': 'Guild not found'})
        
        # Check permissions
        is_admin = str(gid) in user.get('permissions', {}).get('guild_admin', []) or user.get('permissions', {}).get('bot_owner')
        if not is_admin:
            return web.json_response({'success': False, 'error': 'Admin access required'})
        
        data = await request.json()
        config = webiface.cog.config.guild(guild)
        
        params_config = {
            'temperature': float(data.get('temperature', 0.7)),
            'max_tokens': int(data.get('max_tokens', 512)),
            'top_p': float(data.get('top_p', 1.0))
        }
        
        await config.params.set(params_config)
        return web.json_response({'success': True})
    except Exception as e:
        return web.json_response({'success': False, 'error': str(e)})

async def handle_rate_limits_config(request: web.Request):
    """Handle rate limits configuration"""
    webiface = request.app['webiface']
    user, resp = await _require_session(request)
    if resp: return web.json_response({'success': False, 'error': 'Not logged in'})
    
    try:
        gid = int(request.match_info['guild_id'])
        guild = webiface.cog.bot.get_guild(gid)
        if not guild:
            return web.json_response({'success': False, 'error': 'Guild not found'})
        
        # Check permissions
        is_admin = str(gid) in user.get('permissions', {}).get('guild_admin', []) or user.get('permissions', {}).get('bot_owner')
        if not is_admin:
            return web.json_response({'success': False, 'error': 'Admin access required'})
        
        data = await request.json()
        config = webiface.cog.config.guild(guild)
        
        async with config.rate_limits() as rate_limits:
            rate_limits['cooldown_sec'] = int(data.get('cooldown_sec', 10))
            rate_limits['per_user_per_min'] = int(data.get('per_user_per_min', 6))
            rate_limits['per_channel_per_min'] = int(data.get('per_channel_per_min', 20))
            rate_limits['tools_per_user_per_min'] = int(data.get('tools_per_user_per_min', 4))
        
        return web.json_response({'success': True})
    except Exception as e:
        return web.json_response({'success': False, 'error': str(e)})

async def handle_listening_config(request: web.Request):
    """Handle passive listening configuration"""
    webiface = request.app['webiface']
    user, resp = await _require_session(request)
    if resp: return web.json_response({'success': False, 'error': 'Not logged in'})
    
    try:
        gid = int(request.match_info['guild_id'])
        guild = webiface.cog.bot.get_guild(gid)
        if not guild:
            return web.json_response({'success': False, 'error': 'Guild not found'})
        
        # Check permissions
        is_admin = str(gid) in user.get('permissions', {}).get('guild_admin', []) or user.get('permissions', {}).get('bot_owner')
        if not is_admin:
            return web.json_response({'success': False, 'error': 'Admin access required'})
        
        data = await request.json()
        config = webiface.cog.config.guild(guild)
        
        keywords = [k.strip() for k in data.get('keywords', '').split(',') if k.strip()]
        
        async with config.listening() as listening:
            listening['mode'] = data.get('mode', 'mention')
            listening['keywords'] = keywords
        
        return web.json_response({'success': True})
    except Exception as e:
        return web.json_response({'success': False, 'error': str(e)})

BASE_STYLE = "body{font-family:Segoe UI,Arial,sans-serif;margin:20px;background:#f5f7fb;color:#222}a{color:#3366cc;text-decoration:none}nav a{margin-right:12px}.card{background:#fff;padding:16px;border-radius:8px;box-shadow:0 2px 6px rgba(0,0,0,0.06);margin:12px 0}table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:6px 8px;border-bottom:1px solid #eee;font-size:14px}th{background:#fafafa}code{background:#eef;padding:2px 4px;border-radius:4px;font-size:90%}input,select,textarea{padding:8px;border:1px solid #ddd;border-radius:4px;font-family:inherit;font-size:14px;width:100%;box-sizing:border-box}button{background:#5865F2;color:white;border:none;padding:10px 16px;border-radius:4px;cursor:pointer;font-size:14px;margin:4px 2px}button:hover{background:#4752C4}button.secondary{background:#6c757d}button.secondary:hover{background:#545b62}button.danger{background:#dc3545}button.danger:hover{background:#c82333}button.success{background:#28a745}button.success:hover{background:#218838}.form-group{margin:12px 0}.form-row{display:flex;gap:12px;align-items:center}.form-row > *{flex:1}.toggle{display:inline-block;width:50px;height:24px;background:#ccc;border-radius:12px;position:relative;cursor:pointer}.toggle.on{background:#28a745}.toggle::after{content:'';width:20px;height:20px;border-radius:50%;background:white;position:absolute;top:2px;left:2px;transition:0.2s}.toggle.on::after{left:28px}.status-badge{padding:2px 8px;border-radius:12px;font-size:12px;font-weight:500}.status-enabled{background:#d4edda;color:#155724}.status-disabled{background:#f8d7da;color:#721c24}"

def _html_base(title: str, body: str) -> str:
    return f"""<!DOCTYPE html><html><head><meta charset='utf-8'><title>{title}</title>
<style>{BASE_STYLE}</style>
<script>
function toggleSetting(guildId, setting, value) {{
    fetch(`/api/guild/${{guildId}}/toggle`, {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{setting: setting, value: value}})
    }})
    .then(r => r.json())
    .then(data => {{
        if (data.success) location.reload();
        else alert('Error: ' + data.error);
    }})
    .catch(e => alert('Error: ' + e));
}}
function submitForm(formId) {{
    const form = document.getElementById(formId);
    const formData = new FormData(form);
    const data = Object.fromEntries(formData.entries());
    
    fetch(form.action, {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify(data)
    }})
    .then(r => r.json())
    .then(result => {{
        if (result.success) {{
            alert('Settings saved successfully!');
            location.reload();
        }} else {{
            alert('Error: ' + result.error);
        }}
    }})
    .catch(e => alert('Error: ' + e));
}}
</script>
</head><body><nav><a href='/dashboard'>Dashboard</a><a href='/profile'>Profile</a><a href='/logout'>Logout</a></nav>{body}</body></html>"""

def setup(webiface):
    app = webiface.app
    app['webiface'] = webiface
    app.router.add_get('/dashboard', dashboard)
    app.router.add_get('/profile', profile)
    app.router.add_get('/guild/{guild_id}', guild_dashboard)
    app.router.add_get('/config/{guild_id}', guild_config)
    
    # Add API endpoints for form submissions
    app.router.add_post('/api/guild/{guild_id}/toggle', handle_toggle)
    app.router.add_post('/api/guild/{guild_id}/config/providers', handle_providers_config)
    app.router.add_post('/api/guild/{guild_id}/config/model', handle_model_config)
    app.router.add_post('/api/guild/{guild_id}/config/params', handle_params_config)
    app.router.add_post('/api/guild/{guild_id}/config/rate_limits', handle_rate_limits_config)
    app.router.add_post('/api/guild/{guild_id}/config/listening', handle_listening_config)
