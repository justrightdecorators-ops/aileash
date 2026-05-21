from fastapi import APIRouter
from config import COUNTRY_RISK, DEFAULT_COUNTRY_RISK

router = APIRouter(tags=["Risk Assessment"])

def calculate_risk(amount: float, device_risk: float, anomaly: float, country: str, current_trust: float, velocity_factor: float) -> float:
    base_score = 0.0
    base_score += min(amount / 10000.0, 1.0) * 0.25
    base_score += device_risk * 0.20
    base_score += anomaly * 0.20
    base_score += COUNTRY_RISK.get(country.upper(), DEFAULT_COUNTRY_RISK) * 0.10
    base_score += velocity_factor * 0.15
    base_score += (1.0 - current_trust) * 0.10
    return round(max(0.0, min(1.0, base_score)), 4)
  
