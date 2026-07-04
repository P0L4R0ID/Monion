"""
matcher.py -- Fuzzy-match OCR'd bill line items against Malaysian medical
fee reference databases.

Databases are searched in priority order, and the first match scoring
above the "matched" threshold wins:

  1. extracted_schedule13_enriched.json -- Schedule 13 legal fee caps
                                            (2,174 procedures, English names
                                            + aliases via translation)
  2. drug_prices.json                   -- MyPriMe drug advisory benchmarks
                                            (54 drugs)
  3. reference_prices.json              -- General category advisory/market
                                            benchmarks (17 categories)
"""

import json
import re
import sys
from pathlib import Path
from typing import Optional

from rapidfuzz import fuzz, process, utils

DATA_DIR = Path(__file__).parent.parent / "data"

_HIGH_CONFIDENCE = 85  # > this -> "matched"
_LOW_CONFIDENCE = 70   # >= this (and <= high) -> "low_confidence"; below -> "unrecognised"


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


# ---------------------------------------------------------------------------
# Database loaders -- each normalises its source JSON into a common schema:
#   {id, name, aliases, reference_min, reference_max, reference_type, source_db}
# ---------------------------------------------------------------------------

def _load_schedule13() -> list:
    """
    Schedule 13 entries have no "id" field -- only procedure names and fee
    columns. We synthesize the id and use fee_min/fee_max as the reference
    range (falling back to the specialist fee columns when fee_min/fee_max
    are absent).

    Loads the *enriched* file (translated + manually curated), matching on
    procedure_name_en / aliases rather than the original Malay
    procedure_name_ms, so English-language OCR'd bill text can match
    directly. Falls back to the Malay name only if no English translation
    is present for a given row.
    """
    path = DATA_DIR / "extracted_schedule13_enriched.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    entries = []
    for i, item in enumerate(raw["data"]):
        name = item.get("procedure_name_en") or item.get("procedure_name_ms")
        if not name:
            continue

        fee_candidates = [
            v for v in (
                item.get("fee_min"), item.get("fee_max"),
                item.get("pakar_bedah_fee"), item.get("pakar_anestesia_fee"),
            )
            if v is not None
        ]
        ref_min = item.get("fee_min")
        if ref_min is None:
            ref_min = min(fee_candidates) if fee_candidates else None
        ref_max = item.get("fee_max")
        if ref_max is None:
            ref_max = max(fee_candidates) if fee_candidates else None

        entries.append({
            "id":              f"schedule13_{i}",
            "name":            name,
            "aliases":         item.get("aliases") or [],
            "reference_min":   ref_min,
            "reference_max":   ref_max,
            "reference_type":  "legal_cap",
            "source_db":       "schedule13",
        })
    return entries


def _load_drug_prices() -> list:
    path = DATA_DIR / "drug_prices.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    entries = []
    for item in raw["items"]:
        name = item.get("drug_name")
        if not name:
            continue
        entries.append({
            "id":              f"drug_{_slugify(name)}",
            "name":            name,
            "aliases":         item.get("aliases") or [],
            "reference_min":   item.get("price_per_unit_min"),
            "reference_max":   item.get("price_per_unit_max"),
            "reference_type":  item.get("reference_type", "advisory_benchmark"),
            "source_db":       "drug_prices",
        })
    return entries


def _load_reference_prices() -> list:
    path = DATA_DIR / "reference_prices.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    entries = []
    for item in raw["items"]:
        name = item.get("name")
        if not name:
            continue
        entries.append({
            "id":              item.get("id") or f"reference_{_slugify(name)}",
            "name":            name,
            "aliases":         item.get("aliases") or [],
            "reference_min":   item.get("reference_min"),
            "reference_max":   item.get("reference_max"),
            "reference_type":  item.get("reference_type", "market_range"),
            "source_db":       "reference_prices",
        })
    return entries


_DB_LOADERS = [
    ("schedule13",       _load_schedule13),
    ("drug_prices",      _load_drug_prices),
    ("reference_prices", _load_reference_prices),
]

_databases: Optional[list] = None  # lazy-loaded, cached at module scope


def _build_choice_index(entries: list):
    """
    Build parallel (choice_text, owner_index) lists so every "name" AND every
    alias is a separately searchable string that maps back to its entry.
    """
    choices = []
    owner = []
    for idx, entry in enumerate(entries):
        choices.append(entry["name"])
        owner.append(idx)
        for alias in entry["aliases"]:
            choices.append(alias)
            owner.append(idx)
    return choices, owner


def _get_databases() -> list:
    """Load and cache all three databases as (source_name, entries, choices, owner)."""
    global _databases
    if _databases is None:
        _databases = []
        for source_name, loader in _DB_LOADERS:
            entries = loader()
            choices, owner = _build_choice_index(entries)
            _databases.append((source_name, entries, choices, owner))
    return _databases


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

def _empty_match() -> dict:
    return {
        "matched_id":      None,
        "matched_name":    None,
        "source_db":       None,
        "confidence":      0.0,
        "reference_max":   None,
        "reference_min":   None,
        "reference_type":  None,
        "status":          "unrecognised",
    }


def _to_match_dict(entry: dict, source_name: str, score: float, status: str) -> dict:
    return {
        "matched_id":      entry["id"],
        "matched_name":    entry["name"],
        "source_db":       source_name,
        "confidence":      round(float(score), 2),
        "reference_max":   entry["reference_max"],
        "reference_min":   entry["reference_min"],
        "reference_type":  entry["reference_type"],
        "status":          status,
    }


_PAREN_RE = re.compile(r"\(.*?\)")
_QTY_SUFFIX_RE = re.compile(r"\s[×x]\s.*")


def normalize_query(item_name: str) -> str:
    """
    Strip trailing modifiers that dilute fuzzy-match confidence but aren't
    part of the actual procedure name, e.g.
    "Specialist Consultation (Cardiology) - Initial Visit" ->
    "Specialist Consultation":

      1. Parenthetical asides: "(Cardiology)", "(FBC)", "(6%)"
      2. Visit-type suffixes after " - ": "- Initial Visit", "- Follow-up"
      3. Quantity suffixes after " x "/" × ": "x 100", "× 2 bags"
    """
    text = _PAREN_RE.sub("", item_name)
    text = text.split(" - ")[0]
    text = _QTY_SUFFIX_RE.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


GP_KEYWORDS = {"gp", "general practitioner", "general practice", "klinik am"}


def is_gp_item(normalized_query: str) -> bool:
    """
    True if the (already-normalized) query names a GP/general-practice item.
    Schedule 13 covers specialists in private hospitals only -- GP fees are
    governed by PHFSA Schedule 7, which is not part of this dataset. Without
    this guard, a bare "GP Consultation" query can fuzzy-match Schedule 13's
    generic consultation-tier entries and get told it violates a specialist
    fee cap that was never legally applicable to it.
    """
    tokens = set(normalized_query.lower().split())
    return bool(tokens & GP_KEYWORDS)


def match_item(item_name: str) -> dict:
    """
    Fuzzy-match a single bill line item's name against the schedule13,
    drug_prices, and reference_prices databases, in that priority order.

    The item_name is normalized (see normalize_query()) before matching so
    that trailing modifiers -- specialty asides, visit-type suffixes,
    quantity suffixes -- don't dilute the fuzzy-match score against a
    reference procedure name. The original item_name is untouched in the
    caller's data; only the matching step uses the normalized form.

    If the normalized query names a GP/general-practice item (see
    is_gp_item()), Schedule 13 is skipped entirely and matching starts from
    drug_prices/reference_prices -- Schedule 13 covers specialists only.

    Stops and returns immediately at the first match scoring > 85
    ("matched"). If no database reaches that threshold, the single best
    candidate seen across all three is used to decide between
    "low_confidence" (70-85) and "unrecognised" (< 70, no match returned).
    """
    if not item_name or not item_name.strip():
        return _empty_match()

    query = normalize_query(item_name) or item_name
    skip_schedule13 = is_gp_item(query)

    best = None  # (score, source_name, entry)

    for source_name, entries, choices, owner in _get_databases():
        if source_name == "schedule13" and skip_schedule13:
            continue
        if not choices:
            continue

        # token_sort_ratio (not WRatio) is deliberate: WRatio's partial-ratio
        # component treats a short query as a substring to hunt for inside
        # much longer choices, which produces spurious high scores when
        # matching short English item names against long, unrelated Malay
        # Schedule 13 phrases (e.g. any phrase containing "sinar-X" scores
        # ~85 against "Chest X-Ray" purely by coincidental character overlap).
        result = process.extractOne(
            query, choices, scorer=fuzz.token_sort_ratio, processor=utils.default_process,
        )
        if result is None:
            continue

        _, score, choice_idx = result
        entry = entries[owner[choice_idx]]

        if best is None or score > best[0]:
            best = (score, source_name, entry)

        if score > _HIGH_CONFIDENCE:
            return _to_match_dict(entry, source_name, score, "matched")

    if best is None:
        return _empty_match()

    score, source_name, entry = best
    if score >= _LOW_CONFIDENCE:
        return _to_match_dict(entry, source_name, score, "low_confidence")

    return _empty_match()


def match_bill(line_items: list) -> list:
    """
    Run match_item() on every OCR'd line item's item_name and merge the
    match result into the original line item dict.

    Unrecognised items are never dropped -- they pass through unchanged
    plus a status of "unrecognised".
    """
    results = []
    for item in line_items:
        match = match_item(item.get("item_name") or "")
        merged = dict(item)
        merged.update(match)
        results.append(merged)
    return results


if __name__ == "__main__":
    query = " ".join(sys.argv[1:]) or "Full Blood Count"
    print(json.dumps(match_item(query), indent=2, ensure_ascii=False))
