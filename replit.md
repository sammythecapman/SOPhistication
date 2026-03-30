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
- `sba_extractions` table stores all extraction results

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
- `SHAREPOINT_CLIENT_ID` — Optional (Azure AD app)
- `SHAREPOINT_CLIENT_SECRET` — Optional (Azure AD secret)
- `SHAREPOINT_TENANT_ID` — Optional (Azure AD tenant)
- `SHAREPOINT_SITE_URL` — Optional (e.g., https://yourfirm.sharepoint.com/sites/SBALoans)
- `SHAREPOINT_LIST_NAME` — Optional (defaults to "SBA Extractions")

## SharePoint Setup

1. Register an app in Azure AD: portal.azure.com → Azure Active Directory → App registrations
2. Grant permissions: `Sites.ReadWrite.All`, `Files.ReadWrite.All`
3. Create a client secret
4. Set the four SHAREPOINT_* environment variables above
