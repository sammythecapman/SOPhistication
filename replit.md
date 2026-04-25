# SBA Loan Data Extraction Tool

## Overview

A full-stack law firm internal tool that extracts structured data from SBA loan documents (Terms & Conditions PDFs and optional Credit Memo PDFs) using a 3-stage AI pipeline.

## Architecture

### Frontend (`artifacts/sba-web/`)
- **React + Vite** web app served at `/`
- Drag-and-drop PDF upload for Terms & Conditions and optional Credit Memo
- Real-time progress polling during extraction
- Color-coded results display (green = populated, gray = empty)
- Extraction history sidebar
- JSON download of results
- SharePoint push button (placeholder, configurable)

### Python Flask Backend (`artifacts/sba-backend/`)
- **Flask** API served at `/api` (port 8080)
- Replaces the original Node.js Express api-server
- Full extraction pipeline with threading for async processing

### Database
- **PostgreSQL** (Replit-provisioned) via psycopg2
- `sba_extractions` — extraction results
- `validation_feedback` — reviewer verdicts for cumulative learning
- `file_access_log` — full audit trail of all file token issuances and downloads

### Document Security Controls (`file_security.py`)
- **Encryption at rest** — PDFs are encrypted with Fernet (AES-128-CBC + HMAC-SHA256) before writing to `stored_files/`; key is derived from `SESSION_SECRET` via SHA-256
- **Signed download tokens** — downloads require a time-limited (1 hour) HMAC-SHA256 signed token issued by `GET /api/extractions/{id}/files/{filename}/token`; tokens are single-purpose (tied to extraction ID + filename)
- **Access audit log** — every token issuance and download attempt (success or failure + reason) is recorded in `file_access_log`
- **Automatic file expiration** — a background thread deletes stored files older than `FILE_RETENTION_DAYS` days (default: 30); configurable via env var

## Extraction Pipeline (3 stages)

1. **PDF Ingestion** — `pdfplumber` reads text from uploaded PDFs
2. **NER Preprocessing** — spaCy `en_core_web_sm` extracts named entities (persons, orgs, dates, money) to create hint blocks for Claude
3. **LLM Extraction** — Two Claude API calls:
   - `analyze_deal_structure()` — identifies deal type, guarantor counts, etc.
   - `extract_fields()` — extracts all applicable fields using NER hints
4. **Post-Extraction** — regex fallbacks for LoanNumber/MaturityDate, NER validation for hallucinations
5. **Formatting** — currency (`$X,XXX.XX`), dates (`January 15, 2025`), percentages (`X.XX%`), number-to-words

## Stack

- **Monorepo tool**: pnpm workspaces
- **Backend language**: Python 3.12
- **Backend framework**: Flask 3.x + Flask-CORS
- **AI model**: Anthropic Claude (`claude-sonnet-4-20250514`)
- **NER**: spaCy `en_core_web_sm` 3.8
- **PDF parsing**: pdfplumber
- **Database**: PostgreSQL + psycopg2
- **Frontend**: React + Vite + TypeScript + Tailwind CSS
- **Frontend packages**: lucide-react, react-dropzone, framer-motion, date-fns

## Directory Structure

```
artifacts/
├── sba-web/          # React Vite frontend (port 21230, proxy at /)
│   └── src/
│       ├── pages/    # Home, History, ExtractionView, Results
│       └── components/
└── sba-backend/      # Python Flask backend (port 8080, proxy at /api)
    ├── app.py        # Main Flask app + all routes
    ├── db.py         # PostgreSQL connection + CRUD operations
    ├── extraction/   # Core AI pipeline modules
    │   ├── pipeline.py      # Orchestrator
    │   ├── ner_engine.py    # spaCy NER
    │   ├── schemas.py       # Deal analysis + dynamic schema
    │   ├── formatting.py    # Field formatters
    │   └── regex_fallbacks.py # Critical field fallbacks
    └── sharepoint/   # SharePoint integration (configurable)
        ├── auth.py   # MSAL authentication
        ├── reader.py # Browse/download from SharePoint
        └── writer.py # Push to SharePoint list/folder
lib/
├── api-spec/         # OpenAPI 3.1 spec
├── api-client-react/ # Generated React Query hooks
└── api-zod/          # Generated Zod schemas
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/healthz | Health check |
| POST | /api/extract | Upload PDFs, start extraction job |
| GET | /api/jobs/{jobId} | Poll job status + progress |
| GET | /api/extractions | List all past extractions |
| GET | /api/extractions/{id} | Get specific extraction |
| DELETE | /api/extractions/{id} | Delete extraction |
| GET | /api/extractions/{id}/download | Download formatted JSON |
| GET | /api/sharepoint/status | Check SharePoint config |
| POST | /api/sharepoint/push/{id} | Push extraction to SharePoint |

## Environment Variables Required

- `ANTHROPIC_API_KEY` — Required for Claude API calls
- `DATABASE_URL` — Auto-provisioned by Replit
- `SESSION_SECRET` — Required. Used to derive the file-encryption key and to sign download tokens
- `ALLOWED_ORIGINS` — **Required for production.** Comma-separated CORS allowlist (e.g. `https://jbl-sba-data-extractor.smcapper4.repl.co,http://localhost:5173`). If unset/empty in dev, falls back to `http://localhost:5173,http://localhost:21230` — **never** `*`. The resolved list is logged at startup.
- `FILE_RETENTION_DAYS` — Optional. Days to keep encrypted source PDFs (default: 30)
- `SHAREPOINT_MODE` — Optional. Set to `mock` to force the mock SharePoint backend even when credentials are present
- `SHAREPOINT_CLIENT_ID` — Optional (Azure AD app)
- `SHAREPOINT_CLIENT_SECRET` — Optional (Azure AD secret)
- `SHAREPOINT_TENANT_ID` — Optional (Azure AD tenant)
- `SHAREPOINT_SITE_URL` — Optional (e.g., https://yourfirm.sharepoint.com/sites/SBALoans)
- `SHAREPOINT_LIST_NAME` — Optional (defaults to "SBA Extractions")

## Extraction Health

Every extraction now carries an `extraction_health` block:

```json
{ "degraded": true|false, "stage_failures": [ { "stage": "...", "reason": "...", "message": "..." } ] }
```

If a Claude stage (`deal_analysis` or `field_extraction`) fails — malformed JSON, API error, schema validation, etc. — the pipeline raises `ExtractionStageError` (defined in `extraction/errors.py`), the orchestrator records it instead of crashing, and the result is marked degraded. The frontend Results page surfaces this as an amber warning banner so reviewers know that blank fields may reflect a stage failure rather than missing data.

## Versioned Prompts and Schema Validation

Both Claude prompts live as plain text under `extraction/prompts/<name>/vN.txt` and are loaded at call time via `extraction/prompts/registry.load_prompt(name, version="latest")` — no prompt strings remain in `schemas.py`. The active versions are logged at startup as `PROMPT_VERSIONS`.

Claude's JSON output is validated at the boundary by `extraction/models.py`:
- `DealStructure` (Pydantic, `extra="forbid"`) gates the deal-analysis output. Unknown keys raise `ValidationError`, which the pipeline converts to `ExtractionStageError(reason="schema_validation")` and marks the extraction degraded.
- `validate_extracted_fields(raw, expected_keys)` reconciles the dynamic field-extraction output against `build_schema(deal)`: unknown keys are dropped (warn-log), non-strings are coerced to `str` (warn-log), missing expected keys are filled with `""`.

Every saved extraction is tagged with the prompt versions that produced it via two new columns: `deal_analysis_prompt_version` and `field_extraction_prompt_version`. The `ExtractionView` page shows them in fine print (hidden on legacy rows). To tag pre-existing rows once after deploying this change, run `python artifacts/sba-backend/scripts/backfill_prompt_versions.py` — it's idempotent and stamps untagged rows as `pre-versioning`.

## SharePoint Setup

1. Register an app in Azure AD: portal.azure.com → Azure Active Directory → App registrations
2. Grant permissions: `Sites.ReadWrite.All`, `Files.ReadWrite.All`
3. Create a client secret
4. Set the four SHAREPOINT_* environment variables above
