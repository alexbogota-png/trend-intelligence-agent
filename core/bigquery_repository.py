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
    _run(
        f"""
        CREATE TABLE IF NOT EXISTS {_table('trend_runs')} (
          run_id STRING,
          user_id STRING,
          market STRING,
          target_date DATE,
          provider STRING,
          endpoint STRING,
          status STRING,
          cost_usd NUMERIC,
          result_count INT64,
          created_at TIMESTAMP,
          completed_at TIMESTAMP,
          loaded_at TIMESTAMP
        )
        """
    )
    _run(
        f"""
        CREATE TABLE IF NOT EXISTS {_table('trend_hashtags')} (
          run_id STRING,
          user_id STRING,
          market STRING,
          snapshot_date DATE,
          rank_index INT64,
          hashtag_id STRING,
          hashtag_name STRING,
          publish_count INT64,
          views INT64,
          industry_ids JSON,
          popularity_curve JSON,
          top_creators JSON,
          raw_json JSON,
          loaded_at TIMESTAMP
        )
        """
    )
    _run(
        f"""
        CREATE TABLE IF NOT EXISTS {_table('trend_posts')} (
          run_id STRING,
          user_id STRING,
          market STRING,
          snapshot_date DATE,
          post_id STRING,
          published_at TIMESTAMP,
          title STRING,
          author STRING,
          url STRING,
          views INT64,
          likes INT64,
          comments INT64,
          shares INT64,
          engagement_rate FLOAT64,
          hashtags JSON,
          sound JSON,
          raw_json JSON,
          loaded_at TIMESTAMP
        )
        """
    )
    _run(
        f"""
        CREATE TABLE IF NOT EXISTS {_table('trend_sounds')} (
          run_id STRING,
          user_id STRING,
          market STRING,
          snapshot_date DATE,
          sound_id STRING,
          sound_name STRING,
          sound_author STRING,
          video_count INT64,
          views INT64,
          raw_json JSON,
          loaded_at TIMESTAMP
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
        f"SELECT run_id FROM {_table('raw_monid_runs')} WHERE run_id = @run_id AND ingested_at IS NOT NULL LIMIT 1",
        [("run_id", "STRING", run_id)],
    ))
    if existing:
        return {"run_id": run_id, "status": run.get("status"), "already_ingested": True, "result_count": len(output)}

    _append_rows("raw_monid_runs", [{
        "run_id": run_id,
        "user_id": user_id,
        "provider": run.get("provider", "apify"),
        "endpoint": run.get("endpoint", "/apidojo/tiktok-scraper"),
        "status": run.get("status", "COMPLETED"),
        "input_json": run.get("input", {}),
        "output_json": run.get("output", []),
        "cost_usd": (run.get("cost") or {}).get("value") or 0,
        "result_count": run.get("resultCount") or len(output),
        "created_at": run.get("createdAt"),
        "started_at": run.get("startedAt"),
        "completed_at": run.get("completedAt"),
        "ingested_at": datetime.now(timezone.utc).isoformat(),
    }])

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


def save_trend_started(*, user_id: str, market: str, target_date: str, run: dict[str, Any]) -> None:
    ensure_tables()
    _append_rows("trend_runs", [{
        "run_id": str(run.get("runId") or run.get("run_id") or ""),
        "user_id": user_id,
        "market": market,
        "target_date": target_date,
        "provider": run.get("provider", ""),
        "endpoint": run.get("endpoint", ""),
        "status": run.get("status", "RUNNING"),
        "cost_usd": (run.get("price") or {}).get("amount", {}).get("value") or 0,
        "result_count": 0,
        "created_at": run.get("createdAt"),
    }])


def _nested(item: dict[str, Any], *keys: str) -> Any:
    current: Any = item
    for key in keys:
        current = current.get(key) if isinstance(current, dict) else None
    return current


def _int_value(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def save_trend_result(*, user_id: str, market: str, target_date: str, run: dict[str, Any]) -> dict[str, Any]:
    """Persist TikHub trend outputs and normalize the fields used by the radar."""
    ensure_tables()
    run_id = str(run.get("runId") or run.get("run_id") or "")
    output = run.get("output") if isinstance(run.get("output"), dict) else {}
    endpoint = str(run.get("endpoint") or "")
    loaded_at = datetime.now(timezone.utc).isoformat()
    result_count = 0
    if endpoint.endswith("get_trends_hashtag_list"):
        items = output.get("items") or []
        rows = []
        for item in items:
            rows.append({
                "run_id": run_id,
                "user_id": user_id,
                "market": market,
                "snapshot_date": target_date,
                "rank_index": _int_value(item.get("rankIndex")),
                "hashtag_id": str(item.get("hashtagID") or ""),
                "hashtag_name": str(item.get("hashtagName") or ""),
                "publish_count": _int_value(item.get("publishCnt")),
                "views": _int_value(item.get("vv")),
                "industry_ids": item.get("industryIDs") or [],
                "popularity_curve": item.get("popularityCurve") or [],
                "top_creators": item.get("topCreators") or [],
                "raw_json": item,
                "loaded_at": loaded_at,
            })
        _append_rows("trend_hashtags", rows)
        result_count = len(rows)
    elif endpoint.endswith("get_top_contents_list"):
        items = output.get("entityInfos") or []
        rows = []
        sound_rows = []
        for item in items:
            info = item.get("itemInfo") if isinstance(item.get("itemInfo"), dict) else item
            metrics = item.get("itemMetrics") if isinstance(item.get("itemMetrics"), dict) else {}
            author = item.get("itemAuthorInfo") if isinstance(item.get("itemAuthorInfo"), dict) else {}
            rows.append({
                "run_id": run_id,
                "user_id": user_id,
                "market": market,
                "snapshot_date": target_date,
                "post_id": str(info.get("id") or info.get("itemId") or ""),
                "published_at": _published_timestamp(info),
                "title": str(info.get("desc") or info.get("title") or ""),
                "author": str(author.get("uniqueId") or author.get("nickname") or ""),
                "url": str(info.get("shareUrl") or info.get("url") or ""),
                "views": _int_value(metrics.get("playCount") or metrics.get("views")),
                "likes": _int_value(metrics.get("diggCount") or metrics.get("likes")),
                "comments": _int_value(metrics.get("commentCount") or metrics.get("comments")),
                "shares": _int_value(metrics.get("shareCount") or metrics.get("shares")),
                "engagement_rate": float(metrics.get("engagementRate") or 0),
                "hashtags": item.get("contentTags") or info.get("hashtags") or [],
                "sound": info.get("music") or item.get("music") or {},
                "raw_json": item,
                "loaded_at": loaded_at,
            })
            sound = info.get("music") or item.get("music") or {}
            if isinstance(sound, dict) and (sound.get("id") or sound.get("title") or sound.get("name")):
                sound_rows.append({
                    "run_id": run_id,
                    "user_id": user_id,
                    "market": market,
                    "snapshot_date": target_date,
                    "sound_id": str(sound.get("id") or sound.get("musicId") or ""),
                    "sound_name": str(sound.get("title") or sound.get("name") or ""),
                    "sound_author": str(sound.get("authorName") or sound.get("author") or ""),
                    "video_count": _int_value(sound.get("videoCount")),
                    "views": _int_value(sound.get("playCount") or sound.get("views")),
                    "raw_json": sound,
                    "loaded_at": loaded_at,
                })
        _append_rows("trend_posts", rows)
        _append_rows("trend_sounds", sound_rows)
        result_count = len(rows)
    _append_rows("trend_runs", [{
        "run_id": run_id,
        "user_id": user_id,
        "market": market,
        "target_date": target_date,
        "provider": run.get("provider", ""),
        "endpoint": endpoint,
        "status": run.get("status", "COMPLETED"),
        "cost_usd": (run.get("cost") or {}).get("value") or 0,
        "result_count": result_count,
        "created_at": run.get("createdAt"),
        "completed_at": run.get("completedAt"),
        "loaded_at": loaded_at,
    }])
    return {"run_id": run_id, "endpoint": endpoint, "result_count": result_count, "status": run.get("status")}


def latest_trend_date(*, user_id: str, market: str) -> str | None:
    ensure_tables()
    rows = _run(
        f"""
        SELECT CAST(MAX(target_date) AS STRING) AS target_date
        FROM {_table('trend_runs')}
        WHERE user_id = @user_id AND market = @market
        """,
        [("user_id", "STRING", user_id), ("market", "STRING", market)],
    )
    first = next(iter(rows), None)
    value = dict(first).get("target_date") if first else None
    return str(value) if value else None


def get_trend_radar(*, user_id: str, market: str, target_date: str) -> dict[str, Any]:
    ensure_tables()
    hashtag_rows = _run(
        f"""
        SELECT rank_index, hashtag_id, hashtag_name, publish_count, views,
               popularity_curve, top_creators
        FROM {_table('trend_hashtags')}
        WHERE user_id = @user_id AND market = @market AND snapshot_date = @target_date
        QUALIFY ROW_NUMBER() OVER (PARTITION BY hashtag_id ORDER BY loaded_at DESC) = 1
        ORDER BY rank_index ASC, views DESC
        LIMIT 100
        """,
        [("user_id", "STRING", user_id), ("market", "STRING", market), ("target_date", "DATE", target_date)],
    )
    post_rows = _run(
        f"""
        SELECT post_id, published_at, title, author, url, views, likes, comments, shares,
               engagement_rate, hashtags, sound
        FROM {_table('trend_posts')}
        WHERE user_id = @user_id AND market = @market AND snapshot_date = @target_date
        QUALIFY ROW_NUMBER() OVER (PARTITION BY post_id ORDER BY loaded_at DESC) = 1
        ORDER BY (likes + comments + shares) DESC, views DESC
        LIMIT 100
        """,
        [("user_id", "STRING", user_id), ("market", "STRING", market), ("target_date", "DATE", target_date)],
    )
    mention_rows = _run(
        f"""
        SELECT m.mention_id AS post_id, m.published_at, m.title, m.author, m.url,
               m.views, m.likes, m.comments, m.shares, 0.0 AS engagement_rate,
               m.hashtags, CAST(NULL AS JSON) AS sound
        FROM {_table('mentions')} AS m
        JOIN {_table('trend_runs')} AS r ON r.run_id = m.run_id
        WHERE m.user_id = @user_id AND m.market = @market AND r.target_date = @target_date
        ORDER BY (m.likes + m.comments + m.shares) DESC, m.views DESC
        LIMIT 100
        """,
        [("user_id", "STRING", user_id), ("market", "STRING", market), ("target_date", "DATE", target_date)],
    )
    combined_posts = [dict(row) for row in post_rows] or [dict(row) for row in mention_rows]
    sound_rows = _run(
        f"""
        SELECT sound_id, sound_name, sound_author, video_count, views
        FROM {_table('trend_sounds')}
        WHERE user_id = @user_id AND market = @market AND snapshot_date = @target_date
        QUALIFY ROW_NUMBER() OVER (PARTITION BY sound_id ORDER BY loaded_at DESC) = 1
        ORDER BY video_count DESC, views DESC
        LIMIT 50
        """,
        [("user_id", "STRING", user_id), ("market", "STRING", market), ("target_date", "DATE", target_date)],
    )
    return {"target_date": target_date, "market": market, "hashtags": [dict(row) for row in hashtag_rows], "posts": combined_posts, "sounds": [dict(row) for row in sound_rows]}


def get_weekly_analysis(*, user_id: str, market: str, week_start: str, week_end: str) -> dict[str, Any] | None:
    ensure_tables()
    key = f"{user_id}:{market}:{week_start}:{week_end}"
    rows = list(_run(
        f"SELECT analysis FROM {_table('weekly_comparisons')} WHERE analysis_key = @analysis_key ORDER BY generated_at DESC LIMIT 1",
        [("analysis_key", "STRING", key)],
    ))
    first = next(iter(rows), None)
    if not first:
        return None
    analysis = dict(first).get("analysis")
    if isinstance(analysis, str):
        return json.loads(analysis)
    return analysis


def save_weekly_analysis(*, user_id: str, market: str, week_start: str, week_end: str, previous_week_start: str, previous_week_end: str, analysis: dict[str, Any]) -> None:
    ensure_tables()
    key = f"{user_id}:{market}:{week_start}:{week_end}"
    _append_rows("weekly_comparisons", [{
        "analysis_key": key,
        "user_id": user_id,
        "market": market,
        "week_start": week_start,
        "week_end": week_end,
        "previous_week_start": previous_week_start,
        "previous_week_end": previous_week_end,
        "analysis": analysis,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }])
