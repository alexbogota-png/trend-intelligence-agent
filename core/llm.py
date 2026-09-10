import json, os

def interpret(result: dict) -> tuple[str | None, str | None]:
    if not os.getenv("OPENAI_API_KEY"): return None, None
    try:
        from openai import OpenAI
        prompt = f"Interpreta estos resultados en español sin cambiar los scores ni inventar evidencia. Devuelve una recomendación breve con implicaciones y riesgos. Datos: {json.dumps(result, ensure_ascii=False)}"
        return OpenAI().responses.create(model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"), input=prompt).output_text, None
    except Exception as e: return None, str(e)

def summarize_weekly(page: dict) -> tuple[dict | None, str | None]:
    if not os.getenv("OPENAI_API_KEY"): return None, None
    try:
        from openai import OpenAI
        prompt = f"""Resume este one page semanal en español. Usa únicamente la evidencia entregada; no inventes hechos, cifras, marcas ni aprendizajes. Devuelve JSON válido con una clave sections, cuyo valor sea una lista de objetos con id e insight. Mantén la sección pending como pendiente. Escribe insights ejecutivos, claros y breves. Datos: {json.dumps(page, ensure_ascii=False)}"""
        output = OpenAI().responses.create(model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"), input=prompt).output_text
        parsed = json.loads(output)
        return {str(x.get("id")): str(x.get("insight", "")) for x in parsed.get("sections", []) if x.get("id")}, None
    except Exception as e: return None, str(e)
