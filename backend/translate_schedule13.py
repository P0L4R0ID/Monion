"""
translate_schedule13.py -- One-off batch translation of Schedule 13 procedure
names from Malay to English using deep-translator's GoogleTranslator.

Reads:  data/extracted_schedule13_gemini.json  (2,174 entries, Malay only)
Writes: data/extracted_schedule13_enriched.json (adds procedure_name_en, aliases)

Processes in batches of 20 with a 1-second delay between batches to stay
under Google Translate's unofficial rate limits.

Usage:
  python translate_schedule13.py
"""

import json
import sys
import time
from pathlib import Path

from deep_translator import GoogleTranslator

DATA_DIR = Path(__file__).parent.parent / "data"
SRC_PATH = DATA_DIR / "extracted_schedule13_gemini.json"
DST_PATH = DATA_DIR / "extracted_schedule13_enriched.json"

BATCH_SIZE = 20
BATCH_DELAY_SECONDS = 1.0


def translate_all(names: list) -> list:
    """
    Translate a list of Malay procedure names to English in batches of
    BATCH_SIZE, sleeping BATCH_DELAY_SECONDS between batches. Returns a
    parallel list of English translations (None for any that fail).
    """
    translator = GoogleTranslator(source="ms", target="en")
    results = [None] * len(names)
    total_batches = (len(names) + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_num, start in enumerate(range(0, len(names), BATCH_SIZE), start=1):
        batch = names[start:start + BATCH_SIZE]
        try:
            translated = translator.translate_batch(batch)
        except Exception as e:
            print(f"  Batch {batch_num}/{total_batches}: FAILED ({e}) -- retrying one-by-one")
            translated = []
            for name in batch:
                try:
                    translated.append(translator.translate(name))
                except Exception as e2:
                    print(f"    could not translate {name!r}: {e2}")
                    translated.append(None)

        for i, value in enumerate(translated):
            results[start + i] = value

        print(f"  Batch {batch_num}/{total_batches} done ({start + len(batch)}/{len(names)} entries)")

        if batch_num < total_batches:
            time.sleep(BATCH_DELAY_SECONDS)

    return results


def build_aliases(name_en: str) -> list:
    """Minimal auto-generated alias: lowercase English name."""
    if not name_en:
        return []
    return [name_en.lower()]


def main():
    print("=" * 70)
    print("Schedule 13 Malay -> English translation (deep-translator / Google)")
    print("=" * 70)

    raw = json.loads(SRC_PATH.read_text(encoding="utf-8"))
    entries = raw["data"]
    print(f"\nLoaded {len(entries)} entries from {SRC_PATH.name}")

    names = [entry.get("procedure_name_ms") or "" for entry in entries]

    print(f"\nTranslating in batches of {BATCH_SIZE} "
          f"({BATCH_DELAY_SECONDS}s delay between batches)...\n")
    translations = translate_all(names)

    failed = 0
    for entry, name_en in zip(entries, translations):
        entry["procedure_name_en"] = name_en
        entry["aliases"] = build_aliases(name_en)
        if name_en is None:
            failed += 1

    raw["metadata"]["translation_tool"] = "deep-translator (GoogleTranslator ms->en)"
    raw["metadata"]["translation_failed_count"] = failed

    DST_PATH.write_text(
        json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"\n{'=' * 70}")
    print(f"Done. {len(entries) - failed}/{len(entries)} translated successfully.")
    if failed:
        print(f"WARNING: {failed} entries failed translation (procedure_name_en=null).")
    print(f"Saved to: {DST_PATH}")
    print("=" * 70)


if __name__ == "__main__":
    main()
