"""
api/chat.py  —  Campaso CRM AI Assistant
Vercel Python serverless function.

- Fetches live Supabase data, calls Claude, returns a natural-language answer.
- Rate limit: 200 queries / restaurant / calendar month.

Required env var in Vercel dashboard:
  ANTHROPIC_API_KEY
"""

from http.server import BaseHTTPRequestHandler
import json, os, urllib.request, urllib.parse
from datetime import datetime, timezone

SB_URL  = 'https://etetlzcsqucujqjkzsvm.supabase.co'
SB_ANON = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImV0ZXRsemNzcXVjdWpxamt6c3ZtIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzg2OTU3MzUsImV4cCI6MjA5NDI3MTczNX0.KMo40WJKxsLMu7OK5ksblxSkg61gTZLjpA4DIJOMJ8c'
MONTHLY_LIMIT = 200


# ── Supabase helpers ─────────────────────────────────────────────────────────

def sb_headers(token):
    return {
        'apikey': SB_ANON,
        'Authorization': f'Bearer {token}',
        'Accept': 'application/json',
        'Content-Type': 'application/json',
    }

def sb_get(path, params, token):
    url = f'{SB_URL}/rest/v1/{path}?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=sb_headers(token))
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())

def sb_post(path, body, token, prefer='return=representation'):
    payload = json.dumps(body, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(
        f'{SB_URL}/rest/v1/{path}',
        data=payload,
        headers={**sb_headers(token), 'Prefer': prefer},
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())

def sb_patch(path, params, body, token):
    url = f'{SB_URL}/rest/v1/{path}?' + urllib.parse.urlencode(params)
    payload = json.dumps(body, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(
        url, data=payload,
        headers={**sb_headers(token), 'Prefer': 'return=minimal'},
        method='PATCH',
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.status


# ── Rate limiting ─────────────────────────────────────────────────────────────

def current_month_key():
    now = datetime.now(timezone.utc)
    return f'{now.year}-{now.month:02d}'

def check_and_increment(token, restaurant_id):
    """
    Returns (allowed: bool, current_count: int).
    If allowed, increments the counter as a side effect.
    """
    month = current_month_key()
    rows = sb_get('ai_usage', {
        'restaurant_id': f'eq.{restaurant_id}',
        'month_key':     f'eq.{month}',
        'select':        'query_count',
    }, token)

    if not rows:
        # First query this month — insert row with count=1
        sb_post('ai_usage', {
            'restaurant_id': restaurant_id,
            'month_key':     month,
            'query_count':   1,
        }, token, prefer='return=minimal')
        return True, 1

    count = rows[0].get('query_count', 0)
    if count >= MONTHLY_LIMIT:
        return False, count

    # Increment
    sb_patch('ai_usage', {
        'restaurant_id': f'eq.{restaurant_id}',
        'month_key':     f'eq.{month}',
    }, {'query_count': count + 1}, token)
    return True, count + 1


# ── Context builder ──────────────────────────────────────────────────────────

def build_context(token, restaurant_id):
    invoices   = sb_get('invoices', {
        'restaurant_id': f'eq.{restaurant_id}',
        'select': 'invoice_date,invoice_number,total,subtotal,tax_amount,iva_10_5,iva_21,iva_27,suppliers(name)',
        'order': 'invoice_date.desc', 'limit': '200',
    }, token)
    line_items = sb_get('line_items', {
        'restaurant_id': f'eq.{restaurant_id}',
        'select': 'product_name,quantity,unit,total,categories(name)',
        'limit': '2000',
    }, token)
    sb_get('suppliers', {
        'restaurant_id': f'eq.{restaurant_id}',
        'select': 'name,cuit', 'order': 'name.asc',
    }, token)

    total_all = sum((i.get('total') or 0) for i in invoices)

    sup_totals = {}
    for inv in invoices:
        s = inv.get('suppliers') or {}
        name = s.get('name', '?') if isinstance(s, dict) else '?'
        sup_totals[name] = sup_totals.get(name, 0) + (inv.get('total') or 0)

    cat_totals = {}
    for li in line_items:
        c = li.get('categories') or {}
        cat = c.get('name', 'Sin categoría') if isinstance(c, dict) else 'Sin categoría'
        cat_totals[cat] = cat_totals.get(cat, 0) + (li.get('total') or 0)

    prod = {}
    for li in line_items:
        n = li.get('product_name') or '?'
        if n not in prod:
            prod[n] = {'qty': 0, 'total': 0, 'unit': li.get('unit', '')}
        prod[n]['qty']   += li.get('quantity') or 0
        prod[n]['total'] += li.get('total') or 0

    def fmt(n): return f'${n:,.0f}'

    lines = [
        'RESTAURANTE: Campaso (Buenos Aires, Argentina)',
        f"Período: {invoices[-1]['invoice_date'] if invoices else '?'} — {invoices[0]['invoice_date'] if invoices else '?'}",
        f"Facturas: {len(invoices)}  |  Gasto total: {fmt(total_all)} ARS  |  Promedio/factura: {fmt(total_all/len(invoices)) if invoices else '0'} ARS",
        '', 'PROVEEDORES (por gasto total):',
    ]
    for name, total in sorted(sup_totals.items(), key=lambda x: -x[1]):
        count = sum(1 for i in invoices if (i.get('suppliers') or {}).get('name') == name)
        lines.append(f'  {name}: {fmt(total)} ARS ({count} facturas)')

    lines += ['', 'CATEGORÍAS (todas):']
    for name, total in sorted(cat_totals.items(), key=lambda x: -x[1]):
        lines.append(f'  {name}: {fmt(total)} ARS')

    lines += ['', 'TODOS LOS PRODUCTOS:']
    for name, d in sorted(prod.items(), key=lambda x: -x[1]['total']):
        lines.append(f'  {name}: {d["qty"]:.1f} {d["unit"]}  —  {fmt(d["total"])} ARS')

    lines += ['', 'ÚLTIMAS 10 FACTURAS:']
    for inv in invoices[:10]:
        s = inv.get('suppliers') or {}
        sname = s.get('name', '?') if isinstance(s, dict) else '?'
        lines.append(f'  {inv.get("invoice_date","?")}  |  {sname}  |  {fmt(inv.get("total") or 0)} ARS')

    return '\n'.join(lines)


# ── Claude ───────────────────────────────────────────────────────────────────

def call_claude(question, context):
    api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not api_key:
        return 'Error: ANTHROPIC_API_KEY no configurada en Vercel.'

    payload = json.dumps({
        'model': 'claude-sonnet-4-6',
        'max_tokens': 700,
        'system': (
            'Sos el asistente de IA del Campaso CRM Business Suite, '
            'un sistema de gestión de compras para un restaurante en Buenos Aires, Argentina. '
            'Tu trabajo es ayudar al equipo a entender sus datos: facturas, proveedores, gastos y productos. '
            'Respondés siempre en español rioplatense, de forma clara y directa. '
            'Usás datos reales. Montos en formato: $1.234.567 ARS. '
            'Si no hay datos suficientes para responder algo específico, lo decís claramente.'
        ),
        'messages': [{'role': 'user', 'content': f'DATOS ACTUALES DEL SISTEMA:\n\n{context}\n\n---\n\nPREGUNTA: {question}'}]
    }).encode('utf-8')

    req = urllib.request.Request(
        'https://api.anthropic.com/v1/messages',
        data=payload,
        headers={
            'x-api-key': api_key,
            'anthropic-version': '2023-06-01',
            'content-type': 'application/json',
        }
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())['content'][0]['text']


# ── HTTP handler ──────────────────────────────────────────────────────────────

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
            body   = json.loads(self.rfile.read(length))
            q      = body.get('question', '').strip()
            token  = body.get('token', '')
            rid    = body.get('restaurantId', '')

            if not q or not token or not rid:
                self._respond(400, {'error': 'Faltan campos requeridos.'})
                return

            # ── Rate limit check ──
            allowed, count = check_and_increment(token, rid)
            if not allowed:
                self._respond(429, {
                    'error': f'Límite mensual alcanzado ({MONTHLY_LIMIT} consultas/mes). Se renueva el 1° del próximo mes.'
                })
                return

            context = build_context(token, rid)
            answer  = call_claude(question=q, context=context)
            self._respond(200, {
                'answer': answer,
                'usage': {'count': count, 'limit': MONTHLY_LIMIT, 'remaining': MONTHLY_LIMIT - count},
            })

        except Exception as e:
            self._respond(500, {'error': str(e)})

    def _respond(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', len(body))
        self._cors()
        self.end_headers()
        self.wfile.write(body)
