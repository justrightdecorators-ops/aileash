import os
import http.server
import socketserver

# Railway dynamically assigns a port via environment variables
PORT = int(os.environ.get("PORT", 8080))

HTML_CONTENT = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AILeash | Zero-Latency AI Action Firewall</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background-color: #0b0f19;
            color: #f3f4f6;
            line-height: 1.6;
            margin: 0;
            padding: 40px 20px;
        }
        .container {
            max-width: 800px;
            margin: 0 auto;
        }
        span.badge {
            background-color: #1e293b;
            color: #38bdf8;
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 0.85rem;
            font-weight: 600;
            text-transform: uppercase;
            border: 1px solid #38bdf8;
        }
        h1 {
            font-size: 2.5rem;
            margin-top: 20px;
            color: #ffffff;
        }
        p.lead {
            font-size: 1.25rem;
            color: #9ca3af;
        }
        .grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin: 40px 0;
        }
        .card {
            background-color: #111827;
            padding: 24px;
            border-radius: 12px;
            border: 1px solid #1f2937;
        }
        .card h3 {
            margin-top: 0;
            color: #38bdf8;
        }
        .cta-box {
            background: linear-gradient(135deg, #1e1b4b 0%, #311042 100%);
            padding: 30px;
            border-radius: 12px;
            text-align: center;
            border: 1px solid #4c1d95;
            margin-top: 40px;
        }
        .btn {
            display: inline-block;
            background-color: #38bdf8;
            color: #0b0f19;
            text-decoration: none;
            padding: 12px 24px;
            border-radius: 6px;
            font-weight: bold;
            margin-top: 15px;
        }
    </style>
</head>
<body>
    <div class="container">
        <span class="badge">Live Infrastructure</span>
        <h1>AILeash Governance Layer</h1>
        <p class="lead">The market's first deterministic, zero-latency execution gateway for autonomous AI agents.</p>
        
        <div class="grid">
            <div class="card">
                <h3>⚡ 0ms Extra Latency</h3>
                <p>Evaluates and scores 9 concurrent risk signals instantly. Enforces boundaries before actions execute without slowing performance.</p>
            </div>
            <div class="card">
                <h3>🔒 Cryptographically Traceable</h3>
                <p>Secured via SHA-256 cryptographic chaining. Generates forensic-grade, tamper-evident logs for corporate compliance audits.</p>
            </div>
        </div>

        <div class="cta-box">
            <h2>Experience the Engine</h2>
            <p>Every account receives exactly 100 free verification requests to test the live payload mechanics under production load.</p>
            <a href="/api/govern" class="btn">View API Endpoint</a>
        </div>
    </div>
</body>
</html>
"""

class SafeLanderHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(HTML_CONTENT.encode('utf-8'))

if __name__ == "__main__":
    with socketserver.TCPServer(("0.0.0.0", PORT), SafeLanderHandler) as httpd:
        print(f"🚀 Independent marketing lander running on port {PORT}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down lander safely.")
