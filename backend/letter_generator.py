"""
letter_generator.py -- Generate a full patient empowerment package from a
flagged bill report, via a 3-tier LLM priority chain: Groq (fast, cloud)
-> Ollama (local, offline fallback) -> pure-Python template (last resort).

Pipeline: flagging.py's flag_bill() output -> build_prompt() -> TWO separate
call_llm() calls (short sections, then letters) -> merged into:
   {
     bill_summary, your_rights, action_steps,
     hospital_letter (english/bahasa_malaysia),
     escalation_guide, verbal_script
   }

Split into two calls rather than one because small local models (llama3.2,
3B parameters, used when Groq is unavailable) handle a focused 5-key or
1-key schema far more reliably than one giant 6-key schema with two full
bilingual letters embedded -- the single-call version reliably ran out of
its token budget partway through generating valid JSON, even at
num_predict=4096. Each call falls back independently to a pure-Python
template if both Groq and Ollama are unreachable or the response doesn't
parse -- this module must always return a usable package, LLM or not,
per-section.

Setup:
  Groq (primary, recommended): free API key at https://console.groq.com,
  set GROQ_API_KEY in .env. No local install needed.

  Ollama (offline fallback, optional) -- only used if Groq is unset or fails:
    Mac/Linux:
      curl -fsSL https://ollama.ai/install.sh | sh
      ollama pull llama3.2
    Windows:
      Download installer from https://ollama.ai/download
      Then: ollama pull llama3.2
    Then start the server (if not already running as a service):
      ollama serve
"""

import json
import os
import re
import sys
from typing import Callable, Optional

import requests
from dotenv import load_dotenv
from groq import Groq

# Windows consoles default to a legacy codepage (cp1252) that can't encode
# the emoji used in the debug logging below (print("✅ ..."), print("❌ ..."))
# -- without this, those print() calls themselves raise UnicodeEncodeError,
# which then masks whatever the real underlying LLM error was. Fixed here
# (not just in main.py) so it also applies to direct script usage --
# test_letter_generator.py, `python letter_generator.py ...`, etc.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

load_dotenv()

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = "llama-3.1-8b-instant"

PROMPT_SHORT = """
You are a Malaysian patient advocate. A patient has received a hospital bill
with suspicious charges. Generate ONLY this JSON object with EXACTLY these 5
keys -- no letters, no markdown, no extra text outside the JSON object:

{
  "bill_summary": "2-3 sentences in plain English explaining what was found and why it matters. No legal jargon. Write as if explaining to a friend.",
  "your_rights": "3-4 bullet points of the patient's actual legal rights under Malaysian law -- PHFSA 1998 patient grievance mechanism (10 working days for hospital to respond), right to itemised bill, right to request clarification on any charge.",
  "action_steps": ["an ordered list of 5-6 concrete steps the patient should take right now, starting from easiest (call hospital) to strongest (file complaint with MOH). Be specific -- include who to call, what to say, what documents to bring."],
  "escalation_guide": "what to do if the hospital does not respond within 10 working days or refuses to address the concerns. Include these specific escalation paths in order: Hospital Patient Relations Officer (first contact); Hospital CEO/Management (if PRO unresponsive); Ministry of Health Malaysia complaint portal at myhealth.gov.my or call 1-800-88-1000; Malaysian Medical Council (MMC) for doctor-related issues at mmc.gov.my; Tribunal Tuntutan Pengguna Malaysia (Consumer Claims Tribunal) for billing disputes under RM50,000 at ttpm.kpdnhep.gov.my; Media/public pressure as last resort.",
  "verbal_script": "a short, confident script (5-7 sentences) the patient can read when calling or visiting the hospital billing department. Simple conversational English. Example opening: 'Hello, I am calling about my bill dated [date]. I have reviewed my bill and found some charges I would like to discuss...'"
}

Never use: fraud, illegal, cheated, criminal.
Output ONLY valid JSON. No markdown, no explanation outside the JSON object.
"""

PROMPT_LETTERS = """
You are a Malaysian patient advocate. Generate ONLY this JSON object with
EXACTLY 1 key -- no other sections, no markdown, no extra text outside the
JSON object:

{
  "hospital_letter": {
    "english": "Full formal letter in English addressed to the Patient Relations Officer, citing specific flagged items below by name, PHFSA Schedule 13 for legal cap violations, PAC Report June 2026 for unbundling concerns, and MyPriMe for drug overcharges where relevant.",
    "bahasa_malaysia": "The same letter, fully translated into Bahasa Malaysia."
  }
}

Tone: firm but respectful -- requesting clarification, not accusing.
Never use: fraud, illegal, cheated, criminal.
Always use: exceeds the legal maximum, Parliament found, above reference price.
End both letters with: I look forward to your response within 10 working days
as provided under the Private Healthcare Facilities and Services Act 1998.
Add a disclaimer at the bottom of both letters: This letter was generated
based on publicly available Malaysian fee schedules and parliamentary
findings. It is not a legal document and does not constitute professional
legal advice.
Output ONLY valid JSON. No markdown, no explanation outside the JSON object.
"""


# ---------------------------------------------------------------------------
# Ollama call
# ---------------------------------------------------------------------------

def call_ollama(prompt: str, num_predict: int = 2048) -> str:
    response = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.3,
                "num_predict": num_predict,
            },
        },
        timeout=150,  # Ollama is slower than cloud APIs -- give it time
    )
    response.raise_for_status()
    return response.json()["response"]


def call_llm(prompt: str, num_predict: int = 1536) -> str:
    """
    Try Groq first (fast, cloud); fall back to Ollama (local, offline) if
    Groq is unset/fails. Raises if both fail -- callers (call_llm_with_retry)
    catch that and eventually fall back to the pure-Python template.
    """
    if GROQ_API_KEY:
        try:
            print("🚀 Attempting Groq...")
            client = Groq(api_key=GROQ_API_KEY)
            response = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=num_predict,
            )
            print("✅ Groq succeeded")
            return response.choices[0].message.content
        except Exception as e:
            print(f"❌ Groq failed: {e}")

    try:
        print("🔄 Attempting Ollama...")
        result = call_ollama(prompt, num_predict)
        print("✅ Ollama succeeded")
        return result
    except Exception as e:
        print(f"❌ Ollama failed: {e}")
        raise


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

def build_prompt(flagged_report: dict) -> str:
    """
    Build the shared bill-facts prompt from a flagging.py flag_bill() result.
    This is appended to whichever task-specific prompt (PROMPT_SHORT or
    PROMPT_LETTERS) is making the call.

    Note on adaptation from the original spec: flag_bill()'s items carry a
    "flags" list (an item can have more than one flag, at different
    severities) rather than flat "billed"/"message"/"source" fields, and
    flag_bill() itself doesn't know the hospital name / patient name / bill
    date / total amount (ocr.py's _SKIP_PATTERNS discards those header
    lines as noise). Bill metadata is read via .get() with the same
    fallback defaults as the original spec, and each item's "flags" list is
    flattened into one bullet line per flag, tagged by that flag's own
    severity/source/message.
    """
    lines = [
        f"Hospital: {flagged_report.get('hospital_name', 'Unknown Hospital')}",
        f"Patient: {flagged_report.get('patient_name', 'Patient')}",
        f"Bill Date: {flagged_report.get('bill_date', 'Unknown')}",
        f"Total Amount: RM{flagged_report.get('total_amount', '0')}",
        "",
    ]

    red_lines = []
    yellow_lines = []

    for item in flagged_report.get("flagged_items", []):
        name = item.get("item_name") or "Unknown item"
        billed = item.get("total_price", "?")
        ref_max = item.get("reference_max")
        ref_max = "N/A" if ref_max is None else f"RM{ref_max}"

        for flag in item.get("flags", []):
            line = (
                f"- {name}: billed RM{billed}, cap/reference {ref_max}, "
                f"source: {flag['source']}, reason: {flag['message']}"
            )
            if flag["severity"] == "red":
                red_lines.append(line)
            else:
                yellow_lines.append(line)

    if red_lines:
        lines.append("RED FLAGS (serious — cite law/PAC):")
        lines.extend(red_lines)

    if yellow_lines:
        lines.append("\nYELLOW FLAGS (worth querying):")
        lines.extend(yellow_lines)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

_SHORT_REQUIRED_KEYS = [
    "bill_summary", "your_rights", "action_steps",
    "escalation_guide", "verbal_script",
]

# Top-level key names Ollama might invent instead of "hospital_letter".
_LETTER_KEY_ALIASES = {
    "letter": "hospital_letter",
    "letters": "hospital_letter",
    "formal_letter": "hospital_letter",
}

# Sub-key names within hospital_letter Ollama might invent instead of the
# expected "english" / "bahasa_malaysia".
_LETTER_SUBKEY_ALIASES = {
    "en": "english",
    "eng": "english",
    "bm": "bahasa_malaysia",
    "malay": "bahasa_malaysia",
    "bahasa": "bahasa_malaysia",
    "bahasa_melayu": "bahasa_malaysia",
}

_REQUIRED_LETTER_SUBKEYS = ["english", "bahasa_malaysia"]


def _repair_json(text: str) -> str:
    """
    llama3.2 reliably gets the JSON *content* right but frequently botches
    the outer syntax: it forgets the closing "}" for the object entirely
    (observed: zero "}" characters anywhere in the response, so the
    "\\{.*\\}" extraction regex below can't even find a candidate to
    match), and/or leaves a trailing comma before whatever closing brace it
    does write. Neither is a content problem -- just punctuation -- so a
    light structural repair is tried before parsing.
    """
    # Drop a trailing comma immediately before a closing brace/bracket.
    text = re.sub(r",(\s*[}\]])", r"\1", text)

    # Balance any unmatched opening braces/brackets by appending closers.
    # Safe here because "text" is already trimmed to start at the first
    # "{" -- any imbalance at this point means the model simply never
    # emitted the closer(s), not that there's trailing garbage to worry about.
    text = text.rstrip()
    open_braces = text.count("{") - text.count("}")
    open_brackets = text.count("[") - text.count("]")
    text += "]" * max(open_brackets, 0) + "}" * max(open_braces, 0)

    return text


def _extract_json(raw: str) -> dict:
    """Shared JSON extraction/repair logic used by both parse_short_response()
    and parse_letters_response()."""
    # Strip markdown fences -- Ollama sometimes adds them
    clean = re.sub(r"```json|```", "", raw).strip()

    # Find the JSON object if there's extra text around it. If the model
    # never wrote a closing "}" at all, this regex won't match anything --
    # fall back to everything from the first "{" onward and let
    # _repair_json() supply the missing closer.
    match = re.search(r"\{.*\}", clean, re.DOTALL)
    if match:
        clean = match.group()
    else:
        brace_start = clean.find("{")
        if brace_start != -1:
            clean = clean[brace_start:]

    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        return json.loads(_repair_json(clean))


def _coerce_string_field(value):
    """
    your_rights/bill_summary/escalation_guide/verbal_script are specified as
    strings, but llama3.2 sometimes returns a JSON array of bullet strings
    instead of one string with embedded bullets. Left as-is, that renders
    as a raw Python list repr (e.g. "['You have the right...', ...]")
    wherever the value gets displayed. Coerce a list back into a proper
    bullet-point string; leave an already-correct string untouched.
    """
    if isinstance(value, list):
        return "\n".join(f"- {item}" if not str(item).lstrip().startswith("-") else str(item) for item in value)
    return value


def parse_short_response(raw: str) -> dict:
    """Validate the 5-key short-sections response (no hospital_letter)."""
    result = _extract_json(raw)

    if not all(k in result for k in _SHORT_REQUIRED_KEYS):
        raise ValueError(f"Missing required keys. Got: {list(result.keys())}")

    parsed = {k: result[k] for k in _SHORT_REQUIRED_KEYS}
    for key in ("bill_summary", "your_rights", "escalation_guide", "verbal_script"):
        parsed[key] = _coerce_string_field(parsed[key])

    return parsed


def parse_letters_response(raw: str) -> dict:
    """Validate the 1-key hospital_letter response (english/bahasa_malaysia)."""
    result = _extract_json(raw)

    for wrong, right in _LETTER_KEY_ALIASES.items():
        if wrong in result and right not in result:
            result[right] = result.pop(wrong)

    if "hospital_letter" not in result:
        raise ValueError(f"Missing hospital_letter key. Got: {list(result.keys())}")

    hospital_letter = result["hospital_letter"]
    if not isinstance(hospital_letter, dict):
        raise ValueError(f"hospital_letter must be an object, got: {type(hospital_letter)}")

    for wrong, right in _LETTER_SUBKEY_ALIASES.items():
        if wrong in hospital_letter and right not in hospital_letter:
            hospital_letter[right] = hospital_letter.pop(wrong)

    if not all(k in hospital_letter for k in _REQUIRED_LETTER_SUBKEYS):
        raise ValueError(
            f"Missing required hospital_letter keys. Got: {list(hospital_letter.keys())}"
        )

    return {"hospital_letter": {k: hospital_letter[k] for k in _REQUIRED_LETTER_SUBKEYS}}


# ---------------------------------------------------------------------------
# Template fallback (no LLM, no external dependencies)
# ---------------------------------------------------------------------------

_DISCLAIMER = (
    "This letter was generated based on publicly available Malaysian fee "
    "schedules and parliamentary findings. It is not a legal document and "
    "does not constitute professional legal advice."
)

_CLOSING = (
    "I look forward to your response within 10 working days as provided "
    "under the Private Healthcare Facilities and Services Act 1998."
)

_CLOSING_BM = (
    "Saya menantikan maklum balas tuan/puan dalam tempoh 10 hari bekerja "
    "sebagaimana diperuntukkan di bawah Akta Kemudahan dan Perkhidmatan "
    "Penjagaan Kesihatan Swasta 1998."
)

_DISCLAIMER_BM = (
    "Surat ini dijana berdasarkan skedul yuran Malaysia dan penemuan "
    "parlimen yang tersedia secara umum. Ini bukan dokumen undang-undang "
    "dan tidak merupakan nasihat guaman profesional."
)

_ESCALATION_GUIDE = """If the hospital does not respond within 10 working days, or refuses to \
address your concerns, escalate in this order:

1. Hospital Patient Relations Officer (first contact) -- ask for a written \
response and a reference/complaint number for your enquiry.

2. Hospital CEO / Management -- if the Patient Relations Officer does not \
respond or you are unsatisfied with their answer, request your enquiry be \
escalated in writing to hospital management/the CEO's office.

3. Ministry of Health Malaysia complaint portal -- myhealth.gov.my, or call \
1-800-88-1000. MOH oversees private hospital compliance with PHFSA 1998.

4. Malaysian Medical Council (MMC) -- mmc.gov.my, for concerns specifically \
about a doctor's conduct or professional fees.

5. Tribunal Tuntutan Pengguna Malaysia (Consumer Claims Tribunal) -- \
ttpm.kpdnhep.gov.my, for billing disputes under RM50,000. This is a formal, \
low-cost avenue for consumer claims without needing a lawyer.

6. Media / public pressure -- as a last resort, credible consumer or health \
journalism outlets have previously reported on private hospital billing \
practices following PAC's June 2026 findings.

Keep a written record (dates, names, reference numbers) at every step -- \
you will need it if you escalate further."""


def _flatten_flags(flagged_report: dict) -> tuple:
    """Returns (red_entries, yellow_entries), each a list of
    (item_name, billed, reference_max, source, message)."""
    red, yellow = [], []
    for item in flagged_report.get("flagged_items", []):
        name = item.get("item_name") or "Unknown item"
        billed = item.get("total_price", "?")
        ref_max = item.get("reference_max")
        ref_max = "N/A" if ref_max is None else f"RM{ref_max}"
        for flag in item.get("flags", []):
            entry = (name, billed, ref_max, flag["source"], flag["message"])
            (red if flag["severity"] == "red" else yellow).append(entry)
    return red, yellow


def _build_bill_summary(hospital: str, bill_date: str, total_amount, red: list, yellow: list) -> str:
    parts = [
        f"We reviewed your bill from {hospital} (dated {bill_date}, total "
        f"RM{total_amount}) and found {len(red)} charge(s) that appear to "
        f"break the legal maximum fee rules, and {len(yellow)} charge(s) "
        f"that are worth asking the hospital about."
    ]
    if red:
        parts.append(
            "The serious ones are charges above the legal maximum set by "
            "PHFSA Schedule 13, or items Parliament's Public Accounts "
            "Committee (June 2026) said should already be included in your "
            "room charge instead of billed on their own."
        )
    if yellow:
        parts.append(
            "The rest are smaller concerns -- prices above the usual "
            "reference range, or charges that might be duplicated or split "
            "up unnecessarily -- worth a polite question rather than a "
            "formal dispute."
        )
    return " ".join(parts)


_YOUR_RIGHTS = """- You have the right to receive an itemised bill that clearly lists every \
charge, not just a lump sum.
- Under the Private Healthcare Facilities and Services Act (PHFSA) 1998, a \
hospital's patient grievance mechanism must respond to a formal enquiry \
within 10 working days.
- You have the right to request written clarification on any charge on your \
bill before you pay it, especially charges that seem duplicated, unbundled, \
or above the legal fee cap.
- Raising these questions is not an accusation -- hospitals are required to \
be able to explain their own charges, and asking does not affect your right \
to future treatment there."""


def _build_action_steps(red: list, yellow: list) -> list:
    steps = [
        "Call the hospital's billing department or Patient Relations Officer "
        "and ask them to explain the specific charges listed below -- have "
        "your invoice number and the item names ready.",
        "Request a fully itemised, written breakdown of your bill if you "
        "don't already have one -- you are entitled to this under PHFSA 1998.",
    ]
    if red:
        steps.append(
            "For the items exceeding the legal maximum fee, specifically ask "
            "the billing department to explain the charge against PHFSA "
            "Schedule 13, and request a corrected invoice."
        )
    if yellow:
        steps.append(
            "For the remaining items, ask whether they should have been "
            "included in an existing room, nursing, or procedure charge "
            "instead of billed separately."
        )
    steps.extend([
        "Send the enclosed formal letter (English or Bahasa Malaysia) to the "
        "hospital's Patient Relations Officer, by email or in person, and "
        "keep a copy plus proof of submission.",
        "If there is no response, or an unsatisfactory one, within 10 "
        "working days, follow the escalation guide below -- starting with "
        "hospital management, then the Ministry of Health.",
    ])
    return steps


_VERBAL_SCRIPT_TEMPLATE = """Hello, I am calling about my bill from {hospital}, dated {bill_date}, \
totalling RM{total_amount}. I have reviewed the bill and found a few charges \
I would like to discuss -- some appear to be above the legal maximum fee, \
and a few others I'd like explained. Could you connect me with your Patient \
Relations Officer, or someone who can walk through the itemised charges with \
me? I have the specific line items and reference amounts ready to go through. \
I'd appreciate a written response, and if needed I'm happy to follow up by \
email so there's a record of our conversation. Thank you for your help."""


def generate_template_short(flagged_report: dict) -> dict:
    """Pure-Python fallback for the 5 short sections (no letters)."""
    hospital = flagged_report.get("hospital_name", "Unknown Hospital")
    bill_date = flagged_report.get("bill_date", "Unknown")
    total_amount = flagged_report.get("total_amount", "0")

    red, yellow = _flatten_flags(flagged_report)

    return {
        "bill_summary": _build_bill_summary(hospital, bill_date, total_amount, red, yellow),
        "your_rights": _YOUR_RIGHTS,
        "action_steps": _build_action_steps(red, yellow),
        "escalation_guide": _ESCALATION_GUIDE,
        "verbal_script": _VERBAL_SCRIPT_TEMPLATE.format(
            hospital=hospital, bill_date=bill_date, total_amount=total_amount,
        ),
    }


def generate_template_letters(flagged_report: dict) -> dict:
    """Pure-Python fallback for the hospital_letter section only."""
    hospital = flagged_report.get("hospital_name", "Unknown Hospital")
    patient = flagged_report.get("patient_name", "Patient")
    bill_date = flagged_report.get("bill_date", "Unknown")
    total_amount = flagged_report.get("total_amount", "0")

    red, yellow = _flatten_flags(flagged_report)

    def format_items(entries, heading):
        if not entries:
            return ""
        body = "\n".join(
            f"  - {name}: billed RM{billed} (reference {ref_max}) -- {message} "
            f"[{source}]"
            for name, billed, ref_max, source, message in entries
        )
        return f"\n{heading}\n{body}\n"

    red_block = format_items(red, "Items exceeding a legal maximum fee:")
    yellow_block = format_items(yellow, "Items worth querying:")

    letter_english = f"""To the Patient Relations Officer,
{hospital}

Re: Formal Inquiry Regarding Invoice Dated {bill_date} -- Patient: {patient}

Dear Sir/Madam,

I am writing to request clarification on several charges in my recent bill \
(total RM{total_amount}), which appear to exceed the legal maximum fee set \
by PHFSA Schedule 13, or which Parliament's Public Accounts Committee (PAC \
Report, June 2026) found should not be billed as separate line items.
{red_block}{yellow_block}
I would appreciate a written explanation for each item above, and a \
corrected invoice where applicable. This letter is a request for \
clarification, not an accusation of wrongdoing.

{_CLOSING}

Yours faithfully,
{patient}

---
{_DISCLAIMER}
"""

    def format_items_bm(entries, heading):
        if not entries:
            return ""
        body = "\n".join(
            f"  - {name}: dicaj RM{billed} (rujukan {ref_max}) -- {message} "
            f"[{source}]"
            for name, billed, ref_max, source, message in entries
        )
        return f"\n{heading}\n{body}\n"

    red_block_bm = format_items_bm(red, "Item yang melebihi fi maksimum yang dibenarkan undang-undang:")
    yellow_block_bm = format_items_bm(yellow, "Item yang wajar dipertanyakan:")

    letter_bahasa_malaysia = f"""Kepada Pegawai Perhubungan Pesakit,
{hospital}

Perihal: Pertanyaan Rasmi Berkenaan Invois Bertarikh {bill_date} -- Pesakit: {patient}

Tuan/Puan,

Saya menulis untuk memohon penjelasan berkenaan beberapa caj dalam bil saya \
baru-baru ini (jumlah RM{total_amount}), yang didapati melebihi fi maksimum \
yang dibenarkan di bawah Skedul 13 PHFSA, atau yang didapati oleh Jawatankuasa \
Kira-Kira Wang Negara Parlimen (Laporan PAC, Jun 2026) sepatutnya tidak \
dicajkan secara berasingan.
{red_block_bm}{yellow_block_bm}
Saya amat menghargai penjelasan bertulis bagi setiap item di atas, dan invois \
yang telah dibetulkan jika berkenaan. Surat ini adalah permohonan penjelasan, \
bukan tuduhan kesalahan.

{_CLOSING_BM}

Yang benar,
{patient}

---
{_DISCLAIMER_BM}
"""

    return {
        "hospital_letter": {
            "english": letter_english,
            "bahasa_malaysia": letter_bahasa_malaysia,
        },
    }


def generate_template_letter(flagged_report: dict) -> dict:
    """Full pure-Python fallback (all 6 keys) -- convenience wrapper merging
    generate_template_short() and generate_template_letters()."""
    return {
        **generate_template_short(flagged_report),
        **generate_template_letters(flagged_report),
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def call_llm_with_retry(
    prompt: str, parse_fn: Callable[[str], dict], strict_reminder: str,
    num_predict: int = 2048,
) -> dict:
    """
    Try the LLM priority chain (Groq -> Ollama, see call_llm()) once; if the
    response doesn't parse (small models sometimes invent extra keys or
    truncate the JSON), retry once with a stricter, more explicit
    instruction before giving up.
    """
    try:
        raw = call_llm(prompt, num_predict=num_predict)
        return parse_fn(raw)
    except Exception as e:
        print(f"First attempt failed: {e} — retrying with stricter prompt")

    raw = call_llm(strict_reminder + "\n\n" + prompt, num_predict=num_predict)
    return parse_fn(raw)


_STRICT_SHORT_REMINDER = (
    "IMPORTANT: Respond with ONLY a JSON object. No extra text, no markdown, "
    "no additional keys, no letters. The JSON must have EXACTLY these 5 "
    "keys: bill_summary, your_rights, action_steps, escalation_guide, "
    "verbal_script."
)

_STRICT_LETTERS_REMINDER = (
    "IMPORTANT: Respond with ONLY a JSON object. No extra text, no markdown, "
    "no additional keys. The JSON must have EXACTLY 1 key: hospital_letter "
    "(an object with exactly \"english\" and \"bahasa_malaysia\" keys)."
)


def generate_letter(flagged_report: dict) -> dict:
    """
    Generate a patient empowerment package from a flag_bill() result, via
    two independent LLM calls (short sections, then letters) merged
    together. Each call goes through the Groq -> Ollama -> template priority
    chain independently, so, for example, a working letters response is
    kept even if the short-sections call happened to fail, and vice versa.

    Always returns:
      {
        "bill_summary":      str,
        "your_rights":       str,
        "action_steps":      list[str],
        "hospital_letter":   {"english": str, "bahasa_malaysia": str},
        "escalation_guide":  str,
        "verbal_script":     str,
      }
    """
    prompt = build_prompt(flagged_report)

    try:
        short_parsed = call_llm_with_retry(
            PROMPT_SHORT + "\n\n" + prompt, parse_short_response,
            _STRICT_SHORT_REMINDER, num_predict=1536,
        )
        print("Short sections generated via LLM")
    except requests.exceptions.ConnectionError:
        print("Ollama not running — start it with: ollama serve")
        short_parsed = generate_template_short(flagged_report)
    except Exception as e:
        print(f"Short sections failed: {e} — using template")
        short_parsed = generate_template_short(flagged_report)

    try:
        letters_parsed = call_llm_with_retry(
            PROMPT_LETTERS + "\n\n" + prompt, parse_letters_response,
            _STRICT_LETTERS_REMINDER, num_predict=2048,
        )
        print("Hospital letters generated via LLM")
    except requests.exceptions.ConnectionError:
        print("Ollama not running — start it with: ollama serve")
        letters_parsed = generate_template_letters(flagged_report)
    except Exception as e:
        print(f"Letters failed: {e} — using template")
        letters_parsed = generate_template_letters(flagged_report)

    return {**short_parsed, **letters_parsed}


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python letter_generator.py <flagged_report.json>")
        sys.exit(1)
    with open(sys.argv[1], encoding="utf-8") as f:
        report = json.load(f)
    result = generate_letter(report)
    print(json.dumps(result, indent=2, ensure_ascii=False))
