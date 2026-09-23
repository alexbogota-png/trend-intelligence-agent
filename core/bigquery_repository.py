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


def _published_timestamp(item: dict[str, Any]) -> str | None:
    value = item.get("uploadedAt") or item.get("uploadedAtFormatted")
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()
    raw = str(value).strip()
    if raw.isdigit():
        return datetime.fromtimestamp(int(raw), tz=timezone.utc).isoformat()
    return raw


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


def _append_rows(table_name: str, rows: list[dict[str, Any]]) -> None:
    """Append rows with a BigQuery load job instead of streaming inserts.

    Load jobs work with projects that do not have streaming-insert access or
    billing enabled for the streaming API.
    """
    if not rows:
        return
    from google.cloud import bigquery

    client = _client()
    table_id = f"{os.environ['GCP_PROJECT_ID']}.{os.environ['BQ_DATASET']}.{table_name}"
    job_config = bigquery.LoadJobConfig(write_disposition=bigquery.WriteDisposition.WRITE_APPEND)
    job = client.load_table_from_json(rows, table_id, job_config=job_config)
    job.result()
    if job.errors:
        raise RuntimeError(f"No se pudieron cargar filas en {table_name}: {job.errors}")


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
    _run(
        f"""
        CREATE TABLE IF NOT EXISTS {_table('weekly_comparisons')} (
          analysis_key STRING,
          user_id STRING,
          market STRING,
          week_start DATE,
          week_end DATE,
          previous_week_start DATE,
          previous_week_end DATE,
          analysis JSON,
          generated_at TIMESTAMP
        )
        """
    )


def save_monid_started(*, user_id: str, run: dict[str, Any]) -> None:
    ensure_tables()
    run_id = str(run.get("runId") or run.get("run_id") or "")
    if not run_id:
        raise RuntimeError("Monid no devolvió un runId.")
    existing = list(_run(
        f"SELECT run_id FROM {_table('raw_monid_runs')} WHERE run_id = @run_id LIMIT 1",
        [("run_id", "STRING", run_id)],
    ))
    if existing:
        return
    _append_rows("raw_monid_runs", [{
            "run_id": run_id,
            "user_id": user_id,
            "provider": run.get("provider", "apify"),
            "endpoint": run.get("endpoint", "/apidojo/tiktok-scraper"),
            "status": run.get("status", "RUNNING"),
            "input_json": run.get("input", {}),
            "created_at": run.get("createdAt"),
        }])


def save_history(*, user_id: str, source_file: str, trend_name: str, best_brand: str | None, result: dict[str, Any]) -> None:
    ensure_tables()
    _append_rows("analysis_history", [{
            "created_at": datetime.now(timezone.utc).isoformat(),
            "user_id": user_id,
            "source_file": source_file,
            "trend_name": trend_name,
            "best_brand": best_brand,
            "result": result,
        }])


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
    _append_rows("weekly_pages", [row])
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
        f"SELECT run_id, ingested_at FROM {_table('raw_monid_runs')} WHERE run_id = @run_id LIMIT 1",
        [("run_id", "STRING", run_id)],
    ))
    if existing and dict(existing[0]).get("ingested_at"):
        return {"run_id": run_id, "status": run.get("status"), "already_ingested": True, "result_count": len(output)}

    _run(
        f"""
        UPDATE {_table('raw_monid_runs')}
        SET status = @status,
            input_json = PARSE_JSON(@input_json),
            output_json = PARSE_JSON(@output_json),
            cost_usd = @cost_usd,
            result_count = @result_count,
            created_at = SAFE_CAST(@created_at AS TIMESTAMP),
            started_at = SAFE_CAST(@started_at AS TIMESTAMP),
            completed_at = SAFE_CAST(@completed_at AS TIMESTAMP),
            ingested_at = CURRENT_TIMESTAMP()
        WHERE run_id = @run_id
        """,
        [
            ("run_id", "STRING", run_id),
            ("status", "STRING", run.get("status", "COMPLETED")),
            ("input_json", "STRING", json.dumps(run.get("input", {}), ensure_ascii=False)),
            ("output_json", "STRING", json.dumps(run.get("output", []), ensure_ascii=False)),
            ("cost_usd", "NUMERIC", (run.get("cost") or {}).get("value") or 0),
            ("result_count", "INT64", run.get("resultCount") or len(output)),
            ("created_at", "STRING", run.get("createdAt")),
            ("started_at", "STRING", run.get("startedAt")),
            ("completed_at", "STRING", run.get("completedAt")),
        ],
    )

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
            "published_at": _published_timestamp(item),
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
        _append_rows("mentions", mention_rows)
    return {"run_id": run_id, "status": run.get("status"), "already_ingested": False, "result_count": len(mention_rows)}


def list_mentions(*, market: str, week_start: str, week_end: str, previous_week_start: str, previous_week_end: str) -> list[dict[str, Any]]:
    ensure_tables()
    rows = _run(
        f"""
        SELECT mention_id, run_id, user_id, market, keyword, published_at, title,
               author, url, views, likes, comments, shares, bookmarks, hashtags, raw_json
        FROM {_table('mentions')}
        WHERE market = @market
          AND DATE(published_at) BETWEEN @previous_week_start AND @week_end
        ORDER BY published_at DESC
        """,
        [
            ("market", "STRING", market),
            ("previous_week_start", "DATE", previous_week_start),
            ("week_end", "DATE", week_end),
        ],
    )
    return [dict(row) for row in rows]


def get_weekly_analysis(*, user_id: str, market: str, week_start: str, week_end: str) -> dict[str, Any] | None:
    ensure_tables()
    key = f"{user_id}:{market}:{week_start}:{week_end}"
    rows = _run(
        f"SELECT analysis FROM {_table('weekly_comparisons')} WHERE analysis_key = @analysis_key LIMIT 1",
        [("analysis_key", "STRING", key)],
    )
    if not rows:
        return None
    analysis = dict(rows[0]).get("analysis")
    if isinstance(analysis, str):
        return json.loads(analysis)
    return analysis


def save_weekly_analysis(*, user_id: str, market: str, week_start: str, week_end: str, previous_week_start: str, previous_week_end: str, analysis: dict[str, Any]) -> None:
    ensure_tables()
    key = f"{user_id}:{market}:{week_start}:{week_end}"
    existing = list(_run(
        f"SELECT analysis_key FROM {_table('weekly_comparisons')} WHERE analysis_key = @analysis_key LIMIT 1",
        [("analysis_key", "STRING", key)],
    ))
    params = [
        ("analysis_key", "STRING", key),
        ("user_id", "STRING", user_id),
        ("market", "STRING", market),
        ("week_start", "DATE", week_start),
        ("week_end", "DATE", week_end),
        ("previous_week_start", "DATE", previous_week_start),
        ("previous_week_end", "DATE", previous_week_end),
        ("analysis", "STRING", json.dumps(analysis, ensure_ascii=False)),
    ]
    if existing:
        _run(
            f"UPDATE {_table('weekly_comparisons')} SET analysis = PARSE_JSON(@analysis), generated_at = CURRENT_TIMESTAMP() WHERE analysis_key = @analysis_key",
            [("analysis", "STRING", json.dumps(analysis, ensure_ascii=False)), ("analysis_key", "STRING", key)],
        )
    else:
        _run(
            f"""
            INSERT INTO {_table('weekly_comparisons')}
            (analysis_key, user_id, market, week_start, week_end, previous_week_start, previous_week_end, analysis, generated_at)
            VALUES (@analysis_key, @user_id, @market, @week_start, @week_end, @previous_week_start, @previous_week_end, PARSE_JSON(@analysis), CURRENT_TIMESTAMP())
            """,
            params,
        )
