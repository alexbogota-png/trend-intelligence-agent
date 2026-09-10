import re
import json
import unicodedata
from collections import Counter
from datetime import datetime
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

def _date_value(value):
    raw = str(value or "").strip()
    for fmt in ("%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try: return datetime.strptime(raw[:10], fmt).date()
        except ValueError: pass
    return None

def _xlsx_records(text: str) -> list[dict]:
    if not text.startswith("__XLSX_JSON__"): return []
    try:
        tables = json.loads(text[len("__XLSX_JSON__"):]); records = []
        for table in tables:
            rows = table.get("rows", [])
            if not rows: continue
            headers = [str(x or "").strip() for x in rows[0]]
            for row in rows[1:]:
                record = {headers[i]: row[i] for i in range(min(len(headers), len(row))) if headers[i]}
                if record: records.append(record)
        return records
    except (ValueError, TypeError): return []

def _conversation_label(raw: str) -> str:
    lines = str(raw or "").replace("\\n", " ").splitlines()
    text = (lines[0] if lines else "").strip()
    low = _fold(text)
    if "rexona" in low and ("desodor" in low or "clinical" in low or "antiperspir" in low):
        return "Rexona: desempeño y protección del desodorante"
    if ("dove" in low or "pond" in low) and any(x in low for x in ["serum", "hidrat", "crema", "piel", "skincare"]):
        brand = "Dove" if "dove" in low else "Pond’s"
        return f"{brand}: hidratación y cuidado de la piel"
    if any(x in low for x in ["hidrat", "serum corporal", "crema corporal", "cuidado de la piel"]):
        return "Hidratación y cuidado de la piel"
    if any(x in low for x in ["desodor", "antiperspir", "clinical"]):
        return "Desodorantes y protección corporal"
    if "juanfer" in low or "juan fernando quintero" in low or "quintero" in low:
        return "Juanfer Quintero y su salida de la Selección Colombia"
    if "seleccion colombia" in low or "seleccion nacional" in low:
        return "Selección Colombia"
    stop = {"para", "como", "sobre", "esta", "este", "desde", "entre", "cuando", "porque", "tiene", "tambien", "todo", "ante", "tras", "una", "que", "del", "los", "las", "con", "por", "sus", "más", "muy"}
    tokens = [x for x in re.findall(r"[a-z0-9áéíóúñ]{4,}", low) if x not in stop]
    return " ".join(tokens[:7]).title() or "Conversación sin tema identificable"

def _fold(value: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(value).lower()) if unicodedata.category(c) != "Mn")

def _weekly_analysis(text: str, filename: str) -> dict | None:
    records = _xlsx_records(text)
    dated = [(r, _date_value(r.get("Fecha"))) for r in records]
    dated = [(r, d) for r, d in dated if d]
    if not dated: return None
    weeks = sorted({d.isocalendar()[:2] for _, d in dated})
    latest_key = weeks[-1]; previous_key = weeks[-2] if len(weeks) > 1 else None
    current = [r for r, d in dated if d.isocalendar()[:2] == latest_key]
    previous = [r for r, d in dated if previous_key and d.isocalendar()[:2] == previous_key]
    def value(row, name): return str(row.get(name) or "").strip()
    def counter(rows, field): return Counter(x for x in (value(r, field) for r in rows) if x)
    def conversation_source(row):
        return value(row, "Tendencia") or value(row, "Título") or value(row, "Texto") or value(row, "Temas")
    current_trends = Counter(_conversation_label(conversation_source(r)) for r in current)
    previous_trends = Counter(_conversation_label(conversation_source(r)) for r in previous)
    trend_rows = []
    for name, count in current_trends.most_common(8):
        old = previous_trends.get(name, 0); change = count - old
        movement = f"subió {change} menciones" if change > 0 else f"bajó {abs(change)} menciones" if change < 0 else "se mantuvo estable"
        label = f"{movement} vs. la semana anterior" if previous_key else "concentró el mayor volumen del periodo"
        trend_rows.append({"name": name, "count": count, "previous": old, "change": change, "label": label})
    def brand_rows(brand):
        aliases = {"Rexona": ["rexona"], "Pond’s": ["pond", "pond's", "pond’s"], "Dove": ["dove"]}[brand]
        matched = [r for r in current if any(a in " ".join(value(r, k).lower() for k in ["Texto", "Tendencia", "Temas", "Marcas en la imagen"]) for a in aliases)]
        old_matched = [r for r in previous if any(a in " ".join(value(r, k).lower() for k in ["Texto", "Tendencia", "Temas", "Marcas en la imagen"]) for a in aliases)]
        topics = Counter(t for r in matched for t in re.split(r"[,|]", value(r, "Temas")) if t.strip())
        conversations = Counter(_conversation_label(conversation_source(r)) for r in matched)
        return matched, old_matched, topics, conversations
    brand_data = {}
    for brand in ["Rexona", "Pond’s", "Dove"]:
        matched, old_matched, topics, conversations = brand_rows(brand)
        brand_data[brand] = {"mentions": len(matched), "previous": len(old_matched), "topics": topics.most_common(3), "conversations": conversations.most_common(2), "sample": [value(r, "Texto")[:180] for r in matched[:3] if value(r, "Texto")]}
    candidate_names = ["Nivea", "Neutrogena", "Garnier", "L’Oréal", "L'Oreal", "CeraVe", "Eucerin", "Vaseline", "Old Spice", "Axe", "Secret", "Gillette", "Adidas", "Nike", "Puma"]
    competitors = Counter()
    for r in current:
        raw = " ".join(value(r, field) for field in ["Marcas en la imagen", "Texto", "Tendencia"])
        for candidate in candidate_names:
            if re.search(rf"(?i)(?<![\w]){re.escape(candidate)}(?![\w])", raw): competitors[candidate] += 1
    comp = [{"name": n, "count": c} for n, c in competitors.most_common(8)]
    week_label = f"Semana {latest_key[1]} de {latest_key[0]}"
    comparison = f"Se comparan {len(current)} menciones de {week_label} con {len(previous)} de la semana anterior." if previous_key else f"El archivo contiene {len(current)} menciones en {week_label}; no hay una semana anterior completa en el archivo."
    culture_bullets = [f"{x['name']} concentró {x['count']} menciones y {x['label']}." for x in trend_rows[:5]]
    if not culture_bullets: culture_bullets = ["No se encontraron conversaciones con volumen suficiente para construir un hallazgo cultural."]
    brand_bullets = []
    for brand, data in brand_data.items():
        topics = ", ".join(t for t, _ in data["topics"]) or "sin tema dominante identificado"
        difference = data['mentions']-data['previous']
        movement = (f"subió {difference}" if difference > 0 else f"bajó {abs(difference)}" if difference < 0 else "se mantuvo estable") + " menciones frente a la semana anterior" if previous_key else "sin comparación semanal disponible"
        conversation = "; ".join(f"{name} ({count})" for name, count in data["conversations"]) or "sin conversación de marca identificada"
        brand_bullets.append(f"{brand}: {data['mentions']} menciones, {movement}. Conversaciones principales: {conversation}. Temas: {topics}.")
    comp_bullets = [f"{x['name']} aparece como posible actor competitivo o adyacente en {x['count']} registros del periodo." for x in comp]
    if not comp_bullets: comp_bullets = ["No se identificaron competidores directos de cuidado personal o belleza en la evidencia disponible.", "La conversación del periodo está dominada por deporte y selección nacional, por lo que los actores visibles son adyacentes, no necesariamente competidores de nuestras marcas."]
    return {"week_start": min(d for _, d in dated if d.isocalendar()[:2] == latest_key).isoformat(), "title": "One Page semanal", "source_file": filename, "comparison": comparison, "metrics": {"current_mentions": len(current), "previous_mentions": len(previous), "top_conversation": trend_rows[0]["name"] if trend_rows else "Sin conversación dominante", "platforms": counter(current, "Fuente").most_common(5)}, "sections": [{"id": "culture", "title": "Qué fue tendencia esta semana", "prompt": "La conversación que movió el periodo", "insight": f"{trend_rows[0]['name']} fue la conversación con mayor volumen, con {trend_rows[0]['count']} menciones." if trend_rows else "No se identificó una conversación dominante.", "implication": "Este es el punto de partida de la lectura: antes de evaluar marcas, entendemos qué conversación tuvo escala.", "bullets": culture_bullets, "evidence": [f"{x['name']} · {x['count']} menciones · anterior: {x['previous']}" for x in trend_rows]}, {"id": "brands", "title": "Cómo impacta a nuestras marcas", "prompt": "Rexona, Pond’s y Dove por separado", "insight": "La relevancia no es igual para las tres marcas. La señal se desglosa por volumen, temas y presencia en el texto.", "implication": "La oportunidad depende de que cada marca tenga legitimidad para entrar en la conversación.", "bullets": brand_bullets, "evidence": []}, {"id": "pending", "title": "", "prompt": "", "insight": "", "implication": "", "bullets": [], "evidence": []}, {"id": "competition", "title": "Qué está haciendo la competencia", "prompt": "Posibles competidores y aprendizaje de categoría", "insight": "El análisis identifica actores que aparecen junto a las conversaciones del periodo y los convierte en señales competitivas.", "implication": "Estas señales sirven para observar quién está ganando presencia y qué tipo de respuesta está generando la categoría.", "bullets": comp_bullets, "evidence": []}], "raw_excerpt": _readable_source(text)[:6000]}

def _v2_text(row: dict) -> str:
    return " ".join(str(row.get(k) or "") for k in ["Tendencia", "Título", "Texto", "Temas", "Categorías automáticas", "Marcas en la imagen"])

def _v2_label(row: dict) -> str:
    low = _fold(_v2_text(row))
    if "juanfer" in low or "juan fernando quintero" in low or "quintero" in low:
        return "Juanfer Quintero y la Selección Colombia"
    if "dove" in low and any(x in low for x in ["serum", "hidrat", "crema", "piel", "body care"]):
        return "Dove y el cuidado de la piel"
    if "pond" in low and any(x in low for x in ["serum", "hidrat", "crema", "piel", "skincare"]):
        return "Pond’s y el cuidado de la piel"
    if "rexona" in low and any(x in low for x in ["desodor", "clinical", "antiperspir"]):
        return "Rexona y la protección corporal"
    if any(x in low for x in ["hidrat", "serum corporal", "crema corporal", "skincare", "cuidado de la piel"]):
        return "Hidratación y cuidado de la piel"
    if any(x in low for x in ["desodor", "antiperspir", "clinical"]):
        return "Desodorantes y protección corporal"
    if any(x in low for x in ["champú", "shampoo", "cabello", "pelo", "hair"]):
        return "Cuidado del cabello"
    if any(x in low for x in ["futbol", "fútbol", "seleccion", "deporte", "jugador"]):
        return "Deporte y cultura popular"
    if any(x in low for x in ["promocion", "precio", "descuento", "sorteo", "compra"]):
        return "Promociones y recomendación de producto"
    return "Otras conversaciones de cuidado personal"

def _v2_movement(current: int, previous: int, has_previous: bool) -> str:
    if not has_previous: return "sin comparación semanal"
    delta = current - previous
    if delta > 0: return f"subió {delta} menciones"
    if delta < 0: return f"bajó {abs(delta)} menciones"
    return "se mantuvo estable"

def _weekly_analysis_v2(text: str, filename: str) -> dict | None:
    records = _xlsx_records(text)
    dated = [(r, _date_value(r.get("Fecha"))) for r in records]
    dated = [(r, d) for r, d in dated if d]
    if not dated: return None
    periods = sorted({d.isocalendar()[:2] for _, d in dated})
    current_key = periods[-1]; previous_key = periods[-2] if len(periods) > 1 else None
    current = [r for r, d in dated if d.isocalendar()[:2] == current_key]
    previous = [r for r, d in dated if previous_key and d.isocalendar()[:2] == previous_key]
    current_counts = Counter(_v2_label(r) for r in current)
    previous_counts = Counter(_v2_label(r) for r in previous)
    conversation_rows = []
    for name, count in current_counts.most_common():
        old = previous_counts.get(name, 0)
        conversation_rows.append({"name": name, "current": count, "previous": old, "change": count-old, "movement": _v2_movement(count, old, bool(previous_key))})
    conversation_rows.sort(key=lambda x: (x["current"], x["change"]), reverse=True)
    named_rows = [x for x in conversation_rows if x["name"] != "Otras conversaciones de cuidado personal"]
    top = named_rows[0] if named_rows else (conversation_rows[0] if conversation_rows else None)
    week_label = f"Semana {current_key[1]} de {current_key[0]}"
    comparison = f"Se comparan {len(current)} menciones de {week_label} con {len(previous)} de la semana anterior." if previous_key else f"El archivo contiene {len(current)} menciones en {week_label}. No hay una semana anterior comparable."
    if top:
        executive = f"La conversación con mayor volumen fue {top['name']}, con {top['current']} menciones. {top['movement'].capitalize()} frente a la semana anterior." if previous_key else f"La conversación con mayor volumen fue {top['name']}, con {top['current']} menciones."
    else: executive = "No fue posible identificar conversaciones a partir de los campos disponibles."
    def brand_info(name, aliases):
        def matches(rows): return [r for r in rows if any(alias in _fold(_v2_text(r)) for alias in aliases)]
        now, old = matches(current), matches(previous)
        topics = Counter(t.strip() for r in now for t in re.split(r"[,|]", str(r.get("Temas") or "")) if t.strip())
        conversations = Counter(_v2_label(r) for r in now)
        change = len(now)-len(old)
        bullets = [f"{len(now)} menciones en la semana actual. {_v2_movement(len(now), len(old), bool(previous_key)).capitalize()}."]
        bullets.append(f"Conversaciones principales: {', '.join(f'{n} ({c})' for n,c in conversations.most_common(2)) or 'no se identificó una conversación específica' }.")
        bullets.append(f"Temas más frecuentes: {', '.join(n for n,_ in topics.most_common(3)) or 'sin tema dominante identificado'}.")
        return {"name": name, "mentions": len(now), "previous": len(old), "change": change, "sentiment": Counter(str(r.get("Sentimiento") or "") for r in now).most_common(3), "bullets": bullets, "evidence": [str(r.get("Título") or r.get("Texto") or "")[:220] for r in now[:5]]}
    brand_data = [brand_info("Rexona", ["rexona"]), brand_info("Pond’s", ["pond", "pond's", "pond’s"]), brand_info("Dove", ["dove"])]
    candidates = {"Nivea":"directo", "Neutrogena":"directo", "Garnier":"directo", "L’Oréal":"directo", "L'Oreal":"directo", "CeraVe":"directo", "Eucerin":"directo", "Vaseline":"directo", "Old Spice":"directo", "Axe":"directo", "Secret":"directo", "Adidas":"adyacente", "Nike":"adyacente", "Puma":"adyacente"}
    competitor_counts = Counter()
    for r in current:
        raw = _v2_text(r)
        for candidate in candidates:
            if re.search(rf"(?i)(?<![\w]){re.escape(candidate)}(?![\w])", raw): competitor_counts[candidate] += 1
    direct = [f"{n} aparece en {c} registros como posible competidor directo." for n,c in competitor_counts.most_common() if candidates[n] == "directo"]
    adjacent = [f"{n} aparece en {c} registros como actor adyacente, no necesariamente competidor de cuidado personal." for n,c in competitor_counts.most_common() if candidates[n] == "adyacente"]
    competition_bullets = direct[:5] or ["No se identificaron competidores directos de belleza o cuidado personal en este periodo."]
    competition_bullets += adjacent[:3]
    culture_bullets = [f"{x['name']}: {x['current']} menciones, {x['movement']}." for x in named_rows[:6]] or ["No se encontraron conversaciones analizables en los campos disponibles."]
    return {"week_start": min(d for _,d in dated if d.isocalendar()[:2] == current_key).isoformat(), "title":"One Page semanal", "source_file":filename, "comparison":comparison, "executive_takeaway":executive, "metrics":{"current_mentions":len(current), "previous_mentions":len(previous), "delta_mentions":len(current)-len(previous), "top_conversation":top["name"] if top else "Sin conversación identificable", "platforms":Counter(str(r.get("Fuente") or "") for r in current if r.get("Fuente")).most_common(5)}, "trend_table":conversation_rows[:10], "sections":[{"id":"culture","title":"Qué fue tendencia esta semana","prompt":"La conversación que movió el periodo","insight":executive,"implication":"Este capítulo establece qué conversación tuvo escala y cómo cambió frente a la semana anterior.","bullets":culture_bullets,"evidence":[f"{x['name']} · actual {x['current']} · anterior {x['previous']} · {x['movement']}" for x in conversation_rows[:10]]},{"id":"brands","title":"Cómo impacta a nuestras marcas","prompt":"Lectura separada para Rexona, Pond’s y Dove","insight":"La misma conversación no tiene el mismo significado para todas las marcas. La lectura se separa por presencia, temas y movimiento.","implication":"La marca debe entrar solo donde exista una relación observable con la conversación y un territorio legítimo.","bullets":[f"{b['name']}: {bullet}" for b in brand_data for bullet in b['bullets']],"brand_data":brand_data,"evidence":[]},{"id":"pending","title":"","prompt":"","insight":"","implication":"","bullets":[],"evidence":[]},{"id":"competition","title":"Qué hizo la categoría","prompt":"Competidores directos y actores adyacentes","insight":"La evidencia separa competidores de categoría de actores que solo aparecen en el contexto cultural de la semana.","implication":"El aprendizaje competitivo debe basarse en presencia de marca y relación con la categoría, no solo en aparecer en el mismo texto.","bullets":competition_bullets,"evidence":[]}],"raw_excerpt":_readable_source(text)[:6000]}

def classify_week(text: str, filename: str, week_start: str | None = None) -> dict:
    if text.startswith("__XLSX_JSON__"):
        result = _weekly_analysis_v2(text, filename)
        if result:
            if week_start: result["week_start"] = week_start
            return result
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
