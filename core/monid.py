"""Monid API client used by the server-side ingestion routes."""

from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class MonidError(RuntimeError):
    pass


def _base_url() -> str:
    return os.getenv("MONID_BASE_URL", "https://api.monid.ai").rstrip("/")


def _request(method: str, path: str, body: dict | None = None) -> dict:
    api_key = os.getenv("MONID_API_KEY", "")
    if not api_key:
        raise MonidError("MONID_API_KEY no está configurada en el servidor.")
    payload = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }
    if payload is not None:
        headers["Content-Type"] = "application/json"
    request = Request(f"{_base_url()}{path}", data=payload, headers=headers, method=method)
    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise MonidError(f"Monid respondió {exc.code}: {detail}") from exc
    except (URLError, TimeoutError, ValueError) as exc:
        raise MonidError(f"No se pudo consultar Monid: {exc}") from exc


def start_run(*, keywords: list[str], market: str, sort_type: str, max_items: int) -> dict:
    body = {
        "provider": "apify",
        "endpoint": "/apidojo/tiktok-scraper",
        "input": {
            "body": {
                "keywords": keywords,
                "sortType": sort_type,
                "location": market,
                "maxItems": max_items,
                "includeSearchKeywords": True,
            },
            "queryParams": {},
            "pathParams": {},
        },
    }
    return _request("POST", "/v1/run", body)


def get_run(run_id: str) -> dict:
    return _request("GET", f"/v1/runs/{run_id}")
