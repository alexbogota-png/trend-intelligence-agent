import json, os

def interpret(result: dict) -> tuple[str | None, str | None]:
    if not os.getenv("OPENAI_API_KEY"): return None, None
    try:
        from openai import OpenAI
        prompt = f"Interpreta estos resultados en español sin cambiar los scores ni inventar evidencia. Devuelve una recomendación breve con implicaciones y riesgos. Datos: {json.dumps(result, ensure_ascii=False)}"
        return OpenAI().responses.create(model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"), input=prompt).output_text, None
    except Exception as e: return None, str(e)
