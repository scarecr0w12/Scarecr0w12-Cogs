"""Page handlers (dashboard, profile, guild views, config)"""
from __future__ import annotations
from aiohttp import web
from aiohttp_session import get_session
from typing import Any, Dict
import json

def _user_access_guild(user, gid: int) -> bool:
    """Check if user has access to guild"""
    if not user:
        return False
    permissions = user.get('permissions', {})
    return str(gid) in permissions.get('guilds', []) or permissions.get('bot_owner', False)

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
    
    # Breadcrumb
    breadcrumb = """
    <div class="breadcrumb">
        <span>🏠 Dashboard</span>
    </div>
    """
    
    # Welcome message
    welcome_card = f"""
    <div class="card">
        <div class="card-header">
            <h2>Welcome back, {user.get('username')}!</h2>
        </div>
        <div class="card-body">
            <p>Manage your SkynetV2 AI assistant configuration across your Discord servers.</p>
            {f'<div class="alert alert-info">✨ You have <strong>Bot Owner</strong> privileges with full access to all features.</div>' if is_bot_owner else ''}
        </div>
    </div>
    """
    
    # Quick stats
    stats_grid = f"""
    <div class="grid grid-cols-3">
        <div class="card">
            <div class="card-body">
                <h3>🏠 Accessible Guilds</h3>
                <div style="font-size: 2rem; font-weight: 600; color: #3b82f6;">{accessible_guilds}</div>
                <p style="color: #6b7280; margin: 0;">Out of {total_guilds} total bot guilds</p>
            </div>
        </div>
        <div class="card">
            <div class="card-body">
                <h3>🛡️ Admin Access</h3>
                <div style="font-size: 2rem; font-weight: 600; color: #16a34a;">{admin_guilds}</div>
                <p style="color: #6b7280; margin: 0;">Guilds with admin permissions</p>
            </div>
        </div>
        <div class="card">
            <div class="card-body">
                <h3>👑 Access Level</h3>
                <div class="status-badge status-{'enabled' if is_bot_owner else 'warning'}" style="font-size: 1.1rem;">
                    {'Bot Owner' if is_bot_owner else 'Guild User'}
                </div>
                <p style="color: #6b7280; margin: 0.5rem 0 0 0;">Current permission level</p>
            </div>
        </div>
    </div>
    """
    
    # Build guild cards with better organization
    guild_cards = ""
    if accessible_guilds > 0:
        guild_cards = "<h2 style='margin: 2rem 0 1rem 0;'>🌐 Your Guilds</h2>"
        
        # Group guilds by admin status
        admin_guilds_list = []
        member_guilds_list = []
        
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
            
            # Create guild card
            status_badges = f"""
                <span class="status-badge status-{'enabled' if enabled else 'disabled'}">
                    {'🟢 Active' if enabled else '🔴 Disabled'}
                </span>
                {f'<span class="status-badge status-enabled">🎧 Listening</span>' if listening_enabled else ''}
            """
            
            action_buttons = f"""
                <div style="margin-top: 1rem; display: flex; gap: 0.5rem;">
                    <button onclick="location.href='/guild/{g.id}'" class="btn-outline btn-sm">
                        📊 Dashboard
                    </button>
                    {f'''<button onclick="location.href='/guild/{g.id}/config'" class="btn-sm">⚙️ Configure</button>''' if is_admin else ''}
                    {f'''<button onclick="location.href='/guild/{g.id}/channels'" class="btn-secondary btn-sm">📝 Channels</button>''' if is_admin else ''}
                </div>
            """
            
            guild_card = f"""
            <div class="card">
                <div class="card-body">
                    <div class="form-row" style="margin-bottom: 1rem;">
                        <div>
                            <h3 style="margin: 0;">{g.name}</h3>
                            <p style="margin: 0; color: #6b7280; font-size: 0.875rem;">
                                👥 {g.member_count} members • ID: {g.id}
                            </p>
                        </div>
                        <div>
                            <span class="status-badge status-{'enabled' if is_admin else 'warning'}">
                                {'🛡️ Admin' if is_admin else '👤 Member'}
                            </span>
                        </div>
                    </div>
                    <div style="margin: 0.5rem 0;">
                        {status_badges}
                    </div>
                    {action_buttons}
                </div>
            </div>
            """
            
            if is_admin:
                admin_guilds_list.append(guild_card)
            else:
                member_guilds_list.append(guild_card)
        
        # Render admin guilds first
        if admin_guilds_list:
            guild_cards += f"""
            <div class="card">
                <div class="card-header">
                    <h3>🛡️ Administrator Access ({len(admin_guilds_list)})</h3>
                </div>
            </div>
            <div class="grid grid-cols-2">
                {''.join(admin_guilds_list)}
            </div>
            """
        
        # Then member guilds
        if member_guilds_list:
            guild_cards += f"""
            <div class="card" style="margin-top: 1rem;">
                <div class="card-header">
                    <h3>👤 Member Access ({len(member_guilds_list)})</h3>
                </div>
            </div>
            <div class="grid grid-cols-2">
                {''.join(member_guilds_list)}
            </div>
            """
    else:
        guild_cards = f"""
        <div class="card">
            <div class="card-body">
                <h3>No Accessible Guilds</h3>
                <p>You don't have access to any guilds where this bot is installed.</p>
                <div class="alert alert-info">
                    <strong>💡 Tip:</strong> Make sure you have appropriate permissions in Discord servers where SkynetV2 is installed.
                </div>
            </div>
        </div>
        """
    
    # Bot owner actions
    owner_actions = ""
    if is_bot_owner:
        owner_actions = f"""
        <div class="card">
            <div class="card-header">
                <h2>👑 Bot Owner Actions</h2>
            </div>
            <div class="card-body">
                <div class="grid grid-cols-3">
                    <button onclick="location.href='/global-config'" class="btn-secondary">
                        🌐 Global Configuration
                    </button>
                    <button onclick="location.href='/bot-stats'" class="btn-secondary">
                        📊 Bot Statistics
                    </button>
                    <button onclick="location.href='/logs'" class="btn-secondary">
                        📋 View Logs
                    </button>
                </div>
            </div>
        </div>
        """
    
    body = f"""
    {breadcrumb}
    {welcome_card}
    {stats_grid}
    {owner_actions}
    {guild_cards}
    """
    
    return web.Response(text=_html_base('Dashboard', body, 'dashboard'), content_type='text/html')

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
    
    print(f"SkynetV2 Web: Guild dashboard accessed by {user.get('username') if user else 'unknown'}")
    
    try:
        gid = int(request.match_info['guild_id'])
        print(f"SkynetV2 Web: Guild dashboard - parsed guild ID: {gid}")
    except ValueError:
        print(f"SkynetV2 Web: Guild dashboard - invalid guild ID format")
        return web.Response(text='Invalid guild id', status=400)
    if str(gid) not in user.get('permissions', {}).get('guilds', []):
        print(f"SkynetV2 Web: Guild dashboard - access denied for guild {gid}")
        return web.Response(text='Forbidden', status=403)
    guild = webiface.cog.bot.get_guild(gid)
    if not guild:
        print(f"SkynetV2 Web: Guild dashboard - guild not found: {gid}")
        return web.Response(text='Guild not found', status=404)
    
    is_admin = str(gid) in user.get('permissions', {}).get('guild_admin', []) or user.get('permissions', {}).get('bot_owner')
    print(f"SkynetV2 Web: Guild dashboard - successfully loaded guild: {guild.name} ({gid}), admin: {is_admin}")
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
            <button onclick="location.href='/guild/{gid}/channels'">📺 Channel Settings</button>
            <button onclick="location.href='/guild/{gid}/prompts'">💬 Prompt Management</button>
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
    
    print(f"SkynetV2 Web: Guild config accessed by {user.get('username') if user else 'unknown'}")
    
    try:
        gid = int(request.match_info['guild_id'])
        print(f"SkynetV2 Web: Guild config - parsed guild ID: {gid}")
    except ValueError:
        print(f"SkynetV2 Web: Guild config - invalid guild ID format")
        return web.Response(text='Invalid guild id', status=400)
    if str(gid) not in user.get('permissions', {}).get('guilds', []):
        print(f"SkynetV2 Web: Guild config - access denied for guild {gid}")
        return web.Response(text='Forbidden', status=403)
    guild = webiface.cog.bot.get_guild(gid)
    if not guild:
        print(f"SkynetV2 Web: Guild config - guild not found: {gid}")
        return web.Response(text='Guild not found', status=404)
    admin = str(gid) in user.get('permissions', {}).get('guild_admin', []) or user.get('permissions', {}).get('bot_owner')
    
    if not admin:
        print(f"SkynetV2 Web: Guild config - admin access required for guild {gid}")
        return web.Response(text='Admin access required', status=403)
    
    print(f"SkynetV2 Web: Guild config - successfully loaded guild: {guild.name} ({gid})")
    
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
        <h2>AI Provider Configuration</h2>
        <form id='providers-form' action='/api/guild/{}/config/providers' method='POST'>
    """.format(gid)
    
    # Cloud providers
    cloud_providers = [
        ("openai", "OpenAI", "api_key"),
        ("anthropic", "Anthropic Claude", "api_key"),
        ("groq", "Groq", "api_key"),
        ("gemini", "Google Gemini", "api_key")
    ]
    
    # Local/Self-hosted providers  
    local_providers = [
        ("ollama", "Ollama", ["base_url"]),
        ("lmstudio", "LM Studio", ["base_url"]),
        ("localai", "LocalAI", ["base_url", "api_key"]),
        ("vllm", "vLLM", ["base_url", "api_key"]),
        ("text_generation_webui", "Text Generation WebUI", ["base_url"]),
        ("openai_compatible", "OpenAI Compatible", ["base_url", "api_key"])
    ]
    
    providers_form += "<h3>Cloud Providers</h3>"
    for prov, display_name, field in cloud_providers:
        gk = providers_cfg.get(prov, {}).get("api_key")
        globk = global_providers.get(prov, {}).get("api_key")
        current_val = gk[:12] + '***' if gk else (globk[:12] + '*** (global)' if globk else '')
        
        providers_form += f"""
            <div class='form-group'>
                <label for='{prov}_api_key'>{display_name} API Key:</label>
                <input type='password' id='{prov}_api_key' name='{prov}_api_key' placeholder='{"Current: " + current_val if current_val else "Enter API key"}' />
                <small>Leave blank to keep current key{" (using global)" if globk and not gk else ""}</small>
            </div>
        """
    
    providers_form += "<h3>Self-Hosted / Local Providers</h3>"
    for prov, display_name, fields in local_providers:
        providers_form += f"<h4>{display_name}</h4>"
        
        for field in fields:
            current_val = providers_cfg.get(prov, {}).get(field) or global_providers.get(prov, {}).get(field, "")
            field_type = "password" if field == "api_key" else "url" if field == "base_url" else "text"
            placeholder = "Enter API key" if field == "api_key" else "http://localhost:port/v1" if field == "base_url" else f"Enter {field}"
            
            providers_form += f"""
                <div class='form-group'>
                    <label for='{prov}_{field}'>{field.replace('_', ' ').title()}:</label>
                    <input type='{field_type}' id='{prov}_{field}' name='{prov}_{field}' 
                           value='{"" if field == "api_key" else current_val}' 
                           placeholder='{placeholder}' />
                    {f"<small>Current: {current_val[:20]}...</small>" if field == "api_key" and current_val else ""}
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
                    <option value='anthropic' {'selected' if current_model.get('provider') == 'anthropic' else ''}>Anthropic Claude</option>
                    <option value='groq' {'selected' if current_model.get('provider') == 'groq' else ''}>Groq</option>
                    <option value='gemini' {'selected' if current_model.get('provider') == 'gemini' else ''}>Google Gemini</option>
                    <option value='ollama' {'selected' if current_model.get('provider') == 'ollama' else ''}>Ollama</option>
                    <option value='lmstudio' {'selected' if current_model.get('provider') == 'lmstudio' else ''}>LM Studio</option>
                    <option value='localai' {'selected' if current_model.get('provider') == 'localai' else ''}>LocalAI</option>
                    <option value='vllm' {'selected' if current_model.get('provider') == 'vllm' else ''}>vLLM</option>
                    <option value='text_generation_webui' {'selected' if current_model.get('provider') == 'text_generation_webui' else ''}>Text Generation WebUI</option>
                    <option value='openai_compatible' {'selected' if current_model.get('provider') == 'openai_compatible' else ''}>OpenAI Compatible</option>
                </select>
            </div>
            <div class='form-group'>
                <label for='model_name'>Model Name:</label>
                <input type='text' id='model_name' name='model_name' value='{current_model.get("name", "gpt-4o-mini")}' 
                       placeholder='Enter model name (e.g., gpt-4o-mini, claude-3-sonnet, llama2)' />
                <small>For local providers, use the exact model name as it appears in your server</small>
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

async def guild_channels(request: web.Request):
    """Channel-specific configuration page"""
    webiface = request.app['webiface']
    user, resp = await _require_session(request)
    if resp: return resp
    
    try:
        gid = int(request.match_info['guild_id'])
    except ValueError:
        return web.Response(text='Invalid guild id', status=400)
    if not _user_access_guild(user, gid):
        return web.Response(text='Forbidden', status=403)
    guild = webiface.cog.bot.get_guild(gid)
    if not guild:
        return web.Response(text='Guild not found', status=404)
    
    # Check admin permissions
    is_admin = str(gid) in user.get('permissions', {}).get('guild_admin', []) or user.get('permissions', {}).get('bot_owner')
    if not is_admin:
        return web.Response(text='Admin access required', status=403)
    
    # Get current configuration
    config = webiface.cog.config.guild(guild)
    channel_listening = await config.channel_listening()
    global_listening = await config.listening()
    
    # Build channel configuration forms
    channel_forms = []
    
    for channel in guild.text_channels:
        channel_id = str(channel.id)
        channel_config = channel_listening.get(channel_id, {})
        
        # Default to global settings if no channel-specific config
        enabled = channel_config.get('enabled', global_listening.get('enabled', False))
        mode = channel_config.get('mode', global_listening.get('mode', 'mention'))
        keywords = ', '.join(channel_config.get('keywords', global_listening.get('keywords', [])))
        
        channel_form = f"""
        <div class='card'>
            <h3>#{channel.name}</h3>
            <form id='channel-{channel.id}-form' action='/api/guild/{gid}/channel/{channel.id}/config' method='POST'>
                <div class='form-group'>
                    <label>
                        <input type='checkbox' name='enabled' {'checked' if enabled else ''}>
                        Enable AI listening in this channel
                    </label>
                    <small>Override global listening setting for this specific channel</small>
                </div>
                
                <div class='form-group'>
                    <label>Trigger Mode:</label>
                    <select name='mode'>
                        <option value='mention' {'selected' if mode == 'mention' else ''}>On Mention</option>
                        <option value='keyword' {'selected' if mode == 'keyword' else ''}>Keywords</option>
                        <option value='all' {'selected' if mode == 'all' else ''}>All Messages</option>
                    </select>
                </div>
                
                <div class='form-group'>
                    <label>Keywords (comma-separated):</label>
                    <input type='text' name='keywords' value='{keywords}' placeholder='ai, help, bot'>
                    <small>Only used when trigger mode is "Keywords"</small>
                </div>
                
                <div class='form-group'>
                    <button type='submit'>Update Channel Settings</button>
                    <button type='button' onclick='resetChannel({channel.id})'>Reset to Global</button>
                </div>
            </form>
        </div>
        """
        channel_forms.append(channel_form)
    
    body = f"""
    <h1>Channel Configuration - {guild.name}</h1>
    <p><a href='/guild/{gid}'>← Back to Guild Page</a> | <a href='/guild/{gid}/config'>Guild Settings</a></p>
    
    <div class='card'>
        <h2>Global Listening Settings</h2>
        <p><strong>Enabled:</strong> {'Yes' if global_listening.get('enabled') else 'No'}</p>
        <p><strong>Mode:</strong> {global_listening.get('mode', 'mention').title()}</p>
        <p><strong>Keywords:</strong> {', '.join(global_listening.get('keywords', []))}</p>
        <p><small>These are the default settings. Each channel can override them individually below.</small></p>
    </div>
    
    <h2>Channel-Specific Settings</h2>
    {''.join(channel_forms)}
    
    <script>
    function resetChannel(channelId) {{
        if (confirm('Reset this channel to use global settings?')) {{
            fetch(`/api/guild/{gid}/channel/${{channelId}}/reset`, {{method: 'POST'}})
                .then(r => r.json())
                .then(data => {{
                    if (data.success) {{
                        location.reload();
                    }} else {{
                        alert('Error: ' + data.error);
                    }}
                }});
        }}
    }}
    
    document.querySelectorAll('form[id^="channel-"]').forEach(form => {{
        form.onsubmit = function(e) {{
            e.preventDefault();
            const formData = new FormData(form);
            const data = {{}};
            for (let [key, value] of formData.entries()) {{
                if (key === 'enabled') {{
                    data[key] = true;
                }} else if (key === 'keywords') {{
                    data[key] = value.split(',').map(k => k.trim()).filter(k => k);
                }} else {{
                    data[key] = value;
                }}
            }}
            if (!formData.has('enabled')) {{
                data.enabled = false;
            }}
            
            fetch(form.action, {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify(data)
            }})
            .then(r => r.json())
            .then(data => {{
                if (data.success) {{
                    alert('Channel settings updated!');
                }} else {{
                    alert('Error: ' + data.error);
                }}
            }});
        }};
    }});
    </script>
    """
    
    return web.Response(text=_html_base('Channel Configuration', body), content_type='text/html')

async def guild_prompts(request: web.Request):
    """Prompts management page with generator"""
    webiface = request.app['webiface']
    user, resp = await _require_session(request)
    if resp: return resp
    
    try:
        gid = int(request.match_info['guild_id'])
    except ValueError:
        return web.Response(text='Invalid guild id', status=400)
    if not _user_access_guild(user, gid):
        return web.Response(text='Forbidden', status=403)
    guild = webiface.cog.bot.get_guild(gid)
    if not guild:
        return web.Response(text='Guild not found', status=404)
    
    # Check admin permissions
    is_admin = str(gid) in user.get('permissions', {}).get('guild_admin', []) or user.get('permissions', {}).get('bot_owner')
    if not is_admin:
        return web.Response(text='Admin access required', status=403)
    
    # Get current configuration
    config = webiface.cog.config.guild(guild)
    system_prompts = await config.system_prompts()
    global_prompts = await webiface.cog.config.system_prompts()
    
    guild_prompt = system_prompts.get('guild', '')
    member_prompts = system_prompts.get('members', {})
    
    # Build member search and management interface
    body = f"""
    <div class="container">
        <div class="breadcrumb">
            <a href="/guild/{gid}">Guild Dashboard</a>
            <span class="breadcrumb-separator">></span>
            <span>Prompt Management</span>
        </div>
        
        <h1>AI Prompt Management - {guild.name}</h1>
        
        <!-- Prompt Generator -->
        <div class="card">
            <div class="card-header">
                <h2>🤖 AI Prompt Generator</h2>
            </div>
            <div class="card-body">
                <div class="alert alert-info">
                    <strong>Smart Prompt Creation:</strong> Describe what you want your AI to do and let our generator create optimized prompts.
                </div>
                
                <div class="form-group">
                    <label for="prompt-purpose">What should the AI do?</label>
                    <select id="prompt-purpose" onchange="updatePromptTemplate()">
                        <option value="">Select a purpose...</option>
                        <option value="helpful_assistant">General Helpful Assistant</option>
                        <option value="technical_support">Technical Support</option>
                        <option value="creative_writing">Creative Writing Helper</option>
                        <option value="educational">Educational Tutor</option>
                        <option value="gaming_companion">Gaming Companion</option>
                        <option value="roleplay_character">Roleplay Character</option>
                        <option value="professional_assistant">Professional Assistant</option>
                        <option value="custom">Custom (describe below)</option>
                    </select>
                </div>
                
                <div class="form-group">
                    <label for="prompt-description">Describe your requirements:</label>
                    <textarea id="prompt-description" rows="3" placeholder="Example: I want the AI to be friendly, knowledgeable about programming, and help users debug code issues. It should ask clarifying questions and provide step-by-step solutions."></textarea>
                </div>
                
                <div class="form-row">
                    <div class="form-group">
                        <label for="prompt-tone">Tone:</label>
                        <select id="prompt-tone">
                            <option value="professional">Professional</option>
                            <option value="friendly">Friendly</option>
                            <option value="casual">Casual</option>
                            <option value="formal">Formal</option>
                            <option value="humorous">Humorous</option>
                            <option value="encouraging">Encouraging</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label for="prompt-expertise">Expertise Level:</label>
                        <select id="prompt-expertise">
                            <option value="beginner">Beginner-friendly</option>
                            <option value="intermediate">Intermediate</option>
                            <option value="advanced">Advanced</option>
                            <option value="expert">Expert</option>
                        </select>
                    </div>
                </div>
                
                <div class="form-group">
                    <button onclick="generatePrompt()" class="btn-success">✨ Generate Prompt</button>
                    <div id="prompt-loading" class="loading" style="display:none;"></div>
                </div>
                
                <div id="generated-prompt" style="display:none;">
                    <label for="generated-text">Generated Prompt:</label>
                    <textarea id="generated-text" rows="6" readonly></textarea>
                    <div style="margin-top: 1rem;">
                        <button onclick="useAsGuildPrompt()" class="btn-success">Use as Guild Prompt</button>
                        <button onclick="copyToClipboard()" class="btn-outline">Copy to Clipboard</button>
                        <button onclick="regeneratePrompt()" class="btn-secondary">🔄 Regenerate</button>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- System Prompt Hierarchy -->
        <div class="card">
            <div class="card-header">
                <h2>📋 Current Prompt Hierarchy</h2>
            </div>
            <div class="card-body">
                <div class="alert alert-info">
                    <strong>Prompt Order:</strong> Global System → Guild → Member (each layer adds to the previous)
                </div>
                
                <div class="form-group">
                    <label><strong>Global System Prompt:</strong></label>
                    <div style='background: #f8f9fa; padding: 12px; border-radius: 4px; font-family: monospace; white-space: pre-wrap; font-size: 0.9em; max-height: 150px; overflow-y: auto;'>{global_prompts.get('system', 'You are a helpful AI assistant.')}</div>
                    <small>Global prompts can only be managed by bot owners</small>
                </div>
            </div>
        </div>
        
        <!-- Guild Prompt -->
        <div class="card">
            <div class="card-header">
                <h2>🏰 Guild-Level Prompt</h2>
            </div>
            <div class="card-body">
                <form id='guild-prompt-form' action='/api/guild/{gid}/prompts/guild' method='POST'>
                    <div class='form-group'>
                        <label>Guild-Specific Instructions:</label>
                        <textarea name='prompt' placeholder='Instructions specific to this server...' rows='4'>{guild_prompt}</textarea>
                        <small>This prompt is added to all conversations in this server</small>
                    </div>
                    <div class='form-group'>
                        <button type='submit'>💾 Update Guild Prompt</button>
                        <button type='button' onclick='clearGuildPrompt()' class="btn-danger">🗑️ Clear</button>
                    </div>
                </form>
            </div>
        </div>
        
        <!-- Member Prompt Management -->
        <div class="card">
            <div class="card-header">
                <h2>👥 Member-Specific Prompts</h2>
            </div>
            <div class="card-body">
                <div class="alert alert-info">
                    <strong>Search & Add:</strong> Find members to create personalized AI instructions for individual users.
                </div>
                
                <div class="form-row">
                    <div class="form-group">
                        <label for="member-search-input">Search Members:</label>
                        <input type="text" id="member-search-input" placeholder="Start typing member name..." 
                               oninput="searchMembers()" autocomplete="off">
                        <div id="member-search-results" class="dropdown-content" style="position:relative;"></div>
                    </div>
                </div>
                
                <div id="current-member-prompts">
                    <h3>Current Member Prompts ({len(member_prompts)})</h3>"""

    # Show existing member prompts
    if member_prompts:
        body += """<div class="grid grid-cols-2" style="margin-top: 1rem;">"""
        for member_id, prompt in member_prompts.items():
            member = guild.get_member(int(member_id))
            if member:
                body += f"""
                    <div class="card" style="margin: 0.5rem 0;">
                        <div class="card-header">
                            <h4>{member.display_name} (@{member.name})</h4>
                        </div>
                        <div class="card-body">
                            <div style="background: #f8f9fa; padding: 8px; border-radius: 4px; font-size: 0.9em; margin-bottom: 1rem; max-height: 100px; overflow-y: auto;">
                                {prompt[:200]}{'...' if len(prompt) > 200 else ''}
                            </div>
                            <button onclick="editMemberPrompt('{member_id}', '{member.display_name}')" class="btn-outline btn-sm">✏️ Edit</button>
                            <button onclick="deleteMemberPrompt('{member_id}', '{member.display_name}')" class="btn-danger btn-sm">🗑️ Delete</button>
                        </div>
                    </div>
                """
        body += """</div>"""
    else:
        body += """<p><em>No member-specific prompts configured yet.</em></p>"""

    body += f"""
                </div>
            </div>
        </div>
    </div>
    
    <!-- Member Prompt Modal -->
    <div id="member-prompt-modal" style="display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.5); z-index:1000;">
        <div style="position:absolute; top:50%; left:50%; transform:translate(-50%,-50%); background:white; padding:2rem; border-radius:8px; width:90%; max-width:600px;">
            <h3 id="modal-title">Edit Member Prompt</h3>
            <form id="member-prompt-form">
                <input type="hidden" id="modal-member-id">
                <div class="form-group">
                    <label for="modal-prompt">Prompt for <span id="modal-member-name"></span>:</label>
                    <textarea id="modal-prompt" rows="6" placeholder="Special instructions for this user..."></textarea>
                    <small>This prompt is added to all conversations with this specific user</small>
                </div>
                <div class="form-group">
                    <button type="submit" class="btn-success">💾 Save Prompt</button>
                    <button type="button" onclick="closeModal()" class="btn-secondary">❌ Cancel</button>
                </div>
            </form>
        </div>
    </div>
    
    <script>
    let searchTimeout;
    let memberCache = new Map();
    
    // Prompt templates
    const promptTemplates = {{
        'helpful_assistant': 'You are a helpful, knowledgeable AI assistant. You provide clear, accurate information and are eager to help users with their questions and tasks.',
        'technical_support': 'You are a technical support specialist. You help users troubleshoot problems by asking clarifying questions, providing step-by-step solutions, and explaining technical concepts in simple terms.',
        'creative_writing': 'You are a creative writing assistant. You help users brainstorm ideas, develop characters, improve their writing style, and overcome writer\'s block with inspiring suggestions.',
        'educational': 'You are an educational tutor. You break down complex topics into understandable parts, use examples and analogies, and adapt your teaching style to the learner\'s level.',
        'gaming_companion': 'You are a gaming companion and guide. You help with game strategies, provide tips and tricks, discuss game lore, and enhance the gaming experience.',
        'roleplay_character': 'You are a roleplay character. You stay in character, respond appropriately to the scenario, and help create engaging roleplay experiences.',
        'professional_assistant': 'You are a professional business assistant. You help with work-related tasks, provide formal communication, and maintain a professional demeanor.'
    }};
    
    function updatePromptTemplate() {{
        const purpose = document.getElementById('prompt-purpose').value;
        const description = document.getElementById('prompt-description');
        if (purpose && purpose !== 'custom' && promptTemplates[purpose]) {{
            description.value = promptTemplates[purpose];
        }}
    }}
    
    function generatePrompt() {{
        const purpose = document.getElementById('prompt-purpose').value;
        const description = document.getElementById('prompt-description').value;
        const tone = document.getElementById('prompt-tone').value;
        const expertise = document.getElementById('prompt-expertise').value;
        
        if (!purpose || !description) {{
            alert('Please select a purpose and provide a description.');
            return;
        }}
        
        document.getElementById('prompt-loading').style.display = 'inline-block';
        
        // Generate enhanced prompt
        let generatedPrompt = '';
        
        // Base prompt from template or description
        if (purpose !== 'custom' && promptTemplates[purpose]) {{
            generatedPrompt = promptTemplates[purpose];
        }} else {{
            generatedPrompt = description;
        }}
        
        // Add tone adjustments
        const toneAdjustments = {{
            'professional': ' Maintain a professional tone and use formal language.',
            'friendly': ' Be warm, approachable, and conversational in your responses.',
            'casual': ' Keep things relaxed and use casual, everyday language.',
            'formal': ' Use formal language and maintain proper etiquette at all times.',
            'humorous': ' Add light humor when appropriate and keep interactions enjoyable.',
            'encouraging': ' Be supportive, motivating, and positive in all interactions.'
        }};
        
        generatedPrompt += toneAdjustments[tone] || '';
        
        // Add expertise level adjustments
        const expertiseAdjustments = {{
            'beginner': ' Explain concepts simply, avoid jargon, and provide additional context for technical terms.',
            'intermediate': ' Assume some background knowledge but still explain complex concepts clearly.',
            'advanced': ' You can use technical language and assume strong foundational knowledge.',
            'expert': ' Engage at a highly technical level with detailed, expert-level discussion.'
        }};
        
        generatedPrompt += expertiseAdjustments[expertise] || '';
        
        // Add custom description if provided and different from template
        if (purpose === 'custom' || (description && description !== promptTemplates[purpose])) {{
            generatedPrompt += '\\n\\nAdditional requirements: ' + description;
        }}
        
        // Add server-specific context
        generatedPrompt += '\\n\\nYou are operating in the "{guild.name}" Discord server. Be mindful of the server\'s community and culture.';
        
        setTimeout(() => {{
            document.getElementById('generated-text').value = generatedPrompt;
            document.getElementById('generated-prompt').style.display = 'block';
            document.getElementById('prompt-loading').style.display = 'none';
        }}, 1000); // Simulate generation time
    }}
    
    function regeneratePrompt() {{
        generatePrompt();
    }}
    
    function useAsGuildPrompt() {{
        const generatedText = document.getElementById('generated-text').value;
        document.querySelector('#guild-prompt-form textarea[name="prompt"]').value = generatedText;
        alert('✅ Generated prompt moved to Guild Prompt field. Click "Update Guild Prompt" to save.');
        document.getElementById('guild-prompt-form').scrollIntoView({{ behavior: 'smooth' }});
    }}
    
    function copyToClipboard() {{
        const generatedText = document.getElementById('generated-text');
        generatedText.select();
        document.execCommand('copy');
        alert('✅ Prompt copied to clipboard!');
    }}
    
    function searchMembers() {{
        const query = document.getElementById('member-search-input').value.trim();
        const resultsDiv = document.getElementById('member-search-results');
        
        if (query.length < 2) {{
            resultsDiv.innerHTML = '';
            resultsDiv.style.display = 'none';
            return;
        }}
        
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(async () => {{
            try {{
                const response = await fetch(`/api/guild/{gid}/members/search?q=${{encodeURIComponent(query)}}`);
                const data = await response.json();
                
                if (data.success) {{
                    displaySearchResults(data.members);
                }} else {{
                    resultsDiv.innerHTML = '<div class="dropdown-item">Error searching members</div>';
                    resultsDiv.style.display = 'block';
                }}
            }} catch (e) {{
                resultsDiv.innerHTML = '<div class="dropdown-item">Search failed</div>';
                resultsDiv.style.display = 'block';
            }}
        }}, 300);
    }}
    
    function displaySearchResults(members) {{
        const resultsDiv = document.getElementById('member-search-results');
        
        if (members.length === 0) {{
            resultsDiv.innerHTML = '<div class="dropdown-item">No members found</div>';
        }} else {{
            resultsDiv.innerHTML = members.map(member => 
                `<div class="dropdown-item" onclick="selectMember('${{member.id}}', '${{member.display_name}}', '${{member.name}}')">
                    ${{member.display_name}} (@${{member.name}})
                </div>`
            ).join('');
        }}
        resultsDiv.style.display = 'block';
    }}
    
    function selectMember(memberId, displayName, username) {{
        document.getElementById('member-search-results').style.display = 'none';
        document.getElementById('member-search-input').value = '';
        editMemberPrompt(memberId, displayName);
    }}
    
    function editMemberPrompt(memberId, displayName) {{
        document.getElementById('modal-member-id').value = memberId;
        document.getElementById('modal-member-name').textContent = displayName;
        document.getElementById('modal-title').textContent = `Edit Prompt for ${{displayName}}`;
        
        // Load existing prompt if any
        const existingPrompts = {json.dumps(member_prompts)};
        document.getElementById('modal-prompt').value = existingPrompts[memberId] || '';
        
        document.getElementById('member-prompt-modal').style.display = 'block';
    }}
    
    function deleteMemberPrompt(memberId, displayName) {{
        if (confirm(`Delete prompt for ${{displayName}}?`)) {{
            fetch(`/api/guild/{gid}/prompts/member/${{memberId}}`, {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify({{prompt: ''}})
            }})
            .then(r => r.json())
            .then(data => {{
                if (data.success) location.reload();
                else alert('Error: ' + data.error);
            }});
        }}
    }}
    
    function closeModal() {{
        document.getElementById('member-prompt-modal').style.display = 'none';
    }}
    
    function clearGuildPrompt() {{
        if (confirm('Clear guild prompt?')) {{
            fetch('/api/guild/{gid}/prompts/guild', {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify({{prompt: ''}})
            }})
            .then(r => r.json())
            .then(data => {{
                if (data.success) location.reload();
                else alert('Error: ' + data.error);
            }});
        }}
    }}
    
    // Handle guild prompt form
    document.getElementById('guild-prompt-form').onsubmit = function(e) {{
        e.preventDefault();
        const formData = new FormData(this);
        const data = Object.fromEntries(formData);
        
        fetch(this.action, {{
            method: 'POST',
            headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify(data)
        }})
        .then(r => r.json())
        .then(data => {{
            if (data.success) {{
                alert('✅ Guild prompt updated!');
            }} else {{
                alert('Error: ' + data.error);
            }}
        }});
    }};
    
    // Handle member prompt form
    document.getElementById('member-prompt-form').onsubmit = function(e) {{
        e.preventDefault();
        const memberId = document.getElementById('modal-member-id').value;
        const prompt = document.getElementById('modal-prompt').value;
        
        fetch(`/api/guild/{gid}/prompts/member/${{memberId}}`, {{
            method: 'POST',
            headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify({{prompt: prompt}})
        }})
        .then(r => r.json())
        .then(data => {{
            if (data.success) {{
                alert('✅ Member prompt updated!');
                closeModal();
                location.reload();
            }} else {{
                alert('Error: ' + data.error);
            }}
        }});
    }};
    
    // Close modal when clicking outside
    document.getElementById('member-prompt-modal').onclick = function(e) {{
        if (e.target === this) closeModal();
    }};
    
    // Hide search results when clicking elsewhere
    document.addEventListener('click', function(e) {{
        if (!e.target.closest('#member-search-input') && !e.target.closest('#member-search-results')) {{
            document.getElementById('member-search-results').style.display = 'none';
        }}
    }});
    </script>
    """
    
    return web.Response(text=_html_base('Prompt Management', body), content_type='text/html')

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
            # Cloud providers (API key only)
            for provider in ['openai', 'anthropic', 'groq', 'gemini']:
                key = data.get(f'{provider}_api_key', '').strip()
                if key:
                    if provider not in providers:
                        providers[provider] = {}
                    providers[provider]['api_key'] = key
            
            # Local/Self-hosted providers
            local_providers = [
                ('ollama', ['base_url']),
                ('lmstudio', ['base_url']),
                ('localai', ['base_url', 'api_key']),
                ('vllm', ['base_url', 'api_key']),
                ('text_generation_webui', ['base_url']),
                ('openai_compatible', ['base_url', 'api_key'])
            ]
            
            for provider_name, fields in local_providers:
                provider_data = {}
                has_data = False
                
                for field in fields:
                    value = data.get(f'{provider_name}_{field}', '').strip()
                    if value:
                        provider_data[field] = value
                        has_data = True
                
                if has_data:
                    if provider_name not in providers:
                        providers[provider_name] = {}
                    providers[provider_name].update(provider_data)
        
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

async def handle_channel_config(request: web.Request):
    """Handle per-channel listening configuration"""
    webiface = request.app['webiface']
    user, resp = await _require_session(request)
    if resp: return web.json_response({'success': False, 'error': 'Not logged in'})
    
    try:
        gid = int(request.match_info['guild_id'])
        channel_id = request.match_info['channel_id']
        guild = webiface.cog.bot.get_guild(gid)
        if not guild:
            return web.json_response({'success': False, 'error': 'Guild not found'})
        
        # Check permissions
        is_admin = str(gid) in user.get('permissions', {}).get('guild_admin', []) or user.get('permissions', {}).get('bot_owner')
        if not is_admin:
            return web.json_response({'success': False, 'error': 'Admin access required'})
        
        data = await request.json()
        config = webiface.cog.config.guild(guild)
        
        keywords = data.get('keywords', [])
        if isinstance(keywords, str):
            keywords = [k.strip() for k in keywords.split(',') if k.strip()]
        
        async with config.channel_listening() as channel_listening:
            if channel_id not in channel_listening:
                channel_listening[channel_id] = {}
            
            channel_listening[channel_id].update({
                'enabled': data.get('enabled', False),
                'mode': data.get('mode', 'mention'),
                'keywords': keywords
            })
        
        return web.json_response({'success': True})
    except Exception as e:
        return web.json_response({'success': False, 'error': str(e)})

async def handle_channel_reset(request: web.Request):
    """Reset channel to use global settings"""
    webiface = request.app['webiface']
    user, resp = await _require_session(request)
    if resp: return web.json_response({'success': False, 'error': 'Not logged in'})
    
    try:
        gid = int(request.match_info['guild_id'])
        channel_id = request.match_info['channel_id']
        guild = webiface.cog.bot.get_guild(gid)
        if not guild:
            return web.json_response({'success': False, 'error': 'Guild not found'})
        
        # Check permissions
        is_admin = str(gid) in user.get('permissions', {}).get('guild_admin', []) or user.get('permissions', {}).get('bot_owner')
        if not is_admin:
            return web.json_response({'success': False, 'error': 'Admin access required'})
        
        config = webiface.cog.config.guild(guild)
        
        async with config.channel_listening() as channel_listening:
            if channel_id in channel_listening:
                del channel_listening[channel_id]
        
        return web.json_response({'success': True})
    except Exception as e:
        return web.json_response({'success': False, 'error': str(e)})

async def handle_guild_prompt(request: web.Request):
    """Handle guild prompt configuration"""
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
        
        async with config.system_prompts() as prompts:
            prompts['guild'] = data.get('prompt', '')
        
        return web.json_response({'success': True})
    except Exception as e:
        return web.json_response({'success': False, 'error': str(e)})

async def handle_member_prompt(request: web.Request):
    """Handle member prompt configuration"""
    webiface = request.app['webiface']
    user, resp = await _require_session(request)
    if resp: return web.json_response({'success': False, 'error': 'Not logged in'})
    
    try:
        gid = int(request.match_info['guild_id'])
        member_id = request.match_info['member_id']
        guild = webiface.cog.bot.get_guild(gid)
        if not guild:
            return web.json_response({'success': False, 'error': 'Guild not found'})
        
        # Check permissions
        is_admin = str(gid) in user.get('permissions', {}).get('guild_admin', []) or user.get('permissions', {}).get('bot_owner')
        if not is_admin:
            return web.json_response({'success': False, 'error': 'Admin access required'})
        
        data = await request.json()
        config = webiface.cog.config.guild(guild)
        
        async with config.system_prompts() as prompts:
            members = prompts.setdefault('members', {})
            prompt_text = data.get('prompt', '').strip()
            if prompt_text:
                members[member_id] = prompt_text
            elif member_id in members:
                del members[member_id]
        
        return web.json_response({'success': True})
    except Exception as e:
        return web.json_response({'success': False, 'error': str(e)})

async def handle_member_search(request: web.Request):
    """Handle member search API"""
    webiface = request.app['webiface']
    user, resp = await _require_session(request)
    if resp: return web.json_response({'success': False, 'error': 'Not logged in'})
    
    try:
        gid = int(request.match_info['guild_id'])
        query = request.query.get('q', '').strip().lower()
        
        if not query or len(query) < 2:
            return web.json_response({'success': True, 'members': []})
            
        guild = webiface.cog.bot.get_guild(gid)
        if not guild:
            return web.json_response({'success': False, 'error': 'Guild not found'})
        
        # Check permissions
        is_admin = str(gid) in user.get('permissions', {}).get('guild_admin', []) or user.get('permissions', {}).get('bot_owner')
        if not is_admin:
            return web.json_response({'success': False, 'error': 'Admin access required'})
        
        # Search members (limit to first 20 matches)
        matching_members = []
        for member in guild.members:
            if member.bot:
                continue
            if (query in member.display_name.lower() or 
                query in member.name.lower() or 
                query in str(member.id)):
                matching_members.append({
                    'id': str(member.id),
                    'name': member.name,
                    'display_name': member.display_name,
                    'discriminator': member.discriminator
                })
                if len(matching_members) >= 20:
                    break
        
        return web.json_response({'success': True, 'members': matching_members})
    except Exception as e:
        return web.json_response({'success': False, 'error': str(e)})

BASE_STYLE = """
body{font-family:'Segoe UI',system-ui,-apple-system,sans-serif;margin:0;background:#f8fafc;color:#1e293b;line-height:1.6}
header{background:#1e40af;color:white;padding:1rem 2rem;box-shadow:0 2px 4px rgba(0,0,0,0.1)}
header h1{margin:0;font-size:1.5rem;font-weight:600}
nav{background:#3b82f6;padding:0.75rem 2rem;box-shadow:0 1px 3px rgba(0,0,0,0.1)}
nav a{color:white;text-decoration:none;margin-right:1.5rem;padding:0.5rem 1rem;border-radius:0.375rem;transition:background 0.2s}
nav a:hover{background:rgba(255,255,255,0.1)}
nav a.active{background:rgba(255,255,255,0.2)}
.container{max-width:1200px;margin:0 auto;padding:2rem}
.card{background:white;border-radius:0.75rem;box-shadow:0 4px 6px rgba(0,0,0,0.07);border:1px solid #e2e8f0;overflow:hidden;margin-bottom:1.5rem}
.card-header{background:#f8fafc;border-bottom:1px solid #e2e8f0;padding:1rem 1.5rem}
.card-header h2{margin:0;font-size:1.25rem;font-weight:600;color:#374151}
.card-header h3{margin:0;font-size:1.1rem;font-weight:500;color:#6b7280}
.card-body{padding:1.5rem}
.tabs{display:flex;border-bottom:1px solid #e2e8f0;background:#f8fafc}
.tab{padding:1rem 1.5rem;cursor:pointer;border-bottom:2px solid transparent;transition:all 0.2s;color:#6b7280;font-weight:500}
.tab:hover{color:#374151;background:#f1f5f9}
.tab.active{color:#3b82f6;border-bottom-color:#3b82f6;background:white}
.tab-content{display:none;padding:1.5rem}
.tab-content.active{display:block}
table{width:100%;border-collapse:collapse;margin-top:1rem}
th,td{text-align:left;padding:0.75rem;border-bottom:1px solid #e2e8f0}
th{background:#f8fafc;font-weight:600;color:#374151}
tr:hover{background:#f8fafc}
.form-group{margin-bottom:1.5rem}
.form-row{display:flex;gap:1rem;align-items:center;margin-bottom:1rem}
.form-row > label{min-width:150px;font-weight:500;color:#374151}
input,select,textarea{padding:0.75rem;border:2px solid #e2e8f0;border-radius:0.5rem;font-family:inherit;font-size:0.875rem;transition:border-color 0.2s;background:white}
input:focus,select:focus,textarea:focus{outline:none;border-color:#3b82f6;box-shadow:0 0 0 3px rgba(59,130,246,0.1)}
button{background:#3b82f6;color:white;border:none;padding:0.75rem 1.5rem;border-radius:0.5rem;cursor:pointer;font-size:0.875rem;font-weight:500;transition:all 0.2s;display:inline-flex;align-items:center;gap:0.5rem}
button:hover{background:#2563eb;transform:translateY(-1px)}
button:active{transform:translateY(0)}
.btn-secondary{background:#6b7280;color:white}
.btn-secondary:hover{background:#4b5563}
.btn-danger{background:#dc2626}
.btn-danger:hover{background:#b91c1c}
.btn-success{background:#16a34a}
.btn-success:hover{background:#15803d}
.btn-outline{background:transparent;color:#3b82f6;border:2px solid #3b82f6}
.btn-outline:hover{background:#3b82f6;color:white}
.btn-sm{padding:0.5rem 1rem;font-size:0.8rem}
.toggle{position:relative;display:inline-block;width:3rem;height:1.5rem;background:#e2e8f0;border-radius:0.75rem;cursor:pointer;transition:background 0.2s}
.toggle.on{background:#16a34a}
.toggle::after{content:'';width:1.25rem;height:1.25rem;border-radius:50%;background:white;position:absolute;top:0.125rem;left:0.125rem;transition:transform 0.2s;box-shadow:0 2px 4px rgba(0,0,0,0.2)}
.toggle.on::after{transform:translateX(1.5rem)}
.status-badge{display:inline-flex;align-items:center;padding:0.25rem 0.75rem;border-radius:9999px;font-size:0.75rem;font-weight:600;text-transform:uppercase;letter-spacing:0.05em}
.status-enabled{background:#dcfce7;color:#166534}
.status-disabled{background:#fee2e2;color:#991b1b}
.status-warning{background:#fef3c7;color:#92400e}
.grid{display:grid;gap:1.5rem}
.grid-cols-2{grid-template-columns:repeat(2,1fr)}
.grid-cols-3{grid-template-columns:repeat(3,1fr)}
.dropdown{position:relative;display:inline-block}
.dropdown-trigger{background:#f8fafc;border:2px solid #e2e8f0;border-radius:0.5rem;padding:0.75rem 1rem;cursor:pointer;display:flex;align-items:center;justify-content:space-between;min-width:200px}
.dropdown-trigger:hover{border-color:#3b82f6}
.dropdown-content{position:absolute;top:100%;left:0;right:0;background:white;border:2px solid #e2e8f0;border-radius:0.5rem;box-shadow:0 10px 15px rgba(0,0,0,0.1);z-index:1000;max-height:300px;overflow-y:auto;display:none}
.dropdown.active .dropdown-content{display:block}
.dropdown-item{padding:0.75rem 1rem;cursor:pointer;border-bottom:1px solid #f1f5f9;transition:background 0.1s}
.dropdown-item:hover{background:#f8fafc}
.dropdown-item:last-child{border-bottom:none}
.alert{padding:1rem;border-radius:0.5rem;margin-bottom:1rem;border-left:4px solid}
.alert-info{background:#dbeafe;border-color:#3b82f6;color:#1e40af}
.alert-success{background:#dcfce7;border-color:#16a34a;color:#166534}
.alert-warning{background:#fef3c7;border-color:#f59e0b;color:#92400e}
.alert-danger{background:#fee2e2;border-color:#dc2626;color:#991b1b}
.loading{display:inline-block;width:1rem;height:1rem;border:2px solid #e2e8f0;border-top:2px solid #3b82f6;border-radius:50%;animation:spin 1s linear infinite}
@keyframes spin{0%{transform:rotate(0deg)}100%{transform:rotate(360deg)}}
.breadcrumb{display:flex;align-items:center;margin-bottom:1.5rem;color:#6b7280;font-size:0.875rem}
.breadcrumb a{color:#3b82f6;text-decoration:none}
.breadcrumb a:hover{text-decoration:underline}
.breadcrumb-separator{margin:0 0.5rem}
@media(max-width:768px){
  .container{padding:1rem}
  .form-row{flex-direction:column;align-items:stretch}
  .grid-cols-2,.grid-cols-3{grid-template-columns:1fr}
  nav{padding:0.5rem 1rem}
  nav a{margin-right:0.75rem;padding:0.25rem 0.5rem}
}
"""

def _html_base(title: str, body: str, current_page: str = '') -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{title} - SkynetV2</title>
    <style>{BASE_STYLE}</style>
    <script>
    // Enhanced JavaScript for better UX
    function toggleSetting(guildId, setting, value) {{
        const btn = event.target;
        btn.disabled = true;
        btn.innerHTML = '<div class="loading"></div> Saving...';
        
        fetch(`/api/guild/${{guildId}}/toggle`, {{
            method: 'POST',
            headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify({{setting: setting, value: value}})
        }})
        .then(r => r.json())
        .then(data => {{
            if (data.success) {{
                location.reload();
            }} else {{
                showAlert('Error: ' + data.error, 'danger');
                btn.disabled = false;
                btn.innerHTML = btn.getAttribute('data-original-text') || 'Toggle';
            }}
        }})
        .catch(e => {{
            showAlert('Error: ' + e, 'danger');
            btn.disabled = false;
            btn.innerHTML = btn.getAttribute('data-original-text') || 'Toggle';
        }});
    }}
    
    function submitForm(formId) {{
        const form = document.getElementById(formId);
        const formData = new FormData(form);
        const data = Object.fromEntries(formData.entries());
        const submitBtn = form.querySelector('button[type="submit"]');
        
        if (submitBtn) {{
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<div class="loading"></div> Saving...';
        }}
        
        fetch(form.action, {{
            method: 'POST',
            headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify(data)
        }})
        .then(r => r.json())
        .then(result => {{
            if (result.success) {{
                showAlert('Settings saved successfully!', 'success');
                setTimeout(() => location.reload(), 1500);
            }} else {{
                showAlert('Error: ' + result.error, 'danger');
                if (submitBtn) {{
                    submitBtn.disabled = false;
                    submitBtn.innerHTML = submitBtn.getAttribute('data-original-text') || 'Save';
                }}
            }}
        }})
        .catch(e => {{
            showAlert('Error: ' + e, 'danger');
            if (submitBtn) {{
                submitBtn.disabled = false;
                submitBtn.innerHTML = submitBtn.getAttribute('data-original-text') || 'Save';
            }}
        }});
    }}
    
    function showAlert(message, type) {{
        const alert = document.createElement('div');
        alert.className = `alert alert-${{type}}`;
        alert.innerHTML = message;
        alert.style.position = 'fixed';
        alert.style.top = '20px';
        alert.style.right = '20px';
        alert.style.zIndex = '9999';
        alert.style.minWidth = '300px';
        document.body.appendChild(alert);
        
        setTimeout(() => alert.remove(), 5000);
    }}
    
    function switchTab(tabName) {{
        // Hide all tab contents
        document.querySelectorAll('.tab-content').forEach(content => {{
            content.classList.remove('active');
        }});
        
        // Remove active class from all tabs
        document.querySelectorAll('.tab').forEach(tab => {{
            tab.classList.remove('active');
        }});
        
        // Show selected tab content
        const targetContent = document.getElementById(tabName + '-content');
        if (targetContent) {{
            targetContent.classList.add('active');
        }}
        
        // Add active class to clicked tab
        const targetTab = document.querySelector(`[onclick="switchTab('${{tabName}}')"]`);
        if (targetTab) {{
            targetTab.classList.add('active');
        }}
        
        // Save active tab in localStorage
        localStorage.setItem('activeTab', tabName);
    }}
    
    function toggleDropdown(dropdownId) {{
        const dropdown = document.getElementById(dropdownId);
        const isActive = dropdown.classList.contains('active');
        
        // Close all dropdowns
        document.querySelectorAll('.dropdown').forEach(d => d.classList.remove('active'));
        
        // Toggle clicked dropdown
        if (!isActive) {{
            dropdown.classList.add('active');
        }}
    }}
    
    // Initialize page when DOM loads
    document.addEventListener('DOMContentLoaded', function() {{
        // Restore active tab from localStorage
        const activeTab = localStorage.getItem('activeTab');
        if (activeTab) {{
            switchTab(activeTab);
        }} else {{
            // Activate first tab by default
            const firstTab = document.querySelector('.tab');
            if (firstTab) {{
                const tabName = firstTab.getAttribute('onclick').match(/switchTab\\('([^']+)'\\)/)[1];
                switchTab(tabName);
            }}
        }}
        
        // Close dropdowns when clicking outside
        document.addEventListener('click', function(e) {{
            if (!e.target.closest('.dropdown')) {{
                document.querySelectorAll('.dropdown').forEach(d => d.classList.remove('active'));
            }}
        }});
        
        // Store original button text for restoration
        document.querySelectorAll('button').forEach(btn => {{
            btn.setAttribute('data-original-text', btn.innerHTML);
        }});
        
        // Add current page class to nav
        const currentPage = '{current_page}';
        if (currentPage) {{
            const navLink = document.querySelector(`nav a[href*="${{currentPage}}"]`);
            if (navLink) navLink.classList.add('active');
        }}
    }});
    </script>
</head>
<body>
    <header>
        <h1>🤖 SkynetV2 Web Interface</h1>
    </header>
    <nav>
        <a href="/dashboard">📊 Dashboard</a>
        <a href="/profile">👤 Profile</a>
        <a href="/logout">🚪 Logout</a>
    </nav>
    <div class="container">
        {body}
    </div>
</body>
</html>"""

def setup(webiface):
    app = webiface.app
    app['webiface'] = webiface
    app.router.add_get('/dashboard', dashboard)
    app.router.add_get('/profile', profile)
    app.router.add_get('/guild/{guild_id}', guild_dashboard)
    app.router.add_get('/guild/{guild_id}/config', guild_config)  # Fixed route to match templates
    app.router.add_get('/guild/{guild_id}/channels', guild_channels)
    app.router.add_get('/guild/{guild_id}/prompts', guild_prompts)
    
    # Add API endpoints for form submissions
    app.router.add_post('/api/guild/{guild_id}/toggle', handle_toggle)
    app.router.add_post('/api/guild/{guild_id}/config/providers', handle_providers_config)
    app.router.add_post('/api/guild/{guild_id}/config/model', handle_model_config)
    app.router.add_post('/api/guild/{guild_id}/config/params', handle_params_config)
    app.router.add_post('/api/guild/{guild_id}/config/rate_limits', handle_rate_limits_config)
    app.router.add_post('/api/guild/{guild_id}/config/listening', handle_listening_config)
    app.router.add_post('/api/guild/{guild_id}/channel/{channel_id}/config', handle_channel_config)
    app.router.add_post('/api/guild/{guild_id}/channel/{channel_id}/reset', handle_channel_reset)
    app.router.add_post('/api/guild/{guild_id}/prompts/guild', handle_guild_prompt)
    app.router.add_post('/api/guild/{guild_id}/prompts/member/{member_id}', handle_member_prompt)
    app.router.add_get('/api/guild/{guild_id}/members/search', handle_member_search)
