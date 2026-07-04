"""
test_ocr.py -- Run the full OCR pipeline on a sample bill image or PDF.

Usage:
  python test_ocr.py                         # uses first image/PDF in ../samples/
  python test_ocr.py ../samples/bill.pdf     # specific file

Output:
  - Per-page: raw OCR lines + parsed items for each page
  - Merged summary: deduplicated items across all pages + hit-rate stats
  - Full JSON dump for debugging
"""

import sys
import json
from pathlib import Path

# Add backend directory to path so we can import ocr
sys.path.insert(0, str(Path(__file__).parent))

from ocr import process_bill


def find_sample() -> str:
    """Find the first image/PDF in the samples directory."""
    samples_dir = Path(__file__).parent.parent / "samples"
    for ext in ("*.jpg", "*.jpeg", "*.png", "*.pdf"):
        matches = list(samples_dir.glob(ext))
        if matches:
            return str(matches[0])
    return None


def print_divider(title: str = "", width: int = 70):
    if title:
        pad = max(0, width - len(title) - 4)
        print(f"\n-- {title} " + "-" * pad)
    else:
        print("-" * width)


def print_items_table(items: list):
    """Print a table of parsed line items."""
    if not items:
        print("  (no line items extracted)")
        return

    header = f"  {'PG':>2}  {'LINE':>4}  {'ITEM NAME':<35}  {'QTY':>5}  {'UNIT':>8}  {'TOTAL':>8}"
    print(header)
    print_divider(width=len(header))

    for item in items:
        pg    = str(item["page_number"]) if item["page_number"] is not None else "-"
        name  = (item["item_name"] or "<no name>")[:35]
        qty   = str(item["quantity"])            if item["quantity"]   is not None else "null"
        unit  = f"RM {item['unit_price']:.2f}"  if item["unit_price"] is not None else "null"
        total = f"RM {item['total_price']:.2f}" if item["total_price"] is not None else "null"
        print(f"  {pg:>2}  {item['line_number']:>4}  {name:<35}  {qty:>5}  {unit:>8}  {total:>8}")


def run_test(file_path: str):
    print(f"\nRunning OCR pipeline on: {file_path}")
    print_divider()

    try:
        result = process_bill(file_path)
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    # -------------------------------------------------------- per-page results
    for page_info in result["per_page"]:
        pg = page_info["page"]
        total_pages = result["pages"]

        print_divider(f"PAGE {pg}/{total_pages} -- RAW OCR")
        raw_lines = page_info["raw_text"].splitlines()
        for i, line in enumerate(raw_lines, start=1):
            print(f"  {i:>3} | {line}")

        print_divider(f"PAGE {pg}/{total_pages} -- PARSED ITEMS ({page_info['item_count']} found)")
        # Show only items from this page
        page_items = [it for it in result["line_items"] if it["page_number"] == pg]
        print_items_table(page_items)

    # ---------------------------------------------------- merged summary table
    items = result["line_items"]
    dedup_removed = result["total_lines_extracted"] - len(items)

    print_divider(f"MERGED & DEDUPLICATED ({len(items)} items, {dedup_removed} duplicates removed)")
    print_items_table(items)

    # ------------------------------------------------------------------  stats
    print_divider("SUMMARY")
    print(f"  File:                {result['file']}")
    print(f"  Pages processed:     {result['pages']}")
    print(f"  Items before dedup:  {result['total_lines_extracted']}")
    print(f"  Items after dedup:   {len(items)}")
    print(f"  Duplicates removed:  {dedup_removed}")

    if items:
        named    = sum(1 for i in items if i["item_name"])
        with_qty = sum(1 for i in items if i["quantity"])
        with_tot = sum(1 for i in items if i["total_price"])
        print(f"  With name:           {named}/{len(items)}")
        print(f"  With quantity:       {with_qty}/{len(items)}")
        print(f"  With total:          {with_tot}/{len(items)}")

    print()

    # --------------------------------------------------------- full JSON output
    print_divider("FULL JSON (for debugging)")
    print(json.dumps(result["line_items"], indent=2, ensure_ascii=False))
    print()


if __name__ == "__main__":
    if len(sys.argv) >= 2:
        target = sys.argv[1]
    else:
        target = find_sample()
        if not target:
            print("No sample file found in ../samples/")
            print("Usage: python test_ocr.py <image_or_pdf_path>")
            print("       or drop a bill image into the samples/ folder")
            sys.exit(1)
        print(f"No file specified -- using: {target}")

    run_test(target)
