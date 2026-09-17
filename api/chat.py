"""
api/chat.py  —  Restaurant Platform AI Assistant
Vercel Python serverless function. Shared by every restaurant-platform
client (Campaso, Cofi, ...), scoped per-request by `restaurantId`.

Three things this function does, all via Claude — it never writes to
Supabase itself (all actual DB/Storage writes happen client-side, in the
browser, using the logged-in user's own token and RLS):

  action omitted / 'ask'      — existing behavior: read-only Q&A over live
                                 purchase + sales data (build_context +
                                 build_sales_context → Claude → answer).
  action 'extract'            — Claude vision: extract invoice fields from
                                 an uploaded PDF/image (compra or venta).
  action 'correct'            — Claude: apply a plain-language correction
                                 to a previously extracted JSON.

Rate limit: 200 queries / restaurant / calendar month — shared across all
three actions.

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
        raw = r.read()
        return json.loads(raw) if raw else None

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


# ── Context builder — purchases (compra) ──────────────────────────────────────

def build_context(token, restaurant_id):
    invoices   = sb_get('invoices', {
        'restaurant_id': f'eq.{restaurant_id}',
        'select': 'invoice_date,invoice_number,total,subtotal,tax_amount,iva_10_5,iva_21,iva_27,suppliers(name)',
        'order': 'invoice_date.desc', 'limit': '200',
    }, token)
    line_items = sb_get('line_items', {
        'restaurant_id': f'eq.{restaurant_id}',
        'select': 'product_name,quantity,unit,unit_price,total,suppliers(name),invoices(invoice_date),categories(name)',
        'limit': '2000',
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
        supplier = (li.get('suppliers') or {}).get('name', '')
        inv_date = (li.get('invoices') or {}).get('invoice_date', '')
        unit_price = li.get('unit_price') or 0
        if n not in prod:
            prod[n] = {'qty': 0, 'total': 0, 'unit': li.get('unit', ''),
                       'suppliers': set(), 'latest_date': '', 'latest_unit_price': 0}
        prod[n]['qty']   += li.get('quantity') or 0
        prod[n]['total'] += li.get('total') or 0
        if supplier:
            prod[n]['suppliers'].add(supplier)
        if inv_date > prod[n]['latest_date']:
            prod[n]['latest_date'] = inv_date
            prod[n]['latest_unit_price'] = unit_price

    def fmt(n): return f'${n:,.0f}'

    lines = [
        'COMPRAS (lo que el negocio le compra a sus proveedores):',
        f"Período: {invoices[-1]['invoice_date'] if invoices else '?'} — {invoices[0]['invoice_date'] if invoices else '?'}",
        f"Facturas: {len(invoices)}  |  Gasto total: {fmt(total_all)} ARS  |  Promedio/factura: {fmt(total_all/len(invoices)) if invoices else '0'} ARS",
        '', 'PROVEEDORES (por gasto total):',
    ]
    for name, total in sorted(sup_totals.items(), key=lambda x: -x[1]):
        count = sum(1 for i in invoices if (i.get('suppliers') or {}).get('name') == name)
        lines.append(f'  {name}: {fmt(total)} ARS ({count} facturas)')

    lines += ['', 'CATEGORÍAS DE COMPRA (todas):']
    for name, total in sorted(cat_totals.items(), key=lambda x: -x[1]):
        lines.append(f'  {name}: {fmt(total)} ARS')

    lines += ['', 'TODOS LOS PRODUCTOS COMPRADOS:']
    for name, d in sorted(prod.items(), key=lambda x: -x[1]['total']):
        sup_str = ', '.join(sorted(d['suppliers'])) or 'desconocido'
        price_str = f', último precio: {fmt(d["latest_unit_price"])}/{d["unit"]}' if d['latest_unit_price'] else ''
        lines.append(f'  {name}: {d["qty"]:.1f} {d["unit"]} — {fmt(d["total"])} ARS | proveedor: {sup_str}{price_str}')

    lines += ['', 'ÚLTIMAS 10 FACTURAS DE COMPRA:']
    for inv in invoices[:10]:
        s = inv.get('suppliers') or {}
        sname = s.get('name', '?') if isinstance(s, dict) else '?'
        lines.append(f'  {inv.get("invoice_date","?")}  |  {sname}  |  {fmt(inv.get("total") or 0)} ARS')

    return '\n'.join(lines)


# ── Context builder — sales (venta) ───────────────────────────────────────────

def build_sales_context(token, restaurant_id):
    """
    Symmetric to build_context(), but for what the restaurant SELLS
    (sales_invoices / sales_line_items / sales_clients). Returns '' if the
    client has no sales data at all (keeps the prompt short for
    purchase-only clients like Campaso).
    """
    invoices = sb_get('sales_invoices', {
        'restaurant_id': f'eq.{restaurant_id}',
        'select': 'invoice_date,invoice_number,total,subtotal,tax_amount,sales_clients(name,cuit)',
        'order': 'invoice_date.desc', 'limit': '200',
    }, token)
    if not invoices:
        return ''

    line_items = sb_get('sales_line_items', {
        'restaurant_id': f'eq.{restaurant_id}',
        'select': 'product_name,quantity,unit,unit_price,total,sales_invoices(invoice_date),sales_clients(name)',
        'limit': '2000',
    }, token)

    total_all = sum((i.get('total') or 0) for i in invoices)

    client_stats = {}
    for inv in invoices:
        c = inv.get('sales_clients') or {}
        name = c.get('name', '?') if isinstance(c, dict) else '?'
        st = client_stats.setdefault(name, {'total': 0, 'count': 0, 'first': None, 'last': None})
        st['total'] += inv.get('total') or 0
        st['count'] += 1
        d = inv.get('invoice_date')
        if d:
            if not st['first'] or d < st['first']: st['first'] = d
            if not st['last']  or d > st['last']:  st['last']  = d

    prod = {}
    for li in line_items:
        n = li.get('product_name') or '?'
        client_name = (li.get('sales_clients') or {}).get('name', '')
        if n not in prod:
            prod[n] = {'qty': 0, 'total': 0, 'unit': li.get('unit', '')}
        prod[n]['qty']   += li.get('quantity') or 0
        prod[n]['total'] += li.get('total') or 0

    def fmt(n): return f'${n:,.0f}'

    lines = [
        '', 'VENTAS (lo que el negocio le vende a sus clientes):',
        f"Facturas de venta: {len(invoices)}  |  Ingreso total: {fmt(total_all)} ARS  |  Promedio/factura: {fmt(total_all/len(invoices)) if invoices else '0'} ARS",
        '', 'CLIENTES (por ingreso total, de mayor a menor):',
    ]
    for name, st in sorted(client_stats.items(), key=lambda x: -x[1]['total']):
        avg = st['total'] / st['count'] if st['count'] else 0
        lines.append(f'  {name}: {fmt(st["total"])} ARS ({st["count"]} facturas, promedio {fmt(avg)} ARS) — primera compra {st["first"] or "?"}, última {st["last"] or "?"}')

    lines += ['', 'PRODUCTOS MÁS VENDIDOS:']
    for name, d in sorted(prod.items(), key=lambda x: -x[1]['total']):
        lines.append(f'  {name}: {d["qty"]:.1f} {d["unit"]} — {fmt(d["total"])} ARS')

    lines += ['', 'ÚLTIMAS 10 FACTURAS DE VENTA:']
    for inv in invoices[:10]:
        c = inv.get('sales_clients') or {}
        cname = c.get('name', '?') if isinstance(c, dict) else '?'
        lines.append(f'  {inv.get("invoice_date","?")}  |  {cname}  |  {fmt(inv.get("total") or 0)} ARS')

    return '\n'.join(lines)


# ── Claude — Q&A ───────────────────────────────────────────────────────────────

def call_claude(question, context):
    api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not api_key:
        return 'Error: ANTHROPIC_API_KEY no configurada en Vercel.'

    payload = json.dumps({
        'model': 'claude-sonnet-4-6',
        'max_tokens': 700,
        'system': (
            'Sos el asistente del sistema de gestión de un restaurante en Buenos Aires — '
            'compras a proveedores y, si el negocio también vende, sus ventas a clientes.\n'
            'REGLAS ESTRICTAS:\n'
            '1. Respondés ÚNICAMENTE lo que se preguntó. Nunca agregás datos no pedidos.\n'
            '2. Usás datos exactos del sistema. Nunca suponés, inferís ni estimás.\n'
            '3. Si los datos están disponibles, dás la respuesta concreta y puntual.\n'
            '4. Si no están disponibles, decís exactamente qué dato falta — sin adivinar ni dar alternativas.\n'
            '5. Para preguntas de precio: citás el precio unitario de la última compra o venta registrada.\n'
            '6. Para preguntas de proveedor o cliente: citás el nombre exacto tal como aparece en las facturas.\n'
            '7. Respondés en español rioplatense, de forma corta y directa. Montos: $1.234.567 ARS.\n'
            '8. Nunca usás markdown (nada de **negrita**, guiones de lista, ni #). Texto plano únicamente.'
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


# ── Claude — invoice extraction (compra / venta) ──────────────────────────────

EXTRACT_PROMPT_COMPRA = """You are an invoice data extractor for Argentine restaurant suppliers.
Extract all fields from the invoice image/document and return a single JSON object.

Required fields:
- supplier_name: string — the company that ISSUED this invoice (the seller/proveedor). Look for the issuer's letterhead, logo, or CUIT at the top of the document — NOT the buyer's block.
- invoice_number: string (format: XXXXX-XXXXXXXX, e.g. "00005-00000087")
- invoice_date: string (format DD/MM/YYYY)
- cuit: string (format XX-XXXXXXXX-X) — the supplier's CUIT
- tipo_comprobante: string (e.g. "Factura A", "Factura B", "Factura C")
- condicion_iva: string (e.g. "IVA Responsable Inscripto", "Monotributista")
- subtotal: number (neto gravado, before tax)
- tax_amount: number (total IVA)
- tax_rate: string (e.g. "21%", "10.5%")
- total: number (total amount)
- payment_method: string or null (e.g. "Transferencia Bancaria")
- payment_due_date: string (format DD/MM/YYYY) or null — fecha de vencimiento de pago, if shown
- notes: string or null — brief summary of any other relevant printed info not captured above (CAE number, CAE due date, percepciones, observaciones)
- line_items: array of:
  - description: string
  - quantity: number — the exact number from the CANTIDAD column; never pre-multiply
  - unit: string — the measurement unit of the product content, derived from the product name (e.g. "kg" for "PAN RALLADO 5KG", "lt" for "ACEITE 5LT", "g" for "TOMATE 950G", "un" for items with no explicit size in the name)
  - unit_content: number — content size per ordering unit, extracted from the product name (e.g. 5 for "5KG", 5 for "5LT", 950 for "950G", 1 if no size is specified)
  - unit_price: number — price per ordering unit as shown on the invoice

IMPORTANT for line_items — always extract raw, never convert:
  "PAN RALLADO 5KG PREFERIDO", CANTIDAD=2  → quantity=2, unit="kg", unit_content=5
  "ACEITE DE GIRASOL 5LT ALSAMAR", CANTIDAD=2 → quantity=2, unit="lt", unit_content=5
  "LECHE ENT 1LT TREGAR", CANTIDAD=36     → quantity=36, unit="lt", unit_content=1
  "ARROZ PARBOIL 5KG DOS HERMANOS", CANTIDAD=1 → quantity=1, unit="kg", unit_content=5
  "SAL FINA 5K D. ANCLAS", CANTIDAD=1     → quantity=1, unit="kg", unit_content=5
  "HUEVOS MANO", CANTIDAD=3               → quantity=3, unit="un", unit_content=1
  "KG CAFÉ BRASIL BOURBON ROJO", CANTIDAD=60, U.medida=kg → quantity=60, unit="kg", unit_content=1

Return ONLY the raw JSON object. No markdown, no code fences, no explanation."""

EXTRACT_PROMPT_VENTA = """You are an invoice data extractor for an Argentine business's own sales invoices (facturas de venta).
Extract all fields from the invoice image/document and return a single JSON object.

The business ISSUING this invoice is the restaurant/client itself — do NOT extract its own name. Instead extract the BUYER (the "Apellido y Nombre / Razón Social" / receptor block, not the issuer's letterhead/logo block at the top).

Required fields:
- client_name: string — the buyer's name or razón social (the receptor, not the issuer)
- client_cuit: string (format XX-XXXXXXXX-X) — the buyer's CUIT
- client_domicilio: string or null — the buyer's domicilio comercial
- invoice_number: string (format: XXXXX-XXXXXXXX, e.g. "00005-00000087")
- invoice_date: string (format DD/MM/YYYY)
- tipo_comprobante: string (e.g. "Factura A", "Factura B", "Factura C")
- condicion_iva: string (e.g. "IVA Responsable Inscripto", "Monotributista") — of either party if they match; use the buyer's if they differ
- subtotal: number (neto gravado, before tax)
- tax_amount: number (total IVA)
- tax_rate: string (e.g. "21%", "10.5%")
- total: number (total amount)
- payment_method: string or null (e.g. "Transferencia Bancaria")
- payment_due_date: string (format DD/MM/YYYY) or null
- notes: string or null — brief summary of any other relevant printed info not captured above (CAE number, CAE due date, percepciones, observaciones)
- line_items: array of:
  - description: string
  - quantity: number — the exact number from the CANTIDAD column; never pre-multiply
  - unit: string — the measurement unit of the product content, derived from the product name
  - unit_content: number — content size per ordering unit, extracted from the product name (1 if not specified)
  - unit_price: number — price per ordering unit as shown on the invoice

Return ONLY the raw JSON object. No markdown, no code fences, no explanation."""

CORRECT_PROMPT = """You previously extracted the following JSON from an Argentine invoice:

{extracted_json}

The user reviewed it and sent this correction (in Spanish):

"{correction_text}"

Apply ONLY the requested change(s) to the JSON above. Leave every other field exactly as it was. Return the full corrected JSON object with the same shape as the original. Return ONLY the raw JSON object. No markdown, no code fences, no explanation."""


def _claude_messages(payload_dict):
    api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not api_key:
        raise RuntimeError('ANTHROPIC_API_KEY no configurada en Vercel.')
    payload = json.dumps(payload_dict).encode('utf-8')
    req = urllib.request.Request(
        'https://api.anthropic.com/v1/messages',
        data=payload,
        headers={
            'x-api-key': api_key,
            'anthropic-version': '2023-06-01',
            'content-type': 'application/json',
        }
    )
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.loads(r.read())


def _parse_json_reply(msg):
    raw = msg['content'][0]['text']
    raw = raw.replace('```json', '').replace('```', '').strip()
    return json.loads(raw)


# Same category list Campaso's email pipeline uses (run-emails.js /
# supabase-upload.js CAMPASO_CATEGORIES) — must stay in sync with the
# `categories` global template seed (seed.sql).
CATEGORIES = [
    "Envio Mercaderia","Wi-Fi","Bobina Industrial","Bolsa Arranque 25X30","Bolsa Arranque 45X60",
    "Bolsa Arranque 60X90","Bolsa Residuo Negra","Bolsa Residuo Verde","Desengrasante 5LT",
    "Desodorante Piso 5LT","Detergente 5LT","Esponja","Film","Folex","Guantes Nitrilo Talle M",
    "Jabon en plan blanco","Jabon para mano","Lavandina","Papel Higienico","Repasador Frances",
    "Servilleta","Toalla Intercalada","Trapo de piso","Queso Azul","Bondiola","Cheddar","Crema",
    "Queso Fresco","Jamon cocido","Jamon crudo","Manteca","Muzarella","Pateras","Provoleta",
    "Queso crema","Regianito","Ajo","Albahaca","Berenjena","Capuchina","Cebolla Clasica",
    "Cebolla Blanca","Cebolla Morada","Cherry","Cilantro","Espinaca","Francesa","Huevos",
    "Limón","Lechuga Morada","Morrón Rojo","Morrón Verde","Naranja","Palta","Papas","Peras",
    "Perejil","Portobello","Romero","Rucula","Tomate Perita","Tomillo","Zanahoria",
    "Aceite Alto Oleico Seda bidon","Aceite de Girasol","Aceite de Oliva","Aceituna",
    "Aceto Balsamico","Ají Molido","Ajinomoto","Ajo En Polvo","Alcaparras","Almendras",
    "Anchoa","Arroz","Azúcar","Batata","Cacao","Cebolla deshidratada","Choclo",
    "Chocolate semiamargo","Chocolinas","Dulce De Leche","Dulce De Batata","Espinaca Congelada",
    "Crema De Esencia De Vainilla","Fideos","Fritolin","Frutos Rojos","Garbanzos","Harina Leudante",
    "Harina 0000","Ketchup","Ketchup 8g","Leche","Maicena","Maní","Mayonesa","Mayonesa 8g",
    "Membrillo","Morron Lata","Mostaza","Mostaza 8g","Nueces","Nues moscada","Orégano",
    "Pan rallado","Pimentón","Pimienta en grano","Pimienta negra","Puré de tomate","Sal fina",
    "Sal gruesa","Salsa de tomate cubeteado","Tabasco","Tapa de empanada 13.5 cm",
    "Tapa de empanada 12.5 cm","Tomate Deshidratado","Tomate Triturado","Vinagre","Vino Blanco",
    "Vino Tinto","Asado Banderita","Bife de chorizo","Chorizo","Entraña","Hamburguesas","Lomo",
    "Nalga Feteada","Milanesas de berenjena","Mollejas","Morcillas","Ojo de bife","Pata y Muslo",
    "Pechuga","Suprema","Picada Roast Beef","Salchicha Parrillera","Cerveza","Agua","Coca cola",
    "Licores","Jugo De Naranja",
]

def _title_case(s):
    return ' '.join(w[:1].upper() + w[1:].lower() if w else w for w in str(s or '').split(' '))

def classify_line_item_categories(line_items):
    """Mirrors run-emails.js's classifyProductCategories — same category
    list, same prompt shape, Haiku model. Returns { productName: {category, confidence} }."""
    if not line_items:
        return {}
    products = [_title_case(li.get('description') or li.get('name') or '') for li in line_items]
    prompt = (
        "You are a product classifier for an Argentine restaurant supply system.\n"
        "For each product below, return the best matching category from the allowed list, along with your confidence.\n"
        "Confidence levels: 'certain', 'high', 'medium', 'low', 'none'\n"
        "IMPORTANT: category names must be spelled EXACTLY as they appear in the allowed list.\n"
        "IMPORTANT: When a product name contains '8g', '8G', '8gr', or similar (single-serving sachets), prefer the '8g' variant category (e.g. 'Mayonesa 8g', 'Ketchup 8g', 'Mostaza 8g') over the generic one.\n"
        "Return ONLY a valid JSON object: { \"Product Name\": { \"category\": \"...\", \"confidence\": \"...\" } }\n"
        "No explanation, no markdown, no code fences — only the raw JSON object.\n\n"
        "Allowed categories:\n" + '\n'.join(f'- {c}' for c in CATEGORIES) +
        "\n\nProducts to classify:\n" + '\n'.join(f'- {p}' for p in products)
    )
    msg = _claude_messages({
        'model': 'claude-haiku-4-5-20251001',
        'max_tokens': 800,
        'messages': [{'role': 'user', 'content': prompt}],
    })
    return _parse_json_reply(msg)


def call_claude_extract(file_b64, mime_type, tipo):
    prompt = EXTRACT_PROMPT_COMPRA if tipo == 'compra' else EXTRACT_PROMPT_VENTA
    content_type = 'document' if mime_type == 'application/pdf' else 'image'
    msg = _claude_messages({
        'model': 'claude-sonnet-4-6',
        'max_tokens': 1500,
        'messages': [{
            'role': 'user',
            'content': [
                {'type': content_type, 'source': {'type': 'base64', 'media_type': mime_type, 'data': file_b64}},
                {'type': 'text', 'text': prompt},
            ],
        }],
    })
    extracted = _parse_json_reply(msg)

    # Compra only — classify each line item into Campaso's category list,
    # same as the email pipeline does before a tarea ever reaches approval.
    if tipo == 'compra' and extracted.get('line_items'):
        try:
            classified = classify_line_item_categories(extracted['line_items'])
            for li in extracted['line_items']:
                name = _title_case(li.get('description') or li.get('name') or '')
                match = classified.get(name) or {}
                li['category_name'] = match.get('category')
                li['classification_confidence'] = match.get('confidence', 'none')
        except Exception:
            # Non-blocking — extraction still succeeds without categories.
            pass

    return extracted


def call_claude_correct(extracted, correction_text, tipo):
    prompt = CORRECT_PROMPT.format(
        extracted_json=json.dumps(extracted, ensure_ascii=False, indent=2),
        correction_text=correction_text,
    )
    msg = _claude_messages({
        'model': 'claude-sonnet-4-6',
        'max_tokens': 1500,
        'messages': [{'role': 'user', 'content': prompt}],
    })
    return _parse_json_reply(msg)


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
            action = body.get('action', 'ask')
            token  = body.get('token', '')
            rid    = body.get('restaurantId', '')

            if not token or not rid:
                self._respond(400, {'error': 'Faltan campos requeridos.'})
                return

            allowed, count = check_and_increment(token, rid)
            if not allowed:
                self._respond(429, {
                    'error': f'Límite mensual alcanzado ({MONTHLY_LIMIT} consultas/mes). Se renueva el 1° del próximo mes.'
                })
                return
            usage = {'count': count, 'limit': MONTHLY_LIMIT, 'remaining': MONTHLY_LIMIT - count}

            if action == 'extract':
                file_b64  = body.get('fileBase64', '')
                mime_type = body.get('mimeType', 'application/pdf')
                tipo      = body.get('tipo', 'compra')
                if not file_b64 or tipo not in ('compra', 'venta'):
                    self._respond(400, {'error': 'Faltan campos requeridos para extraer (fileBase64, tipo).'})
                    return
                extracted = call_claude_extract(file_b64, mime_type, tipo)
                self._respond(200, {'extracted': extracted, 'usage': usage})
                return

            if action == 'correct':
                extracted       = body.get('extracted')
                correction_text = body.get('correctionText', '').strip()
                tipo            = body.get('tipo', 'compra')
                if not extracted or not correction_text:
                    self._respond(400, {'error': 'Faltan campos requeridos para corregir (extracted, correctionText).'})
                    return
                corrected = call_claude_correct(extracted, correction_text, tipo)
                self._respond(200, {'extracted': corrected, 'usage': usage})
                return

            # default: text Q&A
            q = body.get('question', '').strip()
            if not q:
                self._respond(400, {'error': 'Faltan campos requeridos.'})
                return
            context = build_context(token, rid) + build_sales_context(token, rid)
            answer  = call_claude(question=q, context=context)
            self._respond(200, {'answer': answer, 'usage': usage})

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
