import os

STRIPE_SECRET = os.environ.get("STRIPE_SECRET", "")
BASE_URL = os.environ.get("BASE_URL", "https://sebbi.pro")
PORT = int(os.environ.get("PORT", 8080))
FREE_TIER_LIMIT = 1000
VERSION = "2.0"
PRODUCT = "AILeash"
