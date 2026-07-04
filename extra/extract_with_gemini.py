#!/usr/bin/env python3
"""
Extract Schedule 13 procedures and fees using Google Gemini 2.5 Pro Vision API
Processes pages 268-326 from schedule13.pdf
"""

import json
import os
import sys
import io
import time
from collections import defaultdict
from io import BytesIO

# Force UTF-8 stdout on Windows so print() doesn't crash on unicode symbols
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

try:
    import pdfplumber
except ImportError:
    print("Error: pdfplumber not installed. Run: pip install pdfplumber")
    sys.exit(1)

try:
    import google.generativeai as genai
except ImportError:
    print("Error: google-generativeai not installed. Run: pip install google-generativeai")
    sys.exit(1)

try:
    from PIL import Image
except ImportError:
    print("Error: Pillow not installed. Run: pip install Pillow")
    sys.exit(1)

# Configuration
API_KEY = "AQ.Ab8RN6K2btCvcVGJTuZoqMUbaYZUYJNNLfQo9sc34doBbE_tWw"
PDF_PATH = "schedule13.pdf"
START_PAGE = 268
END_PAGE = 326
OUTPUT_DIR = "data"
MODEL_NAME = "gemini-2.5-pro"

# Configure Gemini API
genai.configure(api_key=API_KEY)

# Extraction prompt for Gemini
EXTRACTION_PROMPT = """Analyze this Schedule 13 medical fee table page carefully.

Extract ALL procedures/items and their fees from this page.

For each row/item, extract:
- procedure_name_ms: Procedure name in Malay (exact text from page)
- fee_min: Minimum fee (if range) or single fee value
- fee_max: Maximum fee (if range), or null if single value
- pakar_bedah_fee: Surgeon fee (if two-column format), or null
- pakar_anestesia_fee: Anesthesiologist fee (if two-column format), or null
- section_type: One of [Consultation, Surgical, Radiology, Examination, Inspection, Dental, Miscellaneous]

IMPORTANT:
- Do NOT skip any procedures
- Do NOT invent data
- If uncertain about a value, use null
- Return ONLY valid JSON array, no other text
- Handle multi-line procedure names (they may continue across lines)
- For ranges like "10 - 35", extract as fee_min: 10, fee_max: 35
- For single values like "235", extract as fee_min: 235, fee_max: null

Return as JSON array:
[{"procedure_name_ms": "...", "fee_min": X, "fee_max": Y, "pakar_bedah_fee": Z, "pakar_anestesia_fee": W, "section_type": "..."}]
"""

def pdf_page_to_image(pdf_path, page_num):
    """Convert a single PDF page to PIL Image"""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            page = pdf.pages[page_num - 1]  # Convert to 0-indexed
            # Get page image
            image = page.to_image(resolution=200)
            return image.original  # Return PIL Image
    except Exception as e:
        print(f"Error converting page {page_num}: {e}")
        return None

def extract_from_page(pdf_path, page_num):
    """Extract procedures from a single PDF page using Gemini"""
    print(f"  Page {page_num}...", end=" ", flush=True)

    try:
        # Convert page to image
        image = pdf_page_to_image(pdf_path, page_num)
        if image is None:
            print("✗ Failed to convert page")
            return []

        # Call Gemini API
        model = genai.GenerativeModel(MODEL_NAME)
        response = model.generate_content([EXTRACTION_PROMPT, image])

        # Parse response
        response_text = response.text.strip()

        # Extract JSON from response (handle markdown code blocks)
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()

        data = json.loads(response_text)
        print(f"✓ {len(data)} items")
        return data
    except json.JSONDecodeError as e:
        print(f"✗ JSON error")
        return []
    except Exception as e:
        print(f"✗ Error: {str(e)[:50]}")
        return []

def deduplicate(entries):
    """Remove duplicate entries"""
    seen = {}
    unique = []
    duplicates_removed = 0

    for entry in entries:
        # Create key based on procedure name and fees
        key = (
            entry.get('procedure_name_ms', '').lower().strip(),
            entry.get('fee_min'),
            entry.get('fee_max'),
            entry.get('pakar_bedah_fee'),
            entry.get('pakar_anestesia_fee')
        )

        if key not in seen:
            seen[key] = True
            unique.append(entry)
        else:
            duplicates_removed += 1

    return unique, duplicates_removed

def validate(entry):
    """Validate an entry"""
    issues = []

    # Check procedure name
    if not entry.get('procedure_name_ms'):
        issues.append("Missing procedure name")
    elif len(entry['procedure_name_ms'].strip()) < 3:
        issues.append("Procedure name too short")

    # Check fees
    if entry.get('fee_min') is not None:
        if not isinstance(entry['fee_min'], (int, float)) or entry['fee_min'] < 0 or entry['fee_min'] > 100000:
            issues.append(f"Invalid fee_min: {entry['fee_min']}")

    if entry.get('fee_max') is not None:
        if not isinstance(entry['fee_max'], (int, float)) or entry['fee_max'] < 0 or entry['fee_max'] > 100000:
            issues.append(f"Invalid fee_max: {entry['fee_max']}")

    if entry.get('pakar_bedah_fee') is not None:
        if not isinstance(entry['pakar_bedah_fee'], (int, float)) or entry['pakar_bedah_fee'] < 0 or entry['pakar_bedah_fee'] > 100000:
            issues.append(f"Invalid pakar_bedah_fee: {entry['pakar_bedah_fee']}")

    if entry.get('pakar_anestesia_fee') is not None:
        if not isinstance(entry['pakar_anestesia_fee'], (int, float)) or entry['pakar_anestesia_fee'] < 0 or entry['pakar_anestesia_fee'] > 100000:
            issues.append(f"Invalid pakar_anestesia_fee: {entry['pakar_anestesia_fee']}")

    return len(issues) == 0, issues

def main():
    print("\n" + "="*70)
    print("Schedule 13 Extraction using Google Gemini 1.5 Pro Vision API")
    print("="*70 + "\n")

    # Check PDF exists
    if not os.path.exists(PDF_PATH):
        print(f"Error: {PDF_PATH} not found")
        sys.exit(1)

    # Extract from pages
    print(f"Extracting procedures from pages {START_PAGE}-{END_PAGE}...")
    all_entries = []
    total_pages = END_PAGE - START_PAGE + 1

    for page_num in range(START_PAGE, END_PAGE + 1):
        entries = extract_from_page(PDF_PATH, page_num)
        all_entries.extend(entries)
        time.sleep(1)  # Rate limiting - 1 second between API calls

    print(f"\n✓ Total raw extractions: {len(all_entries)}")

    # Deduplicate
    print("\nDeduplicating entries...")
    unique_entries, dup_count = deduplicate(all_entries)
    print(f"✓ Removed {dup_count} duplicates")
    print(f"✓ Unique entries: {len(unique_entries)}")

    # Validate
    print("\nValidating entries...")
    valid_entries = []
    flagged_entries = []

    for entry in unique_entries:
        is_valid, issues = validate(entry)
        if is_valid:
            valid_entries.append(entry)
        else:
            flagged_entries.append({"entry": entry, "issues": issues})

    print(f"✓ Valid entries: {len(valid_entries)}")
    print(f"⚠ Flagged for review: {len(flagged_entries)}")

    # Group by section type
    by_section = defaultdict(list)
    for entry in valid_entries:
        section = entry.get('section_type', 'Unknown')
        by_section[section].append(entry)

    # Output results
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Save clean data
    output_file = os.path.join(OUTPUT_DIR, "extracted_schedule13_gemini.json")
    output_data = {
        "metadata": {
            "extraction_tool": "Google Gemini 1.5 Pro Vision API",
            "pages_processed": f"{START_PAGE}-{END_PAGE}",
            "total_pages": total_pages,
            "total_raw_extractions": len(all_entries),
            "duplicates_removed": dup_count,
            "valid_entries": len(valid_entries),
            "flagged_entries": len(flagged_entries),
            "by_section": {section: len(entries) for section, entries in by_section.items()}
        },
        "data": valid_entries
    }

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    print(f"\n✓ Saved clean data to: {output_file}")

    # Save flagged entries
    if flagged_entries:
        flagged_file = os.path.join(OUTPUT_DIR, "flagged_for_review.json")
        with open(flagged_file, 'w', encoding='utf-8') as f:
            json.dump({"flagged_entries": flagged_entries}, f, indent=2, ensure_ascii=False)
        print(f"✓ Saved flagged entries to: {flagged_file}")

    # Save log
    log_file = os.path.join(OUTPUT_DIR, "extraction_log.txt")
    with open(log_file, 'w', encoding='utf-8') as f:
        f.write("SCHEDULE 13 EXTRACTION LOG\n")
        f.write("="*70 + "\n\n")
        f.write(f"Pages processed: {START_PAGE}-{END_PAGE}\n")
        f.write(f"Total pages: {total_pages}\n")
        f.write(f"Extraction tool: Google Gemini 1.5 Pro Vision API\n")
        f.write(f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("STATISTICS\n")
        f.write("-"*70 + "\n")
        f.write(f"Total raw extractions: {len(all_entries)}\n")
        f.write(f"Duplicates removed: {dup_count}\n")
        f.write(f"Unique entries: {len(unique_entries)}\n")
        f.write(f"Valid entries: {len(valid_entries)}\n")
        f.write(f"Flagged for review: {len(flagged_entries)}\n\n")
        f.write("BREAKDOWN BY SECTION\n")
        f.write("-"*70 + "\n")
        for section, entries in sorted(by_section.items()):
            f.write(f"{section}: {len(entries)}\n")

    print(f"✓ Saved log to: {log_file}")

    print("\n" + "="*70)
    print("✓ Extraction Complete!")
    print("="*70 + "\n")

    return output_data

if __name__ == "__main__":
    main()
