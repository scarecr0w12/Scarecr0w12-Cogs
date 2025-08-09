"""Prompt templates pages & API."""
from __future__ import annotations
from aiohttp import web
from aiohttp_session import get_session
import re, time, json
from typing import Dict, Any
try:
    from typing import Protocol  # for type hint only
except Exception:
    Protocol = object  # type: ignore

# helper to safely access permissions dict (avoid type checker complaints)
def _perms(user: Any) -> Dict[str, Any]:  # type: ignore
    if isinstance(user, dict):
        val = user.get('permissions')
        if isinstance(val, dict):
            return val
    return {}

VAR_RE = re.compile(r"{{\s*([a-zA-Z0-9_]{1,32})\s*}}")
NAME_RE = re.compile(r"^[a-z0-9_-]{3,32}$")

BASE_STYLE = "body{font-family:Segoe UI,Arial,sans-serif;margin:20px;background:#f5f7fb;color:#222}a{color:#3366cc;text-decoration:none}nav a{margin-right:12px}.card{background:#fff;padding:16px;border-radius:8px;box-shadow:0 2px 6px rgba(0,0,0,0.06);margin:12px 0}table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:6px 8px;border-bottom:1px solid #eee;font-size:14px}th{background:#fafafa}input,textarea{width:100%;padding:8px;margin:4px 0 10px;font-family:inherit;font-size:14px}textarea{min-height:160px}button{background:#3366cc;color:#fff;border:none;padding:8px 14px;border-radius:4px;cursor:pointer}button:disabled{opacity:.5;cursor:not-allowed}.error{color:#c0392b;font-size:13px;margin:4px 0}.badge{display:inline-block;background:#eef;padding:2px 6px;border-radius:4px;font-size:11px;margin-right:4px}"

def _html(title: str, body: str) -> str:
    return f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>{title}</title><style>{BASE_STYLE}</style></head><body><nav><a href='/dashboard'>Dashboard</a><a href='/profile'>Profile</a><a href='/prompts'>Prompts</a></nav>{body}</body></html>"

async def _require_session(request: web.Request):
    session = await get_session(request); user = session.get('user')
    if not user: return None, web.HTTPFound('/')
    # ensure csrf token
    if 'csrf_token' not in session:
        import secrets; session['csrf_token'] = secrets.token_urlsafe(24)
    return user, None

async def list_prompts(request: web.Request):
    webiface = request.app['webiface']
    user, resp = await _require_session(request)
    if resp: return resp
    session = await get_session(request)
    # Optional guild filtering
    gid_q = request.query.get('guild')
    guild_prompts: Dict[str, Any] = {}
    guild_name = None
    if gid_q and gid_q.isdigit():
        gid = int(gid_q); g = webiface.cog.bot.get_guild(gid)
        if g and str(gid) in _perms(user).get('guilds', []):
            guild_name = g.name
            guild_prompts = await webiface.cog.config.guild(g).prompts()
    global_prompts = await webiface.cog.config.prompts()
    # Build table
    def row(scope, name, data):
        vars_badges = ' '.join(f"<span class='badge'>{v}</span>" for v in data.get('variables', []))
        return f"<tr><td>{name}</td><td>{scope}</td><td>{vars_badges or '(none)'}</td><td><a href='/prompts/{name}?scope={scope}{('&guild='+gid_q) if scope=='guild' and gid_q else ''}'>open</a></td></tr>"
    rows = []
    for n,d in sorted(global_prompts.items()): rows.append(row('global', n, d))
    for n,d in sorted(guild_prompts.items()): rows.append(row('guild', n, d))
    guild_selector = ''
    if _perms(user).get('guilds'):
        opts = [f"<option value=''>-- none --</option>"]
        for gid in _perms(user).get('guilds', []):
            g = webiface.cog.bot.get_guild(int(gid))
            if not g: continue
            sel = ' selected' if gid_q and gid_q == gid else ''
            opts.append(f"<option value='{gid}'{sel}>{g.name}</option>")
        guild_selector = f"<form method='get' style='margin:0 0 12px'><label>Guild: <select name='guild' onchange='this.form.submit()'>{''.join(opts)}</select></label></form>"
    create_hint = "<p><a href='/prompts/new'>Create Global Prompt</a></p>"
    if gid_q and guild_name:
        create_hint += f"<p><a href='/prompts/new?guild={gid_q}'>Create Guild Prompt ({guild_name})</a></p>"
    body = f"<h1>Prompts</h1>{guild_selector}<div class='card'><h2>Templates</h2>{create_hint}<table><tr><th>Name</th><th>Scope</th><th>Vars</th><th></th></tr>{''.join(rows) if rows else '<tr><td colspan=4>(none)</td></tr>'}</table></div>"
    return web.Response(text=_html('Prompts', body), content_type='text/html')

async def new_prompt(request: web.Request):
    webiface = request.app['webiface']
    user, resp = await _require_session(request)
    if resp: return resp
    session = await get_session(request)
    gid_q = request.query.get('guild')
    scope = 'global'
    guild = None
    if gid_q and gid_q.isdigit():
        gid = int(gid_q)
        g = webiface.cog.bot.get_guild(gid)
        if g and str(gid) in _perms(user).get('guild_admin', []):
            scope = 'guild'; guild = g
    if request.method == 'POST':
        data = await request.post()
        if data.get('csrf_token') != session.get('csrf_token'):
            return web.Response(text='CSRF mismatch', status=400)
        name = (data.get('name','') or '').strip().lower()
        content = (data.get('content','') or '').strip()
        if not NAME_RE.match(name):
            err = "Invalid name (lowercase letters, numbers, -_)"
        elif len(content) < 5:
            err = "Content too short"
        else:
            variables = sorted(set(VAR_RE.findall(content)))
            entry = {"content": content, "variables": variables, "created": int(time.time()), "updated": int(time.time()), "scope": scope}
            if scope == 'global':
                async with webiface.cog.config.prompts() as pm:
                    if name in pm:
                        err = "Name exists"
                    else:
                        pm[name] = entry; err = None
            else:
                async with webiface.cog.config.guild(guild).prompts() as pm:  # type: ignore
                    if name in pm:
                        err = "Name exists"
                    else:
                        pm[name] = entry; err = None
            if not err:
                return web.HTTPFound(f"/prompts/{name}?scope={scope}{(f'&guild={guild.id}' if guild else '')}")
        # show form again with error
        body_err = f"<p class='error'>{err}</p>"
    else:
        body_err = ''
        name = ''; content = ''
    body = f"<h1>New Prompt ({scope})</h1><div class='card'>{body_err}<form method='post'><input type='hidden' name='csrf_token' value='{session.get('csrf_token')}'><label>Name<br><input name='name' value='{name}' required></label><label>Content<br><textarea name='content'>{content}</textarea></label><button type='submit'>Create</button></form></div>"
    return web.Response(text=_html('New Prompt', body), content_type='text/html')

async def view_prompt(request: web.Request):
    webiface = request.app['webiface']
    user, resp = await _require_session(request)
    if resp: return resp
    session = await get_session(request)
    name = request.match_info['name']
    scope = request.query.get('scope','global')
    gid_q = request.query.get('guild')
    entry = None; guild=None
    if scope == 'global':
        entry = (await webiface.cog.config.prompts()).get(name)
    elif scope == 'guild' and gid_q and gid_q.isdigit():
        gid = int(gid_q); g = webiface.cog.bot.get_guild(gid)
        if g and str(gid) in _perms(user).get('guilds', []):
            guild = g
            entry = (await webiface.cog.config.guild(g).prompts()).get(name)
    if not entry:
        return web.Response(text='Not found', status=404)
    can_edit = False
    if scope == 'global':
        can_edit = _perms(user).get('bot_owner')
    else:
        can_edit = guild and str(guild.id) in _perms(user).get('guild_admin', [])
    vars_badges = ' '.join(f"<span class='badge'>{v}</span>" for v in entry.get('variables', [])) or '(none)'
    edit_form = ''
    if can_edit and request.method == 'POST':
        data = await request.post()
        if data.get('csrf_token') != session.get('csrf_token'):
            return web.Response(text='CSRF mismatch', status=400)
        content = (data.get('content','') or '').strip()
        if len(content) < 5:
            err = 'Content too short'
        else:
            variables = sorted(set(VAR_RE.findall(content)))
            entry['content'] = content
            entry['variables'] = variables
            entry['updated'] = int(time.time())
            if scope == 'global':
                async with webiface.cog.config.prompts() as pm: pm[name] = entry
            else:
                async with webiface.cog.config.guild(guild).prompts() as pm: pm[name] = entry  # type: ignore
            return web.HTTPFound(request.path_qs)
        edit_form = f"<p class='error'>{err}</p>"
    if can_edit:
        edit_form += f"<form method='post'><input type='hidden' name='csrf_token' value='{session.get('csrf_token')}'><label>Content<br><textarea name='content'>{entry.get('content','')}</textarea></label><button type='submit'>Save</button></form>"
    delete_btn = ''
    if can_edit:
        delete_btn = f"<form method='post' action='/prompts/{name}/delete?scope={scope}{('&guild='+str(guild.id)) if guild else ''}' style='margin-top:10px'><input type='hidden' name='csrf_token' value='{session.get('csrf_token')}'><button type='submit' style='background:#c0392b'>Delete</button></form>"
    body = f"<h1>Prompt: {name}</h1><div class='card'><p>Scope: {scope}</p><p>Variables: {vars_badges}</p><pre style='white-space:pre-wrap'>{entry.get('content','')}</pre>{edit_form}{delete_btn}<p><a href='/prompts'>Back</a></p></div>"
    return web.Response(text=_html('Prompt', body), content_type='text/html')

async def generate_prompt(request: web.Request):
    """Render a simple variable fill form and preview output for a prompt template."""
    webiface = request.app['webiface']
    user, resp = await _require_session(request)
    if resp: return resp
    name = request.match_info['name']
    scope = request.query.get('scope','global')
    gid_q = request.query.get('guild')
    entry = None; guild=None
    if scope == 'global':
        entry = (await webiface.cog.config.prompts()).get(name)
    elif scope == 'guild' and gid_q and gid_q.isdigit():
        gid = int(gid_q); g = webiface.cog.bot.get_guild(gid)
        if g and str(gid) in _perms(user).get('guilds', []):
            guild = g
            entry = (await webiface.cog.config.guild(g).prompts()).get(name)
    if not entry:
        return web.Response(text='Not found', status=404)
    vars_list = entry.get('variables', [])
    filled = {}
    output = None
    if request.method == 'POST':
        data = await request.post()
        for v in vars_list:
            filled[v] = (data.get(v,'') or '').strip()
        # simple substitution
        content = entry.get('content','')
        def rep(m):
            var = m.group(1).strip()
            return filled.get(var, f'{{{{{var}}}}}')
        output = VAR_RE.sub(rep, content)
    form_inputs = ''.join(f"<label>{v}<br><input name='{v}' value='{filled.get(v,'')}'></label>" for v in vars_list) or '<p>(No variables defined)</p>'
    preview = f"<h3>Preview</h3><pre style='white-space:pre-wrap'>{output}</pre>" if output is not None else ''
    body = f"<h1>Generate: {name}</h1><div class='card'><form method='post'>{form_inputs}<button type='submit'>Generate</button></form>{preview}<p><a href='/prompts/{name}?scope={scope}{('&guild='+gid_q) if gid_q else ''}'>Back</a></p></div>"
    return web.Response(text=_html('Generate Prompt', body), content_type='text/html')

async def delete_prompt(request: web.Request):
    webiface = request.app['webiface']
    user, resp = await _require_session(request)
    if resp: return resp
    session = await get_session(request)
    name = request.match_info['name']
    scope = request.query.get('scope','global')
    gid_q = request.query.get('guild')
    if request.method != 'POST' or (request.method=='POST' and (await request.post()).get('csrf_token') != session.get('csrf_token')):
        return web.Response(text='Bad request', status=400)
    if scope == 'global':
        if not _perms(user).get('bot_owner'):
            return web.Response(text='Forbidden', status=403)
        async with webiface.cog.config.prompts() as pm: pm.pop(name, None)
    elif scope == 'guild' and gid_q and gid_q.isdigit():
        gid = int(gid_q); g = webiface.cog.bot.get_guild(gid)
        if not (g and str(gid) in _perms(user).get('guild_admin', [])):
            return web.Response(text='Forbidden', status=403)
        async with webiface.cog.config.guild(g).prompts() as pm: pm.pop(name, None)
    return web.HTTPFound('/prompts')

# JSON API (subset)
async def api_list(request: web.Request):
    webiface = request.app['webiface']
    user, resp = await _require_session(request)
    if resp: return resp
    scope = request.query.get('scope','global')
    if scope == 'global':
        data = await webiface.cog.config.prompts()
    else:
        gid_q = request.query.get('guild'); data = {}
        if gid_q and gid_q.isdigit():
            gid = int(gid_q); g = webiface.cog.bot.get_guild(gid)
            if g and str(gid) in _perms(user).get('guilds', []):
                data = await webiface.cog.config.guild(g).prompts()
    return web.json_response({'prompts': data})

async def api_put(request: web.Request):
    webiface = request.app['webiface']
    user, resp = await _require_session(request)
    if resp: return resp
    body = await request.text()
    try:
        payload = json.loads(body or '{}')
    except Exception:
        return web.json_response({'error':'invalid_json'}, status=400)
    name = (payload.get('name','') or '').strip().lower()
    content = (payload.get('content','') or '').strip()
    scope = payload.get('scope','global')
    gid = payload.get('guild')
    if not NAME_RE.match(name):
        return web.json_response({'error':'invalid_name'}, status=400)
    if len(content) < 5:
        return web.json_response({'error':'content_too_short'}, status=400)
    variables = sorted(set(VAR_RE.findall(content)))
    entry = {"content": content, "variables": variables, "updated": int(time.time())}
    if scope == 'global':
        if not _perms(user).get('bot_owner'):
            return web.json_response({'error':'forbidden'}, status=403)
        async with webiface.cog.config.prompts() as pm:
            pm.setdefault(name, {"created": int(time.time()), "scope": 'global'})
            pm[name].update(entry)
    else:
        if not (isinstance(gid, int) or (isinstance(gid, str) and gid.isdigit())):
            return web.json_response({'error':'missing_guild'}, status=400)
        gid_i = int(gid); g = webiface.cog.bot.get_guild(gid_i)
        if not (g and str(gid_i) in _perms(user).get('guild_admin', [])):
            return web.json_response({'error':'forbidden'}, status=403)
        async with webiface.cog.config.guild(g).prompts() as pm:  # type: ignore
            pm.setdefault(name, {"created": int(time.time()), "scope": 'guild'})
            pm[name].update(entry)
    return web.json_response({'ok': True, 'name': name, 'scope': scope, 'variables': variables})

async def api_delete(request: web.Request):
    webiface = request.app['webiface']
    user, resp = await _require_session(request)
    if resp: return resp
    name = request.match_info['name']
    scope = request.query.get('scope','global')
    if scope == 'global':
        if not _perms(user).get('bot_owner'):
            return web.json_response({'error':'forbidden'}, status=403)
        async with webiface.cog.config.prompts() as pm: pm.pop(name, None)
    else:
        gid_q = request.query.get('guild')
        if not (gid_q and gid_q.isdigit()):
            return web.json_response({'error':'missing_guild'}, status=400)
        gid = int(gid_q); g = webiface.cog.bot.get_guild(gid)
        if not (g and str(gid) in _perms(user).get('guild_admin', [])):
            return web.json_response({'error':'forbidden'}, status=403)
        async with webiface.cog.config.guild(g).prompts() as pm: pm.pop(name, None)
    return web.json_response({'ok': True})

def setup(webiface: 'WebInterface'):
    app = webiface.app  # type: ignore[attr-defined]
    app['webiface'] = webiface
    # pages
    app.router.add_get('/prompts', list_prompts)
    app.router.add_get('/prompts/new', new_prompt)
    app.router.add_post('/prompts/new', new_prompt)
    app.router.add_get('/prompts/{name}', view_prompt)
    app.router.add_post('/prompts/{name}', view_prompt)
    app.router.add_get('/prompts/{name}/generate', generate_prompt)
    app.router.add_post('/prompts/{name}/generate', generate_prompt)
    app.router.add_post('/prompts/{name}/delete', delete_prompt)
    # api
    app.router.add_get('/api/prompts', api_list)
    app.router.add_post('/api/prompts', api_put)
    app.router.add_delete('/api/prompts/{name}', api_delete)

try:
    from .interface import WebInterface  # type: ignore
except Exception:
    class WebInterface:  # type: ignore
        pass
