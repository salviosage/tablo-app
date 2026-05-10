# Tablo-app

**Reconciliation engine for tax tocuments.**

AI-powered financial document reconciliation engine. Drop a shoebox of messy financial records, credit card statements, invoices, receipts, notes and Tablo parses, normalizes, cross-references, and flags what needs attention.

Most tools parse documents individually. Tablo reads them *against each other*: notes.txt tells the credit card parser which charges are personal, transaction IDs catch duplicates across months, refunds get matched to their original charges.

## Architecture

```
Intake > Extract > Normalize > Reconcile → Report
```

Each step is a plugin. New file type? Add an extractor. New bank format? Add a normalizer. New tax rule? Add a reconciliation rule.

## Stack

- **Backend:** FastAPI + Python 3.12, Tesseract OCR, pdfplumber, openpyxl
- **Frontend:** React + Vite, Tailwind CSS, Recharts
- **Infrastructure:** Docker Compose

## Quick start

```bash
docker compose up --build
```

- API: http://localhost:8000
- Frontend: http://localhost:3000
- API docs: http://localhost:8000/docs

## Development

### Backend only

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Frontend only

```bash
cd frontend
npm install
npm run dev
```

### Tests

```bash
cd backend && pytest
```

