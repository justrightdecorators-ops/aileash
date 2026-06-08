from wsgiref.simple_server import make_server
from pyramid.config import Configurator
from pyramid.view import view_config
from pyramid.response import Response

# ====================================================================
# MINT CONFIGURATION - REPLACE WITH YOUR GOOGLE TOKENS
# ====================================================================
GOOGLE_VERIFY_FILE = "google1234567890abcdef"  # Put your exact token name here (leave off .html)
GOOGLE_VERIFY_BODY = "google-site-verification: google1234567890abcdef.html"

# ====================================================================
# 1. LIVE HOMEPAGE VIEW (What Google reads and shows in search results)
# ====================================================================
@view_config(route_name='home', request_method='GET')
def home_view(request):
    html_payload = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AILeash | Live Governance Engine | AI Governance Infrastructure</title>
    <meta name="description" content="Real-time AI action scoring, SHA-256 tamper-evident audit chains, and EU AI Act compliant enforcement. Built for regulated enterprises, financial systems, and autonomous AI agents.">
    <meta name="keywords" content="AI Governance, EU AI Act, SHA-256 Chain, 9-Signal Engine, AILeash, Real-Time Risk Engine">
</head>
<body style="font-family:sans-serif; background:#0f172a; color:#f8fafc; padding:40px; text-align:center;">
    <h1 style="color:#38bdf8;">AILEASH - Live Governance Engine</h1>
    <p>Real-time AI action scoring, SHA-256 tamper-evident audit chains, and EU AI Act compliant enforcement.</p>
    <div style="margin-top:20px; color:#64748b;">Domain Production Node: https://sebbi.pro</div>
</body>
</html>"""
    return Response(html_payload, content_type='text/html')

# ====================================================================
# 2. GOOGLE VERIFICATION VIEW (Proves to Google that you own sebbi.pro)
# ====================================================================
@view_config(route_name='google_verify', request_method='GET')
def google_verify_view(request):
    return Response(GOOGLE_VERIFY_BODY, content_type='text/html')

# ====================================================================
# 3. XML SITEMAP VIEW (Tells Google's master spider exactly what to index)
# ====================================================================
@view_config(route_name='sitemap', request_method='GET')
def sitemap_view(request):
    sitemap_xml = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://sitemaps.org">
    <url>
        <loc>https://sebbi.pro</loc>
        <lastmod>2026-06-08</lastmod>
        <changefreq>daily</changefreq>
        <priority>1.0</priority>
    </url>
</urlset>"""
    return Response(sitemap_xml, content_type='application/xml')

# ====================================================================
# ONE-STOP APPLICATION PYRAMID RUNNER
# ====================================================================
if __name__ == '__main__':
    config = Configurator()
    
    # Strictly map your routes
    config.add_route('home', '/')
    config.add_route('sitemap', '/sitemap.xml')
    config.add_route('google_verify', f'/{GOOGLE_VERIFY_FILE}.html')
    
    config.scan()
    app = config.make_wsgi_app()
    
    print("\n" + "═"*60)
    print(" 🚀 SEBBI.PRO MINT ALL-IN-ONE PYRAMID INSTANCE IS LIVE")
    print(f" 👉 Domain Target:   https://sebbi.pro")
    print(f" 👉 Verification:    /{GOOGLE_VERIFY_FILE}.html")
    print(f" 👉 Sitemap:         /sitemap.xml")
    print(" ═"*60 + "\n")
    
    # Run the server on standard production proxy routing port
    server = make_server('0.0.0.0', 8080, app)
    server.serve_forever()
