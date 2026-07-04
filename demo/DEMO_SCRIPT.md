# Demo Script

## PRE-DEMO CHECKLIST (30 mins before)

- [ ] Backend running: `cd backend && uvicorn main:app --reload --port 8000`
- [ ] Frontend running: `cd frontend && npm run dev`
- [ ] Ollama running: `ollama serve` (offline backup if Groq is down)
- [ ] `GROQ_API_KEY` set in `.env` and verified working (test one upload beforehand)
- [ ] Browser open at http://localhost:5173
- [ ] Bill_1.pdf and Bill_2.pdf on desktop, ready to drag
- [ ] `cached_bill2.json` open in a text editor (emergency backup)
- [ ] Phone silent, notifications off

## DEMO FLOW (3 minutes)

### [30 sec] The Problem

> "70% of private hospital bills in Malaysia are completely unregulated.
> Parliament's own Public Accounts Committee found hospitals charging
> separately for pillowcases and bedsheets. Patients have no way to know
> if their bill is fair. We fix that."

### [30 sec] Upload — Bill_1

- Drag Bill_1.pdf → "Analyse Bill"
- While loading: "Checking against 2,174 procedures from PHFSA Schedule 13,
  38 PAC-sourced and expert-documented bundling rules, and MOH drug prices"
- Show result: **2 red flags** — "Even a routine-looking bill catches real
  violations. This Chest X-Ray was billed at RM100 — the legal cap is RM40.
  This ECG was billed at RM80 — the cap is RM70. A patient has no way to
  spot either of these on their own. That's exactly the gap we close."

*(Note: Bill_1 is not a "zero flags" bill — don't claim otherwise on stage.
Two real Schedule 13 cap violations is actually a stronger opening than a
clean result, since it proves the tool catches things a patient would
never notice in an otherwise ordinary-looking bill.)*

### [60 sec] Flagged Bill — Bill_2

- Upload Bill_2.pdf
- Show summary card: "5 serious concerns, 6 worth querying"
- Point to RM280 specialist consult: "Legal cap is RM235. This is a
  Schedule 13 violation."
- Point to PAC flags: "Parliament named these exact items — pillowcase,
  bedsheet, clinical waste — in June 2026."
- Show Action Steps: "6 steps, from calling the hospital to the Consumer
  Claims Tribunal"

### [60 sec] Patient Package

- Open Letter EN: "Formal letter citing PHFSA and PAC. Generated in under
  4 seconds."
- Switch to Letter BM: "Bilingual."
- Open Phone Script: "For patients who don't know what to say when they
  call."
- Click Download: "They leave with everything they need."

## BACKUP PLAN

- [ ] Groq slow/down → Ollama takes over automatically (60 sec wait, warn judges)
- [ ] API crashes → open `cached_bill2.json`, say "let me show you the pre-run output"
- [ ] Frontend crashes → walk through `cached_bill2.json` verbally using the flag list
- [ ] Total power/laptop failure → show the 3 sample bills and explain the pipeline on the whiteboard
