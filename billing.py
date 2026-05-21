import json
import urllib.request
import urllib.parse
from fastapi import APIRouter, HTTPException, Request
import aiosqlite
from config import DB_PATH, STRIPE_SECRET, BASE_URL, PRODUCT
import auth

router = APIRouter(tags=["Billing"])

@router.get("/checkout")
async def checkout(key: str):
    record = await auth.get_key_record(key)
    if not STRIPE_SECRET:
        raise HTTPException(status_code=500, detail="Stripe configuration handle absent")
        
    params = urllib.parse.urlencode({
        "success_url": BASE_URL + "/success?key=" + key,
        "cancel_url": BASE_URL,
        "mode": "subscription",
        "line_items[0][price_data][currency]": "usd",
        "line_items[0][price_data][product_data][name]": f"{PRODUCT} Pro Suite",
        "line_items[0][price_data][product_data][description]": "Inline Agent Protection Layer",
        "line_items[0][price_data][recurring][interval]": "month",
        "line_items[0][price_data][unit_amount]": "9900",
        "line_items[0][quantity]": "1",
        "customer_email": record["email"],
        "metadata[api_key]": key,
    }).encode()

    req = urllib.request.Request(
        "https://api.stripe.com/v1/checkout/sessions",
        data=params,
        headers={"Authorization": f"Bearer {STRIPE_SECRET}", "Content-Type": "application/x-www-form-urlencoded"}
    )
    
    try:
        res = urllib.request.urlopen(req, timeout=10)
        url = json.loads(res.read())["url"]
        return {"checkout_url": url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Stripe configuration error: {str(e)}")

@router.post("/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    try:
        event = json.loads(payload)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON format")
        
    if event.get("type") == "checkout.session.completed":
        session = event["data"]["object"]
        api_key = session.get("metadata", {}).get("api_key")
        if api_key:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("UPDATE api_keys SET tier='pro' WHERE key=?", (api_key,))
                await db.commit()
            print(f"[{PRODUCT} Billing] License upgrade complete for token: {api_key}")
            
    return {"status": "processed"}
