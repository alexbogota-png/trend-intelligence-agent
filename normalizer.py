import re, json
from pathlib import Path

def _number(value):
    if value is None: return None
    m = re.search(r"-?\d+(?:[.,]\d+)?", str(value).replace("%", ""))
    return float(m.group().replace(",", ".")) if m else None

def normalize(text: str, filename: str, brands: list[dict]) -> dict:
    low = text.lower()
    structured_name = None
    def find(pattern):
        m = re.search(pattern, text, re.I); return _number(m.group(1)) if m else None
    platforms = [p for p in ["TikTok", "Instagram", "YouTube", "Reddit", "Meta", "X", "Google"] if p.lower() in low]
    if text.startswith("__XLSX_JSON__"):
        table = json.loads(text[len("__XLSX_JSON__"):])[0]["rows"]
        header = [str(v).strip() if v is not None else "" for v in table[0]]; pos = {v: i for i, v in enumerate(header) if v}
        rows = table[1:]
        def vals(name):
            i = pos.get(name); return [r[i] for r in rows if i is not None and i < len(r) and r[i] not in (None, "")]
        source_values = vals("Fuente")
        platforms = list(dict.fromkeys([p for p in ["TikTok", "Instagram", "YouTube", "Reddit", "Meta", "X", "Google"] if any(p.lower() in str(v).lower() for v in source_values)]))
        trend_values = [str(v).replace("\\n", "\n").splitlines()[0].strip() for v in vals("Tendencia") if str(v).strip() and not str(v).lower().startswith(("http", "total/"))]
        if trend_values: structured_name = max(set(trend_values), key=trend_values.count)[:180]
        mentions = len(rows)
        growth_value = None
        evidence_parts = vals("Temas") + vals("Categorías automáticas") + vals("Tendencia") + vals("Título") + vals("Texto")
        text = "\n".join(str(v) for v in evidence_parts[:300])
        low = text.lower()
    elif "Hoja:" in text and "\t" in text:
        lines = [line.split("\t") for line in text.splitlines() if "\t" in line]
        if lines:
            header = lines[0]; pos = {str(v).strip(): i for i, v in enumerate(header)}
            rows = lines[1:]
            def col(name): return pos.get(name)
            def vals(name):
                i = col(name); return [r[i] for r in rows if i is not None and i < len(r) and r[i]]
            source_values = vals("Fuente")
            platforms = list(dict.fromkeys([p for p in ["TikTok", "Instagram", "YouTube", "Reddit", "Meta", "X", "Google"] if any(p.lower() in str(v).lower() for v in source_values)]))
            trend_values = vals("Tendencia")
            if trend_values:
                trend_name = max(set(trend_values), key=trend_values.count)
            mentions = len(rows)
        else: mentions = find(r"(?:mentions|menciones|volume|volumen)[^\d]*([\d.,]+)")
    else: mentions = find(r"(?:mentions|menciones|volume|volumen)[^\d]*([\d.,]+)")
    audiences = [a for b in brands for a in b["audiences"] if a.lower() in low]
    detected_name = re.search(r"(?:trend|tendencia)\s*[:\-]\s*([^\n|]+)", text, re.I)
    name = structured_name or (detected_name.group(1).strip() if detected_name else Path(filename).stem.replace("_", " "))
    growth = locals().get("growth_value", find(r"(?:growth|crecimiento|incremento)[^\d-]*([+-]?[\d.,]+)\s*%?"))
    missing = [field for field, value in {"growth": growth, "mentions": mentions, "platforms": platforms, "audiences": audiences}.items() if value in (None, [], 0)]
    return {"name": name, "growth": growth, "mentions": mentions, "sentiment": find(r"(?:positive|positivo|sentiment|sentimiento)[^\d]*([\d.,]+)\s*%?"), "platforms": list(dict.fromkeys(platforms)), "audiences": list(dict.fromkeys(audiences)), "missing_fields": missing, "raw_excerpt": text[:4000]}
