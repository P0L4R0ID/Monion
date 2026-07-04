# Sabah Bill Checker

Malaysian medical bill analyser — Sabah Smart City Hackathon

Detects overcharges, unbundled items, and billing violations
by checking against PHFSA Schedule 13, PAC parliamentary
findings, and MOH drug price references.

## Running locally

```
cd backend && uvicorn main:app --reload --port 8000
cd frontend && npm run dev
ollama serve
```

## Data sources

PHFSA Schedule 13 · PAC Report June 2026 · MOH MyPriMe · SST Policy 5/2025

## Stack

FastAPI · Tesseract OCR · rapidfuzz · Groq (llama-3.1-8b-instant) · React · Vite
