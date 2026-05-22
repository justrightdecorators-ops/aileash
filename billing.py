import urllib.request
import urllib.parse
import json
from config import STRIPE_SECRET, BASE_URL


def create_checkout(email, api_key):
    if not STRIPE_SECRET or not STRIPE_SECRET.startswith("sk_"):
        return None

    params = urllib.parse.urlencode({
        "success_url": BASE_URL + "/success?key=" + api_key,
        "cancel_url": BASE_URL,
        "mode": "subscription",
        "line_items[0][price_data][currency]": "usd",
        "line_items[0][price_data][product_data][name]": "AILeash Pro",
        "line_items[0][price_data][product_data][description]": "AI Action Firewall. EU AI Act compliant. Unlimited requests.",
        "line_items[0][price_data][recurring][interval]": "month",
        "line_items[0][price_data][unit_amount]": "9900",
        "line_items[0][quantity]": "1",
        "customer_email": email,
        "metadata[api_key]": api_key,
    }).encode()

    req = urllib.request.Request(
        "https://api.stripe.com/v1/checkout/sessions",
        data=params,
        headers={
            "Authorization": "Bearer " + STRIPE_SECRET,
            "Content-Type": "application/x-www-form-urlencoded"
        }
    )
    resp = urllib.request.urlopen(req, timeout=10)
    session = json.loads(resp.read())
    return session["url"]
