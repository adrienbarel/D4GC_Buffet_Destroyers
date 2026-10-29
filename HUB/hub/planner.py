"""Cost model + two-tier cache planner (PROJECT_SPEC 7.3).

p_need(d)       = Σ_g share(g) × relevance(d, g) × mission(d) × popularity(d)   (rescaled, max = 1)
cost_missing(d) = urgency(genre) × expected fetch cost of the original later
value(d)        = p_need × cost_missing          priority(d) = value / size_mb
Core tier: greedy by priority (hits per MB). Reserve tier: greedy by value (big, important,
expensive to fetch). All weights/costs come from config.yaml and are DEMO PLACEHOLDERS.
"""
from __future__ import annotations

import math
import time
from collections import Counter, defaultdict
from typing import Any

HOUR_VALUE = 10.0  # cost units per hour of waiting (placeholder)


def relevance(doc: dict, group: str, rel: dict) -> float:
    if doc["group_primary"] == group:
        return rel["primary"]
    if group in doc["groups_secondary"]:
        return rel["secondary"]
    return rel["other"]


def compute_plan(docs: list[dict], cfg: dict, budget_mb: float, always_mb: float,
                 views: list[tuple[str, float]] | None = None) -> dict[str, Any]:
    """Score every document and fill the budget. Returns {summary, rows, tiers}."""
    mission, links, rel = cfg["mission"], cfg["links"], cfg["relevance"]
    boosts, hub = cfg["boosts"], cfg["hub"]
    staff = mission["staff"]
    total_staff = sum(staff.values())
    now = time.time()
    decayed = defaultdict(float)
    for doc_id, ts in views or []:
        decayed[doc_id] += 0.5 ** ((now - ts) / 86400 / boosts["popularity_half_life_days"])

    p_inet = links["internet"]["available_probability"]
    rows = []
    for d in docs:
        base = sum(n / total_staff * relevance(d, g, rel) for g, n in staff.items())
        mentions = [c for c in d["countries"] if c in mission["countries"]]
        lang_ok = d["doc_language"] in mission["languages"]
        mission_f = 1 + boosts["mission_country"] * bool(mentions) + boosts["mission_language"] * lang_ok
        popularity = 1 + math.log1p(decayed[d["doc_id"]])
        size_mb = max((d["original_bytes"] or 0) / 1e6, 0.001)
        sat_cost = links["satellite"]["cost_per_mb"] * size_mb
        fetch = (p_inet * links["internet"]["seconds_per_mb"] * size_mb / 3600 * HOUR_VALUE
                 + (1 - p_inet) * min(sat_cost, links["courier"]["fixed_cost"]))
        urgency = cfg["urgency"].get(d["genre"], cfg["urgency"]["default"])
        rows.append({"doc_id": d["doc_id"], "title": d["title"], "genre": d["genre"],
                     "group": d["group_primary"], "size_mb": round(size_mb, 3), "p_raw": base * mission_f * popularity,
                     "urgency": urgency, "mentions": mentions, "cost_missing": urgency * fetch,
                     "sat_cost": sat_cost, "views": round(decayed[d["doc_id"]], 2)})
    p_max = max(r["p_raw"] for r in rows) or 1.0
    for r in rows:
        r["p_need"] = r.pop("p_raw") / p_max
        r["value"] = r["p_need"] * r["cost_missing"]
        r["priority"] = r["value"] / r["size_mb"]
        r["tier"] = "text_only"

    budget_left = budget_mb - always_mb
    b_core = max(budget_left, 0) * hub["core_share"]
    b_reserve = max(budget_left, 0) - b_core
    used_core = 0.0
    for r in sorted(rows, key=lambda r: -r["priority"]):
        if used_core + r["size_mb"] <= b_core:
            r["tier"], used_core = "core", used_core + r["size_mb"]
    capacity, used_res = (b_core - used_core) + b_reserve, 0.0
    rest = [r for r in rows if r["tier"] == "text_only" and r["p_need"] >= hub["reserve_min_p_need"]]
    for r in sorted(rest, key=lambda r: -r["value"]):
        if used_res + r["size_mb"] <= capacity:
            r["tier"], used_res = "reserve", used_res + r["size_mb"]

    for r in rows:
        r["reason"] = _reason(r, links)
        for key in ("p_need", "cost_missing", "value", "priority", "sat_cost"):
            r[key] = round(r[key], 3)
    rows.sort(key=lambda r: ({"core": 0, "reserve": 1, "text_only": 2}[r["tier"]], -r["priority"]))
    tiers = Counter(r["tier"] for r in rows)
    by_group = defaultdict(Counter)
    for r in rows:
        by_group[r["group"]][r["tier"]] += 1
    summary = {
        "budget_mb": budget_mb, "always_mb": round(always_mb, 1),
        "core_mb": round(used_core, 1), "reserve_mb": round(used_res, 1),
        "free_mb": round(max(budget_left, 0) - used_core - used_res, 1),
        "docs_per_tier": dict(tiers), "per_group": {g: dict(c) for g, c in by_group.items()},
        "warning": (f"Budget is below the always-on tier ({always_mb:.0f} MB index + all text): "
                    "no originals cached") if budget_left < 0 else None,
    }
    return {"summary": summary, "rows": rows, "tiers": {r["doc_id"]: r["tier"] for r in rows}}


def _reason(r: dict, links: dict) -> str:
    """One line that explains why the document is in its tier."""
    bits = [r["genre"]]
    if r["urgency"] > 1:
        bits.append(f"urgency {r['urgency']:g}")
    if r["mentions"]:
        bits.append("mentions mission country " + ",".join(r["mentions"]))
    if r["views"]:
        bits.append(f"{r['views']:g} recent views")
    if r["tier"] == "core":
        return f"Core: {'; '.join(bits)}; {r['size_mb']:.2f} MB; priority {r['priority']:.2f}/MB"
    if r["tier"] == "reserve":
        cost = min(r["sat_cost"], links["courier"]["fixed_cost"])
        return f"Reserve: {r['size_mb']:.1f} MB, expensive to fetch (≈{cost:.0f} by satellite/courier); {'; '.join(bits)}"
    return f"Text only: original fetched on demand ({r['size_mb']:.1f} MB, priority {r['priority']:.2f}/MB)"
