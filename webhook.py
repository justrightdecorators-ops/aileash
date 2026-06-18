import os
import hmac
import hashlib
import time
import json
import threading
import urllib.request
from flask import Flask, request, jsonify
import server

app = Flask(__name__)

# Read webhook signing secret (optional). If not present we will verify events
# by fetching the event from Stripe using STRIPE_SECRET (which you already have).
STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET','')
STRIPE_SECRET = os.environ.get('STRIPE_SECRET','')
# Tolerance in seconds for timestamp
SIG_TOLERANCE = int(os.environ.get('STRIPE_SIG_TOLERANCE', 300))


def verify_by_signature(payload, sig_header):
    if not STRIPE_WEBHOOK_SECRET:
        return False
    if not sig_header:
        return False
    try:
        items = dict(x.split('=',1) for x in sig_header.split(',') if '=' in x)
        t = int(items.get('t', '0'))
        v1 = items.get('v1','')
        if not v1:
            return False
        if abs(time.time() - t) > SIG_TOLERANCE:
            print(f"Stripe signature timestamp outside tolerance: {t}", flush=True)
            return False
        signed_payload = f"{t}.".encode() + payload
        expected = hmac.new(STRIPE_WEBHOOK_SECRET.encode(), signed_payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, v1):
            print("Stripe signature mismatch", flush=True)
            return False
        return True
    except Exception as e:
        print(f"Error verifying signature: {e}", flush=True)
        return False


def verify_by_fetch(event_id, raw_event):
    """Fetch event from Stripe API using STRIPE_SECRET and compare IDs to validate authenticity.
    This avoids needing a separate webhook signing secret and uses the existing STRIPE_SECRET you already have set in Railway."""
    if not STRIPE_SECRET:
        print("No STRIPE_SECRET available to verify webhook by fetching event", flush=True)
        return False
    try:
        url = f"https://api.stripe.com/v1/events/{urllib.request.quote(event_id, safe='') }"
        req = urllib.request.Request(url, headers={
            'Authorization': f'Bearer {STRIPE_SECRET}',
            'Content-Type': 'application/x-www-form-urlencoded'
        })
        with urllib.request.urlopen(req, timeout=10) as r:
            body = r.read()
            ev = json.loads(body)
            # Basic sanity checks: id and type must match
            if ev.get('id') != event_id:
                print(f"Fetched event id mismatch: {ev.get('id')} != {event_id}", flush=True)
                return False
            # Optionally compare payload type
            if raw_event.get('type') and ev.get('type') and raw_event.get('type') != ev.get('type'):
                print(f"Fetched event type mismatch: {raw_event.get('type')} != {ev.get('type')}", flush=True)
                return False
            return True
    except Exception as e:
        print(f"Error fetching event from Stripe for verification: {e}", flush=True)
        return False


def verify_event(payload_bytes, sig_header):
    # Try signature first if webhook secret is set
    if STRIPE_WEBHOOK_SECRET:
        return verify_by_signature(payload_bytes, sig_header)
    # Otherwise, fallback to fetching event using STRIPE_SECRET
    try:
        raw = json.loads(payload_bytes)
        event_id = raw.get('id')
        if not event_id:
            print('No event id in payload to verify', flush=True)
            return False
        return verify_by_fetch(event_id, raw)
    except Exception as e:
        print(f"Failed to parse JSON payload for verification: {e}", flush=True)
        return False


def _mark_account_paid_by_email(email, customer_id=None, subscription_id=None, product='aileash'):
    if not email:
        return None
    key = None
    with server._db_lock:
        row = server._conn.execute("SELECT key,devices FROM api_keys WHERE email=?", (email,)).fetchone()
        if row:
            key = row[0]
            devices = row[1] if row[1] else 1
            try:
                server._conn.execute("UPDATE api_keys SET is_paid=1, active=1, stripe_customer=?, stripe_sub=? WHERE email=?", (customer_id, subscription_id, email))
            except Exception:
                server._conn.execute("UPDATE api_keys SET is_paid=1, active=1, stripe_customer=%s, stripe_sub=%s WHERE email=%s", (customer_id, subscription_id, email))
            server._conn.commit()
        else:
            # Create a new api key for this email using existing helper
            key, err = server.create_api_key(email)
            if not key:
                print(f"Failed to create api_key for {email}: {err}", flush=True)
                return None
            devices = 1
            with server._db_lock:
                try:
                    server._conn.execute("UPDATE api_keys SET is_paid=1, active=1, stripe_customer=?, stripe_sub=? WHERE email=?", (customer_id, subscription_id, email))
                except Exception:
                    server._conn.execute("UPDATE api_keys SET is_paid=1, active=1, stripe_customer=%s, stripe_sub=%s WHERE email=%s", (customer_id, subscription_id, email))
                server._conn.commit()
    # Send welcome email asynchronously using your existing template
    monthly = round((devices or 1) * 0.50, 2)
    name = ''
    try:
        threading.Thread(target=server.send_welcome_email, args=(name, email, product, key, devices, monthly), daemon=True).start()
    except Exception as e:
        print(f"Error starting welcome email thread: {e}", flush=True)
    return key


@app.route('/webhook/stripe', methods=['POST'])
def stripe_webhook():
    payload = request.get_data()
    sig_header = request.headers.get('Stripe-Signature', '')

    if not verify_event(payload, sig_header):
        # If verification fails, reject the webhook
        return jsonify({'error':'invalid_signature_or_verification_failed'}), 400

    try:
        event = json.loads(payload)
    except Exception as e:
        print(f"Invalid JSON in webhook: {e}", flush=True)
        return jsonify({'error':'invalid_json'}), 400

    etype = event.get('type','')
    obj = event.get('data',{}).get('object',{})

    try:
        if etype == 'checkout.session.completed':
            email = obj.get('customer_email') or (obj.get('customer_details') or {}).get('email')
            customer_id = obj.get('customer')
            subscription_id = obj.get('subscription')
            metadata = obj.get('metadata') or {}
            product = metadata.get('product','aileash')
            devices = int(metadata.get('devices',1)) if metadata.get('devices') else 1
            key = _mark_account_paid_by_email(email, customer_id, subscription_id, product)
            print(f"Stripe checkout completed: email={email} key={key}", flush=True)
        elif etype == 'invoice.payment_succeeded':
            customer_id = obj.get('customer')
            if customer_id:
                with server._db_lock:
                    try:
                        server._conn.execute("UPDATE api_keys SET is_paid=1, active=1 WHERE stripe_customer=?", (customer_id,))
                    except Exception:
                        server._conn.execute("UPDATE api_keys SET is_paid=1, active=1 WHERE stripe_customer=%s", (customer_id,))
                    server._conn.commit()
                print(f"Invoice payment succeeded for customer {customer_id}", flush=True)
        elif etype == 'invoice.payment_failed':
            customer_id = obj.get('customer')
            if customer_id:
                with server._db_lock:
                    try:
                        server._conn.execute("UPDATE api_keys SET active=0 WHERE stripe_customer=?", (customer_id,))
                    except Exception:
                        server._conn.execute("UPDATE api_keys SET active=0 WHERE stripe_customer=%s", (customer_id,))
                    server._conn.commit()
                print(f"Invoice payment failed for customer {customer_id}", flush=True)
        elif etype in ('customer.subscription.deleted','customer.subscription.updated'):
            sub = obj
            customer_id = sub.get('customer')
            status = sub.get('status')
            if customer_id and status != 'active':
                with server._db_lock:
                    try:
                        server._conn.execute("UPDATE api_keys SET active=0 WHERE stripe_customer=?", (customer_id,))
                    except Exception:
                        server._conn.execute("UPDATE api_keys SET active=0 WHERE stripe_customer=%s", (customer_id,))
                    server._conn.commit()
                print(f"Subscription {etype} for customer {customer_id} status={status}", flush=True)
        else:
            print(f"Unhandled Stripe event type: {etype}", flush=True)
    except Exception as e:
        print(f"Error handling stripe webhook: {e}", flush=True)
        return jsonify({'error':'handler_error'}), 500

    return jsonify({'received': True}), 200


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8081))
    print(f"Starting Stripe webhook listener on port {port}", flush=True)
    app.run(host='0.0.0.0', port=port)
