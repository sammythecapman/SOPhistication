# Deal Analysis Prompt

## Purpose
First Claude call. Given the Terms & Conditions PDF text and the optional Credit Memo PDF text, determine the high-level deal structure (deal type, borrower/guarantor counts, real estate / construction flags, loan program). The output is then used by `build_schema()` to decide which fields the second Claude call should attempt to extract.

## Inputs
- `{terms_text}` — Terms & Conditions text. Caller is responsible for any truncation (currently first 4000 chars).
- `{memo_text}` — Credit memo text or the literal string `"Not provided"`. Caller truncates (currently first 2000 chars).

## Expected Output Schema
A single JSON object (no prose, no markdown fences). Validated against `extraction.models.DealStructure` (Pydantic, `extra="forbid"`):

```json
{
  "deal_type": "Asset Purchase | Stock Purchase | Real Estate Purchase | Construction | Equipment | Working Capital | Refinance | Other",
  "has_real_estate": true,
  "has_construction": false,
  "has_equipment": false,
  "has_seller": true,
  "has_landlord_lease": false,
  "borrower_count": 1,
  "has_second_borrower": false,
  "has_personal_guarantors": true,
  "personal_guarantor_count": 2,
  "has_corporate_guarantors": false,
  "corporate_guarantor_count": 0,
  "loan_program": "SBA 7(a) Standard"
}
```

## Changelog
- **v1** — initial extraction from inline f-string in `schemas.py`, 2026-04-25.
