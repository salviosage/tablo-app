# Tablo-app

**Reconciliation engine for tax tocuments.**

AI-powered financial document reconciliation engine. Drop a shoebox of messy financial records, credit card statements, invoices, receipts, notes, and Tablo parses, normalizes, cross-references, and flags what needs attention.

Most tools parse documents individually. Tablo reads them *against each other*: notes.txt tells the credit card parser which charges are personal, transaction IDs catch duplicates across months, refunds get matched to their original charges. That's what an accountant does — and what no CSV importer can.

## Architecture

```
Intake > Extract > Normalize > Reconcile → Report
```

Five-layer pipeline. Each layer is a plugin — new file types, bank formats, tax rules, and output formats can be added without changing the pipeline.

**Intake** — accepts ZIP or individual files, recursively extracts nested archives, classifies each file by type using magic-byte sniffing + extension mapping, filters OS junk (__MACOSX, .DS_Store). Creates a job with a unique ID.

**Extract** — dispatches each file to the right parser. PDF statements via pdfplumber + regex. Spreadsheets via openpyxl with brute-force date parsing (handles 6+ formats). Receipt images via Pillow preprocessing + Tesseract OCR (eng+fra for Montréal receipts). Text files with encoding fallback.

**Normalize** — transforms raw extractions into clean records. Category inference from 40+ merchant patterns. Personal charge detection by cross-referencing notes.txt with credit card transactions. Duplicate flagging via transaction ID analysis. Date normalization (DD/MM/YYYY → ISO). Invoice status and payment speed computation. Action item extraction from freeform [todo]/[done] notes.

**Reconcile** — the differentiator. Refund-to-charge matching by merchant + date + amount. Missing receipt detection for CRA compliance. Invoice aging with urgency labels. Expense anomaly detection (flags charges >30% above merchant average). Tax summary (deductible vs non-deductible by category). Data quality scoring (0-100). Human-readable insights.

**Report** — React dashboard with 6 tabs: Overview (stat cards, pie chart, bar charts, data quality score), Expenses (filterable table with flag badges), Invoices (payment tracking), Reconciliation (refund matches, overdue invoices, missing receipts, tax summary), Actions (todo/done), Insights (key findings + recommendations).

## Stack

- **Backend:** FastAPI, Python 3.12, Tesseract OCR, pdfplumber, openpyxl, Pillow
- **Frontend:** React 19, Vite, Tailwind CSS v4, Recharts, Lucide icons
- **Infrastructure:** Docker Compose

## Quick start

```bash
docker compose up --build
```

- Frontend: http://localhost:3000
- API: http://localhost:8000
- API docs: http://localhost:8000/docs

## Development

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload

# Frontend (separate terminal)
cd frontend
npm install
npm run dev

# Tests
cd backend && pytest -v
```

## API

| Method | Path | What it does |
|--------|------|-------------|
| `POST` | `/api/upload` | Upload files or ZIP, classify, create job |
| `POST` | `/api/jobs/{id}/process` | Full pipeline: extract → normalize → reconcile |
| `POST` | `/api/jobs/{id}/extract` | Extract raw data from files |
| `POST` | `/api/jobs/{id}/normalize` | Categorize, flag, compute totals |
| `POST` | `/api/jobs/{id}/reconcile` | Cross-document reconciliation |
| `GET` | `/api/jobs/{id}` | Job status and file inventory |
| `GET` | `/api/jobs` | List all jobs |
| `GET` | `/api/jobs/{id}/extract` | Retrieve extraction results |
| `GET` | `/api/jobs/{id}/normalize` | Retrieve normalized results |
| `GET` | `/api/jobs/{id}/reconcile` | Retrieve reconciliation results |
| `DELETE`| `/api/jobs/{id}` | Delete job and files |

## Test data

The `data/shoebox.zip` contains sample Q1 2025 records for a Montréal freelancer. Intentionally messy:

## Where this goes next: one month + paid APIs

Given another month and access to paid APIs, here's the roadmap — ordered by impact:

### Week 1 — Smarter extraction

**Replace Tesseract with a vision LLM for receipt parsing.**
**Add an LLM-powered text understanding layer.** 

### Week 2 — Live data connections

**Plaid integration for bank feeds.** 

**Email forwarding for receipts.** 
**Accounting software export.** 

### Week 3 — Tax intelligence

**Canadian tax rule engine.** 
**Quarterly installment estimation.** 

### Week 4 — Multi-client + production

**Persistent storage.** 
**Background processing.** 

**Conversational interface.** 

### Beyond

- **Invoice generation** 
- **Recurring expense detection** 
- **Multi-currency support** 
- **Audit trail** 
- **Mobile app** 
