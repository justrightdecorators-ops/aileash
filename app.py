from flask import Flask, request, jsonify, Response
import os
import server
from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST
import urllib.request, urllib.parse

app = Flask(__name__)

REQUESTS = Counter('aileash_requests_total', 'Total requests', ['endpoint','method','status'])

# Helper adapter so we can reuse server.get_api_key which expects an object with .headers
class H:
    def __init__(self, headers):
        self.headers = headers

# Common request pre-checks
def pre_request(path):
    server.track_request()
    # If overloaded, mirror original behaviour: allow /api/govern and /govern
    if server.is_overloaded() and path not in ('/api/govern','/govern'):
        return jsonify({"error":"server_busy","message":"High load. Try again shortly.","rps":server.get_rps()}), 503
    return None

@app.route('/', methods=['GET'])
def landing():
    server.track_request()
    return Response(server.LANDING, mimetype='text/html')

@app.route('/scan', methods=['GET'])
def scan():
    server.track_request()
    return Response(server.SCAN_PAGE, mimetype='text/html')

@app.route('/contact', methods=['GET'])
def contact_page():
    server.track_request()
    return Response(server.CONTACT_PAGE, mimetype='text/html')

@app.route('/api/health', methods=['GET'])
def health():
    server.track_request()
    return jsonify({"status":"ok","version":server.VERSION,"rps":server.get_rps(),"throttle":server.is_overloaded()})

@app.route('/api/verify-chain', methods=['GET'])
def verify_chain():
    server.track_request()
    return jsonify(server.verify_chain())

@app.route('/api/stats', methods=['GET'])
def stats():
    server.track_request()
    with server._db_lock:
        keys = server._conn.execute("SELECT COUNT(*) FROM api_keys").fetchone()[0]
        audits = server._conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
        loads = server._conn.execute("SELECT COUNT(*) FROM load_log").fetchone()[0]
        contacts = server._conn.execute("SELECT COUNT(*) FROM contact_log").fetchone()[0]
    return jsonify({"api_keys":keys,"audit_blocks":audits,"load_events":loads,"contacts":contacts,"rps":server.get_rps(),"throttle":server.is_overloaded(),"version":server.VERSION})

@app.route('/robots.txt', methods=['GET'])
def robots():
    server.track_request()
    host = os.environ.get('HOST', 'http://localhost:8080').rstrip('/')
    sitemap_url = f"{host}/sitemap.xml"
    lines = ["User-agent: *", "Allow: /", f"Sitemap: {sitemap_url}"]
    return Response("\n".join(lines)+"\n", mimetype='text/plain')

@app.route('/openapi.json', methods=['GET'])
def openapi():
    server.track_request()
    return jsonify({"openapi":"3.0.0","info":{"title":"AILeash Platform","version":server.VERSION},"servers":[{"url":os.environ.get('HOST', 'https://sebbi.pro')} ]})

@app.route('/metrics', methods=['GET'])
def metrics():
    # Expose basic Prometheus metrics
    server.track_request()
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

# Sitemap generation
@app.route('/sitemap.xml', methods=['GET'])
def sitemap():
    server.track_request()
    host = os.environ.get('HOST', 'http://localhost:8080').rstrip('/')
    pages = ['/', '/scan', '/contact', '/signup', '/api/verify-chain']
    now_iso = __import__('datetime').datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    urls = []
    for p in pages:
        urls.append(f"  <url>\n    <loc>{host}{p}</loc>\n    <lastmod>{now_iso}</lastmod>\n    <changefreq>monthly</changefreq>\n  </url>")
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    xml += "\n".join(urls)
    xml += '\n</urlset>'
    return Response(xml, mimetype='application/xml')

# Decision endpoint
@app.route('/api/govern', methods=['POST'])
def api_govern():
    pre = pre_request('/api/govern')
    if pre: return pre
    data = request.get_json(silent=True) or {}
    api_key = server.get_api_key(H(request.headers))
    try:
        result, status = server.govern(data, api_key if api_key else None)
        REQUESTS.labels(endpoint='/api/govern', method='POST', status=str(status)).inc()
        return jsonify(result), status
    except ValueError as e:
        REQUESTS.labels(endpoint='/api/govern', method='POST', status='400').inc()
        return jsonify({"error":str(e)}), 400
    except Exception as e:
        REQUESTS.labels(endpoint='/api/govern', method='POST', status='500').inc()
        return jsonify({"error":"internal_error","detail":str(e)}), 500

# Signup / API key creation
@app.route('/signup', methods=['POST'])
@app.route('/api/keys', methods=['POST'])
def signup():
    pre = pre_request('/signup')
    if pre: return pre
    data = request.get_json(silent=True) or {}
    email = str(data.get('email','')).strip().lower()
    phone = str(data.get('phone','')).strip()
    name = str(data.get('name','')).strip()
    org = str(data.get('org','')).strip()
    org_type = str(data.get('org_type','')).strip()
    product = str(data.get('product','aileash')).strip().lower()
    try:
        devices = int(data.get('devices',1))
    except: devices = 1
    if product not in ('aileash','guardian'): product='aileash'
    if devices<1: devices=1
    key, err = server.create_api_key(email, phone, name, org, org_type, product, devices)
    if err:
        msgs={"invalid_email":"Please enter a valid email address.","email_exists":"A key already exists for this email. Contact justin@monopcontent.com to retrieve it."}
        return jsonify({"error":msgs.get(err,err)}), 400
    monthly = round(devices*0.50,2)
    # send welcome email asynchronously as original server did
    threading = __import__('threading')
    threading.Thread(target=server.send_welcome_email, args=(name,email,product,key,devices,monthly), daemon=True).start()
    return jsonify({"api_key":key,"email":email,"product":product,"devices":devices,"monthly":monthly,"plan":"free","quota":server.FREE_QUOTA,"endpoint":f"{os.environ.get('HOST',server.HOST)}/api/govern","message":f"100 free decisions created. Check your inbox for details."})

# Contact form
@app.route('/contact', methods=['POST'])
def contact():
    pre = pre_request('/contact')
    if pre: return pre
    data = request.get_json(silent=True) or {}
    name = str(data.get('name','')).strip()
    email = str(data.get('email','')).strip().lower()
    phone = str(data.get('phone','')).strip()
    org = str(data.get('org','')).strip()
    msg = str(data.get('message','')).strip()
    if not email or '@' not in email:
        return jsonify({"error":"invalid_email"}), 400
    if not msg:
        return jsonify({"error":"no_message"}), 400
    with server._db_lock:
        server._conn.execute("INSERT INTO contact_log(ts,name,email,phone,org,message) VALUES(?,?,?,?,?,?)", (server.time.time() if hasattr(server,'time') else __import__('time').time(), name, email, phone, org, msg))
        server._conn.commit()
    threading = __import__('threading')
    threading.Thread(target=server.send_contact_notification, args=(name,email,phone,org,msg), daemon=True).start()
    return jsonify({"ok":True})

# Create checkout (Stripe)
@app.route('/create-checkout', methods=['POST'])
def create_checkout():
    pre = pre_request('/create-checkout')
    if pre: return pre
    data = request.get_json(silent=True) or {}
    email = str(data.get('email','')).strip().lower()
    product = str(data.get('product','aileash')).strip().lower()
    try:
        devices = int(data.get('devices',1))
    except: devices = 1
    if devices<1: devices=1
    if not email or '@' not in email:
        return jsonify({"error":"invalid_email"}), 400
    if not server.STRIPE_SECRET:
        return jsonify({"error":"stripe_not_configured"}), 503
    price_id = server.STRIPE_PRICE_ID_GUARDIAN if product=='guardian' else server.STRIPE_PRICE_ID_AILEASH
    if not price_id:
        server.setup_stripe()
        price_id = server.STRIPE_PRICE_ID_GUARDIAN if product=='guardian' else server.STRIPE_PRICE_ID_AILEASH
    if not price_id:
        return jsonify({"error":"stripe_setup_failed"}), 503
    session = server.stripe_call('POST', '/checkout/sessions', {
        'mode':'subscription', 'customer_email':email,
        'success_url':f"{os.environ.get('HOST',server.HOST)}/?success=true", 'cancel_url':f"{os.environ.get('HOST',server.HOST)}/?cancel=true",
        'line_items[0][price]':price_id, 'line_items[0][quantity]':str(devices)
    })
    if not session or 'url' not in session:
        return jsonify({"error":"checkout_failed","detail":str(session)}), 500
    return jsonify({"checkout_url":session['url']})

# Test email endpoint (protected by TEST_EMAIL_TOKEN if set)
@app.route('/_test_email', methods=['POST'])
def test_email():
    token = os.environ.get('TEST_EMAIL_TOKEN','')
    provided = request.headers.get('X-Test-Token','') or request.args.get('token','')
    if token and provided != token:
        return jsonify({'error':'unauthorized'}), 401
    data = request.get_json(silent=True) or {}
    to_email = data.get('email', server.OWNER_EMAIL)
    to_name  = data.get('name', server.OWNER_NAME)
    subject  = data.get('subject', 'AILeash Test Email')
    html     = data.get('html', '<p>This is a test email from AILeash.</p>')
    try:
        ok = server.send_email(to_email, to_name, subject, html)
        return jsonify({'ok': bool(ok)}), (200 if ok else 500)
    except Exception as e:
        return jsonify({'ok':False,'error':str(e)}), 500

# Submit sitemap to search engines (protected by ADMIN_TOKEN if set)
@app.route('/_submit_sitemap', methods=['POST'])
def submit_sitemap():
    token = os.environ.get('ADMIN_TOKEN','')
    provided = request.headers.get('X-Admin-Token','') or request.args.get('token','')
    if token and provided != token:
        return jsonify({'error':'unauthorized'}), 401
    host = os.environ.get('HOST', 'http://localhost:8080').rstrip('/')
    sitemap_url = f"{host}/sitemap.xml"
    results = {}
    # Ping Google
    try:
        google_url = f"http://www.google.com/ping?sitemap={urllib.parse.quote(sitemap_url, safe='') }"
        with urllib.request.urlopen(google_url, timeout=10) as r:
            results['google'] = {'code': r.getcode(), 'reason': r.reason if hasattr(r, 'reason') else ''}
    except Exception as e:
        results['google'] = {'error': str(e)}
    # Ping Bing
    try:
        bing_url = f"https://www.bing.com/ping?sitemap={urllib.parse.quote(sitemap_url, safe='') }"
        with urllib.request.urlopen(bing_url, timeout=10) as r:
            results['bing'] = {'code': r.getcode(), 'reason': r.reason if hasattr(r, 'reason') else ''}
    except Exception as e:
        results['bing'] = {'error': str(e)}
    return jsonify({'sitemap': sitemap_url, 'results': results})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    # Development server if run directly
    app.run(host='0.0.0.0', port=port, debug=False)
