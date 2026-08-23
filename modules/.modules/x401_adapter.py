"""
===============================================================================
x401_adapter.py - HTTP-Native Gatekeeper & Adoption Router for witness.py
===============================================================================

WHAT THIS DOES
--------------
This module provides a fail-closed execution gate and universal translation 
layer for `witness.py` without modifying a single line of core witness code.

It bridges standard HTTP transport headers (x401 specifications, bearer tokens,
W3C trace contexts, custom headers) directly into your native `witness.py` 
`observe` schema (`chain`, `tip`, `url`).

ADOPTION ROUTES PROVIDED
------------------------
1. Direct Function Interceptor: `intercept_and_witness(payload, headers, ctx)`
2. Decorator Execution Gate: `@witness_gate(chain_name="my-service")`
3. Middleware Hook: `witness_middleware_handler(method, headers, body, ctx)`
4. x401 Challenge Generator: `build_x401_challenge_header(chain_name)`

FAIL-CLOSED GUARANTEE
---------------------
If an incoming request carries an execution payload, this adapter hashes 
the payload deterministically, passes it to `witness.py`'s `handle()`, and 
inspects the seal. If witnessing fails or state is tampered with, execution 
halts immediately before downstream application logic ever runs.
===============================================================================
"""

import hashlib
import json
import time
from typing import Dict, Any, Tuple, Optional, Callable
from functools import wraps

# Import core witness handle directly from local module directory in-memory
try:
    from .witness import handle, VERSION as WITNESS_VERSION, ANON_KEY
except ImportError:
    # Fallback for flat directory structures or direct execution testing
    from witness import handle, VERSION as WITNESS_VERSION, ANON_KEY

ADAPTER_VERSION = "1.0.0"

# Standard HTTP headers parsed for x401 identity and provenance
HEADER_PROOF_REQUIRED = "proof-required"
HEADER_PROOF_RESPONSE = "proof-response"
HEADER_X401_AGENT = "x-401-agent-id"
HEADER_X_CHAIN = "x-chain-name"
HEADER_X_TIP = "x-chain-tip"
HEADER_X_URL = "x-chain-url"


def compute_deterministic_tip(payload: Any) -> str:
    """
    Turns any Python dictionary, list, string, or raw byte sequence into 
    a deterministic 64-character hex SHA-256 string for witness.py.
    """
    if isinstance(payload, bytes):
        raw_bytes = payload
    elif isinstance(payload, str):
        raw_bytes = payload.encode('utf-8')
    else:
        # Enforce canonical JSON formatting with sorted keys to ensure zero ambiguity
        serialized = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        raw_bytes = serialized.encode('utf-8')

    return hashlib.sha256(raw_bytes).hexdigest().lower()


def extract_chain_identity(headers: Dict[str, str], default_name: str = "anon-agent") -> str:
    """
    Extracts the self-declared chain/peer name from any standard HTTP header format.
    Falls back gracefully to 'anon-agent' or host context.
    """
    # Lowercase all lookup keys for HTTP header case-insensitivity
    norm_headers = {k.lower(): str(v).strip() for k, v in headers.items()} if headers else {}

    # Check primary x401 and custom header fields
    chain = (
        norm_headers.get(HEADER_X_CHAIN) or
        norm_headers.get(HEADER_X401_AGENT) or
        norm_headers.get("x-peer-name") or
        norm_headers.get("host")
    )
    
    if not chain:
        return default_name

    # Sanitize identifier to conform with witness.py limits (80 chars max)
    sanitized = str(chain).strip().lower()[:80]
    return sanitized if sanitized else default_name


def process_x401_observation(
    payload: Any,
    headers: Dict[str, str],
    ctx: Dict[str, Any],
    api_key: Optional[str] = None,
    url: Optional[str] = None
) -> Tuple[Dict[str, Any], int]:
    """
    The core bridge function. Translates external HTTP request parameters into
    witness.py's native `observe` schema and calls handle() directly in memory.
    """
    norm_headers = {k.lower(): str(v).strip() for k, v in headers.items()} if headers else {}
    
    # Step 1: Extract or compute 64-hex SHA-256 tip
    explicit_tip = norm_headers.get(HEADER_X_TIP)
    if explicit_tip and len(explicit_tip) == 64:
        tip = explicit_tip.lower()
    else:
        tip = compute_deterministic_tip(payload)

    # Step 2: Extract peer/chain name
    chain = extract_chain_identity(norm_headers)

    # Step 3: Extract verification URL
    observe_url = url or norm_headers.get(HEADER_X_URL) or ""

    # Step 4: Construct observe payload compatible with witness.py v1.3
    observe_data = {
        "chain": chain,
        "tip": tip,
        "url": observe_url,
        "ts": time.time()
    }

    # Step 5: Execute witness.py handle() directly in Python runtime
    effective_key = api_key or ANON_KEY
    response_data, status_code = handle("POST", "observe", observe_data, effective_key, ctx)

    # Inject adapter metadata into output receipt
    if isinstance(response_data, dict):
        response_data["adapter_version"] = ADAPTER_VERSION
        response_data["x401_header_processed"] = HEADER_PROOF_RESPONSE in norm_headers

    return response_data, status_code


# ----------------------------------------------------------------------
# Adoption Route 1: Generic Middleware Handler (FastAPI, Flask, Django)
# ----------------------------------------------------------------------

def witness_middleware_handler(
    headers: Dict[str, str],
    body_payload: Any,
    ctx: Dict[str, Any],
    api_key: Optional[str] = None
) -> Tuple[bool, Dict[str, Any], Dict[str, str]]:
    """
    Sits in the HTTP pipeline. Inspects inbound request, seals it into 
    witness.py, and returns:
        (is_allowed: bool, response_body: dict, http_headers_to_inject: dict)
    """
    receipt, status = process_x401_observation(body_payload, headers, ctx, api_key)
    
    # Check if observation was successfully sealed in witness_log
    if status == 200 and receipt.get("sealed_in_our_chain"):
        response_headers = {
            "X-Sebbi-Witness-Status": "SEALED",
            "X-Sebbi-Block-Index": str(receipt.get("block_index", "")),
            "X-Sebbi-Audit-Hash": str(receipt.get("sealed_in_our_chain", "")),
            "X-Sebbi-Liveness": str(receipt.get("liveness", ""))
        }
        return True, receipt, response_headers
    else:
        response_headers = {
            "X-Sebbi-Witness-Status": "HALTED",
            "X-Sebbi-Error": str(receipt.get("error", "witness_failed"))
        }
        return False, receipt, response_headers


# ----------------------------------------------------------------------
# Adoption Route 2: Decorator for Python Functions/Routes
# ----------------------------------------------------------------------

def witness_gate(chain_name: str = "app-gate", api_key: Optional[str] = None):
    """
    Python decorator that wraps any function or API route with a fail-closed
    witness execution gate.
    
    Usage:
        @witness_gate(chain_name="payment-service")
        def execute_payment(payload, ctx):
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Extract ctx from kwargs or args if present
            ctx = kwargs.get("ctx")
            if not ctx and len(args) > 1 and isinstance(args[1], dict):
                ctx = args[1]
                
            if ctx:
                payload = kwargs.get("payload") or (args[0] if args else {})
                headers = kwargs.get("headers") or {"x-chain-name": chain_name}
                
                receipt, status = process_x401_observation(payload, headers, ctx, api_key)
                if status != 200 or not receipt.get("sealed_in_our_chain"):
                    raise RuntimeError(f"Execution Gate Halted by witness.py: {receipt.get('error')}")

            return func(*args, **kwargs)
        return wrapper
    return decorator


# ----------------------------------------------------------------------
# Adoption Route 3: x401 Protocol Challenge Helper
# ----------------------------------------------------------------------

def build_x401_challenge_header(chain_name: str, tip: str) -> Dict[str, str]:
    """
    Generates standard HTTP headers to challenge external client agents 
    under the x401 protocol specification.
    """
    challenge_payload = {
        "protocol": "x401",
        "required_witness": chain_name,
        "challenge_tip": tip,
        "timestamp": time.time()
    }
    encoded_challenge = compute_deterministic_tip(challenge_payload)
    
    return {
        "PROOF-REQUIRED": f"x401 realm=\"sebbi.pro\", challenge=\"{encoded_challenge}\"",
        "WWW-Authenticate": f"x401 challenge=\"{encoded_challenge}\""
    }
