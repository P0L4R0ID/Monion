"""
test_flagging.py -- Run the full OCR -> match -> flag pipeline on Bill #2
(Schedule 13 cap violation + PAC Tier 1 unbundling) and Bill #3 (drug
overcharge + duplicate line item), and print the flagged results.

Uses the standard process_bill() pipeline. ocr.py's deduplicate_line_items()
now only strips a repeat when it appears on a DIFFERENT page than its first
occurrence (the genuine repeated-header/footer case); a same-page repeat
(e.g. Bill #3's double-billed FBC) is preserved so flagging.py's duplicate
check can see it intact.
"""

import io
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent))

from ocr import process_bill
from matcher import match_bill
from flagging import flag_bill


def get_matched_items(pdf_path: str) -> list:
    result = process_bill(pdf_path)
    return match_bill(result["line_items"])


def print_flag(flag: dict, indent: str = "      "):
    icon = "\U0001F534" if flag["severity"] == "red" else "\U0001F7E1"
    print(f"{indent}{icon} [{flag['flag_type']}]  tier={flag['tier']}")
    print(f"{indent}   {flag['message']}")
    print(f"{indent}   Action: {flag['action']}")
    print(f"{indent}   Source: {flag['source']}")


def run_test(label: str, pdf_path: str):
    print("=" * 78)
    print(f"{label}: {pdf_path}")
    print("=" * 78)

    matched_items = get_matched_items(pdf_path)
    result = flag_bill(matched_items)

    print(f"\n-- FLAGGED ITEMS ({len(result['flagged_items'])}) --")
    for item in result["flagged_items"]:
        qty = item["quantity"] if item["quantity"] is not None else "-"
        print(f"\n  {item['item_name']!r} -- RM{item['total_price']:.2f} (qty={qty})")
        for flag in item["flags"]:
            print_flag(flag)

    print(f"\n-- CLEAN / UNFLAGGED ITEMS ({len(result['clean_items'])}) --")
    for item in result["clean_items"]:
        total = f"RM{item['total_price']:.2f}" if item["total_price"] is not None else "RM?"
        print(f"  {item['item_name']!r:45} {total:>10}  [{item['status']}]")

    print("\n-- SUMMARY --")
    for key, value in result["summary"].items():
        print(f"  {key}: {value}")
    print()


if __name__ == "__main__":
    run_test("BILL #2 (Schedule 13 violation + PAC unbundling)", "../samples/Bill_2.pdf")
    run_test("BILL #3 (drug overcharge + duplicate)", "../samples/Bill_3.pdf")
