"""
apply_manual_corrections.py -- Manually correct machine-translated Schedule 13
entries for the ~20 procedures most likely to appear in demo bills
(consultations, ECG, ultrasound, common surgeries, etc.).

Machine translation (deep-translator / Google) is generally serviceable for
Schedule 13's formulaic Malay medical phrasing, but these specific entries
get curated English names and richer aliases since matcher.py's fuzzy
matching accuracy on them matters most for demos.

Reads/writes: data/extracted_schedule13_enriched.json (in place)

Usage:
  python apply_manual_corrections.py
"""

import json
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
TARGET_PATH = DATA_DIR / "extracted_schedule13_enriched.json"

# Each entry: (list of row indices sharing this Malay name, corrected
# English name, curated aliases to add on top of the auto-generated ones)
CORRECTIONS = [
    ([0, 5, 8, 11, 2152],
     "Consultation only",
     ["consultation only", "consultation", "consult"]),

    ([1, 6, 9, 12, 2153],
     "Consultation with examination",
     ["consultation with examination", "consult with exam"]),

    ([2, 7, 10, 13, 2154],
     "Consultation with examination and treatment plan",
     ["consultation with examination and treatment plan",
      "consultation and treatment plan"]),

    ([46],
     "Electrocardiogram (ECG) with report",
     ["ecg", "ekg", "electrocardiogram", "ecg with report"]),

    ([1123],
     "Ultrasound",
     ["usg", "ultrasound scan", "sonogram"]),

    ([1238],
     "Detailed fetal ultrasound scan",
     ["fetal ultrasound", "detailed fetal scan", "anomaly scan",
      "fetal anomaly scan"]),

    ([134],
     "Laparoscopic appendectomy",
     ["appendectomy", "appendicectomy", "lap appendicectomy",
      "laparoscopic appendicectomy"]),

    ([504],
     "Tonsillectomy - child (bilateral)",
     ["tonsillectomy", "pediatric tonsillectomy", "child tonsillectomy"]),

    ([505],
     "Tonsillectomy - adult (bilateral)",
     ["tonsillectomy", "adult tonsillectomy"]),

    ([507],
     "Adenotonsillectomy (bilateral)",
     ["adenotonsillectomy", "tonsils and adenoids removal"]),

    ([207],
     "Laparoscopic cholecystectomy",
     ["lap chole", "cholecystectomy", "gallbladder removal"]),

    ([1196],
     "High-resolution computed tomography (HRCT) - inspiratory or expiratory (30%)",
     ["hrct", "ct scan chest", "high resolution ct", "ct chest"]),

    ([243],
     "Primary inguinal hernia repair",
     ["hernia repair", "inguinal hernia repair", "herniorrhaphy"]),

    ([701],
     "Cataract surgery (complex cases, e.g. dislocated lens with or without implant)",
     ["cataract surgery", "cataract operation", "phacoemulsification"]),

    ([70],
     "Toilet and suture (T&S), per suture",
     ["wound suturing", "suture", "toilet and suture", "wound closure"]),

    ([21],
     "Ambulatory blood pressure monitoring",
     ["abpm", "ambulatory bp monitoring", "24 hour bp monitoring"]),

    ([2131, 2137],
     "Medical examination - pre-employment, routine and annual medical "
     "check-up, health screening, comprehensive medical examination, "
     "aviation medical examination (excluding lab investigations, X-ray, "
     "ECG etc.)",
     ["medical checkup", "health screening", "pre-employment medical",
      "annual medical exam"]),

    ([715],
     "Ultrasound-guided biopsy",
     ["ultrasound guided biopsy", "usg guided biopsy"]),

    ([716],
     "CT/MRI-guided biopsy",
     ["ct guided biopsy", "mri guided biopsy"]),

    ([1174],
     "Mammography with additional limited ultrasound (35%)",
     ["mammogram", "mammography", "breast ultrasound"]),

    ([1000],
     "Chest X-Ray (one view)",
     ["chest x-ray", "chest xray", "cxr", "chest radiograph"]),

    # Schedule 13 has 4 duplicate "Consultation with examination" rows (fee
    # tiers 10-35 / 30-125 / 60-180 / 35-90) with no label distinguishing
    # which is "specialist" vs GP vs hospital grade -- there is no principled
    # way to pick the "correct" one. Index 9 (the RM60-180 tier, the highest
    # non-dental tier) is designated here as the canonical specialist
    # consultation entry so fuzzy queries like "Specialist Consultation"
    # resolve to Schedule 13 rather than falling through to reference_prices.
    ([9],
     "Consultation with examination",
     ["specialist consultation", "specialist visit", "consultant fee",
      "pakar perunding", "specialist review"]),
]


def main():
    raw = json.loads(TARGET_PATH.read_text(encoding="utf-8"))
    entries = raw["data"]

    corrected_count = 0

    for indices, name_en, curated_aliases in CORRECTIONS:
        for idx in indices:
            entry = entries[idx]
            original_ms = entry.get("procedure_name_ms")
            machine_en = entry.get("procedure_name_en")

            entry["procedure_name_en"] = name_en

            aliases = set(a.lower() for a in (entry.get("aliases") or []))
            aliases.update(a.lower() for a in curated_aliases)
            if entry.get("section_type") == "Dental" and "consultation" in name_en.lower():
                aliases.add("dental consultation")
            entry["aliases"] = sorted(aliases)

            entry["manually_reviewed"] = True

            corrected_count += 1
            print(f"[{idx:>5}] {original_ms!r}")
            print(f"        machine: {machine_en!r}")
            print(f"        curated: {name_en!r}")
            print(f"        aliases: {entry['aliases']}")
            print()

    raw["metadata"]["manually_reviewed_count"] = corrected_count

    TARGET_PATH.write_text(
        json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"Corrected {corrected_count} row(s) across "
          f"{len(CORRECTIONS)} distinct procedures.")
    print(f"Saved to: {TARGET_PATH}")


if __name__ == "__main__":
    main()
