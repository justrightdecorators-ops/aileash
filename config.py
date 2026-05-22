import os

PORT = int(os.getenv("PORT", 8080))
VERSION = "2.0"
PRODUCT = "AILeash"
FREE_TIER_LIMIT = 1000

STRIPE_SECRET = os.getenv("STRIPE_SECRET", "")
BASE_URL = os.getenv("BASE_URL", "https://sebbi.pro")
