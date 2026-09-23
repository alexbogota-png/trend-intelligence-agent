"""BigQuery persistence for Trend Intelligence Agent.

The repository is intentionally optional. When BigQuery environment variables
are absent, the application keeps using its local fallback for development.
"""

from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timezone
from typing import Any


def configured() -> bool:
    return bool(
        os.getenv("GCP_PROJECT_ID")
        and os.getenv("BQ_DATASET")
        and (
            os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")
            or os.getenv("GOOGLE_APPLICATION_CREDENTIALS_B64")
        )
    )


def _client():
    from google.cloud import bigquery
    from google.oauth2 import service_account

    raw = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON", "")
    if raw:
        info = json.loads(raw)
    else:
        encoded = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_B64", "")
        info = json.loads(base64.b64decode(encoded).decode("utf-8"))
    credentials = service_account.Credentials.from_service_account_info(info)
    return bigquery.Client(project=os.environ["GCP_PROJECT_ID"], credentials=credentials)


def _table(name: str) -> str:
    return f"`{os.environ['GCP_PROJECT_ID']}.{os.environ['BQ_DATASET']}.{name}`"


def _run(sql: str, params: list[tuple[str, str, Any]] | None = None):
    from google.cloud import bigquery

    client = _client()
    location = os.getenv("BQ_LOCATION") or None
    job_config = None
    if params:
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter(name, kind, value)
                for name, kind, value in params
            ]
        )
    return client.query(sql, location=location, job_config=job_config).result()


def ensure_tables() -> None:
    _run(
        f"""
        CREATE TABLE IF NOT EXISTS {_table('analysis_history')} (
          created_at TIMESTAMP,
          user_id STRING,
          source_file STRING,
          trend_name STRING,
          best_brand STRING,
          result JSON
        )
        """
    )
    _run(
        f"""
        CREATE TABLE IF NOT EXISTS {_table('weekly_pages')} (
          saved_at TIMESTAMP,
          user_id STRING,
          week_start STRING,
          title STRING,
          source_file STRING,
          sections JSON,
          raw_excerpt STRING
        )
        """
    )
    _run(
        f"""
        CREATE TABLE IF NOT EXISTS {_table('raw_monid_runs')} (
          run_id STRING,
          user_id STRING,
          provider STRING,
          endpoint STRING,
          status STRING,
          input_json JSON,
          output_json JSON,
          cost_usd NUMERIC,
          result_count INT64,
          created_at TIMESTAMP,
          started_at TIMESTAMP,
          completed_at TIMESTAMP,
          ingested_at TIMESTAMP
        )
        """
    )
    _run(
        f"""
        CREATE TABLE IF NOT EXISTS {_table('mentions')} (
          mention_id STRING,
          run_id STRING,
          user_id STRING,
          market STRING,
          keyword STRING,
          published_at TIMESTAMP,
          title STRING,
          author STRING,
          url STRING,
          views INT64,
          likes INT64,
          comments INT64,
          shares INT64,
          bookmarks INT64,
          hashtags JSON,
          raw_json JSON,
          loaded_at TIMESTAMP
        )
        """
    )


def save_history(*, user_id: str, source_file: str, trend_name: str, best_brand: str | None, result: dict[str, Any]) -> None:
    ensure_tables()
    errors = _client().insert_rows_json(
        f"{os.environ['GCP_PROJECT_ID']}.{os.environ['BQ_DATASET']}.analysis_history",
        [{
            "created_at": datetime.now(timezone.utc).isoformat(),
            "user_id": user_id,
            "source_file": source_file,
            "trend_name": trend_name,
            "best_brand": best_brand,
            "result": result,
        }],
    )
    if errors:
        raise RuntimeError(f"No se pudo guardar el historial en BigQuery: {errors}")


def list_history(user_id: str, limit: int = 50) -> list[dict[str, Any]]:
    ensure_tables()
    rows = _run(
        f"""
        SELECT created_at, user_id, source_file, trend_name, best_brand, result
        FROM {_table('analysis_history')}
        WHERE user_id = @user_id
        ORDER BY created_at DESC
        LIMIT @limit
        """,
        [("user_id", "STRING", user_id), ("limit", "INT64", limit)],
    )
    return [dict(row) for row in rows]


def save_weekly_page(page: dict[str, Any], user_id: str) -> dict[str, Any]:
    ensure_tables()
    row = {
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "user_id": user_id,
        "week_start": page.get("week_start", ""),
        "title": page.get("title", ""),
        "source_file": page.get("source_file", ""),
        "sections": page.get("sections", []),
        "raw_excerpt": page.get("raw_excerpt", ""),
    }
    errors = _client().insert_rows_json(
        f"{os.environ['GCP_PROJECT_ID']}.{os.environ['BQ_DATASET']}.weekly_pages",
        [row],
    )
    if errors:
        raise RuntimeError(f"No se pudo guardar el One Page en BigQuery: {errors}")
    return {**page, "user_id": user_id}


def list_weekly_pages(user_id: str, limit: int = 200) -> list[dict[str, Any]]:
    ensure_tables()
    rows = _run(
        f"""
        SELECT saved_at, user_id, week_start, title, source_file, sections, raw_excerpt
        FROM {_table('weekly_pages')}
        WHERE user_id = @user_id
        QUALIFY ROW_NUMBER() OVER (PARTITION BY week_start ORDER BY saved_at DESC) = 1
        ORDER BY week_start DESC
        LIMIT @limit
        """,
        [("user_id", "STRING", user_id), ("limit", "INT64", limit)],
    )
    return [dict(row) for row in rows]


def connection_status() -> dict[str, Any]:
    status: dict[str, Any] = {
        "configured": configured(),
        "project_id": os.getenv("GCP_PROJECT_ID", ""),
        "dataset": os.getenv("BQ_DATASET", ""),
        "location": os.getenv("BQ_LOCATION", ""),
        "reachable": False,
    }
    if not configured():
        return status
    try:
        _run("SELECT 1 AS connection_test")
        status["reachable"] = True
    except Exception as exc:
        status["error"] = str(exc)[:300]
    return status


def save_monid_result(*, user_id: str, run: dict[str, Any]) -> dict[str, Any]:
    """Persist one completed Monid run and its normalized TikTok records."""
    ensure_tables()
    run_id = str(run.get("runId") or run.get("run_id") or "")
    output = run.get("output") if isinstance(run.get("output"), list) else []
    if not run_id:
        raise RuntimeError("La respuesta de Monid no contiene runId.")

    existing = list(_run(
        f"SELECT run_id FROM {_table('raw_monid_runs')} WHERE run_id = @run_id LIMIT 1",
        [("run_id", "STRING", run_id)],
    ))
    if existing:
        return {"run_id": run_id, "status": run.get("status"), "already_ingested": True, "result_count": len(output)}

    client = _client()
    raw_table = f"{os.environ['GCP_PROJECT_ID']}.{os.environ['BQ_DATASET']}.raw_monid_runs"
    raw_errors = client.insert_rows_json(raw_table, [{
        "run_id": run_id,
        "user_id": user_id,
        "provider": run.get("provider"),
        "endpoint": run.get("endpoint"),
        "status": run.get("status"),
        "input_json": run.get("input", {}),
        "output_json": run.get("output", []),
        "cost_usd": (run.get("cost") or {}).get("value"),
        "result_count": run.get("resultCount") or len(output),
        "created_at": run.get("createdAt"),
        "started_at": run.get("startedAt"),
        "completed_at": run.get("completedAt"),
        "ingested_at": datetime.now(timezone.utc).isoformat(),
    }])
    if raw_errors:
        raise RuntimeError(f"No se pudo guardar el run de Monid: {raw_errors}")

    mention_rows = []
    body = ((run.get("input") or {}).get("body") or {})
    market = body.get("location", "")
    for item in output:
        channel = item.get("channel") if isinstance(item.get("channel"), dict) else {}
        mention_rows.append({
            "mention_id": str(item.get("id") or item.get("postId") or ""),
            "run_id": run_id,
            "user_id": user_id,
            "market": market,
            "keyword": item.get("keyword") or ", ".join(body.get("keywords") or []),
            "published_at": item.get("uploadedAt") or item.get("uploadedAtFormatted"),
            "title": item.get("title") or item.get("text") or "",
            "author": channel.get("username") or channel.get("name") or "",
            "url": item.get("postPage") or item.get("url") or "",
            "views": item.get("views") or 0,
            "likes": item.get("likes") or 0,
            "comments": item.get("comments") or 0,
            "shares": item.get("shares") or 0,
            "bookmarks": item.get("bookmarks") or 0,
            "hashtags": item.get("hashtags") or [],
            "raw_json": item,
            "loaded_at": datetime.now(timezone.utc).isoformat(),
        })
    if mention_rows:
        mention_errors = client.insert_rows_json(
            f"{os.environ['GCP_PROJECT_ID']}.{os.environ['BQ_DATASET']}.mentions",
            mention_rows,
        )
        if mention_errors:
            raise RuntimeError(f"No se pudieron guardar las menciones: {mention_errors}")
    return {"run_id": run_id, "status": run.get("status"), "already_ingested": False, "result_count": len(mention_rows)}
