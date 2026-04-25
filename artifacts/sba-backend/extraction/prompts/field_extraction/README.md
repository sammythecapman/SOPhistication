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
- **v2** — added per-field source citations for process supervision, 2026-04-25. The model now returns a paired `<FieldName>_source` key for every schema key containing a verbatim ≤25-word quote from the source document, which the pipeline then verifies as a literal substring of the Terms & Conditions or Credit Memo text.
- **v3** — relaxed the strict-verbatim contract in two ways, 2026-04-25:
  1. Description fields (`Borrower*Description`, `LenderDescription`, `SellerDescription`) may now be **inferred** from clear contextual evidence (entity-name suffix + address state). The `_source` for an inferred description is the verbatim quote that served as the BASIS for the inference (typically the address line proving the state). Inference is **not** permitted for any other field type — those still require a verbatim quote.
  2. Encouraged value-only quotes for label/value layouts. Quoting `"Pierpoint Bank"` is preferred over inventing punctuation like `"Lender: Pierpoint Bank"` that may not exist verbatim in the PDF text. Pairs with the value-fallback added to the pipeline's verifier.
