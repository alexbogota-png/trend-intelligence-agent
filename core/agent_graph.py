"""LangGraph orchestration for the Trend Intelligence Agent.

The graph coordinates existing deterministic modules. It does not delegate
score calculation to the LLM. LangChain is used only for structured
interpretation when an OPENAI_API_KEY is configured.
"""

from __future__ import annotations

from typing import Any, TypedDict

from core.llm import interpret, summarize_weekly
from core.scoring import evaluate
from core.weekly import classify_week


class TrendState(TypedDict, total=False):
    trend: dict
    brands: list[dict]
    rules: dict
    source_file: str
    analyses: list[dict]
    response: dict


class WeeklyState(TypedDict, total=False):
    raw: str
    filename: str
    week_start: str | None
    page: dict
    summaries: dict
    error: str | None


def _score_node(state: TrendState) -> dict[str, Any]:
    analyses = []
    for brand in state.get("brands", []):
        result = evaluate(state["trend"], brand, state["rules"])
        result.update({
            "trend": state["trend"],
            "brand": brand["name"],
            "source_file": state.get("source_file", ""),
            "llm_used": False,
        })
        analyses.append(result)
    return {"analyses": analyses}


def _interpret_node(state: TrendState) -> dict[str, Any]:
    enriched = []
    for analysis in state.get("analyses", []):
        interpretation, error = interpret(analysis)
        item = dict(analysis)
        if interpretation:
            item["llm_interpretation"] = interpretation
            item["llm_used"] = True
        if error:
            item["llm_error"] = error
        average = (item["brand_fit"] + item["actionability"]) / 2
        item["recommendation"] = "HIGH" if average >= 75 else "MEDIUM" if average >= 55 else "LOW"
        enriched.append(item)
    return {"analyses": enriched}


def _rank_node(state: TrendState) -> dict[str, Any]:
    analyses = sorted(
        state.get("analyses", []),
        key=lambda item: (item["brand_fit"] + item["actionability"]) / 2,
        reverse=True,
    )
    if len(analyses) == 1:
        response = analyses[0]
    else:
        response = {
            "trend": state["trend"],
            "source_file": state.get("source_file", ""),
            "comparison": [
                {key: item[key] for key in ("brand", "brand_fit", "actionability", "recommendation")}
                for item in analyses
            ],
            "best_brand": analyses[0]["brand"] if analyses else None,
            "best_analysis": analyses[0] if analyses else None,
        }
    return {"analyses": analyses, "response": response}


def _weekly_classify_node(state: WeeklyState) -> dict[str, Any]:
    page = classify_week(state["raw"], state["filename"], state.get("week_start"))
    return {"page": page}


def _weekly_interpret_node(state: WeeklyState) -> dict[str, Any]:
    page = dict(state["page"])
    summaries, error = summarize_weekly(page)
    if summaries:
        sections = []
        for section in page.get("sections", []):
            item = dict(section)
            if item["id"] in summaries and item["id"] != "pending":
                item["insight"] = summaries[item["id"]]
            sections.append(item)
        page["sections"] = sections
        page["llm_used"] = True
    else:
        page["llm_used"] = False
    if error:
        page["llm_error"] = error
    return {"page": page, "summaries": summaries or {}, "error": error}


def _weekly_validate_node(state: WeeklyState) -> dict[str, Any]:
    page = dict(state["page"])
    for section in page.get("sections", []):
        if section.get("id") == "pending":
            section["title"] = ""
            section["prompt"] = ""
            section["insight"] = ""
            section["implication"] = ""
            section["bullets"] = []
    return {"page": page}


def _build_graph(state_type: type, nodes: list[tuple[str, Any]], edges: list[tuple[str, str]]):
    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError:
        return None
    graph = StateGraph(state_type)
    for name, node in nodes:
        graph.add_node(name, node)
    for source, target in edges:
        graph.add_edge(START if source == "START" else source, END if target == "END" else target)
    return graph.compile()


def run_trend_agent(trend: dict, brands: list[dict], rules: dict, source_file: str) -> dict:
    graph = _build_graph(
        TrendState,
        [("score", _score_node), ("interpret", _interpret_node), ("rank", _rank_node)],
        [("START", "score"), ("score", "interpret"), ("interpret", "rank"), ("rank", "END")],
    )
    initial: TrendState = {"trend": trend, "brands": brands, "rules": rules, "source_file": source_file}
    if graph is None:
        scored = {**initial, **_score_node(initial)}
        interpreted = {**scored, **_interpret_node(scored)}
        state = _rank_node(interpreted)
    else:
        state = graph.invoke(initial)
    return state["response"]


def run_weekly_agent(raw: str, filename: str, week_start: str | None = None) -> dict:
    graph = _build_graph(
        WeeklyState,
        [("classify", _weekly_classify_node), ("interpret", _weekly_interpret_node), ("validate", _weekly_validate_node)],
        [("START", "classify"), ("classify", "interpret"), ("interpret", "validate"), ("validate", "END")],
    )
    initial: WeeklyState = {"raw": raw, "filename": filename, "week_start": week_start}
    if graph is None:
        classified = {**initial, **_weekly_classify_node(initial)}
        interpreted = {**classified, **_weekly_interpret_node(classified)}
        state = _weekly_validate_node(interpreted)
    else:
        state = graph.invoke(initial)
    return state["page"]
