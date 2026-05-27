from flask import Flask, render_template, jsonify
import os
import stripe
from threading import Lock

app = Flask(__name__)

# Config
STRIPE_SECRET = os.environ.get("STRIPE_SECRET_KEY")
STRIPE_PRICE_ID = None
_db_lock = Lock()

def setup_stripe():
    global STRIPE_PRICE_ID
    if not STRIPE_SECRET:
        print("  WARNING: No STRIPE_SECRET env var set.")
        return
    env_price = os.environ.get("STRIPE_PRICE_ID", "")
    if env_price:
        STRIPE_PRICE_ID = env_price
        print(f"  Stripe ready: {STRIPE_PRICE_ID}")
        return
    with _db_lock:
        row = _conn.execute("SELECT v FROM config WHERE k='stripe_price_id'").fetchone()
    if row:
        STRIPE_PRICE_ID = row[0]
        print(f"  Stripe ready: {STRIPE_PRICE_ID}")
        return
    print("  Stripe price not configured. Add STRIPE_PRICE_ID env var.")

setup_stripe()

@app.route('/')
def landing():
    return render_template('index.html')

@app.route('/create-checkout-session', methods=['POST'])
def create_checkout_session():
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price': STRIPE_PRICE_ID,
                'quantity': 1,
            }],
            mode='payment',
            success_url='https://yourdomain.com/success',
            cancel_url='https://yourdomain.com/',
        )
        return jsonify({'url': session.url})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
