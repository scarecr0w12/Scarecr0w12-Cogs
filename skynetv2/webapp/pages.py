"""Page handlers (dashboard, profile, guild views, config)"""
from __future__ import annotations
from aiohttp import web
from aiohttp_session import get_session
from typing import Any, Dict

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
    """Prompts management page"""
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
    
    # Build member prompt forms
    member_forms = []
    for member in guild.members:
        if member.bot:
            continue
        member_id = str(member.id)
        member_prompt = member_prompts.get(member_id, '')
        
        member_form = f"""
        <div class='card'>
            <h4>{member.display_name} (@{member.name})</h4>
            <form id='member-{member.id}-form' action='/api/guild/{gid}/prompts/member/{member.id}' method='POST'>
                <div class='form-group'>
                    <label>Personal Prompt:</label>
                    <textarea name='prompt' placeholder='Special instructions for this user...'>{member_prompt}</textarea>
                    <small>This prompt is added to all conversations with this user</small>
                </div>
                <div class='form-group'>
                    <button type='submit'>Update User Prompt</button>
                    <button type='button' onclick='clearMemberPrompt({member.id})'>Clear</button>
                </div>
            </form>
        </div>
        """
        member_forms.append(member_form)
    
    body = f"""
    <h1>Prompt Management - {guild.name}</h1>
    <p><a href='/guild/{gid}'>← Back to Guild Page</a> | <a href='/guild/{gid}/config'>Guild Settings</a></p>
    
    <div class='card'>
        <h2>System Prompt Hierarchy</h2>
        <p>Prompts are layered in this order: <strong>Global System</strong> → <strong>Guild</strong> → <strong>Member</strong></p>
        <p><strong>Global System Prompt:</strong></p>
        <div style='background: #f8f9fa; padding: 12px; border-radius: 4px; font-family: monospace; white-space: pre-wrap;'>{global_prompts.get('system', 'You are a helpful AI assistant.')}</div>
        <small>Global prompts can only be managed by bot owners</small>
    </div>
    
    <div class='card'>
        <h2>Guild Prompt</h2>
        <form id='guild-prompt-form' action='/api/guild/{gid}/prompts/guild' method='POST'>
            <div class='form-group'>
                <label>Guild-Level Prompt:</label>
                <textarea name='prompt' placeholder='Instructions specific to this server...' rows='4'>{guild_prompt}</textarea>
                <small>This prompt is added to all conversations in this server</small>
            </div>
            <div class='form-group'>
                <button type='submit'>Update Guild Prompt</button>
                <button type='button' onclick='clearGuildPrompt()'>Clear</button>
            </div>
        </form>
    </div>
    
    <h2>Member-Specific Prompts</h2>
    <div class='card'>
        <p>Configure personalized prompts for individual members. These are added to conversations with specific users.</p>
        <input type='text' id='member-search' placeholder='Search members...' onkeyup='filterMembers()'>
    </div>
    
    <div id='member-prompts-container'>
        {''.join(member_forms)}
    </div>
    
    <script>
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
    
    function clearMemberPrompt(memberId) {{
        if (confirm('Clear member prompt?')) {{
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
    
    function filterMembers() {{
        const search = document.getElementById('member-search').value.toLowerCase();
        const cards = document.querySelectorAll('#member-prompts-container .card');
        cards.forEach(card => {{
            const name = card.querySelector('h4').textContent.toLowerCase();
            card.style.display = name.includes(search) ? '' : 'none';
        }});
    }}
    
    // Handle form submissions
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
                alert('Guild prompt updated!');
            }} else {{
                alert('Error: ' + data.error);
            }}
        }});
    }};
    
    document.querySelectorAll('form[id^="member-"]').forEach(form => {{
        form.onsubmit = function(e) {{
            e.preventDefault();
            const formData = new FormData(form);
            const data = Object.fromEntries(formData);
            
            fetch(form.action, {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify(data)
            }})
            .then(r => r.json())
            .then(data => {{
                if (data.success) {{
                    alert('Member prompt updated!');
                }} else {{
                    alert('Error: ' + data.error);
                }}
            }});
        }};
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
