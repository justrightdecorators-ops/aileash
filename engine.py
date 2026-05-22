COUNTRY_RISK = {
    "UK": 0.05, "US": 0.05, "DE": 0.05, "FR": 0.05,
    "CA": 0.05, "AU": 0.05, "JP": 0.10, "BR": 0.25,
    "IN": 0.20, "CN": 0.40, "RU": 0.70, "KP": 0.90,
    "IR": 0.80, "NG": 0.50,
}

DEFAULT_COUNTRY_RISK = 0.35


def score(event, trust=0.5):
    s = 0.0
    s += (1.0 - trust) * 0.25
    amount = float(event.get("amount", 0))
    s += min(amount / 10000.0, 1.0) * 0.25
    s += float(event.get("device_risk", 0.0)) * 0.20
    s += float(event.get("anomaly", 0.0)) * 0.20
    country = event.get("country", "US")
    s += COUNTRY_RISK.get(country, DEFAULT_COUNTRY_RISK) * 0.10
    return round(max(0.0, min(1.0, s)), 4)


def decide(score):
    if score < 0.30:
        return "ALLOW"
    if score < 0.70:
        return "CHALLENGE"
    return "BLOCK"
