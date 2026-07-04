"""
main.py -- FastAPI entry point wiring OCR -> matcher -> flagging ->
letter_generator into one running API.

Run:
  uvicorn main:app --reload --port 8000
"""

import os
import re
import tempfile
import uuid

import uvicorn
from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ocr import process_bill
from matcher import match_bill
from flagging import flag_bill
from letter_generator import generate_letter

app = FastAPI(title="Sabah Bill Checker API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}
MAX_FILE_SIZE_MB = 10

# tempfile.gettempdir() rather than a hardcoded "/tmp/" -- "/tmp/" is not a
# real path on Windows (this project's dev environment), only on Linux/Mac.
TEMP_DIR = tempfile.gettempdir()


def extract_metadata(ocr_result: dict) -> dict:
    """
    Pull bill header fields (hospital name, patient name, bill date, total
    amount) out of the raw OCR text so letter_generator.py's build_prompt()/
    generate_template_letter() don't have to fall back to placeholders like
    "Unknown Hospital" or a literal "[Bill Date]".

    Note: each pattern's *capture group* is used, not the whole match --
    matching on match.group() (group 0) here would keep the field label in
    the extracted value, e.g. total_amount would come out as
    "TOTAL AMOUNT DUE: RM 4,695.80" instead of "4,695.80", which then
    duplicates the label when build_prompt() writes
    f"Total Amount: RM{total_amount}". The hospital_name pattern also
    matches the whole line (not just from the "hospital"/"klinik" keyword
    onward), since matching from the keyword itself would truncate a prefix
    like "GLENEAGLES " off "GLENEAGLES HOSPITAL KUALA LUMPUR".
    """
    raw = ocr_result.get("raw_text", "")
    metadata = {
        "hospital_name": "Private Hospital",
        "patient_name": "Patient",
        "bill_date": "Unknown",
        "total_amount": "Unknown",
    }

    hospital_match = re.search(
        r"(?im)^.*(?:hospital|klinik|clinic|medical centre).*$", raw
    )
    if hospital_match:
        metadata["hospital_name"] = hospital_match.group().strip()

    patient_match = re.search(r"(?i)patient\s*name[:\s]+([^\n]+)", raw)
    if patient_match:
        metadata["patient_name"] = patient_match.group(1).strip()

    date_match = re.search(r"(?i)(?:invoice|bill)\s*date[:\s]+([^\n]+)", raw)
    if date_match:
        metadata["bill_date"] = date_match.group(1).strip()

    total_match = re.search(
        r"(?i)total\s*amount\s*due[:\s]*RM\s*([\d,]+\.?\d*)", raw
    )
    if total_match:
        metadata["total_amount"] = total_match.group(1).strip()

    return metadata


@app.get("/health")
def health():
    return {
        "status": "ok",
        "modules": ["ocr", "matcher", "flagging", "letter_generator"],
        "ollama_url": os.getenv("OLLAMA_URL", "http://localhost:11434"),
    }


@app.post("/upload")
async def upload_bill(file: UploadFile = File(...)):

    # 1. Validate file type
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return JSONResponse(status_code=415, content={
            "status": "error",
            "message": f"File type '{ext}' not supported. Upload PDF, JPG, or PNG."
        })

    # 2. Validate file size
    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE_MB * 1024 * 1024:
        return JSONResponse(status_code=413, content={
            "status": "error",
            "message": f"File too large. Maximum size is {MAX_FILE_SIZE_MB}MB."
        })

    # 3. Save to temp file with unique name (avoid conflicts)
    temp_path = os.path.join(TEMP_DIR, f"bill_{uuid.uuid4().hex}{ext}")
    with open(temp_path, "wb") as f:
        f.write(contents)

    try:
        # 4. OCR
        try:
            ocr_result = process_bill(temp_path)
        except Exception as e:
            return JSONResponse(status_code=422, content={
                "status": "error", "step": "ocr",
                "message": str(e),
                "hint": "Ensure the bill is clear, well-lit, and not blurry"
            })

        # 5. Match
        try:
            matched = match_bill(ocr_result['line_items'])
        except Exception as e:
            return JSONResponse(status_code=500, content={
                "status": "error", "step": "matcher", "message": str(e)
            })

        # 6. Flag
        try:
            flagged = flag_bill(matched)
        except Exception as e:
            return JSONResponse(status_code=500, content={
                "status": "error", "step": "flagging", "message": str(e)
            })

        # 7. Attach bill metadata (hospital/patient/date/total) so the
        #    letter doesn't fall back to generic placeholders, then
        #    generate the letter (never raises -- has template fallback)
        flagged.update(extract_metadata(ocr_result))
        letter = generate_letter(flagged)

        # 8. Return full result
        return {
            "status": "success",
            "file_info": {
                "filename": file.filename,
                "pages": ocr_result.get("pages", 1),
                "total_lines": ocr_result.get("total_lines_extracted", 0)
            },
            "line_items": ocr_result['line_items'],
            "flags": flagged,
            "letter": letter
        }

    finally:
        # Always clean up temp file
        if os.path.exists(temp_path):
            os.remove(temp_path)


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
