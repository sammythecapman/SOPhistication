"""
NER (Named Entity Recognition) engine using spaCy.
Preprocesses document text to extract entity hints for Claude.
"""

from typing import Dict, List, Optional


_NLP_MODEL = None


def load_ner_model():
    """Load and cache the spaCy NER model."""
    global _NLP_MODEL
    if _NLP_MODEL is not None:
        return _NLP_MODEL

    try:
        import spacy
        _NLP_MODEL = spacy.load("en_core_web_sm")
        return _NLP_MODEL
    except OSError:
        import subprocess
        import sys
        subprocess.run(
            [sys.executable, "-m", "spacy", "download", "en_core_web_sm"],
            check=True, capture_output=True
        )
        import spacy
        _NLP_MODEL = spacy.load("en_core_web_sm")
        return _NLP_MODEL


def run_ner(text: str, nlp=None) -> Dict[str, List[str]]:
    """
    Run NER over document text.
    Returns entities grouped by label (PERSON, ORG, GPE, MONEY, DATE, PERCENT).
    """
    if nlp is None:
        nlp = load_ner_model()

    entities: Dict[str, List[str]] = {
        "PERSON": [],
        "ORG": [],
        "GPE": [],
        "LOC": [],
        "MONEY": [],
        "DATE": [],
        "PERCENT": [],
    }

    # Process in chunks to avoid memory issues on large docs
    chunk_size = 50_000
    seen: Dict[str, set] = {label: set() for label in entities}

    for i in range(0, len(text), chunk_size):
        chunk = text[i:i + chunk_size]
        doc = nlp(chunk)
        for ent in doc.ents:
            label = ent.label_
            if label in entities:
                cleaned = ent.text.strip()
                if cleaned and cleaned not in seen[label] and len(cleaned) > 1:
                    seen[label].add(cleaned)
                    entities[label].append(cleaned)

    return entities


def merge_ner_results(ner1: Dict[str, List[str]], ner2: Optional[Dict[str, List[str]]]) -> Dict[str, List[str]]:
    """Merge NER results from Terms and Credit Memo, deduplicating."""
    if not ner2:
        return ner1

    merged: Dict[str, List[str]] = {}
    all_labels = set(ner1.keys()) | set(ner2.keys())

    for label in all_labels:
        combined = list(ner1.get(label, []))
        seen_set = set(combined)
        for item in ner2.get(label, []):
            if item not in seen_set:
                seen_set.add(item)
                combined.append(item)
        merged[label] = combined

    return merged


def format_ner_hints(entities: Dict[str, List[str]]) -> str:
    """
    Format NER entities into a structured hint block for the Claude extraction prompt.
    """
    lines = ["=== NER ENTITY HINTS (pre-extracted by spaCy) ===",
             "Use these entities as hints when populating name/org/location fields.",
             "Cross-reference extracted values against these entities to catch errors."]

    label_display = {
        "PERSON": "PERSONS (likely guarantors, signers, individuals)",
        "ORG": "ORGANIZATIONS (borrowers, lenders, sellers, contractors)",
        "GPE": "PLACES / JURISDICTIONS (cities, states, countries)",
        "LOC": "LOCATIONS",
        "MONEY": "MONEY AMOUNTS (loan amounts, fees, reserves)",
        "DATE": "DATES (approval dates, maturity dates, payment dates)",
        "PERCENT": "PERCENTAGES (interest rates, spreads)",
    }

    for label, display in label_display.items():
        items = entities.get(label, [])
        if items:
            lines.append(f"\n{display}:")
            for item in items[:30]:  # Cap at 30 per category
                lines.append(f"  - {item}")

    lines.append("\n=== END NER HINTS ===")
    return "\n".join(lines)


def validate_extraction_against_ner(
    extracted: Dict[str, str],
    entities: Dict[str, List[str]]
) -> List[str]:
    """
    Compare extracted names/orgs against NER entity set.
    Returns list of warning strings for any mismatches that may indicate hallucination.
    """
    warnings = []

    person_entities = set(e.lower() for e in entities.get("PERSON", []))
    org_entities = set(e.lower() for e in entities.get("ORG", []))

    name_fields = [
        "Borrower1Name", "Borrower2Name", "LenderName", "SellerName",
        "LandlordName", "ArchitectName", "GeneralContractorName",
    ]

    for i in range(1, 6):
        name_fields.append(f"PersonalGuarantor{i}")
        name_fields.append(f"CompanyGuarantor{i}Name")

    for field in name_fields:
        value = extracted.get(field, "").strip()
        if not value:
            continue

        value_lower = value.lower()

        # Check if any NER entity is a substring match (partial match is ok)
        found_in_persons = any(
            value_lower in p or p in value_lower
            for p in person_entities
            if len(p) > 3
        )
        found_in_orgs = any(
            value_lower in o or o in value_lower
            for o in org_entities
            if len(o) > 3
        )

        if not found_in_persons and not found_in_orgs:
            warnings.append(
                f"Field '{field}' value '{value}' not found in NER entity set — "
                f"verify this is correct (possible hallucination)"
            )

    return warnings
