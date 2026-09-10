import math

def _clamp(x): return max(0, min(100, round(x)))

def evaluate(trend: dict, brand: dict, rules: dict) -> dict:
    growth_value = trend.get("growth") or 0
    growth = _clamp(50 + growth_value / 5); velocity = _clamp(50 + growth_value / 3)
    volume = _clamp(30 + math.log10(trend["mentions"]) * 10) if trend.get("mentions", 0) > 0 else 30
    cross = _clamp(len(trend.get("platforms", [])) * 25); persistence = 65 if growth_value > 20 else 45
    sw = rules["trend_strength"]
    strength_values = {"growth": growth, "velocity": velocity, "volume": volume, "cross_platform": cross, "persistence": persistence}
    strength = _clamp(sum(strength_values[k] * sw[k] for k in strength_values))
    raw = trend.get("raw_excerpt", "").lower()
    cat = sum(c.lower() in raw for c in brand["categories"]) / max(1, len(brand["categories"]))
    aud = 1 if any(a.lower() in raw for a in brand["audiences"]) else .55
    terr = 1 if any(t.lower() in raw for t in brand["territories"]) else .55
    prod = 1 if any(p.lower() in raw for p in brand["products"]) else .55
    safety = .75 if any(x in raw for x in ["claim", "reclamo", "medical", "médico"]) else 1
    fit_values = {"category_match": cat*100, "audience_match": aud*100, "territory_match": terr*100, "product_relevance": prod*100, "safety": safety*100}
    fw = rules["brand_fit"]; fit = _clamp(sum(fit_values[k] * fw[k] for k in fit_values))
    action_values = {"channel_clarity": 75 if trend.get("platforms") else 45, "product_link": prod*100, "audience_clarity": aud*100, "timing": velocity, "evidence_quality": strength}
    aw = rules["actionability"]; action = _clamp(sum(action_values[k] * aw[k] for k in action_values))
    growth_text = f"{growth_value:.0f}%" if trend.get("growth") is not None else "crecimiento no disponible"
    missing = trend.get("missing_fields", [])
    return {"trend_strength": strength, "brand_fit": fit, "actionability": action, "confidence": "Alta" if not missing and len(trend.get("platforms", [])) >= 2 else "Media" if len(missing) <= 2 else "Baja", "components": {"trend_strength": strength_values, "brand_fit": fit_values, "actionability": action_values}, "missing_information": missing, "explanation": f"{trend['name']} muestra {growth_text} y aparece en {len(trend.get('platforms', [])) or 1} plataforma(s). {brand['name']} tiene afinidad por {', '.join(brand['categories'][:2])}.", "activation": f"Crear una activación para {brand['name']} en {', '.join(brand['channels'][:2])}, conectando la tendencia con {brand['products'][0]} y el territorio de {brand['territories'][0]}."}
