import re
from datetime import date

SECTIONS = [
    {"id": "culture", "title": "Hallazgos culturales de la semana", "prompt": "Qué se movió en la cultura y qué nos importa"},
    {"id": "brands", "title": "Conversaciones relevantes alrededor de nuestras marcas", "prompt": "Rexona, Pond’s y Dove"},
    {"id": "pending", "title": "Sección pendiente", "prompt": "Pendiente de definir"},
    {"id": "competition", "title": "Qué vimos en la competencia", "prompt": "Qué activó la categoría y qué aprendemos"},
]

KEYWORDS = {
    "culture": ["cultura", "cultural", "sociedad", "viral", "meme", "comunidad", "generación", "jóvenes", "movimiento"],
    "brands": ["rexona", "pond", "pond's", "dove", "marca", "brand", "producto", "desodorante", "skincare"],
    "competition": ["competencia", "competidor", "competitor", "campaña", "activación", "lanzamiento", "categoría", "aprendizaje"],
}

def _sentences(text: str) -> list[str]:
    return [x.strip() for x in re.split(r"(?<=[.!?])\s+|\n+", text) if len(x.strip()) > 24]

def classify_week(text: str, filename: str, week_start: str | None = None) -> dict:
    sentences = _sentences(text)
    sections = []
    for section in SECTIONS:
        if section["id"] == "pending": evidence = []
        else:
            terms = KEYWORDS[section["id"]]
            evidence = [s for s in sentences if any(term in s.lower() for term in terms)][:8] or sentences[:3]
        sections.append({"id": section["id"], "title": section["title"], "prompt": section["prompt"], "insight": " ".join(evidence[:2]) if evidence else "Pendiente de definir con el template y la taxonomía final.", "comments": "", "evidence": evidence})
    return {"week_start": week_start or date.today().isoformat(), "title": "One Page semanal", "source_file": filename, "sections": sections, "raw_excerpt": text[:6000]}
