"""JSON API endpoints split out."""
from __future__ import annotations
from aiohttp import web
from aiohttp_session import get_session
from typing import Any, Dict, Tuple

async def _require_session(request: web.Request):
    from aiohttp_session import get_session
    session = await get_session(request); user = session.get('user')
    if not user: return None, web.json_response({'error':'unauthorized'}, status=401)
    return user, None

async def guilds(request: web.Request):
    webiface = request.app['webiface']
    user, resp = await _require_session(request)
    if resp: return resp
    perms = user.get('permissions', {}) if isinstance(user, dict) else {}
    data = []
    for gid in perms.get('guilds', []):
        g = webiface.cog.bot.get_guild(int(gid))
        if not g: continue
        data.append({'id': g.id, 'name': g.name, 'admin': str(g.id) in perms.get('guild_admin', [])})
    return web.json_response({'guilds': data})

async def guild_status(request: web.Request):
    webiface = request.app['webiface']
    user, resp = await _require_session(request)
    if resp: return resp
    try:
        gid = int(request.match_info['guild_id'])
    except ValueError:
        return web.json_response({'error': 'invalid_guild_id'}, status=400)
    perms = user.get('permissions', {}) if isinstance(user, dict) else {}
    if str(gid) not in perms.get('guilds', []):
        return web.json_response({'error': 'forbidden'}, status=403)
    guild = webiface.cog.bot.get_guild(gid)
    if not guild:
        return web.json_response({'error': 'not_found'}, status=404)
    status = await webiface.get_guild_status(guild)
    return web.json_response(status)

# Helpers
async def _get_guild_with_access(request: web.Request) -> Tuple[Dict[str, Any] | None, Any, Any, int | None, bool]:
    webiface = request.app['webiface']
    user, resp = await _require_session(request)
    if resp:
        return None, resp, None, None, False
    try:
        gid = int(request.match_info['guild_id'])
    except (KeyError, ValueError):
        return user, web.json_response({'error': 'invalid_guild_id'}, status=400), None, None, False
    perms = user.get('permissions', {}) if isinstance(user, dict) else {}
    if str(gid) not in perms.get('guilds', []):
        return user, web.json_response({'error': 'forbidden'}, status=403), None, gid, False
    guild = webiface.cog.bot.get_guild(gid)
    if not guild:
        return user, web.json_response({'error': 'not_found'}, status=404), None, gid, False
    is_admin = (str(gid) in perms.get('guild_admin', [])) or perms.get('bot_owner', False)
    return user, None, guild, gid, is_admin

def _csv_to_list(s: str) -> list[str]:
    if not s:
        return []
    return [part.strip() for part in s.split(',') if part.strip()]

def _csv_to_int_list(s: str) -> list[int]:
    lst = []
    for part in _csv_to_list(s):
        try:
            lst.append(int(part))
        except ValueError:
            continue
    return lst

def _parse_tool_overrides(text: str) -> Dict[str, int]:
    out: Dict[str, int] = {}
    if not text:
        return out
    for line in text.splitlines():
        if '=' not in line:
            continue
        k, v = line.split('=', 1)
        k = k.strip()
        try:
            out[k] = int(v.strip())
        except ValueError:
            continue
    return out

# ---- Toggle endpoint ----
async def handle_toggle(request: web.Request):
    user, resp, guild, gid, is_admin = await _get_guild_with_access(request)
    if resp:
        return resp
    if not is_admin:
        return web.json_response({'error': 'forbidden'}, status=403)
    payload = await request.json()
    setting = str(payload.get('setting', ''))
    value = bool(payload.get('value', False))
    config = request.app['webiface'].cog.config.guild(guild)

    try:
        if setting == 'enabled':
            await config.enabled.set(value)
        elif setting == 'listening_enabled':
            async with config.listening() as l:
                l['enabled'] = value
        elif setting.startswith('tool_'):
            tool = setting[len('tool_'):]
            async with config.tools() as t:
                if 'enabled' not in t or not isinstance(t['enabled'], dict):
                    t['enabled'] = {}
                t['enabled'][tool] = value
        else:
            return web.json_response({'error': 'unknown_setting'}, status=400)
        return web.json_response({'success': True})
    except Exception as e:
        return web.json_response({'error': 'update_failed'}, status=500)

# ---- Providers config ----
async def handle_providers_config(request: web.Request):
    user, resp, guild, gid, is_admin = await _get_guild_with_access(request)
    if resp:
        return resp
    if not is_admin:
        return web.json_response({'error': 'forbidden'}, status=403)
    payload = await request.json()
    config = request.app['webiface'].cog.config.guild(guild)
    cloud_keys = ['openai', 'anthropic', 'groq', 'gemini', 'serp', 'firecrawl']
    local_fields = {
        'ollama': ['base_url'],
        'lmstudio': ['base_url'],
        'localai': ['base_url', 'api_key'],
        'vllm': ['base_url', 'api_key'],
        'text_generation_webui': ['base_url'],
        'openai_compatible': ['base_url', 'api_key']
    }
    try:
        async with config.providers() as prov:
            # Ensure dict exists
            if not isinstance(prov, dict):
                prov = {}
            # Cloud/web providers (api_key only)
            for name in cloud_keys:
                key_field = f"{name}_api_key"
                val = payload.get(key_field)
                if val is None or val == '':
                    continue  # keep current
                if name not in prov or not isinstance(prov[name], dict):
                    prov[name] = {}
                # Do not log actual key
                prov[name]['api_key'] = str(val)
            # Local/self-hosted providers
            for name, fields in local_fields.items():
                for field in fields:
                    form_key = f"{name}_{field}"
                    val = payload.get(form_key)
                    if val is None or val == '':
                        continue
                    if name not in prov or not isinstance(prov[name], dict):
                        prov[name] = {}
                    prov[name][field] = str(val)
        return web.json_response({'success': True})
    except Exception:
        return web.json_response({'error': 'update_failed'}, status=500)

# ---- Model config ----
async def handle_model_config(request: web.Request):
    user, resp, guild, gid, is_admin = await _get_guild_with_access(request)
    if resp:
        return resp
    if not is_admin:
        return web.json_response({'error': 'forbidden'}, status=403)
    payload = await request.json()
    provider = str(payload.get('provider') or '')
    model_name = str(payload.get('model_name') or '')
    if not provider or not model_name:
        return web.json_response({'error': 'invalid_payload'}, status=400)
    config = request.app['webiface'].cog.config.guild(guild)
    try:
        await config.model.set({'provider': provider, 'name': model_name})
        return web.json_response({'success': True})
    except Exception:
        return web.json_response({'error': 'update_failed'}, status=500)

# ---- Params config ----
async def handle_params_config(request: web.Request):
    user, resp, guild, gid, is_admin = await _get_guild_with_access(request)
    if resp:
        return resp
    if not is_admin:
        return web.json_response({'error': 'forbidden'}, status=403)
    payload = await request.json()
    try:
        temperature = float(payload.get('temperature', 0.7))
    except (ValueError, TypeError):
        temperature = 0.7
    try:
        max_tokens = int(payload.get('max_tokens', 512))
    except (ValueError, TypeError):
        max_tokens = 512
    try:
        top_p = float(payload.get('top_p', 1.0))
    except (ValueError, TypeError):
        top_p = 1.0
    # Clamp to reasonable ranges
    temperature = max(0.0, min(2.0, temperature))
    top_p = max(0.0, min(1.0, top_p))
    max_tokens = max(1, min(100000, max_tokens))
    config = request.app['webiface'].cog.config.guild(guild)
    try:
        await config.params.set({'temperature': temperature, 'max_tokens': max_tokens, 'top_p': top_p})
        return web.json_response({'success': True})
    except Exception:
        return web.json_response({'error': 'update_failed'}, status=500)

# ---- Rate limits config ----
async def handle_rate_limits_config(request: web.Request):
    user, resp, guild, gid, is_admin = await _get_guild_with_access(request)
    if resp:
        return resp
    if not is_admin:
        return web.json_response({'error': 'forbidden'}, status=403)
    payload = await request.json()
    def _to_int(name: str, default: int) -> int:
        try:
            return int(payload.get(name, default))
        except (ValueError, TypeError):
            return default
    cooldown_sec = _to_int('cooldown_sec', 10)
    per_user_per_min = _to_int('per_user_per_min', 6)
    per_channel_per_min = _to_int('per_channel_per_min', 20)
    tools_per_user_per_min = _to_int('tools_per_user_per_min', 4)
    tools_per_guild_per_min = _to_int('tools_per_guild_per_min', 30)
    tool_cooldowns_text = str(payload.get('tool_cooldowns') or '')
    tool_cooldowns = _parse_tool_overrides(tool_cooldowns_text)
    config = request.app['webiface'].cog.config.guild(guild)
    try:
        async with config.rate_limits() as rl:
            rl['cooldown_sec'] = cooldown_sec
            rl['per_user_per_min'] = per_user_per_min
            rl['per_channel_per_min'] = per_channel_per_min
            rl['tools_per_user_per_min'] = tools_per_user_per_min
            rl['tools_per_guild_per_min'] = tools_per_guild_per_min
            rl['tool_cooldowns'] = tool_cooldowns
        return web.json_response({'success': True})
    except Exception:
        return web.json_response({'error': 'update_failed'}, status=500)

# ---- Listening config ----
async def handle_listening_config(request: web.Request):
    user, resp, guild, gid, is_admin = await _get_guild_with_access(request)
    if resp:
        return resp
    if not is_admin:
        return web.json_response({'error': 'forbidden'}, status=403)
    payload = await request.json()
    mode = str(payload.get('mode') or 'mention')
    if mode not in ['mention', 'keyword', 'all']:
        mode = 'mention'
    keywords = _csv_to_list(str(payload.get('keywords') or ''))
    config = request.app['webiface'].cog.config.guild(guild)
    try:
        async with config.listening() as l:
            l['mode'] = mode
            l['keywords'] = keywords
        return web.json_response({'success': True})
    except Exception:
        return web.json_response({'error': 'update_failed'}, status=500)

# ---- Smart replies config ----
async def handle_smart_replies_config(request: web.Request):
    user, resp, guild, gid, is_admin = await _get_guild_with_access(request)
    if resp:
        return resp
    if not is_admin:
        return web.json_response({'error': 'forbidden'}, status=403)
    payload = await request.json()
    enabled = bool(payload.get('enabled', True))
    try:
        sensitivity = int(payload.get('sensitivity', 3))
    except (ValueError, TypeError):
        sensitivity = 3
    sensitivity = max(1, min(5, sensitivity))
    try:
        quiet = int(payload.get('quiet_time_seconds', 300))
    except (ValueError, TypeError):
        quiet = 300
    config = request.app['webiface'].cog.config.guild(guild)
    try:
        async with config.smart_replies() as sr:
            sr['enabled'] = enabled
            sr['sensitivity'] = sensitivity
            sr['quiet_time_seconds'] = quiet
        return web.json_response({'success': True})
    except Exception:
        return web.json_response({'error': 'update_failed'}, status=500)

# ---- Auto web search config ----
async def handle_auto_web_search_config(request: web.Request):
    user, resp, guild, gid, is_admin = await _get_guild_with_access(request)
    if resp:
        return resp
    if not is_admin:
        return web.json_response({'error': 'forbidden'}, status=403)
    payload = await request.json()
    enabled = bool(payload.get('enabled', False))
    def _to_int(name: str, default: int, lo: int | None = None, hi: int | None = None) -> int:
        try:
            v = int(payload.get(name, default))
        except (ValueError, TypeError):
            v = default
        if lo is not None:
            v = max(lo, v)
        if hi is not None:
            v = min(hi, v)
        return v
    sensitivity = _to_int('sensitivity', 3, 1, 5)
    max_results = _to_int('max_results', 5, 1, 10)
    timeout_seconds = _to_int('timeout_seconds', 15, 5, 60)
    cooldown_seconds = _to_int('cooldown_seconds', 60, 0, 3600)
    min_message_length = _to_int('min_message_length', 10, 0, 1000)
    config = request.app['webiface'].cog.config.guild(guild)
    try:
        async with config.auto_web_search() as aws:
            aws['enabled'] = enabled
            aws['sensitivity'] = sensitivity
            aws['max_results'] = max_results
            aws['timeout_seconds'] = timeout_seconds
            aws['cooldown_seconds'] = cooldown_seconds
            aws['min_message_length'] = min_message_length
        return web.json_response({'success': True})
    except Exception:
        return web.json_response({'error': 'update_failed'}, status=500)

# ---- Governance config ----
async def handle_governance_config(request: web.Request):
    user, resp, guild, gid, is_admin = await _get_guild_with_access(request)
    if resp:
        return resp
    if not is_admin:
        return web.json_response({'error': 'forbidden'}, status=403)
    payload = await request.json()
    tools_allow = _csv_to_list(str(payload.get('allow_tools') or ''))
    tools_deny = _csv_to_list(str(payload.get('deny_tools') or ''))
    allow_roles = _csv_to_int_list(str(payload.get('allow_roles') or ''))
    deny_roles = _csv_to_int_list(str(payload.get('deny_roles') or ''))
    allow_channels = _csv_to_int_list(str(payload.get('allow_channels') or ''))
    deny_channels = _csv_to_int_list(str(payload.get('deny_channels') or ''))
    cooldown_roles = _csv_to_int_list(str(payload.get('cooldown_roles') or ''))
    overrides_text = str(payload.get('per_user_minute_overrides') or '')
    overrides = _parse_tool_overrides(overrides_text)
    try:
        tokens_cap = int(float(payload.get('per_user_daily_tokens', 0) or 0))
    except (ValueError, TypeError):
        tokens_cap = 0
    try:
        cost_cap = float(payload.get('per_user_daily_cost_usd', 0.0) or 0.0)
    except (ValueError, TypeError):
        cost_cap = 0.0
    config = request.app['webiface'].cog.config.guild(guild)
    try:
        async with config.governance() as gov:
            if 'tools' not in gov or not isinstance(gov['tools'], dict):
                gov['tools'] = {}
            gov['tools']['allow'] = tools_allow
            gov['tools']['deny'] = tools_deny
            gov['tools']['allow_roles'] = allow_roles
            gov['tools']['deny_roles'] = deny_roles
            gov['tools']['allow_channels'] = allow_channels
            gov['tools']['deny_channels'] = deny_channels
            gov['tools']['per_user_minute_overrides'] = overrides
            if 'bypass' not in gov or not isinstance(gov['bypass'], dict):
                gov['bypass'] = {}
            gov['bypass']['cooldown_roles'] = cooldown_roles
            if 'budget' not in gov or not isinstance(gov['budget'], dict):
                gov['budget'] = {}
            gov['budget']['per_user_daily_tokens'] = tokens_cap
            gov['budget']['per_user_daily_cost_usd'] = cost_cap
        return web.json_response({'success': True})
    except Exception:
        return web.json_response({'error': 'update_failed'}, status=500)

# Register routes
def setup(webiface: Any):
    app = webiface.app
    app['webiface'] = webiface
    r = app.router
    # ...existing routes...
    r.add_get('/api/guilds', guilds)
    r.add_get('/api/status/{guild_id}', guild_status)
    # New POST routes
    r.add_post('/api/guild/{guild_id}/toggle', handle_toggle)
    r.add_post('/api/guild/{guild_id}/config/providers', handle_providers_config)
    r.add_post('/api/guild/{guild_id}/config/model', handle_model_config)
    r.add_post('/api/guild/{guild_id}/config/params', handle_params_config)
    r.add_post('/api/guild/{guild_id}/config/rate_limits', handle_rate_limits_config)
    r.add_post('/api/guild/{guild_id}/config/listening', handle_listening_config)
    r.add_post('/api/guild/{guild_id}/config/smart_replies', handle_smart_replies_config)
    r.add_post('/api/guild/{guild_id}/config/auto_web_search', handle_auto_web_search_config)
    r.add_post('/api/guild/{guild_id}/config/governance', handle_governance_config)
