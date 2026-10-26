"""
api/team.py  —  Agentiva portal "Mi Equipo"
Vercel Python serverless function. Creates and manages team-member logins
for a portal client (owner). Creating auth users needs the service key, so
it can't happen in the browser; everything else about members (listing,
filters, sessions) is read/written client-side under RLS.

Actions (POST JSON, caller's portal access token in `token`):
  check_username  {username}                         → {available}
  create          {nombre, username, password, owner_id?}  → {member}
  reset_password  {member_id, password}
  set_active      {member_id, activo}
  delete          {member_id}

Caller must be the member's owner (role 'client') or an admin. Admins pass
`owner_id` on create; owners always create under themselves.

Members log in with a synthetic email <username>@team.agentiva.com.ar —
the login modal maps a bare username to it.

Required env var in Vercel dashboard:
  AGENTIVA_SUPABASE_SERVICE_KEY
"""

from http.server import BaseHTTPRequestHandler
import json, os, re, urllib.request, urllib.error

SB_URL  = 'https://cyczjwnqrzxbngiqhzcj.supabase.co'
MEMBER_DOMAIN = 'team.agentiva.com.ar'
USERNAME_RE = re.compile(r'^[a-z0-9][a-z0-9._-]{2,31}$')
UUID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
BAN_FOREVER = '876000h'   # ~100 years — Supabase has no "disable", only bans


class ApiError(Exception):
    def __init__(self, status, msg):
        super().__init__(msg)
        self.status, self.msg = status, msg


# ── Supabase helpers ─────────────────────────────────────────────────────────

def _req(method, path, headers, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(SB_URL + path, data=data, method=method, headers={
        'Content-Type': 'application/json', **headers,
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors='replace')
        raise ApiError(e.code, detail[:300])


def service(method, path, body=None, prefer=None):
    key = os.environ['AGENTIVA_SUPABASE_SERVICE_KEY']
    h = {'apikey': key, 'Authorization': f'Bearer {key}'}
    if prefer:
        h['Prefer'] = prefer
    return _req(method, path, h, body)


def caller_profile(token):
    if not token:
        raise ApiError(401, 'Sesión requerida')
    key = os.environ['AGENTIVA_SUPABASE_SERVICE_KEY']
    try:
        user = _req('GET', '/auth/v1/user', {'apikey': key, 'Authorization': f'Bearer {token}'})
    except ApiError:
        raise ApiError(401, 'Sesión vencida — volvé a ingresar')
    rows = service('GET', f"/rest/v1/client_profiles?id=eq.{user['id']}&select=id,role,empresa")
    if not rows or rows[0]['role'] not in ('client', 'admin'):
        raise ApiError(403, 'No autorizado')
    return rows[0]


def member_of(caller, member_id):
    if not UUID_RE.match(member_id or ''):
        raise ApiError(400, 'Miembro inválido')
    rows =service('GET', f'/rest/v1/client_profiles?id=eq.{member_id}&role=eq.member&select=id,owner_id')
    if not rows:
        raise ApiError(404, 'Miembro no encontrado')
    if caller['role'] != 'admin' and rows[0]['owner_id'] != caller['id']:
        raise ApiError(403, 'No autorizado')
    return rows[0]


def clean_username(u):
    u = (u or '').strip().lower()
    if not USERNAME_RE.match(u):
        raise ApiError(400, 'Usuario inválido: 3-32 caracteres, letras, números, punto, guion')
    return u


def check_password(p):
    if not p or len(p) < 8:
        raise ApiError(400, 'La contraseña debe tener al menos 8 caracteres')
    return p


def username_taken(u):
    return bool(service('GET', f'/rest/v1/client_profiles?username=eq.{u}&select=id'))


# ── Actions ──────────────────────────────────────────────────────────────────

def do_check_username(caller, body):
    return {'available': not username_taken(clean_username(body.get('username')))}


def do_create(caller, body):
    nombre = (body.get('nombre') or '').strip()
    if not nombre:
        raise ApiError(400, 'Falta el nombre')
    username = clean_username(body.get('username'))
    password = check_password(body.get('password'))

    owner_id = caller['id']
    empresa = caller.get('empresa')
    if caller['role'] == 'admin':
        owner_id = body.get('owner_id') or ''
        if not UUID_RE.match(owner_id):
            raise ApiError(400, 'Cliente inválido')
        owners =service('GET', f'/rest/v1/client_profiles?id=eq.{owner_id}&role=eq.client&select=id,empresa')
        if not owners:
            raise ApiError(400, 'Cliente inválido')
        empresa = owners[0].get('empresa')

    if username_taken(username):
        raise ApiError(409, 'Ese usuario ya existe — probá con otro')

    email = f'{username}@{MEMBER_DOMAIN}'
    user = service('POST', '/auth/v1/admin/users', {
        'email': email, 'password': password, 'email_confirm': True,
        'user_metadata': {'nombre': nombre, 'member': True},
    })
    uid = user['id']
    try:
        rows = service('POST', '/rest/v1/client_profiles', {
            'id': uid, 'nombre': nombre, 'empresa': empresa, 'email': email,
            'role': 'member', 'owner_id': owner_id, 'username': username, 'activo': True,
        }, prefer='return=representation')
    except ApiError:
        service('DELETE', f'/auth/v1/admin/users/{uid}')   # don't leave an orphan login
        raise
    return {'member': rows[0]}


def do_reset_password(caller, body):
    m = member_of(caller, body.get('member_id'))
    service('PUT', f"/auth/v1/admin/users/{m['id']}", {'password': check_password(body.get('password'))})
    return {'ok': True}


def do_set_active(caller, body):
    m = member_of(caller, body.get('member_id'))
    activo = bool(body.get('activo'))
    service('PUT', f"/auth/v1/admin/users/{m['id']}", {'ban_duration': 'none' if activo else BAN_FOREVER})
    service('PATCH', f"/rest/v1/client_profiles?id=eq.{m['id']}", {'activo': activo})
    return {'ok': True, 'activo': activo}


def do_delete(caller, body):
    m = member_of(caller, body.get('member_id'))
    # client_profiles.id → auth.users ON DELETE CASCADE; filters/sessions cascade from the profile
    service('DELETE', f"/auth/v1/admin/users/{m['id']}")
    return {'ok': True}


ACTIONS = {
    'check_username': do_check_username,
    'create': do_create,
    'reset_password': do_reset_password,
    'set_active': do_set_active,
    'delete': do_delete,
}


class handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_POST(self):
        try:
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length) or b'{}')
            fn = ACTIONS.get(body.get('action'))
            if not fn:
                raise ApiError(400, 'Acción inválida')
            caller = caller_profile(body.get('token', ''))
            self._send(200, fn(caller, body))
        except ApiError as e:
            self._send(e.status, {'error': e.msg})
        except Exception as e:
            self._send(500, {'error': f'Error interno: {e}'})

    def _send(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', len(body))
        self._cors()
        self.end_headers()
        self.wfile.write(body)
