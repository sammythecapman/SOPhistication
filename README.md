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
- **Frontend:** React + Vite + TypeScript at `artifacts/sba-web/`
- **AI:** Anthropic Claude (`claude-sonnet-4-20250514`)
- **NER:** spaCy `en_core_web_sm`
- **PDF parsing:** pdfplumber
- **Database:** PostgreSQL (Replit-provisioned)
- **Monorepo:** pnpm workspaces

A 3-stage extraction pipeline (PDF read → NER preprocessing → Claude deal
analysis + field extraction) feeds tiered confidence scoring, regex fallbacks
for critical fields, and a SharePoint push integration. Prompts are versioned
on disk and persisted per extraction; degraded runs surface through an
`extraction_health` field rather than failing silently.

## Documentation

Full architecture, setup, environment variables, and API reference live in
[`replit.md`](./replit.md).

## Status

Active development. This is not a public package — no releases, no support.
