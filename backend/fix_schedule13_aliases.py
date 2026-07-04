"""
fix_schedule13_aliases.py -- Remove over-broad/misplaced aliases from
extracted_schedule13_enriched.json (one-off cleanup, run once).

Two problems being fixed:

1. Generic single-word aliases ("consultation", "consult") were added to
   Schedule 13's "Consultation only" tier rows. These match almost any bill
   line item that mentions the word "consultation" -- including GP
   consultations, which Schedule 13 does not cover at all (that's Schedule
   7, not in our dataset). Removed entirely; standalone single-word aliases
   have no place in a legal-cap database.

2. The "specialist consultation" / "specialist visit" / "consultant fee" /
   "pakar perunding" / "specialist review" aliases added to schedule13 row 9
   (an earlier attempt to make Schedule 13 win fuzzy-matches for specialist
   consultation queries) are removed. reference_prices.json's
   consult_specialist_first_private entry already carries these same
   aliases with a properly disambiguated, authoritative cap (RM235, cited
   to PHFSA Schedule 13 as amended 2013). Since Schedule 13 is checked
   FIRST in matcher.py's priority order, keeping duplicate aliases on row 9
   -- one of four ambiguous, unlabeled consultation fee tiers -- means
   Schedule 13 always wins the tie and reports the wrong (lower, arbitrary)
   cap. Removing them lets reference_prices.json's disambiguated entry win.

Usage:
  python fix_schedule13_aliases.py
"""

import json
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
TARGET_PATH = DATA_DIR / "extracted_schedule13_enriched.json"

# Bare single-word aliases to strip from every entry, regardless of index.
_GENERIC_STANDALONE_ALIASES = {"consultation", "consult"}

# Aliases to strip specifically from row 9 (see problem #2 above).
_ROW9_ALIASES_TO_REMOVE = {
    "specialist consultation", "specialist visit", "consultant fee",
    "pakar perunding", "specialist review",
}


def main():
    raw = json.loads(TARGET_PATH.read_text(encoding="utf-8"))
    entries = raw["data"]

    generic_removed_count = 0
    for entry in entries:
        aliases = entry.get("aliases") or []
        kept = [a for a in aliases if a.lower() not in _GENERIC_STANDALONE_ALIASES]
        if len(kept) != len(aliases):
            generic_removed_count += 1
            print(f"  removed generic alias(es) from {entry['procedure_name_en']!r}: "
                  f"{sorted(set(a.lower() for a in aliases) - set(a.lower() for a in kept))}")
        entry["aliases"] = kept

    row9 = entries[9]
    before = set(a.lower() for a in row9.get("aliases") or [])
    row9["aliases"] = sorted(a for a in row9["aliases"] if a.lower() not in _ROW9_ALIASES_TO_REMOVE)
    removed_from_row9 = before - set(a.lower() for a in row9["aliases"])
    print(f"\n  removed from row 9 ({row9['procedure_name_en']!r}): {sorted(removed_from_row9)}")
    print(f"  row 9 aliases now: {row9['aliases']}")

    TARGET_PATH.write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\nDone. Stripped generic standalone aliases from {generic_removed_count} entries.")
    print(f"Saved to: {TARGET_PATH}")


if __name__ == "__main__":
    main()
