import json
from datetime import datetime, timezone
from pathlib import Path
from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from core.extractors import extract
from core.normalizer import normalize
from core.scoring import evaluate
from core.llm import interpret

ROOT = Path(__file__).parent
app = FastAPI(title="Trend Intelligence Agent", version="0.1.0")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
RULES = json.loads((ROOT / "config/rules.json").read_text(encoding="utf-8"))
BRANDS = json.loads((ROOT / "config/brands.json").read_text(encoding="utf-8"))
HISTORY_FILE = ROOT / "data" / "history.json"
MAX_FILE_SIZE = 25 * 1024 * 1024

@app.get("/")
def home(): return FileResponse(ROOT / "static/index.html")

@app.get("/api/brands")
def brands(): return [{"id": b["id"], "name": b["name"]} for b in BRANDS]

@app.get("/api/history")
def history():
    if not HISTORY_FILE.exists(): return []
    return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))[-50:][::-1]

@app.post("/api/analyze")
async def analyze(file: UploadFile = File(...), brand_id: str = Form(...)):
    selected = BRANDS if brand_id == "all" else [b for b in BRANDS if b["id"] == brand_id]
    if not selected: raise HTTPException(400, "Marca no encontrada.")
    data = await file.read()
    if len(data) > MAX_FILE_SIZE: raise HTTPException(413, "El archivo supera el máximo permitido de 25 MB.")
    try: trend = normalize(extract(data, file.filename or "archivo"), file.filename or "archivo", BRANDS)
    except Exception as e: raise HTTPException(400, str(e))
    analyses = []
    for brand in selected:
        result = evaluate(trend, brand, RULES); result.update({"trend": trend, "brand": brand["name"], "source_file": file.filename, "llm_used": False})
        interpretation, error = interpret(result)
        if interpretation: result.update({"llm_interpretation": interpretation, "llm_used": True})
        if error: result["llm_error"] = error
        average = (result["brand_fit"] + result["actionability"]) / 2
        result["recommendation"] = "HIGH" if average >= 75 else "MEDIUM" if average >= 55 else "LOW"
        analyses.append(result)
    analyses.sort(key=lambda x: (x["brand_fit"] + x["actionability"]) / 2, reverse=True)
    response = analyses[0] if len(analyses) == 1 else {"trend": trend, "source_file": file.filename, "comparison": [{k: a[k] for k in ["brand", "brand_fit", "actionability", "recommendation"]} for a in analyses], "best_brand": analyses[0]["brand"], "best_analysis": analyses[0]}
    HISTORY_FILE.parent.mkdir(exist_ok=True)
    history = json.loads(HISTORY_FILE.read_text(encoding="utf-8")) if HISTORY_FILE.exists() else []
    history.append({"created_at": datetime.now(timezone.utc).isoformat(), "source_file": file.filename, "trend_name": trend["name"], "best_brand": response.get("brand", response.get("best_brand")), "result": response})
    HISTORY_FILE.write_text(json.dumps(history[-200:], ensure_ascii=False, indent=2), encoding="utf-8")
    return response
