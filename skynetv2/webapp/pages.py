"""Page handlers (dashboard, profile, guild views, config)"""
from __future__ import annotations
from aiohttp import web
from aiohttp_session import get_session
from typing import Any, Dict, cast
import json

# ---- HTML base template and client-side helpers (restored) ----
BASE_STYLE = """
:root{--bg:#0b1020;--panel:#11162a;--panel-2:#0e1426;--text:#e6e8ef;--muted:#94a3b8;--primary:#3b82f6;--success:#16a34a;--warn:#f59e0b;--danger:#ef4444;--border:rgba(255,255,255,.08)}
*{box-sizing:border-box}
body{margin:0;padding:24px;font-family:Inter,system-ui,Arial,sans-serif;background:var(--bg);color:var(--text)}
nav{display:flex;gap:12px;margin:0 0 16px 0}
nav a{color:var(--muted);padding:8px 10px;border-radius:6px;border:1px solid var(--border)}
nav a:hover{color:var(--text);border-color:var(--primary)}
.container{max-width:1100px;margin:0 auto}
.card{background:linear-gradient(180deg,var(--panel),var(--panel-2));border:1px solid var(--border);border-radius:14px;padding:18px;margin:12px 0;box-shadow:0 8px 30px rgba(0,0,0,.25)}
.card-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}
.grid{display:grid;gap:12px}
.grid-cols-2{grid-template-columns:repeat(2,minmax(0,1fr))}
.grid-cols-3{grid-template-columns:repeat(3,minmax(0,1fr))}
.form-group{margin:12px 0}
.form-row{display:flex;justify-content:space-between;align-items:center;gap:12px}
label{font-weight:600;color:var(--muted)}
input[type=text],input[type=password],input[type=number],input[type=url],select{width:100%;padding:10px 12px;border-radius:10px;border:1px solid var(--border);background:#0b1120;color:var(--text)}
small{color:var(--muted)}
button{cursor:pointer;border:1px solid var(--border);background:#0b1120;color:var(--text);padding:10px 14px;border-radius:10px}
button:hover{border-color:var(--primary)}
.btn-primary{background:var(--primary);border-color:var(--primary);color:white}
.btn-secondary{background:#111827;border-color:var(--border)}
.btn-outline{background:transparent}
.btn-sm{font-size:.9rem;padding:6px 10px;border-radius:8px}
.status-badge{display:inline-block;padding:4px 8px;border-radius:8px;font-size:.85rem;border:1px solid var(--border);color:var(--muted)}
.status-enabled{background:rgba(22,163,74,.15);color:#86efac;border-color:rgba(22,163,74,.25)}
.status-disabled{background:rgba(239,68,68,.15);color:#fca5a5;border-color:rgba(239,68,68,.25)}
.status-warning{background:rgba(245,158,11,.15);color:#fcd34d;border-color:rgba(245,158,11,.25)}
.toggle{width:50px;height:28px;border-radius:999px;border:1px solid var(--border);background:#0b1120;position:relative}
.toggle::after{content:'';position:absolute;top:3px;left:3px;width:22px;height:22px;background:#334155;border-radius:999px;transition:all .2s}
.toggle.on{border-color:rgba(22,163,74,.4)}
.toggle.on::after{left:25px;background:#22c55e}
.alert{padding:10px 12px;border-radius:10px;border:1px solid var(--border)}
.alert-info{background:rgba(59,130,246,.12);color:#bfdbfe;border-color:rgba(59,130,246,.25)}
.debug-info{font-size:.9rem}
"""

BASE_SCRIPTS = """
<script>
async function submitForm(formId){
  try{
    const form = document.getElementById(formId);
    const action = form.getAttribute('action');
    const method = (form.getAttribute('method')||'POST').toUpperCase();
    // Build JSON payload from form elements
    const payload = {};
    Array.from(form.elements).forEach(el=>{
      if(!el.name) return;
      if(el.type === 'checkbox') payload[el.name] = !!el.checked;
      else payload[el.name] = el.value;
    });
    const res = await fetch(action,{method,headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    const data = await res.json();
    if(data && data.success){
      console.log('Saved', data);
      const btn = form.querySelector('button[type="button"],button[type="submit"]');
      if(btn){
        const old = btn.textContent; btn.textContent='Saved ✓'; btn.classList.add('btn-primary');
        setTimeout(()=>{btn.textContent=old; btn.classList.remove('btn-primary');},900);
      } else { alert('Saved'); }
    } else {
      alert('Error: '+(data && data.error ? data.error : 'Unknown'));
    }
  }catch(e){ console.error(e); alert('Request failed'); }
}
async function toggleSetting(gid, setting, value){
  try{
    const res = await fetch(`/api/guild/${gid}/toggle`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({setting, value})});
    const data = await res.json();
    if(!(data && data.success)) alert('Toggle failed: '+(data.error||'unknown'));
    else console.log('Toggled', setting, '=>', value);
  }catch(e){ console.error(e); alert('Toggle request failed'); }
}
function updateSensitivityDisplay(input, id){
  const el = document.getElementById(id); if(el) el.textContent = input.value;
}
</script>
"""

def _html_base(title: str, body: str, active_section: str | None = None) -> str:
    """Return full HTML document with shared styles and scripts."""
    nav = (
        "<nav>"
        "<a href='/dashboard'>Dashboard</a>"
        "<a href='/profile'>Profile</a>"
        "<a href='/global-config'>Global Config</a>"
        "</nav>"
    )
    return f"""<!DOCTYPE html>
<html lang='en'>
<head>
<meta charset='utf-8'/>
<meta name='viewport' content='width=device-width, initial-scale=1'/>
<title>{title}</title>
<style>{BASE_STYLE}</style>
</head>
<body>
<div class='container'>
{nav}
{body}
</div>
{BASE_SCRIPTS}
</body>
</html>
"""

# ---- end html base ----

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
    if resp:
        return resp
    user = cast(Dict[str, Any], user)
    print(f"SkynetV2 Web: Dashboard accessed - user: {user.get('username') if user else None}")
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
    user = cast(Dict[str, Any], user)
    perms = user.get('permissions', {})
    body = f"<h1>Profile</h1><div class='card'><p>User: {user.get('username')}#{user.get('discriminator')}</p><p>ID: {user.get('id')}</p><p>Bot Owner: {perms.get('bot_owner')}</p><p>Admin Guilds: {', '.join(perms.get('guild_admin', [])) or '(none)'}" f"</p></div>"
    return web.Response(text=_html_base('Profile', body), content_type='text/html')

async def guild_dashboard(request: web.Request):
    webiface = request.app['webiface']
    user, resp = await _require_session(request)
    if resp: return resp
    user = cast(Dict[str, Any], user)
    
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
    
    # Use guild.id for client-side calls
    guild_id_for_js = guild.id

    # Tools status with toggles (admin only)
    tools_html = ""
    if is_admin:
        tools_html = f"""
        <div class='card'>
            <h2>Tools Configuration</h2>
            <div class='form-group'>
                <div class='form-row'>
                    <label>Enable/Disable Bot:</label>
                    <div class='toggle {"on" if enabled else ""}' onclick='toggleSetting("{guild_id_for_js}", "enabled", {str((not enabled)).lower()})'></div>
                    <span class='status-badge status-{status_color}'>{status_color.title()}</span>
                </div>
            </div>
            <div class='form-group'>
                <div class='form-row'>
                    <label>Passive Listening:</label>
                    <div class='toggle {"on" if listening_config.get("enabled") else ""}' onclick='toggleSetting("{guild_id_for_js}", "listening_enabled", {str((not listening_config.get("enabled", False))).lower()})'></div>
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
                    <div class='toggle {"on" if tool_enabled else ""}' onclick='toggleSetting("{guild_id_for_js}", "tool_{tool}", {str((not tool_enabled)).lower()})'></div>
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
            <button onclick="location.href='/guild/{guild_id_for_js}/config'">⚙️ Full Configuration</button>
            <button onclick="location.href='/guild/{guild_id_for_js}/channels'">📺 Channel Settings</button>
            <button onclick="location.href='/guild/{guild_id_for_js}/prompts'">💬 Prompt Management</button>
            <button onclick=\"location.href='/guild/{guild_id_for_js}/governance'\" class="secondary">🛡️ Governance</button>
            <button onclick="location.href='/test/{guild_id_for_js}'" class="secondary">🧪 Test AI Chat</button>
            <button onclick="location.href='/usage/{guild_id_for_js}'" class="secondary">📊 Usage Statistics</button>
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
    user = cast(Dict[str, Any], user)
    
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
    smart_replies_cfg = await config.smart_replies()
    auto_web_search_cfg = await config.auto_web_search()
    
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
        ("gemini", "Google Gemini", "api_key"),
        # Added search/web providers here for visibility in the same section
        ("serp", "SerpAPI (Web Search)", "api_key"),
        ("firecrawl", "Firecrawl (Scrape/Research)", "api_key"),
    ]
    
    providers_form += "<h3>Cloud & Web Providers</h3>"
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
    
    # Local/Self-hosted providers  
    local_providers = [
        ("ollama", "Ollama", ["base_url"]),
        ("lmstudio", "LM Studio", ["base_url"]),
        ("localai", "LocalAI", ["base_url", "api_key"]),
        ("vllm", "vLLM", ["base_url", "api_key"]),
        ("text_generation_webui", "Text Generation WebUI", ["base_url"]),
        ("openai_compatible", "OpenAI Compatible", ["base_url", "api_key"])
    ]
    
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
            <div class='form-group'>
                <label for='tools_per_guild_per_min'>Tools Per Guild/Min:</label>
                <input type='number' id='tools_per_guild_per_min' name='tools_per_guild_per_min' min='1' max='20' value='{rate_limits.get("tools_per_guild_per_min", 10)}' />
            </div>
            <div class='form-group'>
                <label for='tool_cooldowns'>Per-Tool Cooldowns (optional, one per line: tool=seconds):</label>
                <textarea id='tool_cooldowns' name='tool_cooldowns' rows='4' placeholder='websearch=6\nautosearch=2'></textarea>
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
    
    # Smart replies configuration
    smart_replies_form = f"""
    <div class='card'>
        <h2>Smart Replies</h2>
        <p>Intelligent response control for 'all' mode to avoid interrupting human conversations.</p>
        <form id='smart-replies-form' action='/api/guild/{gid}/config/smart_replies' method='POST'>
            <div class='form-group'>
                <label for='smart_replies_enabled'>Enable Smart Replies:</label>
                <input type='checkbox' id='smart_replies_enabled' name='enabled' {'checked' if smart_replies_cfg.get("enabled", True) else ''} />
            </div>
            <div class='form-group'>
                <label for='smart_replies_sensitivity'>Sensitivity (1=very responsive, 5=very conservative):</label>
                <input type='range' id='smart_replies_sensitivity' name='sensitivity' min='1' max='5' value='{smart_replies_cfg.get("sensitivity", 3)}' oninput='updateSensitivityDisplay(this, "sensitivity-value")' />
                <span id='sensitivity-value'>{smart_replies_cfg.get("sensitivity", 3)}</span>
            </div>
            <div class='form-group'>
                <label for='smart_replies_quiet_time'>Quiet Time (seconds):</label>
                <input type='number' id='smart_replies_quiet_time' name='quiet_time_seconds' value='{smart_replies_cfg.get("quiet_time_seconds", 300)}' />
            </div>
            <button type='button' onclick='submitForm("smart-replies-form")'>Save Smart Replies Settings</button>
        </form>
    </div>
    """
    
    # Auto web search configuration
    auto_web_search_form = f"""
    <div class='card'>
        <h2>Auto Web Search</h2>
        <p>Automatically search for current information when chat messages need up-to-date data.</p>
        <form id='auto-web-search-form' action='/api/guild/{gid}/config/auto_web_search' method='POST'>
            <div class='form-group'>
                <label for='aws_enabled'>Enable Auto Web Search:</label>
                <input type='checkbox' id='aws_enabled' name='enabled' {'checked' if auto_web_search_cfg.get("enabled", False) else ''} />
            </div>
            <div class='form-group'>
                <label for='aws_sensitivity'>Sensitivity (1=very aggressive, 5=very conservative):</label>
                <input type='range' id='aws_sensitivity' name='sensitivity' min='1' max='5' value='{auto_web_search_cfg.get("sensitivity", 3)}' oninput='updateSensitivityDisplay(this, "aws-sensitivity-value")' />
                <span id='aws-sensitivity-value'>{auto_web_search_cfg.get("sensitivity", 3)}</span>
            </div>
            <div class='form-group'>
                <label for='aws_max_results'>Max Search Results:</label>
                <input type='number' id='aws_max_results' name='max_results' min='1' max='10' value='{auto_web_search_cfg.get("max_results", 5)}' />
            </div>
            <div class='form-group'>
                <label for='aws_timeout'>Search Timeout (seconds):</label>
                <input type='number' id='aws_timeout' name='timeout_seconds' min='5' max='60' value='{auto_web_search_cfg.get("timeout_seconds", 15)}' />
            </div>
            <div class='form-group'>
                <label for='aws_cooldown'>User Cooldown (seconds):</label>
                <input type='number' id='aws_cooldown' name='cooldown_seconds' min='10' max='300' value='{auto_web_search_cfg.get("cooldown_seconds", 60)}' />
            </div>
            <div class='form-group'>
                <label for='aws_min_length'>Minimum Message Length:</label>
                <input type='number' id='aws_min_length' name='min_message_length' min='5' max='50' value='{auto_web_search_cfg.get("min_message_length", 10)}' />
            </div>
            <button type='button' onclick='submitForm("auto-web-search-form")'>Save Auto Web Search Settings</button>
        </form>
    </div>
    """
    
    # Governance configuration
    gov_cfg = await config.governance()
    tools_gov = (gov_cfg or {}).get('tools', {}) if gov_cfg else {}
    bypass_gov = (gov_cfg or {}).get('bypass', {}) if gov_cfg else {}
    budget_gov = (gov_cfg or {}).get('budget', {}) if gov_cfg else {}
    allow_tools = ", ".join(tools_gov.get('allow', []) or [])
    deny_tools = ", ".join(tools_gov.get('deny', []) or [])
    allow_roles = ", ".join(str(x) for x in (tools_gov.get('allow_roles', []) or []))
    deny_roles = ", ".join(str(x) for x in (tools_gov.get('deny_roles', []) or []))
    allow_channels = ", ".join(str(x) for x in (tools_gov.get('allow_channels', []) or []))
    deny_channels = ", ".join(str(x) for x in (tools_gov.get('deny_channels', []) or []))
    cooldown_roles = ", ".join(str(x) for x in (bypass_gov.get('cooldown_roles', []) or []))
    per_tool_overrides = tools_gov.get('per_user_minute_overrides', {}) or {}
    per_tool_overrides_text = "\n".join(f"{k}={v}" for k, v in per_tool_overrides.items())
    tokens_cap = int(budget_gov.get('per_user_daily_tokens', 0) or 0)
    cost_cap = float(budget_gov.get('per_user_daily_cost_usd', 0.0) or 0.0)

    governance_form = f"""
    <div class='card'>
        <h2>Governance - {guild.name}</h2>
        <form id='governance-form' action='/api/guild/{gid}/config/governance' method='POST'>
            <div class='grid grid-cols-2'>
                <div class='form-group'>
                    <label for='allow_tools'>Allow Tools (comma)</label>
                    <input type='text' id='allow_tools' name='allow_tools' value='{allow_tools}' placeholder='websearch, ping, autosearch' />
                </div>
                <div class='form-group'>
                    <label for='deny_tools'>Deny Tools (comma)</label>
                    <input type='text' id='deny_tools' name='deny_tools' value='{deny_tools}' placeholder='example_tool' />
                </div>
            </div>
            <div class='grid grid-cols-2'>
                <div class='form-group'>
                    <label for='allow_roles'>Allow Roles (IDs, comma)</label>
                    <input type='text' id='allow_roles' name='allow_roles' value='{allow_roles}' placeholder='123, 456' />
                </div>
                <div class='form-group'>
                    <label for='deny_roles'>Deny Roles (IDs, comma)</label>
                    <input type='text' id='deny_roles' name='deny_roles' value='{deny_roles}' placeholder='789' />
                </div>
            </div>
            <div class='grid grid-cols-2'>
                <div class='form-group'>
                    <label for='allow_channels'>Allow Channels (IDs, comma)</label>
                    <input type='text' id='allow_channels' name='allow_channels' value='{allow_channels}' placeholder='1001, 1002' />
                </div>
                <div class='form-group'>
                    <label for='deny_channels'>Deny Channels (IDs, comma)</label>
                    <input type='text' id='deny_channels' name='deny_channels' value='{deny_channels}' placeholder='1003' />
                </div>
            </div>
            <div class='form-group'>
                <label for='cooldown_roles'>Cooldown Bypass Roles (IDs, comma)</label>
                <input type='text' id='cooldown_roles' name='cooldown_roles' value='{cooldown_roles}' placeholder='role ids' />
            </div>
            <div class='form-group'>
                <label for='per_user_minute_overrides'>Per-Tool Per-User/min Overrides (one per line: tool=number)</label>
                <textarea id='per_user_minute_overrides' name='per_user_minute_overrides' rows='4' placeholder='websearch=6\nautosearch=2'>{per_tool_overrides_text}</textarea>
            </div>
            <div class='grid grid-cols-2'>
                <div class='form-group'>
                    <label for='per_user_daily_tokens'>Daily Token Cap (per user; 0=off)</label>
                    <input type='number' id='per_user_daily_tokens' name='per_user_daily_tokens' value='{tokens_cap}' min='0' />
                </div>
                <div class='form-group'>
                    <label for='per_user_daily_cost_usd'>Daily Cost Cap USD (per user; 0=off)</label>
                    <input type='number' step='0.01' id='per_user_daily_cost_usd' name='per_user_daily_cost_usd' value='{cost_cap}' min='0' />
                </div>
            </div>
            <div class='form-row' style='margin-top:12px;'>
                <button type='button' onclick='submitForm("governance-form")' class='btn-primary'>Save Governance</button>
            </div>
        </form>
    </div>
    """

    body = f"""
    <h1>Guild Configuration - {guild.name}</h1>
    {providers_form}
    {model_form}
    {params_form}
    {rate_limits_form}
    {listening_form}
    {smart_replies_form}
    {auto_web_search_form}
    {governance_form}
    <div class='form-row' style='margin-top:12px;'>
        <button type='button' onclick="location.href='/guild/{gid}'" class='btn-secondary'>← Back to Guild</button>
    </div>
    """
    return web.Response(text=_html_base('Guild Config', body), content_type='text/html')

async def global_config(request: web.Request):
    """Minimal global config page (bot owner only)."""
    webiface = request.app['webiface']
    user, resp = await _require_session(request)
    if resp: return resp
    user = cast(Dict[str, Any], user)
    if not user.get('permissions', {}).get('bot_owner'):
        return web.Response(text='Forbidden', status=403)

    providers = await webiface.cog.config.providers()
    masked = {}
    for prov in ['openai', 'serp', 'firecrawl']:
        key = (providers or {}).get(prov, {}).get('api_key')
        masked[prov] = (key[:8] + '***') if key else '(not set)'

    body = f"""
    <h1>Global Configuration</h1>
    <div class='card'>
        <h2>Providers</h2>
        <ul>
            <li>OpenAI: {masked.get('openai')}</li>
            <li>SerpAPI: {masked.get('serp')}</li>
            <li>Firecrawl: {masked.get('firecrawl')}</li>
        </ul>
        <p>Global provider editing UI will be added here.</p>
        <button onclick="location.href='/dashboard'" class='btn-secondary'>← Back</button>
    </div>
    """
    return web.Response(text=_html_base('Global Config', body), content_type='text/html')

async def guild_governance(request: web.Request):
    """Redirect to the main guild config page for now (keeps link working)."""
    user, resp = await _require_session(request)
    if resp: return resp
    try:
        gid = int(request.match_info['guild_id'])
    except ValueError:
        return web.Response(text='Invalid guild id', status=400)
    return web.HTTPFound(f"/guild/{gid}/config")

async def guild_channels(request: web.Request):
    webiface = request.app['webiface']
    user, resp = await _require_session(request)
    if resp: return resp
    try:
        gid = int(request.match_info['guild_id'])
    except ValueError:
        return web.Response(text='Invalid guild id', status=400)
    perms = user.get('permissions', {}) if isinstance(user, dict) else {}
    if str(gid) not in perms.get('guilds', []):
        return web.Response(text='Forbidden', status=403)
    guild = webiface.cog.bot.get_guild(gid)
    if not guild:
        return web.Response(text='Guild not found', status=404)
    body = f"""
    <h1>Channel Settings - {guild.name}</h1>
    <div class='card'>
        <p>Channel configuration UI is coming soon.</p>
        <button onclick=\"location.href='/guild/{gid}'\" class='btn-secondary'>← Back</button>
    </div>
    """
    return web.Response(text=_html_base('Channels', body), content_type='text/html')

async def guild_prompts(request: web.Request):
    webiface = request.app['webiface']
    user, resp = await _require_session(request)
    if resp: return resp
    try:
        gid = int(request.match_info['guild_id'])
    except ValueError:
        return web.Response(text='Invalid guild id', status=400)
    perms = user.get('permissions', {}) if isinstance(user, dict) else {}
    if str(gid) not in perms.get('guilds', []):
        return web.Response(text='Forbidden', status=403)
    guild = webiface.cog.bot.get_guild(gid)
    if not guild:
        return web.Response(text='Guild not found', status=404)
    body = f"""
    <h1>Prompt Management - {guild.name}</h1>
    <div class='card'>
        <p>Prompt management UI is coming soon.</p>
        <button onclick=\"location.href='/guild/{gid}'\" class='btn-secondary'>← Back</button>
    </div>
    """
    return web.Response(text=_html_base('Prompts', body), content_type='text/html')

async def guild_usage(request: web.Request):
    webiface = request.app['webiface']
    user, resp = await _require_session(request)
    if resp: return resp
    try:
        gid = int(request.match_info['guild_id'])
    except ValueError:
        return web.Response(text='Invalid guild id', status=400)
    perms = user.get('permissions', {}) if isinstance(user, dict) else {}
    if str(gid) not in perms.get('guilds', []):
        return web.Response(text='Forbidden', status=403)
    guild = webiface.cog.bot.get_guild(gid)
    if not guild:
        return web.Response(text='Guild not found', status=404)
    usage = await webiface.cog.config.guild(guild).usage()
    body = f"""
    <h1>Usage - {guild.name}</h1>
    <div class='card'>
        <pre style='white-space:pre-wrap'>{json.dumps(usage, indent=2)}</pre>
        <button onclick=\"location.href='/guild/{gid}'\" class='btn-secondary'>← Back</button>
    </div>
    """
    return web.Response(text=_html_base('Usage', body), content_type='text/html')

async def guild_test(request: web.Request):
    webiface = request.app['webiface']
    user, resp = await _require_session(request)
    if resp: return resp
    try:
        gid = int(request.match_info['guild_id'])
    except ValueError:
        return web.Response(text='Invalid guild id', status=400)
    perms = user.get('permissions', {}) if isinstance(user, dict) else {}
    if str(gid) not in perms.get('guilds', []):
        return web.Response(text='Forbidden', status=403)
    guild = webiface.cog.bot.get_guild(gid)
    if not guild:
        return web.Response(text='Guild not found', status=404)
    body = f"""
    <h1>Test - {guild.name}</h1>
    <div class='card'>
        <p>Interactive chat test UI is coming soon.</p>
        <button onclick=\"location.href='/guild/{gid}'\" class='btn-secondary'>← Back</button>
    </div>
    """
    return web.Response(text=_html_base('Test', body), content_type='text/html')

async def bot_stats(request: web.Request):
    webiface = request.app['webiface']
    user, resp = await _require_session(request)
    if resp: return resp
    perms = user.get('permissions', {}) if isinstance(user, dict) else {}
    if not perms.get('bot_owner', False):
        return web.Response(text='Forbidden', status=403)
    total_guilds = len(webiface.cog.bot.guilds)
    body = f"""
    <h1>Bot Statistics</h1>
    <div class='card'>
        <p>Total guilds: <strong>{total_guilds}</strong></p>
        <button onclick=\"location.href='/dashboard'\" class='btn-secondary'>← Back</button>
    </div>
    """
    return web.Response(text=_html_base('Bot Stats', body), content_type='text/html')

async def logs_page(request: web.Request):
    user, resp = await _require_session(request)
    if resp: return resp
    body = """
    <h1>Logs</h1>
    <div class='card'>
        <p>Logs viewer is coming soon.</p>
        <button onclick=\"location.href='/dashboard'\" class='btn-secondary'>← Back</button>
    </div>
    """
    return web.Response(text=_html_base('Logs', body), content_type='text/html')

def setup(webiface: Any):
    """Register currently implemented page routes."""
    app = webiface.app
    app['webiface'] = webiface
    r = app.router
    r.add_get('/dashboard', dashboard)
    r.add_get('/profile', profile)
    r.add_get('/guild/{guild_id}', guild_dashboard)
    r.add_get('/guild/{guild_id}/config', guild_config)
    r.add_get('/guild/{guild_id}/governance', guild_governance)
    r.add_get('/guild/{guild_id}/channels', guild_channels)
    r.add_get('/guild/{guild_id}/prompts', guild_prompts)
    r.add_get('/usage/{guild_id}', guild_usage)
    r.add_get('/test/{guild_id}', guild_test)
    r.add_get('/bot-stats', bot_stats)
    r.add_get('/logs', logs_page)
    r.add_get('/global-config', global_config)

