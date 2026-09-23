import json
import os
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from datetime import datetime, timezone
from pathlib import Path
from fastapi import FastAPI, File, Form, UploadFile, HTTPException, Header
from pydantic import BaseModel
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from core.extractors import extract
from core.normalizer import normalize
from core.agent_graph import run_trend_agent, run_weekly_agent
from core import bigquery_repository as bq
from core.monid import MonidError, get_run, start_run

ROOT = Path(__file__).parent
app = FastAPI(title="Trend Intelligence Agent", version="0.1.0")
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

@app.post("/api/monid/run")
def monid_run(request: MonidRunRequest, authorization: str | None = Header(default=None)):
    require_user(authorization)
    keywords = [item.strip() for item in request.keywords if item and item.strip()]
    if not keywords: raise HTTPException(400, "Debes enviar al menos una keyword.")
    if len(keywords) > 20: raise HTTPException(400, "Puedes enviar máximo 20 keywords por extracción.")
    if request.max_items < 1 or request.max_items > 500: raise HTTPException(400, "max_items debe estar entre 1 y 500.")
    try:
        return start_run(keywords=keywords, market=request.market.upper(), sort_type=request.sort_type, max_items=request.max_items)
    except MonidError as exc: raise HTTPException(502, str(exc))

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
    except MonidError as exc: raise HTTPException(502, str(exc))
    except Exception as exc: raise HTTPException(503, f"No se pudo guardar el resultado en BigQuery: {str(exc)[:240]}")

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
