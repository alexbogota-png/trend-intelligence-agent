import json
import logging
import os
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from datetime import datetime, timezone, date, timedelta
from pathlib import Path
from fastapi import FastAPI, File, Form, UploadFile, HTTPException, Header
from pydantic import BaseModel
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from core.extractors import extract
from core.normalizer import normalize
from core.agent_graph import run_trend_agent, run_weekly_agent
from core.weekly import mentions_to_source
from core.llm import ask_weekly_chat
from core import bigquery_repository as bq
from core.monid import MonidError, get_run, start_run, start_provider_run

ROOT = Path(__file__).parent
app = FastAPI(title="Trend Intelligence Agent", version="0.1.0")
logger = logging.getLogger("trend_agent")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
RULES = json.loads((ROOT / "config/rules.json").read_text(encoding="utf-8"))
BRANDS = json.loads((ROOT / "config/brands.json").read_text(encoding="utf-8"))
HISTORY_FILE = ROOT / "data" / "history.json"
WEEKLY_FILE = ROOT / "data" / "weekly_pages.json"
MAX_FILE_SIZE = 25 * 1024 * 1024

@app.get("/")
def home(): return FileResponse(ROOT / "static/index.html")

@app.get("/api/brands")
def brands(): return [{"id": b["id"], "name": b["name"]} for b in BRANDS]

@app.get("/api/config")
def public_config(): return {"supabase_url": os.getenv("SUPABASE_URL", ""), "supabase_anon_key": os.getenv("SUPABASE_ANON_KEY", "")}

@app.get("/api/storage/status")
def storage_status(authorization: str | None = Header(default=None)):
    require_user(authorization)
    return bq.connection_status()

def require_user(authorization: str | None):
    if not authorization or not authorization.lower().startswith("bearer "): raise HTTPException(401, "Debes iniciar sesión.")
    url, key = os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_ANON_KEY")
    if not url or not key: raise HTTPException(500, "Supabase no está configurado en el servidor.")
    req = Request(f"{url.rstrip('/')}/auth/v1/user", headers={"apikey": key, "Authorization": authorization})
    try:
        with urlopen(req, timeout=8) as response: return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, ValueError): raise HTTPException(401, "La sesión no es válida o ha expirado.")

@app.get("/api/history")
def history(authorization: str | None = Header(default=None)):
    user = require_user(authorization)
    if bq.configured():
        try: return bq.list_history(user.get("id"))
        except Exception as exc: raise HTTPException(503, f"BigQuery no está disponible: {str(exc)[:240]}")
    if not HISTORY_FILE.exists(): return []
    return [x for x in json.loads(HISTORY_FILE.read_text(encoding="utf-8")) if x.get("user_id") == user.get("id")][-50:][::-1]

class WeeklyPage(BaseModel):
    week_start: str
    title: str
    source_file: str = ""
    sections: list[dict]
    raw_excerpt: str = ""

class MonidRunRequest(BaseModel):
    keywords: list[str]
    market: str = "CO"
    sort_type: str = "DATE_POSTED"
    max_items: int = 50

class WeeklyBQRequest(BaseModel):
    market: str = "CO"
    week_start: str
    week_end: str = ""

class WeeklyChatRequest(BaseModel):
    market: str = "CO"
    week_start: str
    question: str
    messages: list[dict] = []

class TrendRadarRequest(BaseModel):
    market: str = "CO"
    target_date: str

class TrendRadarEnrichRequest(BaseModel):
    market: str = "CO"
    target_date: str
    hashtags: list[str]


def _mention_date(value: object) -> date | None:
    raw = str(value or "")[:10]
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None

@app.post("/api/trends/radar/run")
def trend_radar_run(request: TrendRadarRequest, authorization: str | None = Header(default=None)):
    user = require_user(authorization)
    try:
        date.fromisoformat(request.target_date)
    except ValueError:
        raise HTTPException(400, "target_date debe tener formato YYYY-MM-DD.")
    if not bq.configured():
        raise HTTPException(503, "BigQuery no está configurado en el servidor.")
    try:
        hashtag_run = start_provider_run(
            provider="tikhub",
            endpoint="/api/v1/tiktok/ads/get_trends_hashtag_list",
            input_body={"country_code": request.market.upper(), "time_range": 7, "page": 1, "limit": 100},
        )
        top_run = start_provider_run(
            provider="tikhub",
            endpoint="/api/v1/tiktok/ads/get_top_contents_list",
            input_body={"country_code": request.market.upper(), "period_dimension": 3, "period_end_timestamp": int(datetime.fromisoformat(request.target_date + "T23:59:59").replace(tzinfo=timezone.utc).timestamp()), "order_by_metric": 2, "organic_only": True, "page": 1, "limit": 100, "content_label_ids": ""},
        )
        for run in (hashtag_run, top_run):
            bq.save_trend_started(user_id=user.get("id"), market=request.market.upper(), target_date=request.target_date, run=run)
        return {"target_date": request.target_date, "runs": [hashtag_run, top_run]}
    except MonidError as exc:
        raise HTTPException(502, str(exc))
    except Exception as exc:
        logger.exception("Trend radar start error")
        raise HTTPException(503, f"No se pudo iniciar el radar: {str(exc)[:240]}")

@app.get("/api/trends/radar/run/{run_id}")
def trend_radar_run_status(run_id: str, target_date: str, authorization: str | None = Header(default=None)):
    user = require_user(authorization)
    try:
        result = get_run(run_id)
        if str(result.get("status", "")).upper() == "COMPLETED":
            endpoint = str(result.get("endpoint") or "")
            if endpoint.endswith("tiktok-scraper"):
                ingested = bq.save_monid_result(user_id=user.get("id"), run=result)
            else:
                ingested = bq.save_trend_result(user_id=user.get("id"), market="CO", target_date=target_date, run=result)
            return {"run": result, "ingested": ingested}
        return {"run": result, "ingested": None}
    except MonidError as exc:
        raise HTTPException(502, str(exc))
    except Exception as exc:
        logger.exception("Trend radar status error")
        raise HTTPException(503, f"No se pudo consultar el radar: {str(exc)[:240]}")

@app.post("/api/trends/radar/enrich")
def trend_radar_enrich(request: TrendRadarEnrichRequest, authorization: str | None = Header(default=None)):
    user = require_user(authorization)
    hashtags = [str(item).strip().lstrip("#") for item in request.hashtags if str(item).strip()][:20]
    if not hashtags:
        raise HTTPException(400, "No hay hashtags para enriquecer.")
    try:
        date.fromisoformat(request.target_date)
        run = start_provider_run(
            provider="apify",
            endpoint="/apidojo/tiktok-scraper",
            input_body={"keywords": hashtags, "sortType": "DATE_POSTED", "location": request.market.upper(), "maxItems": 100, "includeSearchKeywords": True},
        )
        bq.save_trend_started(user_id=user.get("id"), market=request.market.upper(), target_date=request.target_date, run=run)
        return run
    except ValueError:
        raise HTTPException(400, "target_date debe tener formato YYYY-MM-DD.")
    except MonidError as exc:
        raise HTTPException(502, str(exc))
    except Exception as exc:
        logger.exception("Trend radar enrichment start error")
        raise HTTPException(503, f"No se pudo enriquecer el radar: {str(exc)[:240]}")

@app.get("/api/trends/radar")
def trend_radar(market: str = "CO", target_date: str = "", authorization: str | None = Header(default=None)):
    user = require_user(authorization)
    try:
        target = target_date or bq.latest_trend_date(user_id=user.get("id"), market=market.upper()) or (date.today() - timedelta(days=1)).isoformat()
        date.fromisoformat(target)
        result = bq.get_trend_radar(user_id=user.get("id"), market=market.upper(), target_date=target)
        result["latest_available_date"] = target
        return result
    except ValueError:
        raise HTTPException(400, "target_date debe tener formato YYYY-MM-DD.")
    except Exception as exc:
        logger.exception("Trend radar read error")
        raise HTTPException(503, f"No se pudo leer el radar: {str(exc)[:240]}")

def _to_number(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0

def _chat_visual(records: list[dict]) -> dict:
    """Build a small evidence graphic from stored records, without LLM-generated numbers."""
    totals = {
        "Menciones": len(records),
        "Vistas": int(sum(_to_number(row.get("views")) for row in records)),
        "Interacciones": int(sum(
            _to_number(row.get("likes")) + _to_number(row.get("comments")) + _to_number(row.get("shares"))
            for row in records
        )),
    }
    topics: dict[str, int] = {}
    for row in records:
        raw = str(row.get("keyword") or row.get("title") or "").strip()
        for item in raw.replace(";", ",").split(","):
            label = item.strip()
            if label:
                topics[label] = topics.get(label, 0) + 1
    topic_items = sorted(topics.items(), key=lambda pair: (-pair[1], pair[0].lower()))[:5]
    bars = [{"label": label, "value": count} for label, count in topic_items]
    return {
        "title": "Señales observadas",
        "metrics": [{"label": label, "value": value} for label, value in totals.items()],
        "bars": bars,
        "note": "Cifras calculadas directamente sobre la evidencia almacenada en BigQuery.",
    }

def _chat_ranking(records: list[dict], question: str) -> list[dict]:
    ranking_terms = ("top", "ranking", "más interacción", "mas interacción", "mejor desempeño", "mejor desempeno")
    if not any(term in question.lower() for term in ranking_terms):
        return []
    ranked = []
    for row in records:
        likes = int(_to_number(row.get("likes")))
        comments = int(_to_number(row.get("comments")))
        shares = int(_to_number(row.get("shares")))
        ranked.append({
            "title": str(row.get("title") or "Sin título"),
            "author": str(row.get("author") or "Sin autor"),
            "published_at": str(row.get("published_at") or "")[:10],
            "likes": likes,
            "comments": comments,
            "shares": shares,
            "interactions": likes + comments + shares,
            "url": str(row.get("url") or ""),
        })
    return sorted(ranked, key=lambda row: (-row["interactions"], -row["likes"], row["title"]))[:5]

def _chat_answer_text(answer: dict | str | None) -> str:
    """Keep a readable fallback for older frontend deployments."""
    if isinstance(answer, str):
        return answer
    if not isinstance(answer, dict):
        return "No se pudo construir una respuesta estructurada."
    parts = []
    if answer.get("respuesta_directa"):
        parts.append(f"Respuesta directa\n{answer['respuesta_directa']}")
    for key, title in (("evidencia", "Evidencia"), ("interpretacion", "Interpretación"), ("accion", "Acción sugerida")):
        items = answer.get(key) or []
        if items:
            parts.append(title + "\n" + "\n".join(f"• {item}" for item in items))
    if answer.get("nivel_evidencia"):
        parts.append(f"Nivel de evidencia\n{answer['nivel_evidencia']}")
    return "\n\n".join(parts)

@app.post("/api/monid/run")
def monid_run(request: MonidRunRequest, authorization: str | None = Header(default=None)):
    user = require_user(authorization)
    keywords = [item.strip() for item in request.keywords if item and item.strip()]
    if not keywords: raise HTTPException(400, "Debes enviar al menos una keyword.")
    if len(keywords) > 20: raise HTTPException(400, "Puedes enviar máximo 20 keywords por extracción.")
    if request.max_items < 1 or request.max_items > 500: raise HTTPException(400, "max_items debe estar entre 1 y 500.")
    try:
        result = start_run(keywords=keywords, market=request.market.upper(), sort_type=request.sort_type, max_items=request.max_items)
        if bq.configured(): bq.save_monid_started(user_id=user.get("id"), run=result)
        return result
    except MonidError as exc: raise HTTPException(502, str(exc))
    except Exception as exc:
        logger.exception("BigQuery preparation error before Monid run persistence")
        raise HTTPException(503, f"Monid respondió, pero no se pudo preparar BigQuery: {str(exc)[:300]}")

@app.get("/api/monid/run/{run_id}")
def monid_run_status(run_id: str, authorization: str | None = Header(default=None)):
    user = require_user(authorization)
    try:
        result = get_run(run_id)
        status = str(result.get("status", "")).upper()
        ingested = None
        if status == "COMPLETED" and bq.configured():
            ingested = bq.save_monid_result(user_id=user.get("id"), run=result)
        return {"run": result, "ingested": ingested}
    except MonidError as exc:
        logger.error("Monid status error for run %s: %s", run_id, exc)
        raise HTTPException(502, str(exc))
    except Exception as exc:
        logger.exception("BigQuery ingestion error for Monid run %s", run_id)
        raise HTTPException(503, f"No se pudo guardar el resultado en BigQuery: {str(exc)[:240]}")

@app.post("/api/weekly/analyze-from-bigquery")
def weekly_analyze_from_bigquery(request: WeeklyBQRequest, authorization: str | None = Header(default=None)):
    user = require_user(authorization)
    try:
        current_start = date.fromisoformat(request.week_start)
        current_end = date.fromisoformat(request.week_end) if request.week_end else current_start + timedelta(days=6)
    except ValueError: raise HTTPException(400, "week_start y week_end deben tener formato YYYY-MM-DD.")
    previous_end = current_start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=6)
    if not bq.configured(): raise HTTPException(503, "BigQuery no está configurado en el servidor.")
    try:
        cached = bq.get_weekly_analysis(user_id=user.get("id"), market=request.market.upper(), week_start=current_start.isoformat(), week_end=current_end.isoformat())
        if cached:
            return {**cached, "from_cache": True}
        records = bq.list_mentions(
            market=request.market.upper(),
            week_start=current_start.isoformat(),
            week_end=current_end.isoformat(),
            previous_week_start=previous_start.isoformat(),
            previous_week_end=previous_end.isoformat(),
        )
        current_records = [
            record for record in records
            if (published := _mention_date(record.get("published_at")))
            and current_start <= published <= current_end
        ]
        if not current_records:
            raise HTTPException(404, f"No hay menciones en la semana seleccionada ({current_start.isoformat()} a {current_end.isoformat()}).")
        page = run_weekly_agent(mentions_to_source(records), f"BigQuery · {request.market.upper()}", current_start.isoformat())
        page["market"] = request.market.upper()
        page["period"] = {"week_start": current_start.isoformat(), "week_end": current_end.isoformat(), "previous_week_start": previous_start.isoformat(), "previous_week_end": previous_end.isoformat()}
        page["data_source"] = "BigQuery"
        bq.save_weekly_analysis(user_id=user.get("id"), market=request.market.upper(), week_start=current_start.isoformat(), week_end=current_end.isoformat(), previous_week_start=previous_start.isoformat(), previous_week_end=previous_end.isoformat(), analysis=page)
        return {**page, "from_cache": False}
    except HTTPException: raise
    except Exception as exc:
        logger.exception("BigQuery weekly analysis error")
        raise HTTPException(503, f"No se pudo analizar desde BigQuery: {str(exc)[:240]}")

@app.post("/api/weekly/chat")
def weekly_chat(request: WeeklyChatRequest, authorization: str | None = Header(default=None)):
    user = require_user(authorization)
    question = request.question.strip()
    if not question:
        raise HTTPException(400, "Escribe una pregunta.")
    try:
        current_start = date.fromisoformat(request.week_start)
    except ValueError:
        raise HTTPException(400, "week_start debe tener formato YYYY-MM-DD.")
    current_end = current_start + timedelta(days=6)
    previous_end = current_start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=6)
    if not bq.configured():
        raise HTTPException(503, "BigQuery no está configurado en el servidor.")
    try:
        market = request.market.upper()
        page = bq.get_weekly_analysis(
            user_id=user.get("id"), market=market,
            week_start=current_start.isoformat(), week_end=current_end.isoformat(),
        )
        records = bq.list_mentions(
            market=market,
            week_start=current_start.isoformat(), week_end=current_end.isoformat(),
            previous_week_start=previous_start.isoformat(), previous_week_end=previous_end.isoformat(),
        )
        chat_records = [
            record for record in records
            if (published := _mention_date(record.get("published_at")))
            and current_start <= published <= current_end
        ] or records
        if not page:
            current_records = [
                record for record in records
                if (published := _mention_date(record.get("published_at")))
                and current_start <= published <= current_end
            ]
            if not current_records:
                raise HTTPException(404, "No hay evidencia para la semana seleccionada.")
            page = run_weekly_agent(mentions_to_source(records), f"BigQuery · {market}", current_start.isoformat())
            page["market"] = market
            page["period"] = {
                "week_start": current_start.isoformat(),
                "week_end": current_end.isoformat(),
                "previous_week_start": previous_start.isoformat(),
                "previous_week_end": previous_end.isoformat(),
            }
            page["data_source"] = "BigQuery"
            bq.save_weekly_analysis(
                user_id=user.get("id"), market=market,
                week_start=current_start.isoformat(), week_end=current_end.isoformat(),
                previous_week_start=previous_start.isoformat(), previous_week_end=previous_end.isoformat(),
                analysis=page,
            )
        radar = bq.get_trend_radar(user_id=user.get("id"), market=market, target_date=current_start.isoformat())
        answer, error = ask_weekly_chat(question, {**page, "trend_radar": radar}, chat_records, request.messages)
        if error:
            raise HTTPException(503, f"No se pudo consultar el cerebro analítico: {error[:240]}")
        ranking = _chat_ranking(chat_records, question)
        return {
            "answer": _chat_answer_text(answer),
            "structured_answer": answer,
            "ranking": ranking,
            "visual": _chat_visual(chat_records),
            "week_start": current_start.isoformat(),
            "market": market,
            "data_source": "BigQuery",
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Weekly chat error")
        raise HTTPException(503, f"No se pudo responder la pregunta: {str(exc)[:240]}")

def _weekly_pages(user_id: str) -> list[dict]:
    if not WEEKLY_FILE.exists(): return []
    try: return [x for x in json.loads(WEEKLY_FILE.read_text(encoding="utf-8")) if x.get("user_id") == user_id]
    except (OSError, ValueError): return []

@app.get("/api/weekly")
def weekly_list(authorization: str | None = Header(default=None)):
    user = require_user(authorization)
    if bq.configured():
        try: return bq.list_weekly_pages(user.get("id"))
        except Exception as exc: raise HTTPException(503, f"BigQuery no está disponible: {str(exc)[:240]}")
    return sorted(_weekly_pages(user.get("id")), key=lambda x: x.get("week_start", ""), reverse=True)

@app.post("/api/weekly/draft")
async def weekly_draft(file: UploadFile = File(...), week_start: str = Form(default=""), authorization: str | None = Header(default=None)):
    require_user(authorization)
    data = await file.read()
    if len(data) > MAX_FILE_SIZE: raise HTTPException(413, "El archivo supera el máximo permitido de 25 MB.")
    try: raw = extract(data, file.filename or "raw-data")
    except Exception as e: raise HTTPException(400, str(e))
    return run_weekly_agent(raw, file.filename or "raw-data", week_start or None)

@app.put("/api/weekly")
def weekly_save(page: WeeklyPage, authorization: str | None = Header(default=None)):
    user = require_user(authorization)
    if bq.configured():
        try: return bq.save_weekly_page(page.model_dump(), user.get("id"))
        except Exception as exc: raise HTTPException(503, f"No se pudo guardar en BigQuery: {str(exc)[:240]}")
    pages = []
    if WEEKLY_FILE.exists():
        try: pages = json.loads(WEEKLY_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError): pages = []
    pages = [x for x in pages if not (x.get("user_id") == user.get("id") and x.get("week_start") == page.week_start)]
    item = page.model_dump(); item["user_id"] = user.get("id"); pages.append(item)
    try:
        WEEKLY_FILE.parent.mkdir(exist_ok=True)
        WEEKLY_FILE.write_text(json.dumps(pages[-200:], ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError: raise HTTPException(503, "El guardado local no está disponible en este servidor. Usa una base de datos para persistir las semanas.")
    return item

@app.post("/api/analyze")
async def analyze(file: UploadFile = File(...), brand_id: str = Form(...), authorization: str | None = Header(default=None)):
    user = require_user(authorization)
    selected = BRANDS if brand_id == "all" else [b for b in BRANDS if b["id"] == brand_id]
    if not selected: raise HTTPException(400, "Marca no encontrada.")
    data = await file.read()
    if len(data) > MAX_FILE_SIZE: raise HTTPException(413, "El archivo supera el máximo permitido de 25 MB.")
    try: trend = normalize(extract(data, file.filename or "archivo"), file.filename or "archivo", BRANDS)
    except Exception as e: raise HTTPException(400, str(e))
    response = run_trend_agent(trend, selected, RULES, file.filename or "archivo")
    if bq.configured():
        try:
            bq.save_history(
                user_id=user.get("id"),
                source_file=file.filename or "archivo",
                trend_name=trend["name"],
                best_brand=response.get("brand", response.get("best_brand")),
                result=response,
            )
        except Exception as exc: raise HTTPException(503, f"No se pudo guardar el historial en BigQuery: {str(exc)[:240]}")
    # El sistema de archivos de Vercel no es un almacenamiento persistente.
    # El resultado del análisis no debe fallar si no se puede guardar el historial local.
    try:
        HISTORY_FILE.parent.mkdir(exist_ok=True)
        history = json.loads(HISTORY_FILE.read_text(encoding="utf-8")) if HISTORY_FILE.exists() else []
        history.append({"created_at": datetime.now(timezone.utc).isoformat(), "user_id": user.get("id"), "source_file": file.filename, "trend_name": trend["name"], "best_brand": response.get("brand", response.get("best_brand")), "result": response})
        HISTORY_FILE.write_text(json.dumps(history[-200:], ensure_ascii=False, indent=2), encoding="utf-8")
    except (OSError, ValueError):
        pass
    return response
