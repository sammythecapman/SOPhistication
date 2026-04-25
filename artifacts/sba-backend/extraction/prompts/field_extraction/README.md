# Field Extraction Prompt

## Purpose
Second Claude call. Given the deal-structure result from the first call, the Terms & Conditions PDF text, the optional Credit Memo PDF text, NER hints from spaCy, and a JSON schema describing exactly which fields apply to this deal, extract every applicable field as a JSON object of strings.

## Inputs
- `{deal_type}` — string, e.g. `"Asset Purchase"` or `"Unknown"`.
- `{loan_program}` — string, e.g. `"SBA 7(a) Standard"` or `"Unknown"`.
- `{ner_hints}` — pre-formatted NER hint block (may be empty string).
- `{terms_text}` — full Terms & Conditions text (no truncation).
- `{memo_text}` — credit memo text or the literal string `"Not provided"`.
- `{schema_str}` — pretty-printed JSON object whose keys are the fields to extract for this deal (built by `build_schema()`).

## Expected Output Schema
A flat JSON object. Keys MUST be exactly the set of keys present in `{schema_str}`. Values MUST be strings (empty string `""` when not found). Validated by `extraction.models.validate_extracted_fields(raw, expected_keys=set(schema.keys()))`:

- Unexpected keys are dropped with a warning log (recoverable schema drift).
- Non-string values are coerced via `str(v)` with a warning log.
- Missing expected keys are filled with `""`.

## Changelog
- **v1** — initial extraction from inline f-string in `schemas.py`, 2026-04-25.
