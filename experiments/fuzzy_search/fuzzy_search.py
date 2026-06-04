from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
IATA_PATH = ROOT / "database" / "transport" / "iata_codes.json"
POI_PATH = ROOT / "frontend" / "frontend" / "src" / "data" / "poi_database.json"
DEBUG_OUTPUT_PATH = Path(__file__).resolve().parent / "debug_output.json"

MIN_MATCH_SCORE = 0.56
AMBIGUITY_DELTA = 0.06
CONTEXT_OVERRIDE_MARGIN = 0.18


CITY_ALIASES = {
    "Amsterdam": ["阿姆斯特丹"],
    "Barcelona": ["巴塞罗那"],
    "Dubai": ["迪拜"],
    "Frankfurt": ["法兰克福"],
    "London": ["伦敦"],
    "New York": ["纽约"],
    "Paris": ["巴黎"],
    "Rome": ["罗马"],
    "Shanghai": ["上海"],
    "Zurich": ["苏黎世"],
}

CATEGORY_ALIASES = {
    "hotel": ["酒店", "住宿", "住"],
    "restaurant": ["餐厅", "饭店", "吃饭", "用餐", "美食"],
    "attraction": ["景点", "公园", "展馆", "游玩"],
    "mall": ["商场", "购物"],
    "transport": ["交通", "地铁", "车站", "机场"],
    "entertainment": ["娱乐", "电影", "酒吧", "ktv"],
    "resting_area": ["休息", "避雨"],
}


@dataclass(frozen=True)
class Candidate:
    kind: str
    id: str
    label: str
    aliases: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def normalize(value: str) -> str:
    value = value.strip().lower()
    value = value.replace("·", "")
    value = re.sub(r"[\s\-_()（）/]+", "", value)
    return value


def char_bigrams(value: str) -> set[str]:
    text = normalize(value)
    if len(text) <= 1:
        return {text} if text else set()
    return {text[index : index + 2] for index in range(len(text) - 1)}


def similarity(left: str, right: str) -> float:
    left_norm = normalize(left)
    right_norm = normalize(right)
    if not left_norm or not right_norm:
        return 0.0
    if left_norm == right_norm:
        return 1.0
    if left_norm in right_norm:
        return 0.96 if len(left_norm) >= 4 else 0.9
    if right_norm in left_norm:
        return 0.9 if len(right_norm) >= 4 else 0.72

    sequence_score = SequenceMatcher(None, left_norm, right_norm).ratio()
    left_bigrams = char_bigrams(left_norm)
    right_bigrams = char_bigrams(right_norm)
    overlap = 0.0
    if left_bigrams and right_bigrams:
        overlap = len(left_bigrams & right_bigrams) / len(left_bigrams | right_bigrams)

    return max(sequence_score, overlap)


def build_candidates() -> list[Candidate]:
    candidates: list[Candidate] = []
    iata_data = load_json(IATA_PATH)

    cities: dict[str, list[dict[str, str]]] = {}
    for airport in iata_data["airports"]:
        cities.setdefault(airport["city"], []).append(airport)
        aliases = {
            airport["iata"],
            airport["name"],
            airport["city"],
            airport["country"],
            *CITY_ALIASES.get(airport["city"], []),
        }
        candidates.append(
            Candidate(
                kind="airport",
                id=f"airport:{airport['iata']}",
                label=f"{airport['name']} ({airport['iata']})",
                aliases=tuple(sorted(aliases)),
                metadata=airport,
            )
        )

    for city, airports in cities.items():
        aliases = {city, *CITY_ALIASES.get(city, [])}
        aliases.update(airport["iata"] for airport in airports)
        candidates.append(
            Candidate(
                kind="city",
                id=f"city:{city}",
                label=city,
                aliases=tuple(sorted(aliases)),
                metadata={
                    "city": city,
                    "airport_codes": [airport["iata"] for airport in airports],
                    "country": airports[0]["country"],
                },
            )
        )

    poi_data = load_json(POI_PATH)
    for poi in poi_data:
        category = poi.get("category", "")
        aliases = {
            poi["poi_id"],
            poi["poi_name"],
            poi.get("district", ""),
            category,
            poi.get("sub_category", ""),
            *poi.get("tags", []),
            *poi.get("suitable_for", []),
            *CATEGORY_ALIASES.get(category, []),
        }
        candidates.append(
            Candidate(
                kind="poi",
                id=f"poi:{poi['poi_id']}",
                label=poi["poi_name"],
                aliases=tuple(sorted(alias for alias in aliases if alias)),
                metadata=poi,
            )
        )

    return candidates


def context_score(candidate: Candidate, context: dict[str, Any] | None) -> tuple[float, list[str]]:
    if not context:
        return 0.0, []

    score = 0.0
    evidence: list[str] = []

    def add_evidence(name: str, amount: float) -> None:
        nonlocal score
        score += amount
        evidence.append(name)

    city = candidate.metadata.get("city")
    if candidate.kind == "airport":
        city = candidate.metadata.get("city")
    if candidate.kind == "poi":
        district = candidate.metadata.get("district")
        category = candidate.metadata.get("category")
        if district and district == context.get("preferred_district"):
            add_evidence(f"preferred_district:{district}", 0.18)
        if category and category in set(context.get("preferred_categories", [])):
            add_evidence(f"preferred_category:{category}", 0.14)

    recent_destinations = context.get("recent_destinations", [])
    itinerary_cities = context.get("itinerary_cities", [])
    current_city = context.get("current_city")

    if city and city in recent_destinations:
        count = recent_destinations.count(city)
        add_evidence(f"recent_destinations:{city}x{count}", min(0.12 * count, 0.3))
    if city and city in itinerary_cities:
        add_evidence(f"itinerary_city:{city}", 0.24)
    if city and city == current_city:
        add_evidence(f"current_city:{city}", 0.08)

    return score, evidence


def score_candidate(query: str, candidate: Candidate, context: dict[str, Any] | None) -> dict[str, Any]:
    alias_scores = [(alias, similarity(query, alias)) for alias in candidate.aliases]
    best_alias, base_score = max(alias_scores, key=lambda item: item[1])
    boost, evidence = context_score(candidate, context)
    final_score = min(base_score + boost, 1.0)
    return {
        "kind": candidate.kind,
        "id": candidate.id,
        "label": candidate.label,
        "score": round(final_score, 4),
        "base_score": round(base_score, 4),
        "context_boost": round(boost, 4),
        "matched_alias": best_alias,
        "evidence": evidence,
        "metadata": candidate.metadata,
    }


def fuzzy_search(
    query: str,
    *,
    kind: str | None = None,
    context: dict[str, Any] | None = None,
    top_k: int = 5,
) -> dict[str, Any]:
    candidates = build_candidates()
    if kind:
        candidates = [candidate for candidate in candidates if candidate.kind == kind]

    scored = [score_candidate(query, candidate, context) for candidate in candidates]
    scored.sort(key=lambda item: item["score"], reverse=True)
    top = scored[:top_k]

    if not top or top[0]["score"] < MIN_MATCH_SCORE:
        status = "no_match"
    elif len(top) > 1 and top[0]["score"] - top[1]["score"] < AMBIGUITY_DELTA:
        status = "ambiguous"
    else:
        status = "matched"

    literal = max(scored, key=lambda item: item["base_score"], default=None)
    contextual = top[0] if top else None
    context_champion = max(scored, key=lambda item: item["context_boost"], default=None)
    if (
        literal
        and contextual
        and literal["id"] != contextual["id"]
        and literal["base_score"] >= 0.86
        and contextual["score"] - literal["base_score"] >= CONTEXT_OVERRIDE_MARGIN
        and len(contextual["evidence"]) >= 2
    ):
        status = "context_override"
    elif (
        literal
        and context_champion
        and literal["id"] != context_champion["id"]
        and literal["base_score"] >= 0.95
        and context_champion["context_boost"] >= 0.42
        and len(context_champion["evidence"]) >= 2
    ):
        status = "context_override"
        top = [context_champion, *[item for item in top if item["id"] != context_champion["id"]]][:top_k]

    return {
        "query": query,
        "kind_filter": kind,
        "status": status,
        "selected": top[0] if status != "no_match" else None,
        "candidates": top,
        "literal_candidate": literal,
        "notes": _notes_for_status(status),
    }


def _notes_for_status(status: str) -> str:
    if status == "context_override":
        return "Strong context beat the literal mention. Agent should explain the correction reason."
    if status == "ambiguous":
        return "Several candidates are close. Agent should ask for clarification or present choices."
    if status == "no_match":
        return "No bounded local candidate was found. Agent must not invent IDs or availability."
    return "Clear bounded match."


def run_debug_cases() -> list[dict[str, Any]]:
    cases = [
        {"query": "Pariss", "kind": "city"},
        {"query": "伦敦", "kind": "city"},
        {"query": "CDG", "kind": "airport"},
        {"query": "Wagas轻食", "kind": "poi"},
        {"query": "亚朵", "kind": "poi"},
        {"query": "公园", "kind": "poi"},
        {
            "query": "Paris",
            "kind": "city",
            "context": {
                "recent_destinations": ["Shanghai", "Shanghai"],
                "itinerary_cities": ["Shanghai"],
                "current_city": "London",
            },
        },
        {
            "query": "巴黎",
            "kind": "city",
            "context": {
                "recent_destinations": ["Paris"],
                "itinerary_cities": ["Paris"],
                "current_city": "London",
            },
        },
        {"query": "广州", "kind": "city"},
    ]
    return [fuzzy_search(**case) for case in cases]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("query", nargs="?")
    parser.add_argument("--kind", choices=["city", "airport", "poi"])
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    if args.debug:
        results = run_debug_cases()
        DEBUG_OUTPUT_PATH.write_text(
            json.dumps(results, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"Wrote {DEBUG_OUTPUT_PATH}")
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return

    if not args.query:
        raise SystemExit("Provide a query or use --debug.")

    print(json.dumps(fuzzy_search(args.query, kind=args.kind), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
