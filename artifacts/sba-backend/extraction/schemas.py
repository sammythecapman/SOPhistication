"""
Deal structure analysis and dynamic schema building.

The actual prompt text lives in `extraction/prompts/<name>/vN.txt` and is
loaded via `prompts.registry.load_prompt`. This module is responsible only
for orchestrating the call, parsing/validating the response (Pydantic), and
returning the (data, prompt_version) tuple to the pipeline.
"""

import json
import time
import logging
import anthropic
from typing import Dict, Tuple

from pydantic import ValidationError

from .errors import ExtractionStageError
from .models import DealStructure, validate_extracted_fields
from .prompts.registry import load_prompt

logger = logging.getLogger(__name__)


def _claude_with_retry(client, max_retries: int = 5, **kwargs):
    """
    Call client.messages.create with exponential backoff on overloaded (529) errors.
    Retries up to max_retries times with delays: 2s, 4s, 8s, 16s, 32s.
    """
    delay = 2
    for attempt in range(max_retries):
        try:
            return client.messages.create(**kwargs)
        except anthropic.APIStatusError as e:
            if e.status_code == 529 and attempt < max_retries - 1:
                logger.warning(
                    "Claude overloaded (attempt %d/%d), retrying in %ds...",
                    attempt + 1, max_retries, delay,
                )
                time.sleep(delay)
                delay = min(delay * 2, 60)
            else:
                raise
        except anthropic.APIConnectionError:
            if attempt < max_retries - 1:
                logger.warning(
                    "Claude connection error (attempt %d/%d), retrying in %ds...",
                    attempt + 1, max_retries, delay,
                )
                time.sleep(delay)
                delay = min(delay * 2, 60)
            else:
                raise


def _strip_code_fence(raw: str) -> str:
    """Strip ```json … ``` or ``` … ``` fences if present."""
    if "```json" in raw:
        raw = raw.split("```json")[1].split("```")[0]
    elif "```" in raw:
        raw = raw.split("```")[1].split("```")[0]
    return raw.strip()


def analyze_deal_structure(
    terms_text: str, memo_text: str, client
) -> Tuple[dict, str]:
    """
    First Claude API call: figure out the deal type and structure
    so we only extract applicable fields in the next step.

    Returns (deal_dict, prompt_version).
    """
    template, prompt_version = load_prompt("deal_analysis")
    prompt = template.format(
        terms_text=terms_text[:4000],
        memo_text=memo_text[:2000] if memo_text else "Not provided",
    )

    try:
        response = _claude_with_retry(
            client,
            model="claude-sonnet-4-20250514",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}]
        )
    except Exception as e:
        logger.error(
            "analyze_deal_structure: Claude API error: %s", e, exc_info=True,
        )
        raise ExtractionStageError(
            stage="deal_analysis",
            reason="api_error",
            message=f"Anthropic API call failed: {e}",
        )

    raw = response.content[0].text
    cleaned = _strip_code_fence(raw)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as e:
        excerpt = raw[:500] if raw else ""
        logger.error(
            "analyze_deal_structure: JSON decode failed (%s). Raw excerpt: %r",
            e, excerpt,
        )
        raise ExtractionStageError(
            stage="deal_analysis",
            reason="json_decode",
            message=f"Claude returned malformed JSON for deal analysis: {e}",
            raw_excerpt=excerpt,
        )

    try:
        validated = DealStructure.model_validate(parsed)
    except ValidationError as e:
        # Log full details server-side, surface a sanitized message to callers.
        logger.error(
            "analyze_deal_structure: Pydantic validation failed. Errors: %s. Raw parsed: %r",
            e.errors(), parsed,
        )
        raise ExtractionStageError(
            stage="deal_analysis",
            reason="schema_validation",
            message=(
                "Claude returned a deal-analysis JSON object that did not match "
                f"the expected schema ({len(e.errors())} validation error(s))."
            ),
        )

    return validated.model_dump(), prompt_version


def build_schema(deal: dict) -> dict:
    """
    Return only the fields applicable to this deal type.
    Avoids extracting irrelevant fields.
    """
    fields = {
        "SBALoanNumber":        "",
        "SBALoanName":          "",
        "SBAApprovalDate":      "",
        "LoanAmountShort":      "",
        "LoanAmountLong":       "",
        # NOTE: LoanType is intentionally omitted here. It is derived from
        # the deal-analysis stage's `loan_program` (validated by the
        # DealStructure Literal) and injected into raw_data by the pipeline
        # after extract_fields. Re-adding it here would let Claude guess
        # values like "Variable" from interest-rate context.
        "SpreadShort":          "",
        "SpreadLong":           "",
        "InitialRateShort":     "",
        "InitialRateLong":      "",
        "MaturityDate":         "",
        "InitialPaymentDate":   "",
        "FirstPaymentAmountShort": "",
        "FirstPaymentAmountLong":  "",
        "LenderName":           "",
        "LenderDescription":    "",
        "LenderAddress1":       "",
        "LenderAddress2":       "",
        "Borrower1Name":        "",
        "Borrower1Description": "",
        "Borrower1StateOfOrganization": "",
        "BorrowerAddress1":     "",
        "BorrowerAddress2":     "",
        "DealType":             "",
        "State":                "",
    }

    if deal.get("has_second_borrower"):
        fields.update({
            "Borrower2Name":        "",
            "Borrower2Description": "",
            "Borrower2StateOfOrganization": "",
        })

    count = deal.get("personal_guarantor_count", 0)
    for i in range(1, min(count + 1, 5)):
        fields[f"PersonalGuarantor{i}"] = ""

    cg_count = deal.get("corporate_guarantor_count", 0)
    for i in range(1, min(cg_count + 1, 5)):
        fields.update({
            f"CompanyGuarantor{i}Name":                "",
            f"CompanyGuarantor{i}Description":         "",
            f"CompanyGuarantor{i}StateOfOrganization": "",
            f"CompanyGuarantor{i}Signor":              "",
            f"CompanyGuarantor{i}Title":               "",
        })

    if deal.get("has_real_estate"):
        fields.update({
            "PropertyAPN":          "",
            "PropertyCity":         "",
            "PropertyCounty":       "",
            "PropertyState":        "",
            "CommercialRealEstate": "",
            "ResidentialRealEstate":"",
            "Mortgages/DeedsOfTrust": "",
            "TitleCompanyName":     "",
        })

    if deal.get("has_construction"):
        fields.update({
            "GeneralContractorName":          "",
            "GeneralContractorDescription":   "",
            "GeneralContractorAddress1":      "",
            "GeneralContractorAddress2":      "",
            "ConstructionContractTitle":      "",
            "ConstructionContractDate":       "",
            "ConstructionContractAmountShort":"",
            "ConstructionContractAmountLong": "",
            "ConstructionPeriod":             "",
            "ArchitectName":                  "",
            "ArchitectDescription":           "",
            "ArchitectContractTitle":         "",
            "ArchitectContractDate":          "",
            "ArchitectAddress1":              "",
            "ArchitectAddress2":              "",
            "Construction":                   "",
            "InterestReserveAmountShort":     "",
            "InterestReserveAmountLong":      "",
        })

    if (deal.get("has_seller") or
            deal.get("deal_type") in ["Asset Purchase", "Stock Purchase"] or
            "purchase" in deal.get("deal_type", "").lower()):
        fields.update({
            "SellerName":       "",
            "SellerDescription":"",
            "SellerSignerName": "",
            "SellerSignerTitle":"",
            "InjectionAmountShort": "",
            "InjectionAmountLong":  "",
        })

    if deal.get("has_landlord_lease"):
        fields.update({
            "LeaseDate":          "",
            "LeaseAgreementTitle":"",
            "LandlordName":       "",
            "LandlordDescription":"",
        })

    return fields


def extract_fields(
    terms_text: str, memo_text: str, schema: dict, deal: dict,
    ner_hints: str, client,
) -> Tuple[Dict[str, str], Dict[str, str], str]:
    """
    Second Claude API call: extract all relevant fields with NER hints injected.

    Returns (values, sources, prompt_version):
      - values: dict reconciled against the dynamic schema (unknown keys
        dropped, non-strings coerced, missing keys filled with "")
      - sources: parallel dict of paired `<key>_source` quotes from the v2
        prompt's process-supervision contract; same key set as `values`
      - prompt_version: the version tag of the field_extraction template used
    """
    schema_str = json.dumps(schema, indent=2)
    # NOTE: load_prompt resolves to the latest version, currently v2 — which
    # asks the model to return paired `<FieldName>_source` keys for every
    # schema key. The pipeline's quote-verification step depends on this
    # contract; if you pin back to v1, source dicts will be empty and the
    # `field_sources` UI block will disappear gracefully.
    template, prompt_version = load_prompt("field_extraction")
    prompt = template.format(
        deal_type=deal.get("deal_type", "Unknown"),
        loan_program=deal.get("loan_program", "Unknown"),
        ner_hints=ner_hints,
        terms_text=terms_text,
        memo_text=memo_text if memo_text else "Not provided",
        schema_str=schema_str,
    )

    try:
        response = _claude_with_retry(
            client,
            model="claude-sonnet-4-20250514",
            # Doubled for paired _source quotes per field (v2 prompt)
            max_tokens=8192,
            messages=[{"role": "user", "content": prompt}]
        )
    except Exception as e:
        logger.error(
            "extract_fields: Claude API error: %s", e, exc_info=True,
        )
        raise ExtractionStageError(
            stage="field_extraction",
            reason="api_error",
            message=f"Anthropic API call failed: {e}",
        )

    raw = response.content[0].text
    cleaned = _strip_code_fence(raw)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as e:
        excerpt = raw[:500] if raw else ""
        logger.error(
            "extract_fields: JSON decode failed (%s). Raw excerpt: %r",
            e, excerpt,
        )
        raise ExtractionStageError(
            stage="field_extraction",
            reason="json_decode",
            message=f"Claude returned malformed JSON for field extraction: {e}",
            raw_excerpt=excerpt,
        )

    if not isinstance(parsed, dict):
        logger.error(
            "extract_fields: Claude returned non-dict JSON (%s). Raw excerpt: %r",
            type(parsed).__name__, raw[:500] if raw else "",
        )
        raise ExtractionStageError(
            stage="field_extraction",
            reason="schema_validation",
            message=(
                "Claude returned a non-object JSON value for field extraction "
                f"(got {type(parsed).__name__})."
            ),
        )

    try:
        values, sources = validate_extracted_fields(parsed, set(schema.keys()))
    except Exception as e:
        logger.error(
            "extract_fields: validation failed: %s. Raw parsed keys: %s",
            e, list(parsed.keys())[:30],
        )
        raise ExtractionStageError(
            stage="field_extraction",
            reason="schema_validation",
            message=f"Field-extraction output failed validation: {e}",
        )

    return values, sources, prompt_version
