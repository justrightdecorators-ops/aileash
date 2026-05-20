AILeash
A lightweight AI Action Firewall that evaluates AI decisions in real time and prevents unsafe or high-risk actions before they execute.
What it does
AILeash sits between your AI system and the outside world. Every action your AI takes is scored for risk before it executes. The engine returns one of three decisions:
ALLOW — risk is low, action proceeds
CHALLENGE — risk is elevated, flag for human review
BLOCK — risk is too high, action is stopped
Every decision is logged in a tamper-evident audit chain. EU AI Act compliant.
Quickstart
Python
API
POST /govern
Headers: x-api-key: your_key
Body:
Json
Response:
Json
GET /health
Json
POST /register
Register for a free API key.
Body: {"email": "you@example.com"}
GET /checkout?key=your_key
Redirects to Stripe checkout for Pro subscription.
GET /audit
Returns last 50 audit records for your API key.
Decision thresholds
Score
Decision
0.00 - 0.29
ALLOW
0.30 - 0.69
CHALLENGE
0.70 - 1.00
BLOCK
Railway deployment
Push this repo to GitHub
Connect to Railway
Add environment variables:
STRIPE_SECRET — your Stripe secret key
BASE_URL — your deployment URL (e.g. https://sebbi.pro)
Railway runs python server.py via Procfile
Stripe setup
Create a Stripe account at stripe.com
Copy your secret key (starts with sk_live_)
Add as STRIPE_SECRET in Railway environment variables
Add your Railway URL as BASE_URL
Set up webhook in Stripe dashboard pointing to BASE_URL/webhook
Listen for checkout.session.completed event
Local development
Bash
Server starts on port 8080.
Compliance
AILeash implements core technical requirements of:
EU AI Act Articles 9, 12, 13, 14
UK AI framework
US state AI legislation (Colorado, California)
Not a substitute for legal advice. Consult qualified legal counsel to confirm your compliance obligations.
Built by Monopcontent | hello@monopcontent.com | MIT License
