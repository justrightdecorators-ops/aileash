import os, subprocess, requests, hashlib, hmac, base64, uuid, re, json, time
from typing import Dict, Any, List, Optional
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Live-MSP-Engine")

# --- LIVE EXECUTION TOOLS ---
@mcp.tool()
def run_cli_command(command: str) -> dict:
    """Run a local shell command on the host machine and return output."""
    res = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30)
    return {"exit_code": res.returncode, "stdout": res.stdout, "stderr": res.stderr}

@mcp.tool()
def call_api(url: str, method: str = "GET", payload: dict = None, headers: dict = None) -> dict:
    """Hit a real HTTP REST endpoint, microservice, or webhook."""
    r = requests.request(method, url, json=payload, headers=headers, timeout=15)
    return {"status": r.status_code, "response": r.text}

@mcp.tool()
def deploy_railway_service(service_id: str, api_token: str) -> dict:
    """Trigger a live container redeployment on Railway."""
    url = "https://backboard.railway.app/graphql/v2"
    q = "mutation($s: String!){serviceInstanceRedeploy(serviceId:$s)}"
    r = requests.post(url, json={"query": q, "variables": {"s": service_id}}, headers={"Authorization": f"Bearer {api_token}"})
    return {"status": r.status_code, "data": r.json()}

# --- UTILITY & SECURITY TOOLS ---
@mcp.tool()
def sec_hash_sha256(data: str) -> str:
    """Generate SHA-256 digest for input data."""
    return hashlib.sha256(data.encode()).hexdigest()

@mcp.tool()
def sec_hmac_sign(key: str, message: str) -> str:
    """Sign payload using HMAC-SHA256."""
    return hmac.new(key.encode(), message.encode(), hashlib.sha256).hexdigest()

@mcp.tool()
def sec_hmac_verify(key: str, message: str, signature: str) -> bool:
    """Verify HMAC-SHA256 signature against payload."""
    expected = hmac.new(key.encode(), message.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)

@mcp.tool()
def sec_verify_merkle_leaf(leaf: str, proof: List[str], root: str) -> bool:
    """Verify standard Merkle tree membership proof."""
    current = leaf
    for sibling in proof:
        combined = "".join(sorted([current, sibling]))
        current = hashlib.sha256(combined.encode()).hexdigest()
    return current == root

@mcp.tool()
def sec_base64_encode(payload: str) -> str:
    """Base64 encode standard string payload."""
    return base64.b64encode(payload.encode()).decode()

@mcp.tool()
def sec_base64_decode(encoded_str: str) -> str:
    """Base64 decode string back to original format."""
    return base64.b64decode(encoded_str.encode()).decode()

@mcp.tool()
def sec_generate_uuid_v4() -> str:
    """Generate cryptographically secure UUID v4 identifier."""
    return str(uuid.uuid4())

@mcp.tool()
def sec_mask_sensitive_keys(data: Dict[str, Any]) -> Dict[str, Any]:
    """Scrub sensitive keys from dictionary."""
    sensitive = {"token", "key", "password", "secret", "auth", "bearer"}
    return {k: ("***REDACTED***" if any(s in k.lower() for s in sensitive) else v) for k, v in data.items()}

@mcp.tool()
def data_flatten_dict(nested_dict: Dict[str, Any], parent_key: str = '', sep: str = '.') -> Dict[str, Any]:
    """Flatten nested dictionary into single dot-notation key map."""
    items = []
    for k, v in nested_dict.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(data_flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)

@mcp.tool()
def data_csv_to_json(csv_text: str) -> List[Dict[str, str]]:
    """Convert raw CSV string content into JSON list of key-value maps."""
    import csv, io
    return [row for row in csv.DictReader(io.StringIO(csv_text.strip()))]

@mcp.tool()
def data_json_to_csv(json_list: List[Dict[str, Any]]) -> str:
    """Convert JSON list of dictionaries into formatted CSV string."""
    import csv, io
    if not json_list: return ""
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=json_list[0].keys())
    writer.writeheader()
    writer.writerows(json_list)
    return out.getvalue()

@mcp.tool()
def data_calculate_array_stats(numbers: List[float]) -> Dict[str, float]:
    """Compute min, max, average, sum, and length of numerical array."""
    if not numbers: return {"count": 0, "sum": 0, "avg": 0, "min": 0, "max": 0}
    return {"count": float(len(numbers)), "sum": float(sum(numbers)), "avg": float(sum(numbers)/len(numbers)), "min": float(min(numbers)), "max": float(max(numbers))}

@mcp.tool()
def data_human_readable_bytes(num_bytes: int) -> str:
    """Format raw byte integer into human-readable size string."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if abs(num_bytes) < 1024.0: return f"{num_bytes:3.1f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} PB"

@mcp.tool()
def data_slugify_string(text: str) -> str:
    """Convert text string into clean URL-friendly slug."""
    return re.sub(r'[\s_-]+', '-', re.sub(r'[^\w\s-]', '', text.lower().strip()))

@mcp.tool()
def data_deduplicate_list(lst: List[Any]) -> List[Any]:
    """Remove duplicate values while maintaining original order."""
    seen = set()
    return [x for x in lst if not (x in seen or seen.add(x))]

@mcp.tool()
def data_filter_nulls(data: Dict[str, Any]) -> Dict[str, Any]:
    """Remove keys with None or empty values from dictionary."""
    return {k: v for k, v in data.items() if v not in (None, "", [], {})}

@mcp.tool()
def net_parse_url_params(url: str) -> Dict[str, List[str]]:
    """Parse URL target and extract query parameter dictionary."""
    from urllib.parse import parse_qs, urlparse
    return parse_qs(urlparse(url).query)

@mcp.tool()
def net_validate_ip(ip_address: str) -> Dict[str, Any]:
    """Validate IPv4 or IPv6 format compliance."""
    import ipaddress
    try:
        ip = ipaddress.ip_address(ip_address)
        return {"valid": True, "version": ip.version, "is_private": ip.is_private}
    except ValueError:
        return {"valid": False, "version": None, "is_private": False}

@mcp.tool()
def net_extract_domain(url: str) -> str:
    """Extract hostname domain from full target URL."""
    from urllib.parse import urlparse
    return urlparse(url).netloc

@mcp.tool()
def net_generate_curl(url: str, method: str = "GET", headers: Optional[Dict[str, str]] = None) -> str:
    """Build equivalent cURL command string for debugging endpoints."""
    cmd = f"curl -X {method.upper()} \"{url}\""
    if headers:
        for k, v in headers.items(): cmd += f" -H \"{k}: {v}\""
    return cmd

@mcp.tool()
def net_strip_html_tags(html_content: str) -> str:
    """Strip all HTML tags returning clean text content."""
    return re.sub(r'<[^>]*>', '', html_content).strip()

@mcp.tool()
def net_extract_urls(text: str) -> List[str]:
    """Regex extract web links from text."""
    return re.findall(r'https?://[^\s<>"]+', text)

@mcp.tool()
def time_get_epoch() -> float:
    """Return current UTC epoch timestamp in seconds."""
    return time.time()

@mcp.tool()
def time_epoch_to_iso(epoch: float) -> str:
    """Convert epoch timestamp into ISO-8601 string."""
    from datetime import datetime, timezone
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()

@mcp.tool()
def time_iso_to_epoch(iso_str: str) -> float:
    """Convert ISO-8601 string to standard UTC epoch timestamp."""
    from datetime import datetime
    return datetime.fromisoformat(iso_str.replace("Z", "+00:00")).timestamp()

@mcp.tool()
def time_format_duration(seconds: float) -> str:
    """Format total elapsed seconds into HH:MM:SS format."""
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

@mcp.tool()
def biz_calculate_vat(amount: float, rate: float = 0.20) -> Dict[str, float]:
    """Compute VAT/Tax addition and total billing amount."""
    tax = amount * rate
    return {"net": amount, "tax": round(tax, 2), "total": round(amount + tax, 2)}

@mcp.tool()
def biz_calculate_margin(cost: float, revenue: float) -> Dict[str, float]:
    """Calculate gross profit and profit margin percentage."""
    profit = revenue - cost
    return {"profit": round(profit, 2), "margin_pct": round((profit / revenue * 100) if revenue > 0 else 0.0, 2)}

@mcp.tool()
def biz_apply_discount(price: float, discount_pct: float) -> Dict[str, float]:
    """Apply percentage discount calculation to base price."""
    saved = price * (discount_pct / 100.0)
    return {"original": price, "saved": round(saved, 2), "final": round(price - saved, 2)}

@mcp.tool()
def biz_calculate_hourly_rate(total_project_cost: float, estimated_hours: float) -> float:
    """Calculate target hourly billing rate from fixed project value."""
    return round(total_project_cost / estimated_hours, 2) if estimated_hours > 0 else 0.0

if __name__ == "__main__":
    mcp.run()
