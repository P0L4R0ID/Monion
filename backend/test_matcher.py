"""
test_matcher.py -- Sanity-check matcher.match_item() against a fixed set of
representative bill line item names.

Usage:
  python test_matcher.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from matcher import match_item

test_items = [
    "Specialist Consultation",        # should match schedule13, high confidence
    "Full Blood Count",               # should match schedule13, high confidence
    "Paracetamol 500mg",              # should match drug_prices, high confidence
    "Chest X-Ray",                    # should match schedule13, high confidence
    "Pillowcase",                     # should match reference_prices or unrecognised
    "Semi-Private Room",              # should match reference_prices
    "FBC",                            # abbreviation -- tests alias matching
    "PCM 500",                        # brand alias -- tests drug alias matching
    "Ubat Sakit Kepala",               # Malay, likely unrecognised
    "XYZABC Unknown Procedure",       # garbage -- must return unrecognised
    "Specialist Consultation (Cardiology) - Initial Visit",  # trailing modifiers -- tests normalize_query()
    "Full Blood Count (FBC)",         # parenthetical alias -- should still match correctly
    "Paracetamol 500mg tablet × 100", # quantity suffix -- should still match correctly
]


def run_test():
    name_width = max(len(item) for item in test_items)
    header = (
        f"{'ITEM NAME':<{name_width}} | {'MATCHED NAME':<45} | {'SOURCE':<17} | "
        f"{'CONF':>6} | {'STATUS':<14} | {'REF MAX':>10}"
    )
    print(header)
    print("-" * len(header))

    for item_name in test_items:
        result = match_item(item_name)

        matched_name = (result["matched_name"] or "<no match>")[:45]
        source = result["source_db"] or "-"
        confidence = f"{result['confidence']:.1f}"
        status = result["status"]
        ref_max = (
            f"{result['reference_max']:.2f}"
            if result["reference_max"] is not None
            else "null"
        )

        print(
            f"{item_name:<{name_width}} | {matched_name:<45} | {source:<17} | "
            f"{confidence:>6} | {status:<14} | {ref_max:>10}"
        )


if __name__ == "__main__":
    run_test()
