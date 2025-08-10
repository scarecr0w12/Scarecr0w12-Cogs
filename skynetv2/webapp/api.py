"""JSON API endpoints split out."""
from __future__ import annotations
from aiohttp import web
from aiohttp_session import get_session
from typing import Any, Dict, Tuple
# Add provider types for chat test
from ..api.base import ChatMessage, ChatParams, ProviderError
from ..logging_system import get_system_logs as _get_system_logs, get_guild_logs as _get_guild_logs

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
    guild = request.app['webiface'].cog.bot.get_guild(gid)
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

# ---- Channel listening (per-channel) config ----
async def handle_channel_listening_config(request: web.Request):
    user, resp, guild, gid, is_admin = await _get_guild_with_access(request)
    if resp:
        return resp
    if not is_admin:
        return web.json_response({'error': 'forbidden'}, status=403)
    payload = await request.json()
    # Validate inputs
    try:
        channel_id = int(str(payload.get('channel_id')))
    except (TypeError, ValueError):
        return web.json_response({'error': 'invalid_channel_id'}, status=400)
    enabled = bool(payload.get('enabled', False))
    mode = str(payload.get('mode') or 'mention')
    if mode not in ['mention', 'keyword', 'all']:
        mode = 'mention'
    keywords = _csv_to_list(str(payload.get('keywords') or ''))
    config = request.app['webiface'].cog.config.guild(guild)
    try:
        async with config.channel_listening() as ch_cfg:
            if not isinstance(ch_cfg, dict):
                ch_cfg = {}
            ch = ch_cfg.get(str(channel_id), {}) if isinstance(ch_cfg.get(str(channel_id)), dict) else {}
            ch['enabled'] = enabled
            ch['mode'] = mode
            ch['keywords'] = keywords
            ch_cfg[str(channel_id)] = ch
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

# ---- Memory scopes (per-user memory) config ----
async def handle_memory_scopes_config(request: web.Request):
    user, resp, guild, gid, is_admin = await _get_guild_with_access(request)
    if resp:
        return resp
    if not is_admin:
        return web.json_response({'error': 'forbidden'}, status=403)
    payload = await request.json()
    # normalize booleans coming from checkbox or string
    def _to_bool(v: object) -> bool:
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.lower() in ('1','true','yes','on','checked')
        return bool(v)
    enabled = _to_bool(payload.get('per_user_enabled', False))
    try:
        limit = int(payload.get('per_user_limit', 10))
    except (ValueError, TypeError):
        limit = 10
    limit = max(1, min(100, limit))
    strategy = str(payload.get('merge_strategy') or 'append').lower()
    if strategy not in ('append','interleave','user_first'):
        strategy = 'append'
    config = request.app['webiface'].cog.config.guild(guild)
    try:
        async with config.memory() as mem:
            if 'scopes' not in mem or not isinstance(mem['scopes'], dict):
                mem['scopes'] = {}
            mem['scopes']['per_user_enabled'] = enabled
            mem['scopes']['per_user_limit'] = limit
            mem['scopes']['merge_strategy'] = strategy
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

# ---- Chat test (simple, non-streaming) ----
async def handle_chat_test(request: web.Request):
    user, resp, guild, gid, is_admin = await _get_guild_with_access(request)
    if resp:
        return resp
    payload = await request.json()
    prompt = str(payload.get('message') or payload.get('prompt') or '').strip()
    if not prompt:
        return web.json_response({'error': 'missing_message'}, status=400)

    webiface = request.app['webiface']
    try:
        provider_name, model_dict, provider_config = await webiface.cog.resolve_provider_and_model(guild)
        model_name = model_dict.get('name') if isinstance(model_dict, dict) else str(model_dict)
        provider = webiface.cog.build_provider(provider_name, provider_config)

        # Build ChatParams from guild/global config
        gparams = await webiface.cog.config.guild(guild).params()
        if not gparams:
            gparams = await webiface.cog.config.params()
        params = ChatParams(
            temperature=float(gparams.get('temperature', 0.7) or 0.7),
            max_tokens=int(gparams.get('max_tokens', 512) or 512),
            top_p=float(gparams.get('top_p', 1.0) or 1.0),
        )
        messages = [ChatMessage(role='user', content=prompt)]

        # Collect non-streaming response
        chunks: list[str] = []
        async for part in provider.chat(model=model_name, messages=messages, params=params, stream=False):
            if part:
                chunks.append(str(part))
        text = (''.join(chunks)).strip() or '(no response)'
        if len(text) > 2000:
            text = text[:2000]
        return web.json_response({'success': True, 'text': text})
    except ProviderError:
        return web.json_response({'error': 'provider_error'}, status=502)
    except Exception:
        return web.json_response({'error': 'request_failed'}, status=500)

# ---- Webfetch test (admin-only) ----
async def handle_webfetch_test(request: web.Request):
    user, resp, guild, gid, is_admin = await _get_guild_with_access(request)
    if resp:
        return resp
    if not is_admin:
        return web.json_response({'error': 'forbidden'}, status=403)
    payload = await request.json()
    mode = str(payload.get('mode') or '').strip().lower()
    target = str(payload.get('target') or '').strip()
    if not mode or not target:
        return web.json_response({'error': 'invalid_payload'}, status=400)
    try:
        limit = payload.get('limit')
        depth = payload.get('depth')
        try:
            limit = int(limit) if limit is not None and str(limit).strip() != '' else None
        except (ValueError, TypeError):
            limit = None
        try:
            depth = int(depth) if depth is not None and str(depth).strip() != '' else None
        except (ValueError, TypeError):
            depth = None
        # Clamp to safe bounds
        if limit is not None:
            limit = max(1, min(50, limit))
        if depth is not None:
            depth = max(0, min(3, depth))
        # Execute via cog tool
        result = await request.app['webiface'].cog._tool_run_webfetch(guild=guild, mode=mode, target=target, limit=limit, depth=depth, user=None)
        if not isinstance(result, str):
            result = str(result)
        if len(result) > 2000:
            result = result[:2000]
        return web.json_response({'success': True, 'text': result})
    except Exception:
        return web.json_response({'error': 'request_failed'}, status=500)

# ---- Global providers config (owner-only) ----
async def handle_global_providers_config(request: web.Request):
    user, resp = await _require_session(request)
    if resp:
        return resp
    perms = user.get('permissions', {}) if isinstance(user, dict) else {}
    if not perms.get('bot_owner', False):
        return web.json_response({'error': 'forbidden'}, status=403)
    payload = await request.json()
    conf = request.app['webiface'].cog.config
    cloud_keys = ['openai', 'serp', 'firecrawl', 'anthropic', 'groq', 'gemini']
    local_fields = {
        'ollama': ['base_url'],
        'lmstudio': ['base_url'],
        'localai': ['base_url', 'api_key'],
        'vllm': ['base_url', 'api_key'],
        'text_generation_webui': ['base_url'],
        'openai_compatible': ['base_url', 'api_key']
    }
    try:
        async with conf.providers() as prov:
            if not isinstance(prov, dict):
                prov = {}
            # Cloud/web providers
            for name in cloud_keys:
                key_field = f"{name}_api_key"
                val = payload.get(key_field)
                if val is None or val == '':
                    continue
                if name not in prov or not isinstance(prov[name], dict):
                    prov[name] = {}
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

# ---- Global web flags (owner-only) ----
async def handle_global_web_flags(request: web.Request):
    user, resp = await _require_session(request)
    if resp:
        return resp
    perms = user.get('permissions', {}) if isinstance(user, dict) else {}
    if not perms.get('bot_owner', False):
        return web.json_response({'error': 'forbidden'}, status=403)
    payload = await request.json()
    conf = request.app['webiface'].cog.config
    try:
        # Normalize checkbox values: can be bool or 'on'
        logs_enabled = payload.get('web_logs_enabled')
        debug_enabled = payload.get('web_debug')
        def _to_bool(v):
            if isinstance(v, bool): return v
            if isinstance(v, str):
                return v.lower() in ('1','true','yes','on','checked')
            return bool(v)
        await conf.web_logs_enabled.set(_to_bool(logs_enabled))
        await conf.web_debug.set(_to_bool(debug_enabled))
        return web.json_response({'success': True})
    except Exception:
        return web.json_response({'error': 'update_failed'}, status=500)

# ---- Logs (JSON) ----
async def handle_system_logs(request: web.Request):
    user, resp = await _require_session(request)
    if resp:
        return resp
    # Respect global flag to disable logs API entirely
    logs_enabled = bool(await request.app['webiface'].cog.config.web_logs_enabled())
    if not logs_enabled:
        return web.json_response({'error': 'disabled'}, status=403)
    # Optional: restrict to bot owners only; keep open to logged-in for now
    try:
        limit = int(request.query.get('limit', '50'))
    except (TypeError, ValueError):
        limit = 50
    level = request.query.get('level')
    logs = await _get_system_logs(limit=limit)
    if level:
        logs = [e for e in logs if getattr(e, 'level', None) == level]
    data = [e.to_dict() if hasattr(e, 'to_dict') else e for e in logs]
    return web.json_response({'logs': data})

async def handle_guild_logs(request: web.Request):
    user, resp = await _require_session(request)
    if resp:
        return resp
    # Respect global flag
    logs_enabled = bool(await request.app['webiface'].cog.config.web_logs_enabled())
    if not logs_enabled:
        return web.json_response({'error': 'disabled'}, status=403)
    perms = user.get('permissions', {}) if isinstance(user, dict) else {}
    try:
        gid = int(request.match_info['guild_id'])
    except (KeyError, ValueError):
        return web.json_response({'error': 'invalid_guild_id'}, status=400)
    if not (perms.get('bot_owner', False) or (str(gid) in perms.get('guilds', []))):
        return web.json_response({'error': 'forbidden'}, status=403)
    try:
        limit = int(request.query.get('limit', '50'))
    except (TypeError, ValueError):
        limit = 50
    level = request.query.get('level')
    logs = await _get_guild_logs(guild_id=gid, limit=limit)
    if level:
        logs = [e for e in logs if getattr(e, 'level', None) == level]
    data = [e.to_dict() if hasattr(e, 'to_dict') else e for e in logs]
    return web.json_response({'logs': data})

# Register routes
def setup(webiface: Any):
    app = webiface.app
    app['webiface'] = webiface
    r = app.router
    # ...existing routes...
    r.add_get('/api/guilds', guilds)
    r.add_get('/api/status/{guild_id}', guild_status)
    # Logs
    r.add_get('/api/logs/system', handle_system_logs)
    r.add_get('/api/logs/guild/{guild_id}', handle_guild_logs)
    # New POST routes
    r.add_post('/api/guild/{guild_id}/toggle', handle_toggle)
    r.add_post('/api/guild/{guild_id}/config/providers', handle_providers_config)
    r.add_post('/api/guild/{guild_id}/config/model', handle_model_config)
    r.add_post('/api/guild/{guild_id}/config/params', handle_params_config)
    r.add_post('/api/guild/{guild_id}/config/rate_limits', handle_rate_limits_config)
    r.add_post('/api/guild/{guild_id}/config/listening', handle_listening_config)
    r.add_post('/api/guild/{guild_id}/config/channel_listening', handle_channel_listening_config)
    r.add_post('/api/guild/{guild_id}/config/smart_replies', handle_smart_replies_config)
    r.add_post('/api/guild/{guild_id}/config/auto_web_search', handle_auto_web_search_config)
    r.add_post('/api/guild/{guild_id}/config/memory_scopes', handle_memory_scopes_config)
    r.add_post('/api/guild/{guild_id}/config/governance', handle_governance_config)
    # Chat test
    r.add_post('/api/guild/{guild_id}/chat_test', handle_chat_test)
    # Webfetch test (admin-only)
    r.add_post('/api/guild/{guild_id}/webfetch_test', handle_webfetch_test)
    # Global config
    r.add_post('/api/global/config/providers', handle_global_providers_config)
    r.add_post('/api/global/config/web_flags', handle_global_web_flags)
