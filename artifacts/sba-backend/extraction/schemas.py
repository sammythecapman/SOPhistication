"""
Deal structure analysis and dynamic schema building.
"""

import json
import time
import logging
import anthropic
from typing import Dict

from .errors import ExtractionStageError

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


def analyze_deal_structure(terms_text: str, memo_text: str, client) -> dict:
    """
    First Claude API call: figure out the deal type and structure
    so we only extract applicable fields in the next step.
    """
    prompt = f"""Analyze these SBA loan documents and identify the deal structure.

TERMS & CONDITIONS:
{terms_text[:4000]}

CREDIT MEMO (if available):
{memo_text[:2000] if memo_text else "Not provided"}

Return ONLY this JSON (no other text):
{{
  "deal_type": "one of: Asset Purchase, Stock Purchase, Real Estate Purchase, Construction, Equipment, Working Capital, Refinance, Other",
  "has_real_estate": true or false,
  "has_construction": true or false,
  "has_equipment": true or false,
  "has_seller": true or false,
  "has_landlord_lease": true or false,
  "borrower_count": 1,
  "has_second_borrower": true or false,
  "has_personal_guarantors": true or false,
  "personal_guarantor_count": 0,
  "has_corporate_guarantors": true or false,
  "corporate_guarantor_count": 0,
  "loan_program": "one of: SBA 7(a) Standard, SBA 7(a) Express, SBA 504, Conventional"
}}"""

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
        return json.loads(cleaned)
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
        "LoanType":             "",
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


def extract_fields(terms_text: str, memo_text: str, schema: dict, deal: dict,
                   ner_hints: str, client) -> dict:
    """
    Second Claude API call: extract all relevant fields with NER hints injected.
    """
    schema_str = json.dumps(schema, indent=2)

    prompt = f"""You are a paralegal extracting data from SBA loan documents for a law firm.

DEAL TYPE: {deal.get('deal_type', 'Unknown')}
LOAN PROGRAM: {deal.get('loan_program', 'Unknown')}

{ner_hints}

TERMS & CONDITIONS DOCUMENT:
{terms_text}

CREDIT MEMO (if available):
{memo_text if memo_text else "Not provided"}

Extract the following fields and return ONLY a valid JSON object. No explanation, no markdown.

{schema_str}

CRITICAL FIELD RULES (these must NEVER be left blank if the data exists):
- SBALoanNumber: Look for "SBA Loan #", "Loan No.", "Loan Number", "Note No.", "Note Number".
  Extract any loan/note/SBA number found in the document into this field.

EXTRACTION RULES:
- Use "" (empty string) for fields genuinely not found
- NEVER make up or guess values
- Dates: extract as found (MM/DD/YYYY, written format, etc.) — will be formatted later
- Amount fields ending in "Short": extract numeric values ONLY (e.g. "4342000.00", no $ or commas)
- Amount fields ending in "Long": extract COMPLETE written format as it appears in document
- Rate fields ending in "Short": extract numeric values ONLY (e.g. "4.25", no % sign)
- Rate fields ending in "Long": extract written format (e.g. "Four and 25/100")
- PersonalGuarantor fields: full legal name as it appears
- CompanyGuarantor fields: full legal entity name
- Borrower1Description: entity type e.g. "a Wisconsin corporation"
- LenderDescription: entity type e.g. "a New York state chartered bank"
- BorrowerAddress1: street address only
- BorrowerAddress2: city, state, zip
- LenderAddress1: street address only
- LenderAddress2: city, state, zip
- State: the state where the deal is primarily located

SELLER FIELDS (if present):
- SellerName: Look for "seller", "vendor", company being purchased/acquired
- SellerDescription: Entity type of seller
- SellerSignerName: Person signing on behalf of seller
- SellerSignerTitle: Title of person signing for seller
- InjectionAmountShort: Cash injection, owner investment, equity contribution

CRITICAL — LONG FORMAT FIELDS:
- Look specifically for written-out dollar amounts in phrases like "the sum of", "amount of", "principal amount"
- Look for written payment amounts in payment sections
- These are often in legal language like "Four Million Three Hundred Twenty Thousand and 00/100 Dollars"

Return ONLY the JSON object."""

    try:
        response = _claude_with_retry(
            client,
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
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
        return json.loads(cleaned)
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
