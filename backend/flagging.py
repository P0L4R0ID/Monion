"""
flagging.py -- Apply rule-based overcharge/unbundling/compliance checks to
a matcher.py-matched Malaysian medical bill.

Runs checks, in order, against every matched line item (some checks need
whole-bill context -- e.g. "is there a room charge anywhere on this bill" --
and are evaluated per-item against the full list):

  1. Schedule 13 / legal cap violation        (red)
  2. PAC Tier 1 confirmed unbundling           (red)
  3. Bundling Tier 2-5 (bundling_rules.json)   (yellow)
  4. Drug overcharge (> 3x reference price)    (yellow)
  5. SST exemption violation                   (yellow)
  6. Duplicate line item                       (yellow)
  7. Quantity vs. length-of-stay plausibility   (yellow)

Two known data-pipeline limitations (documented at the relevant check):
  - ocr.py's _SKIP_PATTERNS intentionally discards "Sales & Service Tax",
    "Payment Method", "Admission/Discharge Date" and "Length of Stay" lines
    as headers/noise, so checks 5 and 7 rarely have the signal they need
    from real OCR'd bills -- they're implemented correctly for when that
    data is present (e.g. entered manually, or a future OCR change).
  - the drug overcharge check (4) is specified against source_db ==
    "drug_prices", but matcher.py's fuzzy search can resolve a drug to
    reference_prices.json instead (both files use reference_type ==
    "advisory_benchmark" for drug entries), so this check keys off
    reference_type rather than source_db to actually catch those cases.
"""

import json
import re
from pathlib import Path
from typing import Optional

DATA_DIR = Path(__file__).parent.parent / "data"

_DRUG_OVERCHARGE_MULTIPLIER = 3.0

_ROOM_WARD_KEYWORDS = ["room", "ward", "accommodation", "bilik", "wad"]
_CONSULTATION_KEYWORDS = ["consultation", "consult", "perundingan"]
_SST_KEYWORDS = ["sst", "service tax", "sales tax"]
_LENGTH_OF_STAY_KEYWORDS = ["length of stay"]
_GL_KEYWORDS = ["gl patient", "guarantee letter", " gl "]


def _load_json(name: str) -> dict:
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


def _text(item: dict) -> str:
    """Lowercased searchable text for an item (name + raw OCR line)."""
    parts = [item.get("item_name") or "", item.get("raw_text") or ""]
    return " ".join(parts).lower()


def _contains_any(haystack: str, needles: list) -> bool:
    """
    Word-boundary substring match (not naive `in`): several lab-panel
    component aliases are dangerously short 1-3 letter abbreviations
    (e.g. "Na" for sodium, "K" for potassium, "AST"/"ALT" liver enzymes),
    which collide with ordinary English words under plain substring
    matching -- "AST" is a substring of "waste", "Na" is a substring of
    "maintenance". \\b anchors reject those mid-word collisions while still
    matching the alias as a standalone token or multi-word phrase.
    """
    for needle in needles:
        if not needle:
            continue
        pattern = r"\b" + re.escape(needle.lower()) + r"\b"
        if re.search(pattern, haystack):
            return True
    return False


# ---------------------------------------------------------------------------
# Check 1: Schedule 13 / legal cap violation
# ---------------------------------------------------------------------------

def _check_legal_cap(item: dict) -> Optional[dict]:
    if item.get("reference_type") != "legal_cap":
        return None
    total = item.get("total_price")
    cap = item.get("reference_max")
    if total is None or cap is None or total <= cap:
        return None

    # A shaky fuzzy match (confidence 70-85, status "low_confidence") is not
    # solid enough ground to tell a patient they have grounds to formally
    # dispute a "legal violation" -- e.g. "Pelvic Ultrasound" matching
    # "Detailed fetal ultrasound scan" at 78.79% is the wrong procedure
    # entirely, and its reference_max is meaningless for this charge.
    # Only status == "matched" (confidence > 85) earns the red flag; anything
    # weaker is downgraded to a cautious yellow advisory instead.
    if item.get("status") != "matched":
        return {
            "flag_type": "legal_cap_violation",
            "severity": "yellow",
            "message": (
                "Possible overcharge — match confidence too low to confirm "
                "legal violation. Verify this item manually."
            ),
            "action": (
                "Manually check this item against PHFSA Schedule 13 before "
                "assuming it is a legal violation -- the automatic match to "
                "a reference procedure was not confident enough to rely on."
            ),
            "source": "PHFSA Schedule 13",
            "tier": "advisory",
        }

    return {
        "flag_type": "legal_cap_violation",
        "severity": "red",
        "message": (
            f"This charge of RM{total:.2f} exceeds the legal maximum of "
            f"RM{cap:.2f} set by PHFSA Schedule 13. You have grounds to "
            f"formally dispute this charge."
        ),
        "action": (
            "Request a written explanation and bill correction from the "
            "hospital's billing department, citing PHFSA Schedule 13. If "
            "unresolved, lodge a complaint with the Ministry of Health "
            "Medical Practice Division."
        ),
        "source": "PHFSA Schedule 13",
        "tier": "legal_violation",
    }


# ---------------------------------------------------------------------------
# Check 2: PAC Tier 1 confirmed unbundling
# ---------------------------------------------------------------------------

def _bill_has_room_or_ward_charge(all_items: list) -> bool:
    return any(_contains_any(_text(it), _ROOM_WARD_KEYWORDS) for it in all_items)


def _check_pac_tier1(item: dict, all_items: list, bundling_rules: dict) -> Optional[dict]:
    tier1 = bundling_rules["rules"]["tier_1_pac_confirmed"]
    text = _text(item)

    for rule in tier1["items"]:
        aliases = [rule["item"]] + rule.get("aliases", [])
        if _contains_any(text, aliases) and _bill_has_room_or_ward_charge(all_items):
            return {
                "flag_type": "pac_tier1_unbundling",
                "severity": "red",
                "message": tier1["flag_message"],
                "action": (
                    "Ask the hospital to confirm why this consumable is billed "
                    "separately from your daily room charge, and request it "
                    "be refunded or folded into the room rate."
                ),
                "source": "PAC Report June 2026",
                "tier": "pac_confirmed",
            }
    return None


# ---------------------------------------------------------------------------
# Check 3: Bundling Tier 2-5
# ---------------------------------------------------------------------------

def _check_tier_items(item: dict, tier_key: str, bundling_rules: dict) -> Optional[dict]:
    """Generic scan against a flat tier["items"] list of
    {item, aliases, source[, flag_threshold_rm]}. Used for tiers 2 and 3."""
    tier = bundling_rules["rules"][tier_key]
    text = _text(item)

    for rule in tier["items"]:
        aliases = [rule["item"]] + rule.get("aliases", [])
        if not _contains_any(text, aliases):
            continue

        threshold = rule.get("flag_threshold_rm")
        if threshold is not None:
            price = item.get("unit_price")
            if price is None:
                price = item.get("total_price")
            if price is None or price <= threshold:
                continue

        return {
            "flag_type": f"{tier_key}_unbundling",
            "severity": "yellow",
            "message": tier["flag_message"],
            "action": (
                "Ask the hospital to justify this separate charge and "
                "whether it should be folded into an existing room, "
                "nursing, or procedure fee."
            ),
            "source": rule["source"],
            "tier": "expert_documented",
        }
    return None


def _check_lab_panels(item: dict, bundling_rules: dict) -> Optional[dict]:
    tier4 = bundling_rules["rules"]["tier_4_billing_standard"]
    text = _text(item)

    for rule in tier4["lab_panel_rules"]:
        if _contains_any(text, rule["components_that_should_not_be_billed_individually"]):
            return {
                "flag_type": "tier4_lab_panel_unbundling",
                "severity": "yellow",
                "message": tier4["flag_message"],
                "action": (
                    f"Ask the hospital why this appears separately from the "
                    f"{rule['panel']} panel charge."
                ),
                "source": rule["source"],
                "tier": "advisory",
            }
    return None


def _check_procedure_pairs(item: dict, all_items: list, bundling_rules: dict) -> Optional[dict]:
    tier4 = bundling_rules["rules"]["tier_4_billing_standard"]
    text = _text(item)

    for rule in tier4["procedure_pair_rules"]:
        aliases_a = rule.get("procedure_a_aliases")
        aliases_b = rule.get("procedure_b_aliases")
        if not aliases_a or not aliases_b:
            continue  # rules with no alias pairs (e.g. drug-dup, same-incision) -- not alias-matchable

        is_a = _contains_any(text, aliases_a)
        is_b = _contains_any(text, aliases_b)
        if not (is_a or is_b):
            continue

        other_aliases = aliases_b if is_a else aliases_a
        if any(other is not item and _contains_any(_text(other), other_aliases) for other in all_items):
            return {
                "flag_type": "tier4_procedure_pair_unbundling",
                "severity": "yellow",
                "message": rule["flag_message"],
                "action": "Ask the hospital why both related charges appear as separate line items.",
                "source": rule["source"],
                "tier": "advisory",
            }
    return None


def _check_tier5(item: dict, bundling_rules: dict) -> Optional[dict]:
    tier5 = bundling_rules["rules"]["tier_5_price_discrimination"]
    if not _contains_any(_text(item), _GL_KEYWORDS):
        return None

    rule = tier5["items"][0]
    return {
        "flag_type": "tier5_price_discrimination",
        "severity": "yellow",
        "message": tier5["flag_message"],
        "action": rule["advice"],
        "source": rule["source"],
        "tier": "advisory",
    }


def _check_bundling_tiers_2to5(item: dict, all_items: list, bundling_rules: dict) -> Optional[dict]:
    return (
        _check_tier_items(item, "tier_2_hansard_testimony", bundling_rules)
        or _check_tier_items(item, "tier_3_expert_documented", bundling_rules)
        or _check_lab_panels(item, bundling_rules)
        or _check_procedure_pairs(item, all_items, bundling_rules)
        or _check_tier5(item, bundling_rules)
    )


# ---------------------------------------------------------------------------
# Check 4: Drug overcharge
# ---------------------------------------------------------------------------

def _check_drug_overcharge(item: dict) -> Optional[dict]:
    if item.get("reference_type") != "advisory_benchmark":
        return None
    total = item.get("total_price")
    ref_max = item.get("reference_max")
    quantity = item.get("quantity")
    if total is None or ref_max is None or not quantity:
        return None

    threshold = ref_max * quantity * _DRUG_OVERCHARGE_MULTIPLIER
    if total <= threshold:
        return None

    per_unit = total / quantity
    multiplier = per_unit / ref_max if ref_max else 0.0

    return {
        "flag_type": "drug_overcharge",
        "severity": "yellow",
        "message": (
            f"This drug is priced at RM{per_unit:.2f}/unit. The MOH Medicine "
            f"Price Guide (MyPriMe) lists the reference price at "
            f"RM{ref_max:.2f}/unit. This is {multiplier:.1f}x the reference "
            f"price."
        ),
        "action": (
            "Ask the pharmacy or hospital to justify the markup, or request "
            "a generic-equivalent substitution."
        ),
        "source": "MyPriMe, MOH Pharmaceutical Services Programme",
        "tier": "advisory",
    }


# ---------------------------------------------------------------------------
# Check 5: SST exemption violation
# ---------------------------------------------------------------------------

def _check_sst(item: dict, all_items: list, sst_rules: dict) -> Optional[dict]:
    """
    Bill-wide heuristic: an SST line exists somewhere on the bill AND a
    doctor consultation fee item also exists somewhere on the bill. See
    module docstring -- ocr.py normally discards the "Sales & Service Tax"
    summary line as a total/header, so this rarely has data to act on with
    real OCR'd bills; implemented for when the SST line is present.
    """
    if not _contains_any(_text(item), _SST_KEYWORDS):
        return None
    if not any(_contains_any(_text(other), _CONSULTATION_KEYWORDS) for other in all_items):
        return None

    return {
        "flag_type": "sst_exempt_violation",
        "severity": "yellow",
        "message": (
            "SST has been applied to a category that is exempt under "
            "Malaysian SST regulations. Doctor consultation fees are not "
            "subject to SST."
        ),
        "action": "Request a corrected invoice with SST removed from the consultation fee line.",
        "source": "Royal Malaysian Customs Department, SST Policy 5/2025",
        "tier": "advisory",
    }


# ---------------------------------------------------------------------------
# Check 6: Duplicate line item
# ---------------------------------------------------------------------------

def _check_duplicates(all_items: list) -> dict:
    """Returns {id(item): flag_dict} for every item in a same-matched_id,
    same-quantity duplicate group of size > 1."""
    groups: dict = {}
    for item in all_items:
        matched_id = item.get("matched_id")
        if not matched_id:
            continue
        groups.setdefault(matched_id, []).append(item)

    flags = {}
    for group in groups.values():
        if len(group) < 2:
            continue
        if len({g.get("quantity") for g in group}) > 1:
            continue  # quantities differ -- not a naive duplicate

        flag = {
            "flag_type": "duplicate_charge",
            "severity": "yellow",
            "message": (
                "This item appears more than once on your bill. Please "
                "verify both charges were for separate, distinct services."
            ),
            "action": (
                "Ask the hospital to confirm both charges relate to "
                "genuinely separate services, or request a refund for the "
                "duplicate."
            ),
            "source": "Line-item duplicate detection",
            "tier": "advisory",
        }
        for g in group:
            flags[id(g)] = flag
    return flags


# ---------------------------------------------------------------------------
# Check 7: Quantity vs. length-of-stay plausibility
# ---------------------------------------------------------------------------

def _extract_length_of_stay_days(all_items: list) -> Optional[int]:
    for item in all_items:
        if _contains_any(_text(item), _LENGTH_OF_STAY_KEYWORDS) and item.get("quantity"):
            return item["quantity"]
    return None


def _check_quantity_plausibility(item: dict, all_items: list) -> Optional[dict]:
    """
    Best-effort: see module docstring -- ocr.py discards "Length of Stay: N
    days" as a metadata line, so `all_items` will rarely carry that signal
    in the current pipeline.
    """
    if not _contains_any(_text(item), _ROOM_WARD_KEYWORDS):
        return None
    quantity = item.get("quantity")
    if not quantity:
        return None

    days = _extract_length_of_stay_days(all_items)
    if days is None or quantity <= days:
        return None

    return {
        "flag_type": "quantity_plausibility",
        "severity": "yellow",
        "message": (
            f"The quantity billed ({quantity}) exceeds your recorded length "
            f"of stay ({days} days)."
        ),
        "action": "Ask the hospital to explain the discrepancy between the billed quantity and your length of stay.",
        "source": "Bill self-consistency check",
        "tier": "advisory",
    }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def flag_bill(matched_items: list) -> dict:
    """
    Run all checks against every item in a matcher.py-matched bill.

    Returns:
      {
        "flagged_items": list,  # original items + "flags": [flag, ...]
        "clean_items":   list,  # items with no flags (still has "flags": [])
        "summary": {
          "total_items": int,
          "total_flags": int,
          "red_flags": int,
          "yellow_flags": int,
          "unrecognised_items": int,
        },
      }
    """
    bundling_rules = _load_json("bundling_rules.json")
    sst_rules = _load_json("sst_rules.json")
    duplicate_flags = _check_duplicates(matched_items)

    flagged_items = []
    clean_items = []
    total_flags = 0
    red_flags = 0
    yellow_flags = 0
    unrecognised_items = 0

    for item in matched_items:
        if item.get("status") == "unrecognised":
            unrecognised_items += 1

        checks = [
            _check_legal_cap(item),
            _check_pac_tier1(item, matched_items, bundling_rules),
            _check_bundling_tiers_2to5(item, matched_items, bundling_rules),
            _check_drug_overcharge(item),
            _check_sst(item, matched_items, sst_rules),
            duplicate_flags.get(id(item)),
            _check_quantity_plausibility(item, matched_items),
        ]
        item_flags = [flag for flag in checks if flag]

        merged = dict(item)
        merged["flags"] = item_flags

        if item_flags:
            flagged_items.append(merged)
            total_flags += len(item_flags)
            red_flags += sum(1 for f in item_flags if f["severity"] == "red")
            yellow_flags += sum(1 for f in item_flags if f["severity"] == "yellow")
        else:
            clean_items.append(merged)

    return {
        "flagged_items": flagged_items,
        "clean_items": clean_items,
        "summary": {
            "total_items": len(matched_items),
            "total_flags": total_flags,
            "red_flags": red_flags,
            "yellow_flags": yellow_flags,
            "unrecognised_items": unrecognised_items,
        },
    }
