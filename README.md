# SOPhistication

Where NLP meets SOP.

A law-firm internal tool that extracts structured data from SBA loan documents
(Terms & Conditions PDFs and optional Credit Memos) using a hybrid spaCy NER +
Claude pipeline. Reduces a 15–25 minute manual extraction task to under 10
seconds per document.

Built as the final project for *Natural Language Lawyering* at the University of
St. Thomas School of Law, with a parallel production pitch to Johnson Bealka, PLLC.

## Architecture at a glance

- **Backend:** Python 3.12 / Flask 3.x at `artifacts/sba-backend/`
- **Frontend:** React + Vite + TypeScript + Tailwind at `artifacts/sba-web/`
- **AI:** Anthropic Claude (`claude-sonnet-4-20250514`)
- **NER:** spaCy `en_core_web_sm` 3.8
- **PDF parsing:** pdfplumber
- **Database:** PostgreSQL (Replit-provisioned) via psycopg2
- **Generated client libs:** OpenAPI 3.1 spec → React Query hooks + Zod schemas (`lib/`)
- **Monorepo:** pnpm workspaces

## Pipeline

A staged extraction flow (PDF read → spaCy NER preprocessing → Claude deal-structure
analysis → Claude field extraction → regex fallbacks + NER hallucination
validation → formatting) feeds tiered confidence scoring. Critical fields like
`LoanNumber` and `MaturityDate` have regex fallbacks; extracted entities are
checked against the NER pass to flag likely hallucinations. Prompts are
versioned on disk and persisted per extraction; degraded runs surface through
an `extraction_health` field rather than failing silently. Reviewer verdicts
are captured in a `validation_feedback` table for cumulative learning.

## Document security

PDFs are encrypted at rest with Fernet (AES-128-CBC + HMAC-SHA256), keyed off
`SESSION_SECRET`. Downloads require time-limited (1 hour), HMAC-signed,
single-purpose tokens tied to a specific extraction ID and filename. Every
token issuance and download attempt — successful or not — is recorded in a
`file_access_log` audit table. A background thread deletes stored files older
than `FILE_RETENTION_DAYS` (default: 30).

## SharePoint

Optional push integration via MSAL + Microsoft Graph. Reader, writer, and auth
modules live in `artifacts/sba-backend/sharepoint/`. Configured via four
`SHAREPOINT_*` environment variables; the frontend hides the push button when
the backend reports the integration is unconfigured.

## Documentation

Full architecture, setup, environment variables, API reference, and SharePoint
app-registration steps live in [`replit.md`](./replit.md).

## Status

Active development. This is not a public package — no releases, no support.

https://github.com/sammythecapman/SOPhistication
