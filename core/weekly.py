import re
import json
from datetime import date

SECTIONS = [
    {"id": "culture", "title": "Qué cambió en la cultura", "prompt": "La señal cultural y por qué importa"},
    {"id": "brands", "title": "Qué significa para nuestras marcas", "prompt": "Conversaciones alrededor de Rexona, Pond’s y Dove"},
    {"id": "pending", "title": "Qué debemos seguir explorando", "prompt": "Sección pendiente de definir"},
    {"id": "competition", "title": "Qué hizo la categoría", "prompt": "Activaciones de competencia y aprendizajes"},
]

KEYWORDS = {
    "culture": ["cultura", "cultural", "sociedad", "viral", "meme", "comunidad", "generación", "jóvenes", "movimiento"],
    "brands": ["rexona", "pond", "pond's", "dove", "marca", "brand", "producto", "desodorante", "skincare"],
    "competition": ["competencia", "competidor", "competitor", "campaña", "activación", "lanzamiento", "categoría", "aprendizaje"],
}

def _sentences(text: str) -> list[str]:
    return [x.strip() for x in re.split(r"(?<=[.!?])\s+|\n+", text) if len(x.strip()) > 24]

def _readable_source(text: str) -> str:
    if not text.startswith("__XLSX_JSON__"):
        return text
    try:
        tables = json.loads(text[len("__XLSX_JSON__"):])
        lines = []
        useful = {"tendencia", "título", "texto", "temas", "categorías automáticas", "fuente", "sentimiento", "fecha"}
        for table in tables:
            rows = table.get("rows", [])
            if not rows: continue
            headers = [str(x or "").strip() for x in rows[0]]
            indexes = [i for i, h in enumerate(headers) if h.lower() in useful]
            for row in rows[1:201]:
                values = [f"{headers[i]}: {row[i]}" for i in indexes if i < len(row) and row[i] not in (None, "")]
                if values: lines.append(" | ".join(values))
        return "\n".join(lines) or "No se encontraron campos legibles en el XLSX."
    except (ValueError, TypeError, KeyError):
        return "No se pudo convertir el XLSX a evidencia legible."

def classify_week(text: str, filename: str, week_start: str | None = None) -> dict:
    text = _readable_source(text)
    sentences = _sentences(text)
    sections = []
    for section in SECTIONS:
        if section["id"] == "pending": evidence = []
        else:
            terms = KEYWORDS[section["id"]]
            evidence = [s for s in sentences if any(term in s.lower() for term in terms)][:8] or sentences[:3]
        implications = {"culture": "Observar si esta señal cultural puede convertirse en una oportunidad relevante para la categoría.", "brands": "Identificar qué marca tiene mayor legitimidad para participar y con qué producto o territorio.", "pending": "Esta sección requiere la taxonomía final antes de generar una lectura automática.", "competition": "Comparar la respuesta de la categoría y traducirla en un aprendizaje accionable para nuestras marcas."}
        sections.append({"id": section["id"], "title": section["title"], "prompt": section["prompt"], "insight": " ".join(evidence[:2]) if evidence else "Pendiente de definir con el template y la taxonomía final.", "implication": implications[section["id"]], "evidence": evidence})
    return {"week_start": week_start or date.today().isoformat(), "title": "One Page semanal", "source_file": filename, "sections": sections, "raw_excerpt": text[:6000]}
