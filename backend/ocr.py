"""
ocr.py -- Medical bill OCR pipeline (free, local, no API keys)

Pipeline:
  preprocess_image() -> run_ocr() -> parse_line_items()

Supported input: JPG, PNG, PDF (via pdf2image/poppler)
OCR engine:      Tesseract (pytesseract wrapper)
Image prep:      OpenCV -- grayscale, denoise, threshold, deskew, upscale
"""

import os
import re
import sys
from pathlib import Path
from typing import Optional

# Ensure poppler and tesseract are in PATH
poppler_path = r"C:\poppler\poppler-26.02.0\Library\bin"
tesseract_path = r"C:\Program Files\Tesseract-OCR"
for path in [poppler_path, tesseract_path]:
    if path not in os.environ.get("PATH", ""):
        os.environ["PATH"] = path + ";" + os.environ.get("PATH", "")

import cv2
import numpy as np
import pytesseract
from PIL import Image


# ---------------------------------------------------------------------------
# Image preprocessing
# ---------------------------------------------------------------------------

def preprocess_image(image_input):
    """
    Prepare an image for Tesseract.
    Accepts: file path (str/Path) or PIL Image.
    Returns: processed numpy array (grayscale, binarized).

    Steps applied:
      1. Grayscale conversion
      2. Upscale if too small  (Tesseract struggles below ~150 DPI equivalent)
      3. Gaussian denoise
      4. Adaptive threshold   (handles uneven phone-photo lighting)
      5. Deskew               (correct tilts from hand-held photos)
    """
    if isinstance(image_input, (str, Path)):
        img = cv2.imread(str(image_input))
        if img is None:
            raise ValueError(f"Cannot read image: {image_input}")
    elif isinstance(image_input, Image.Image):
        img = cv2.cvtColor(np.array(image_input.convert("RGB")), cv2.COLOR_RGB2BGR)
    else:
        img = image_input  # assume numpy already

    # 1. Grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 2. Upscale if image is small
    h, w = gray.shape
    if max(h, w) < 1500:
        scale = 2.0
        gray = cv2.resize(gray, None, fx=scale, fy=scale,
                          interpolation=cv2.INTER_CUBIC)

    # 3. Denoise
    gray = cv2.GaussianBlur(gray, (3, 3), 0)

    # 4. Adaptive threshold — binarize, handles shadows and gradient lighting
    binary = cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=31,
        C=11,
    )

    # 5. Deskew
    binary = _deskew(binary)

    return binary


def _deskew(image: np.ndarray) -> np.ndarray:
    """Rotate image to correct small tilts (up to +-15 degrees)."""
    coords = np.column_stack(np.where(image < 128))
    if len(coords) < 100:
        return image

    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = 90 + angle
    # Only correct small tilts; large angles are usually mis-detected
    if abs(angle) > 15:
        return image

    h, w = image.shape
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    return cv2.warpAffine(
        image, M, (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )


# ---------------------------------------------------------------------------
# OCR
# ---------------------------------------------------------------------------

# PSM 6: assume a single uniform block of text — works well for bill tables.
# OEM 3: default Tesseract engine (LSTM + legacy).
_TESS_CONFIG = "--psm 6 --oem 3"


def _tesseract_lang() -> str:
    """Use eng+msa if Malay language pack is installed, else eng only."""
    try:
        available = pytesseract.get_languages()
        return "eng+msa" if "msa" in available else "eng"
    except Exception:
        return "eng"


def run_ocr(processed_image: np.ndarray) -> str:
    """
    Run Tesseract on a preprocessed numpy image.
    Returns raw OCR text string.
    """
    lang = _tesseract_lang()
    pil_img = Image.fromarray(processed_image)
    return pytesseract.image_to_string(pil_img, lang=lang, config=_TESS_CONFIG)


# ---------------------------------------------------------------------------
# PDF support
# ---------------------------------------------------------------------------

def pdf_to_images(pdf_path: str) -> list:
    """
    Convert every PDF page to a PIL Image at 300 DPI.
    Requires: pdf2image + poppler installed on the system.
    Returns a non-empty list; raises if conversion yields nothing.
    """
    try:
        from pdf2image import convert_from_path
    except ImportError:
        raise ImportError(
            "pdf2image not installed. Run: pip install pdf2image\n"
            "Also install poppler: https://poppler.freedesktop.org/"
        )
    images = convert_from_path(pdf_path, dpi=300)
    if not images:
        raise RuntimeError(f"pdf2image returned no pages for: {pdf_path}")
    return images


# ---------------------------------------------------------------------------
# Line item parser
# ---------------------------------------------------------------------------

# Matches price-like tokens: 1,234.56 / 123.50 / 1234
_PRICE_RE = re.compile(
    r"\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?"
)

# Matches an "RM"-prefixed monetary amount -- the only thing we treat as a
# price. Bare numbers (dates, quantities, percentages) are never prices.
_RM_PRICE_RE = re.compile(
    r"RM[_\s]*(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)",
    re.IGNORECASE,
)

# Lines that are almost certainly headers / footers / totals — skip them
_SKIP_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        # generic table headers (schedule / gazette style)
        r"^item\s+desc",
        r"^no\.?\s+item",
        r"^butiran",
        r"^tatacara",
        r"^bil\s+item",
        r"^unit\s+price",
        r"^harga\s+seunit",
        r"^jumlah",
        r"^page\s+\d",
        r"^\s*$",
        # decorative separator lines -- only =, -, ─, ═, whitespace
        r"^[\s=\-─═_]+$",
        # patient / invoice metadata headers
        r"invoice\s+date",
        r"patient\s+id",
        r"patient\s+name",
        r"bill\s+number",
        r"admission\s+date",
        r"discharge\s+date",
        r"length\s+of\s+stay",
        r"payment\s+method",
        r"payment\s+status",
        r"date\s+paid",
        r"patient\s+signature",
        # section subtotal lines -- category name IS the whole line, followed
        # only by an RM amount (anchored, so real items that merely mention
        # "nursing"/"medications" etc. in their description are not caught)
        r"^\s*(professional\s+fees|ward\s*&?\s*accommodation|diagnostic\s+investigations|"
        r"medications?(\s*&?\s*supplies)?|nursing(\s*&?\s*ancillary\s+services)?|"
        r"subtotal|summary)\s*:?\s*RM[_\s]*[\d,]+(?:\.\d{1,2})?\s*$",
        # bill total / tax lines
        r"total\s+amount\s+due",
        r"^total\b",
        r"^grand\s+total",
        r"^amount\s+due",
        r"sales\s*&?\s*service\s+tax",
        r"^gst\b|^sst\b|^tax\b",
    ]
]


def _is_skip_line(line: str) -> bool:
    return any(p.search(line.strip()) for p in _SKIP_PATTERNS)


def _clean_price(token: str) -> Optional[float]:
    """Parse a price string to float. Returns None if out of sane range."""
    try:
        value = float(token.replace(",", ""))
        # Sane bounds: RM 0.01 to RM 99,999
        if 0.01 <= value <= 99999:
            return round(value, 2)
    except (ValueError, AttributeError):
        pass
    return None


def _extract_rm_prices(line: str) -> list:
    """
    Return all RM-prefixed monetary amounts found in a line, in order,
    as (value, match_start_index) tuples. Bare numbers (dates, percentages,
    quantities) are never picked up -- only tokens explicitly prefixed
    with "RM" are considered a price.
    """
    out = []
    for m in _RM_PRICE_RE.finditer(line):
        value = _clean_price(m.group(1))
        if value is not None:
            out.append((value, m.start()))
    return out


# Quantity patterns, tried in priority order against the WHOLE line (not just
# a prefix) so that a quantity followed by other words -- e.g. "3 nights @
# RM 600/night" -- is found even though it isn't adjacent to the price token.
_QTY_TIERS = [
    # "N x RM" / "N × RM" -- explicit multiply format immediately before a price
    re.compile(r"(\d{1,3})\s*[x×]\s*(?=RM\b)", re.IGNORECASE),
    # "N nights" / "N days" / "N bags" / "N capsules" / "N tablets" / "N pairs" / "N packs"
    re.compile(
        r"(\d{1,3})\s*(?:nights?|days?|bags?|capsules?|tablets?|pairs?|packs?|"
        r"units?|pcs?|bottles?|btl)\b",
        re.IGNORECASE,
    ),
    # "x N" / "× N" -- multiplier prefix before a bare quantity number
    re.compile(r"[x×]\s*(\d{1,3})\b", re.IGNORECASE),
]


def _extract_quantity_and_span(line: str):
    """
    Scan the whole line for a quantity expression using _QTY_TIERS, tried
    in priority order. Returns (quantity, (start, end)) for the first match,
    or (None, None) if nothing plausible is found.
    """
    for pattern in _QTY_TIERS:
        m = pattern.search(line)
        if m:
            q = int(m.group(1))
            if 1 <= q <= 999:
                return q, m.span()
    return None, None


def _extract_item_name(line: str) -> Optional[str]:
    """
    Strip RM-prefixed price tokens and return the remainder as item name.
    `line` is expected to already have any quantity expression removed by
    the caller. Returns None if nothing meaningful remains (< 3 alphabetic
    chars).
    """
    cleaned = _RM_PRICE_RE.sub("", line)
    cleaned = re.sub(r"[\s.\-|,:x]+$", "", cleaned).strip()
    cleaned = re.sub(r"^\d{1,3}[.)]\s*", "", cleaned)  # strip leading "1."

    # Clean up artifacts left behind by quantity/price extraction. Trailing
    # dashes, "@", and "/unit" fragments can nest (e.g. "Room - @ /night"),
    # so trim repeatedly until the string stops changing.
    cleaned = re.sub(r"\(\s*\)", "", cleaned)  # empty parens: "Foo ()" -> "Foo "
    while True:
        trimmed = re.sub(r"^[\s\-]+", "", cleaned)
        trimmed = re.sub(r"[\s\-@]+$", "", trimmed)       # trailing dashes/@/spaces
        trimmed = re.sub(r"/\s*\w*\s*$", "", trimmed)     # trailing "/night", "/unit"
        if trimmed == cleaned:
            break
        cleaned = trimmed

    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()  # collapse multiple spaces

    if len(re.findall(r"[a-zA-Z]", cleaned)) >= 3:
        return cleaned
    return None


def parse_line_items(raw_text: str, page_number: Optional[int] = None) -> list:
    """
    Parse raw OCR text into structured line items.

    Returns list of dicts:
      {
        "page_number":  int | null, -- source page (None for single-image input)
        "line_number":  int,        -- 1-indexed line in raw_text for this page
        "raw_text":     str,        -- exact OCR line
        "item_name":    str | null, -- extracted description
        "quantity":     int | null, -- extracted quantity
        "unit_price":   float|null, -- price per unit
        "total_price":  float|null, -- line total
      }

    Decision rules:
    - Only "RM"-prefixed tokens are treated as prices; bare numbers
      (dates, percentages, quantities) never are.
    - Lines with no RM-prefixed price are skipped entirely.
    - Quantity is extracted from anywhere in the line (e.g. "3 nights",
      "x 20", "14 capsules") via _extract_quantity_and_span, independent
      of price count, and stripped out before the item name is built.
    - Exactly one RM value on a line: unit_price=null, total_price=that
      value (quantity may still be populated from the text, but no unit
      price is derived without a second price to divide by).
    - Two (or more) RM values on a line: unit_price=first, total_price=
      second.
    - If quantity and unit_price are both present, quantity x unit_price
      must be within 5% of total_price -- otherwise quantity and
      unit_price are cleared and only total_price is kept.
    """
    results = []

    for i, raw_line in enumerate(raw_text.splitlines(), start=1):
        line = raw_line.strip()

        if not line or _is_skip_line(line):
            continue

        prices = _extract_rm_prices(line)
        if not prices:
            continue  # no RM-prefixed price -> not a billable line item

        quantity, qty_span = _extract_quantity_and_span(line)
        unit_price: Optional[float] = None
        total_price: Optional[float] = None

        if len(prices) == 1:
            total_price = prices[0][0]
        else:
            unit_price, total_price = prices[0][0], prices[1][0]

            if quantity and unit_price:
                computed = quantity * unit_price
                tolerance = max(0.10, total_price * 0.05)
                if abs(computed - total_price) > tolerance:
                    quantity = None
                    unit_price = None

        name_source = line
        if qty_span:
            start, end = qty_span
            name_source = name_source[:start] + name_source[end:]

        results.append({
            "page_number":  page_number,
            "line_number":  i,
            "raw_text":     raw_line,
            "item_name":    _extract_item_name(name_source),
            "quantity":     quantity,
            "unit_price":   unit_price,
            "total_price":  total_price,
        })

    return results


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def deduplicate_line_items(line_items: list, keep_potential_duplicates: bool = True) -> list:
    """
    Remove repeated headers/footers that appear across multiple pages.

    Strategy: items with no quantity are candidates for deduplication
    (quantities indicate real charges; header rows never have quantities).
    A (normalised_name, total_price) pair is a repeat candidate once its key
    has already been seen.

    keep_potential_duplicates controls what happens to a repeat:
      - True (default): only removed when it appears on a DIFFERENT page
        than the first occurrence -- the genuine repeated-header/footer
        case (e.g. hospital letterhead reprinted at the top of every page).
        A repeat on the SAME page is left in place, since it may be a real
        duplicate charge (e.g. a lab test billed twice) that downstream
        fraud-flagging logic (flagging.py) needs to see intact.
      - False: removed regardless of page, matching a plain
        first-occurrence-wins dedup.
    """
    first_seen_page: dict = {}
    result = []

    for item in line_items:
        if item["quantity"] is None and item["item_name"] is not None:
            key = (item["item_name"].lower().strip(), item["total_price"])
            if key in first_seen_page:
                same_page = first_seen_page[key] == item.get("page_number")
                if not keep_potential_duplicates or not same_page:
                    continue
            else:
                first_seen_page[key] = item.get("page_number")
        result.append(item)

    return result


# ---------------------------------------------------------------------------
# Multi-page pipeline
# ---------------------------------------------------------------------------

def process_multi_page_bill(file_path: str) -> dict:
    """
    Full multi-page pipeline: file -> per-page preprocess/OCR/parse -> merge.

    Accepts JPG, PNG, or PDF. For images, behaves as a single-page PDF.
    Returns:
      {
        "page_count":           int,
        "pages":                list[dict],  -- per-page raw_text and line_items
        "line_items":           list[dict],  -- merged, deduplicated across all pages
        "total_lines_extracted":int,         -- item count before deduplication
      }

    Each line item carries a "page_number" field for tracing back to source.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    is_pdf = path.suffix.lower() == ".pdf"

    if is_pdf:
        pil_images = pdf_to_images(str(path))
    else:
        pil_images = [Image.open(str(path))]

    page_count = len(pil_images)
    pages = []
    all_items: list = []

    for page_num, pil_img in enumerate(pil_images, start=1):
        preprocessed = preprocess_image(pil_img)
        raw_text = run_ocr(preprocessed)
        items = parse_line_items(raw_text, page_number=page_num)
        pages.append({
            "page":       page_num,
            "raw_text":   raw_text,
            "line_items": items,
        })
        all_items.extend(items)

    total_lines_extracted = len(all_items)
    deduped = deduplicate_line_items(all_items)

    return {
        "page_count":            page_count,
        "pages":                 pages,
        "line_items":            deduped,
        "total_lines_extracted": total_lines_extracted,
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def process_bill(file_path: str) -> dict:
    """
    Full pipeline: file -> preprocessed image(s) -> OCR -> parsed items.

    Accepts JPG, PNG, or PDF. Multi-page PDFs are processed page-by-page
    with deduplication applied across pages.

    Returns:
      {
        "file":                  str,
        "pages":                 int,
        "raw_text":              str,        -- concatenated OCR from all pages
        "line_items":            list[dict], -- parsed, deduplicated items
        "per_page":              list[dict], -- [{"page", "raw_text", "item_count"}]
        "total_lines_extracted": int,        -- item count before deduplication
      }
    """
    multi = process_multi_page_bill(file_path)

    raw_text = "\n".join(p["raw_text"] for p in multi["pages"])

    return {
        "file":                  file_path,
        "pages":                 multi["page_count"],
        "raw_text":              raw_text,
        "line_items":            multi["line_items"],
        "per_page":              [
            {
                "page":       p["page"],
                "raw_text":   p["raw_text"],
                "item_count": len(p["line_items"]),
            }
            for p in multi["pages"]
        ],
        "total_lines_extracted": multi["total_lines_extracted"],
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python ocr.py <image_or_pdf_path>")
        sys.exit(1)
    import json
    result = process_bill(sys.argv[1])
    print(json.dumps(result, indent=2, ensure_ascii=False))
