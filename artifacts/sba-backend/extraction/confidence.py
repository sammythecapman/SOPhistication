"""
Tiered confidence scoring for extracted fields.

Tier GREEN  — Value confirmed by spaCy NER entity match (no warning shown)
Tier YELLOW — Value in source text but not in NER set (NER coverage gap, low risk)
Tier RED    — Value NOT found anywhere in source text (possible hallucination)

Only name / organization fields are scored — amounts, dates, addresses etc.
are validated by other layers and don't benefit from NER cross-checking.
"""

from difflib import SequenceMatcher
from typing import Dict, List, Optional, Any


# Fields checked against PERSON NER entities
PERSON_FIELDS = {
    "PersonalGuarantor1", "PersonalGuarantor2", "PersonalGuarantor3",
    "PersonalGuarantor4", "PersonalGuarantor5",
    "SellerSignerName", "ArchitectName",
    "CompanyGuarantor1Signor", "CompanyGuarantor2Signor",
    "CompanyGuarantor3Signor", "CompanyGuarantor4Signor",
}

# Fields checked against ORG NER entities
ORG_FIELDS = {
    "Borrower1Name", "Borrower2Name", "LenderName", "SellerName",
    "LandlordName", "GeneralContractorName",
    "CompanyGuarantor1Name", "CompanyGuarantor2Name",
    "CompanyGuarantor3Name", "CompanyGuarantor4Name",
}

SCORED_FIELDS = PERSON_FIELDS | ORG_FIELDS

FUZZY_THRESHOLD = 0.85
SNIPPET_CONTEXT = 55  # chars on each side of match


def _fuzzy_ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def _find_in_source(value: str, source_text: str) -> Optional[str]:
    """
    Look for value in source text.
    Returns a ±55-char context snippet if found, else None.
    Tries exact substring first, then a fuzzy sliding-window search.
    """
    if not value or not source_text:
        return None

    val_lower = value.lower().strip()
    src_lower = source_text.lower()

    # Exact substring match
    pos = src_lower.find(val_lower)
    if pos >= 0:
        return _snippet(source_text, pos, pos + len(value))

    # Fuzzy search — only for values long enough to be meaningful
    if len(val_lower) >= 6:
        win = len(val_lower) + 8
        step = max(1, len(val_lower) // 3)
        for i in range(0, max(1, len(src_lower) - win), step):
            chunk = src_lower[i:i + win]
            if _fuzzy_ratio(val_lower, chunk[: len(val_lower)]) >= FUZZY_THRESHOLD:
                return _snippet(source_text, i, i + win)

    return None


def _snippet(text: str, start: int, end: int) -> str:
    s = max(0, start - SNIPPET_CONTEXT)
    e = min(len(text), end + SNIPPET_CONTEXT)
    out = text[s:e].strip()
    if s > 0:
        out = "…" + out
    if e < len(text):
        out = out + "…"
    return out


def _ner_match(value: str, candidates: List[str]) -> bool:
    """Check whether value matches any NER entity via substring or fuzzy."""
    val_lower = value.lower().strip()
    for ent in candidates:
        ent_lower = ent.lower().strip()
        if len(ent_lower) < 3:
            continue
        if val_lower in ent_lower or ent_lower in val_lower:
            return True
        if _fuzzy_ratio(val_lower, ent_lower) >= FUZZY_THRESHOLD:
            return True
    return False


def score_extracted_fields(
    extracted: Dict[str, str],
    ner_entities: Dict[str, List[str]],
    raw_text: str,
    learned_suppressions: Optional[Dict[str, str]] = None,
) -> Dict[str, Dict[str, Any]]:
    """
    Score every SCORED_FIELD that has a non-empty extracted value.

    Returns:
        {
            field_name: {
                "value": str,
                "confidence_tier": "green" | "yellow" | "red",
                "ner_match": bool,
                "source_text_match": bool,
                "source_snippet": str | None,
                "match_details": str,
            }
        }

    learned_suppressions: mapping of field_name → "suppress_yellow" | "downgrade_red"
    applied after scoring to reduce noise for known-noisy field types.
    """
    if learned_suppressions is None:
        learned_suppressions = {}

    person_ents = ner_entities.get("PERSON", [])
    org_ents = ner_entities.get("ORG", [])
    results: Dict[str, Dict[str, Any]] = {}

    for field, value in extracted.items():
        if not value or not str(value).strip():
            continue
        if field not in SCORED_FIELDS:
            continue

        value = str(value).strip()

        if field in PERSON_FIELDS:
            candidates = person_ents
        elif field in ORG_FIELDS:
            candidates = org_ents
        else:
            candidates = person_ents + org_ents

        ner_hit = _ner_match(value, candidates)

        if ner_hit:
            tier = "green"
            source_snippet = None
            source_text_match = True
            match_details = "Confirmed by NER entity set"
        else:
            source_snippet = _find_in_source(value, raw_text)
            source_text_match = source_snippet is not None

            if source_text_match:
                tier = "yellow"
                match_details = "Found in source text — spaCy did not tag as a named entity"
            else:
                tier = "red"
                match_details = "Value NOT found anywhere in source document text"

        # Apply learned threshold adjustments
        suppression = learned_suppressions.get(field)
        if suppression == "suppress_yellow" and tier == "yellow":
            tier = "green"
            match_details += " (auto-confirmed: NER gap rate >90% for this field type)"
        elif suppression == "downgrade_red" and tier == "red":
            tier = "yellow"
            match_details += " (auto-downgraded: red false positive rate >80% for this field type)"

        results[field] = {
            "value": value,
            "confidence_tier": tier,
            "ner_match": ner_hit,
            "source_text_match": source_text_match,
            "source_snippet": source_snippet,
            "match_details": match_details,
        }

    return results
