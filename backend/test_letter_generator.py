"""
test_letter_generator.py -- Generate a full patient empowerment package from
Bill #2's flagged report (Schedule 13 violation + PAC Tier 1 unbundling).

Part 1: normal run, using OLLAMA_URL/OLLAMA_MODEL from the environment (or
their defaults). If Ollama isn't installed/running, generate_letter()
automatically falls back to generate_template_letter() via the
requests.exceptions.ConnectionError handler -- no crash.

Part 2: explicit fallback test -- forces OLLAMA_URL to a guaranteed-
unreachable address and confirms generate_letter() still returns a
complete, well-formed letter, regardless of whether Ollama happens to be
running elsewhere on this machine.
"""

import io
import re
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent))

from ocr import process_bill
from matcher import match_bill
from flagging import flag_bill
import letter_generator
from letter_generator import generate_letter


def build_bill2_report() -> dict:
    """
    OCR + match + flag Bill_2.pdf, then attach the bill metadata that
    ocr.py's header-skip patterns intentionally discard (hospital name,
    patient name, bill date, total amount). letter_generator.py's
    build_prompt() / generate_template_letter() read these via .get() with
    fallback defaults, so supplying them is optional but makes for a more
    realistic letter.
    """
    ocr_result = process_bill("../samples/Bill_2.pdf")
    matched_items = match_bill(ocr_result["line_items"])
    report = flag_bill(matched_items)

    raw_text = ocr_result["raw_text"]
    total_match = re.search(r"TOTAL AMOUNT DUE:\s*RM\s*([\d,]+\.\d{2})", raw_text)
    date_match = re.search(r"Invoice Date:\s*(.+)", raw_text)

    report["hospital_name"] = "Gleneagles Hospital Kuala Lumpur"
    report["patient_name"] = "Nurul Aisyah Binti Rahman"
    report["bill_date"] = date_match.group(1).strip() if date_match else "Unknown"
    report["total_amount"] = total_match.group(1) if total_match else "0"
    return report


def print_section(title: str, text: str):
    print("=" * 78)
    print(title)
    print("=" * 78)
    print(text)
    print()


def print_all_sections(result: dict):
    print_section("1. BILL SUMMARY", result["bill_summary"])
    print_section("2. YOUR RIGHTS", result["your_rights"])

    print("=" * 78)
    print("3. ACTION STEPS")
    print("=" * 78)
    for i, step in enumerate(result["action_steps"], start=1):
        print(f"  {i}. {step}")
    print()

    print_section("4a. HOSPITAL LETTER (ENGLISH)", result["hospital_letter"]["english"])
    print_section("4b. HOSPITAL LETTER (BAHASA MALAYSIA)", result["hospital_letter"]["bahasa_malaysia"])
    print_section("5. ESCALATION GUIDE", result["escalation_guide"])
    print_section("6. VERBAL SCRIPT", result["verbal_script"])


def run_normal_test():
    print("\n" + "#" * 78)
    print("# PART 1: NORMAL RUN (OLLAMA_URL from environment, default localhost:11434)")
    print("#" * 78 + "\n")

    report = build_bill2_report()
    result = generate_letter(report)
    print_all_sections(result)


def run_fallback_test():
    print("\n" + "#" * 78)
    print("# PART 2: FORCED FALLBACK TEST (OLLAMA_URL pointed at an unreachable address)")
    print("#" * 78 + "\n")

    original_url = letter_generator.OLLAMA_URL
    letter_generator.OLLAMA_URL = "http://localhost:59999"  # nothing listens here

    try:
        report = build_bill2_report()
        result = letter_generator.generate_letter(report)

        required_keys = [
            "bill_summary", "your_rights", "action_steps",
            "hospital_letter", "escalation_guide", "verbal_script",
        ]
        for key in required_keys:
            assert key in result, f"missing key: {key}"
        assert "english" in result["hospital_letter"]
        assert "bahasa_malaysia" in result["hospital_letter"]

        print("Fallback succeeded -- generate_letter() returned a complete "
              "6-section package without crashing.")
        print(f"  bill_summary length:        {len(result['bill_summary'])} chars")
        print(f"  your_rights length:         {len(result['your_rights'])} chars")
        print(f"  action_steps count:         {len(result['action_steps'])} steps")
        print(f"  hospital_letter.english:    {len(result['hospital_letter']['english'])} chars")
        print(f"  hospital_letter.bm:         {len(result['hospital_letter']['bahasa_malaysia'])} chars")
        print(f"  escalation_guide length:    {len(result['escalation_guide'])} chars")
        print(f"  verbal_script length:       {len(result['verbal_script'])} chars")
        print()
        print_all_sections(result)
    finally:
        letter_generator.OLLAMA_URL = original_url


if __name__ == "__main__":
    run_normal_test()
    run_fallback_test()
