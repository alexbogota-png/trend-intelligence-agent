import json, os


def _structured_interpret(result: dict) -> str | None:
    """Use LangChain structured output when available, with a safe fallback."""
    try:
        from pydantic import BaseModel, Field
        from langchain_openai import ChatOpenAI

        class Interpretation(BaseModel):
            headline: str
            recommendation: str
            risks: list[str] = Field(default_factory=list)
            activation: str
            confidence: str

        model = ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            temperature=0,
        ).with_structured_output(Interpretation)
        prompt = (
            "Interpreta estos resultados en español. Usa únicamente la evidencia entregada. "
            "No cambies scores, no inventes cifras ni presentes hipótesis como hechos. "
            "Devuelve una lectura breve para un equipo de marca. Datos: "
            + json.dumps(result, ensure_ascii=False)
        )
        output = model.invoke(prompt)
        return json.dumps(output.model_dump(), ensure_ascii=False)
    except Exception:
        return None

def interpret(result: dict) -> tuple[str | None, str | None]:
    if not os.getenv("OPENAI_API_KEY"): return None, None
    try:
        structured = _structured_interpret(result)
        if structured: return structured, None
        from openai import OpenAI
        prompt = f"Interpreta estos resultados en español sin cambiar los scores ni inventar evidencia. Devuelve una recomendación breve con implicaciones y riesgos. Datos: {json.dumps(result, ensure_ascii=False)}"
        return OpenAI().responses.create(model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"), input=prompt).output_text, None
    except Exception as e: return None, str(e)

def summarize_weekly(page: dict) -> tuple[dict | None, str | None]:
    if not os.getenv("OPENAI_API_KEY"): return None, None
    try:
        try:
            from pydantic import BaseModel
            from langchain_openai import ChatOpenAI

            class WeeklySummary(BaseModel):
                sections: list[dict]

            model = ChatOpenAI(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                temperature=0,
            ).with_structured_output(WeeklySummary)
            prompt = (
                "Resume este one page semanal en español. Usa únicamente la evidencia entregada. "
                "No inventes hechos, cifras, marcas ni aprendizajes. Mantén la sección pending vacía. "
                "Devuelve objetos con id e insight. Datos: "
                + json.dumps(page, ensure_ascii=False)
            )
            parsed = model.invoke(prompt).model_dump()
            return {str(x.get("id")): str(x.get("insight", "")) for x in parsed.get("sections", []) if x.get("id")}, None
        except Exception:
            pass
        from openai import OpenAI
        prompt = f"""Resume este one page semanal en español. Usa únicamente la evidencia entregada; no inventes hechos, cifras, marcas ni aprendizajes. Devuelve JSON válido con una clave sections, cuyo valor sea una lista de objetos con id e insight. Mantén la sección pending como pendiente. Escribe insights ejecutivos, claros y breves. Datos: {json.dumps(page, ensure_ascii=False)}"""
        output = OpenAI().responses.create(model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"), input=prompt).output_text
        parsed = json.loads(output)
        return {str(x.get("id")): str(x.get("insight", "")) for x in parsed.get("sections", []) if x.get("id")}, None
    except Exception as e: return None, str(e)


def ask_weekly_chat(question: str, page: dict, evidence: list[dict]) -> tuple[str | None, str | None]:
    """Answer a question using only the selected week's One Page and evidence."""
    if not os.getenv("OPENAI_API_KEY"):
        return None, "OPENAI_API_KEY no está configurada en el servidor."
    try:
        from openai import OpenAI

        compact_evidence = [{
            "fecha": str(row.get("published_at") or ""),
            "titulo": str(row.get("title") or ""),
            "keyword": str(row.get("keyword") or ""),
            "autor": str(row.get("author") or ""),
            "vistas": row.get("views", 0),
            "likes": row.get("likes", 0),
            "comentarios": row.get("comments", 0),
            "url": str(row.get("url") or ""),
        } for row in evidence[:60]]
        prompt = (
            "Actúa como el cerebro analítico de Trend Intelligence Agent. "
            "Responde en español usando únicamente el One Page y la evidencia entregada. "
            "Distingue hechos observados de inferencias. No inventes cifras, conversaciones, marcas ni fuentes. "
            "Si la evidencia no alcanza, dilo claramente. Responde con una conclusión breve y bullets accionables. "
            "Pregunta: " + question + "\n\nOne Page: " + json.dumps(page, ensure_ascii=False) +
            "\n\nEvidencia: " + json.dumps(compact_evidence, ensure_ascii=False, default=str)
        )
        output = OpenAI().responses.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            input=prompt,
        ).output_text
        return output, None
    except Exception as e:
        return None, str(e)
