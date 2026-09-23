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
