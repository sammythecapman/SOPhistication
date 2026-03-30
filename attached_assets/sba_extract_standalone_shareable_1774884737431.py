"""
SBA Loan Data Extraction Tool - Enhanced Version (Standalone)
------------------------------------------------------------
Reads SBA Terms & Conditions (and optionally a Credit Memo) PDF,
extracts all relevant fields with proper formatting, and outputs clean JSON.

FEATURES:
- Proper currency formatting: $5,500,000.10
- Proper percentage formatting: 5.25%  
- Proper date formatting: January 15, 2025
- Clean JSON output ready for any system
- Field validation and cleanup

Usage:
    python3 sba_extract_standalone.py terms.pdf
    python3 sba_extract_standalone.py terms.pdf credit_memo.pdf

Requirements:
    pip3 install anthropic pdfplumber
"""

import anthropic
import pdfplumber
import sys
import json
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

# ──────────────────────────────────────────────
# CONFIGURATION - paste your API key here
# ──────────────────────────────────────────────
API_KEY = "______________________________________________________________"

# ──────────────────────────────────────────────
# FORMATTING FUNCTIONS
# ──────────────────────────────────────────────

def format_currency_short(amount_str: str) -> str:
    """
    Convert numeric amount to formatted currency.
    Input: "5500000.10" or "5500000"
    Output: "$5,500,000.10"
    """
    if not amount_str or amount_str.strip() == "":
        return ""
    
    try:
        # Clean the input - remove any existing formatting
        clean_amount = re.sub(r'[,$\s]', '', str(amount_str))
        
        # Convert to float, then format
        amount = float(clean_amount)
        return f"${amount:,.2f}"
    except (ValueError, TypeError):
        print(f"  ⚠️  Could not format currency: '{amount_str}'")
        return amount_str

def format_percentage_short(rate_str: str) -> str:
    """
    Convert numeric rate to formatted percentage.
    Input: "5.25" or "5.2500"
    Output: "5.25%"
    """
    if not rate_str or rate_str.strip() == "":
        return ""
    
    try:
        # Clean the input - remove any existing formatting
        clean_rate = re.sub(r'[%\s]', '', str(rate_str))
        
        # Convert to float, then format with 2 decimal places
        rate = float(clean_rate)
        return f"{rate:.2f}%"
    except (ValueError, TypeError):
        print(f"  ⚠️  Could not format percentage: '{rate_str}'")
        return rate_str

def format_date_long(date_str: str) -> str:
    """
    Convert various date formats to "Month DD, YYYY" format.
    Input: "01/15/2025", "1/15/25", "January 15, 2025", "2025-01-15"
    Output: "January 15, 2025"
    """
    if not date_str or date_str.strip() == "":
        return ""
    
    # Month names for conversion
    months = [
        "", "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December"
    ]
    
    try:
        date_str = date_str.strip()
        
        # Handle MM/DD/YYYY or M/D/YY formats
        if "/" in date_str:
            parts = date_str.split("/")
            if len(parts) == 3:
                month = int(parts[0])
                day = int(parts[1])
                year = int(parts[2])
                
                # Handle 2-digit years
                if year < 100:
                    year += 2000 if year < 50 else 1900
                
                return f"{months[month]} {day}, {year}"
        
        # Handle YYYY-MM-DD format
        elif "-" in date_str:
            parts = date_str.split("-")
            if len(parts) == 3:
                year = int(parts[0])
                month = int(parts[1])
                day = int(parts[2])
                
                return f"{months[month]} {day}, {year}"
        
        # If already in correct format, return as-is
        elif any(m in date_str for m in months[1:]):
            return date_str
            
        return date_str
    except (ValueError, IndexError):
        print(f"  ⚠️  Could not format date: '{date_str}'")
        return date_str

def percentage_to_words(rate_str: str) -> str:
    """
    Convert numeric percentage to natural language format.
    Input: "4.25" 
    Output: "Four and one-quarter percent"
    """
    if not rate_str or rate_str.strip() == "":
        return ""
    
    try:
        # Clean the input and convert to float
        clean_rate = re.sub(r'[%\s]', '', str(rate_str))
        rate = float(clean_rate)
        
        # Split into whole number and decimal parts
        whole_part = int(rate)
        decimal_part = rate - whole_part
        
        # Number to words for whole numbers
        ones = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
                "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", 
                "Seventeen", "Eighteen", "Nineteen"]
        
        tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]
        
        def convert_whole_number(num):
            if num == 0:
                return "Zero"
            elif num < 20:
                return ones[num]
            elif num < 100:
                result = tens[num // 10]
                if num % 10 > 0:
                    result += "-" + ones[num % 10].lower()
                return result
            else:
                # Handle hundreds if needed
                hundreds = num // 100
                remainder = num % 100
                result = ones[hundreds] + " hundred"
                if remainder > 0:
                    result += " " + convert_whole_number(remainder).lower()
                return result
        
        # Convert whole part
        if whole_part == 0:
            whole_words = ""
        else:
            whole_words = convert_whole_number(whole_part)
        
        # Handle common decimal fractions
        decimal_words = ""
        if abs(decimal_part - 0.25) < 0.001:
            decimal_words = "one-quarter"
        elif abs(decimal_part - 0.5) < 0.001:
            decimal_words = "one-half"
        elif abs(decimal_part - 0.75) < 0.001:
            decimal_words = "three-quarters"
        elif abs(decimal_part - 0.125) < 0.001:
            decimal_words = "one-eighth"
        elif abs(decimal_part - 0.375) < 0.001:
            decimal_words = "three-eighths"
        elif abs(decimal_part - 0.625) < 0.001:
            decimal_words = "five-eighths"
        elif abs(decimal_part - 0.875) < 0.001:
            decimal_words = "seven-eighths"
        else:
            # For other decimals, convert to hundredths
            hundredths = round(decimal_part * 100)
            if hundredths > 0:
                if hundredths < 20:
                    decimal_words = ones[hundredths].lower() + " hundredths"
                else:
                    decimal_words = (tens[hundredths // 10] + 
                                   ("-" + ones[hundredths % 10].lower() if hundredths % 10 > 0 else "")).lower() + " hundredths"
        
        # Combine parts
        if whole_words and decimal_words:
            result = whole_words + " and " + decimal_words + " percent"
        elif whole_words:
            result = whole_words + " percent"
        elif decimal_words:
            result = decimal_words.capitalize() + " percent"
        else:
            result = "Zero percent"
        
        return result
        
    except (ValueError, TypeError):
        print(f"  ⚠️  Could not convert percentage to words: '{rate_str}'")
        return ""

def number_to_words(amount_str: str) -> str:
    """
    Convert numeric amount to written format.
    Input: "4342000.00" or "17209.18"
    Output: "Four Million Three Hundred Forty-Two Thousand and 00/100 Dollars"
    """
    if not amount_str or amount_str.strip() == "":
        return ""
    
    try:
        # Clean the input
        clean_amount = re.sub(r'[,$\s]', '', str(amount_str))
        amount = float(clean_amount)
        
        # Split into dollars and cents
        dollars = int(amount)
        cents = int(round((amount - dollars) * 100))
        
        # Number to words mapping
        ones = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
                "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", 
                "Seventeen", "Eighteen", "Nineteen"]
        
        tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]
        
        def convert_hundreds(num):
            result = ""
            if num >= 100:
                result += ones[num // 100] + " Hundred"
                num %= 100
                if num > 0:
                    result += " "
            
            if num >= 20:
                result += tens[num // 10]
                if num % 10 > 0:
                    result += "-" + ones[num % 10]
            elif num > 0:
                result += ones[num]
            
            return result
        
        def convert_number(num):
            if num == 0:
                return "Zero"
            
            result = ""
            
            # Billions
            if num >= 1000000000:
                result += convert_hundreds(num // 1000000000) + " Billion"
                num %= 1000000000
                if num > 0:
                    result += " "
            
            # Millions
            if num >= 1000000:
                result += convert_hundreds(num // 1000000) + " Million"
                num %= 1000000
                if num > 0:
                    result += " "
            
            # Thousands
            if num >= 1000:
                result += convert_hundreds(num // 1000) + " Thousand"
                num %= 1000
                if num > 0:
                    result += " "
            
            # Hundreds
            if num > 0:
                result += convert_hundreds(num)
            
            return result.strip()
        
        # Convert dollars part
        if dollars == 0:
            dollar_words = "Zero"
        else:
            dollar_words = convert_number(dollars)
        
        # Format final result
        result = f"{dollar_words} and {cents:02d}/100 Dollars"
        return result
        
    except (ValueError, TypeError):
        print(f"  ⚠️  Could not convert to words: '{amount_str}'")
        return ""

def infer_state_from_address(address: str) -> str:
    """
    Extract state from address string.
    Input: "Milwaukee, WI 53226" or "2136 N 90 TH ST, Milwaukee, WI 53226"
    Output: "WI" or "Wisconsin"
    """
    if not address or address.strip() == "":
        return ""
    
    # Common state abbreviations to full names
    state_map = {
        'AL': 'Alabama', 'AK': 'Alaska', 'AZ': 'Arizona', 'AR': 'Arkansas', 'CA': 'California',
        'CO': 'Colorado', 'CT': 'Connecticut', 'DE': 'Delaware', 'FL': 'Florida', 'GA': 'Georgia',
        'HI': 'Hawaii', 'ID': 'Idaho', 'IL': 'Illinois', 'IN': 'Indiana', 'IA': 'Iowa',
        'KS': 'Kansas', 'KY': 'Kentucky', 'LA': 'Louisiana', 'ME': 'Maine', 'MD': 'Maryland',
        'MA': 'Massachusetts', 'MI': 'Michigan', 'MN': 'Minnesota', 'MS': 'Mississippi', 'MO': 'Missouri',
        'MT': 'Montana', 'NE': 'Nebraska', 'NV': 'Nevada', 'NH': 'New Hampshire', 'NJ': 'New Jersey',
        'NM': 'New Mexico', 'NY': 'New York', 'NC': 'North Carolina', 'ND': 'North Dakota', 'OH': 'Ohio',
        'OK': 'Oklahoma', 'OR': 'Oregon', 'PA': 'Pennsylvania', 'RI': 'Rhode Island', 'SC': 'South Carolina',
        'SD': 'South Dakota', 'TN': 'Tennessee', 'TX': 'Texas', 'UT': 'Utah', 'VT': 'Vermont',
        'VA': 'Virginia', 'WA': 'Washington', 'WV': 'West Virginia', 'WI': 'Wisconsin', 'WY': 'Wyoming'
    }
    
    # Look for state abbreviation pattern (2 letters followed by space and digits or end of string)
    import re
    match = re.search(r'\b([A-Z]{2})\s+\d{5}', address)
    if match:
        state_abbrev = match.group(1)
        return state_map.get(state_abbrev, state_abbrev)
    
    # Look for just state abbreviation at end
    match = re.search(r'\b([A-Z]{2})\b\s*$', address)
    if match:
        state_abbrev = match.group(1)
        return state_map.get(state_abbrev, state_abbrev)
    
    return ""

def apply_field_formatting(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply proper formatting to extracted fields based on field names.
    """
    formatted_data = {}
    
    # FIRST PASS: Generate long format fields from short fields BEFORE other formatting
    for field_name, value in data.items():
        if "Long" in field_name:
            short_field_name = field_name.replace("Long", "Short")
            if short_field_name in data and data[short_field_name] and str(data[short_field_name]).strip():
                # Check if this is a percentage field
                if any(x in field_name for x in ["SpreadLong", "InitialRateLong"]):
                    # Generate percentage in natural language
                    written_percentage = percentage_to_words(data[short_field_name])
                    formatted_data[field_name] = written_percentage
                    print(f"  🔤 Generated {field_name}: {written_percentage}")
                else:
                    # Generate from raw numeric value before it gets currency-formatted
                    written_amount = number_to_words(data[short_field_name])
                    formatted_data[field_name] = written_amount
                    print(f"  🔤 Generated {field_name}: {written_amount}")
            elif value and str(value).strip():
                # Use existing written format
                formatted_data[field_name] = str(value)
                print(f"  🔤 Using existing {field_name}: {value}")
            else:
                formatted_data[field_name] = ""
                print(f"  ⚠️  {field_name}: No data to generate from")
    
    # SECOND PASS: Apply formatting to all fields
    for field_name, value in data.items():
        if not value or str(value).strip() == "":
            if field_name not in formatted_data:  # Don't overwrite long fields we just generated
                formatted_data[field_name] = ""
            continue
            
        # Skip long fields - already processed above
        if "Long" in field_name:
            continue
            
        # Currency fields (Short format)
        if any(x in field_name for x in ["AmountShort", "LoanAmountShort", "FirstPaymentAmountShort", "InterestReserveAmountShort", "InjectionAmountShort", "ConstructionContractAmountShort"]):
            formatted_data[field_name] = format_currency_short(value)
            
        # Percentage fields (Short format)
        elif any(x in field_name for x in ["SpreadShort", "InitialRateShort"]):
            formatted_data[field_name] = format_percentage_short(value)
            
        # Date fields 
        elif any(x in field_name for x in ["Date", "MaturityDate", "InitialPaymentDate", "SBAApprovalDate", "LeaseDate", "ConstructionContractDate", "ArchitectContractDate"]):
            formatted_data[field_name] = format_date_long(value)
            
        # All other fields - keep as-is but ensure string
        else:
            formatted_data[field_name] = str(value)
    
    # Infer state of organization from borrower address if missing
    if not formatted_data.get("Borrower1StateOfOrganization") or formatted_data["Borrower1StateOfOrganization"] == "":
        borrower_address = formatted_data.get("BorrowerAddress2", "")
        if borrower_address:
            inferred_state = infer_state_from_address(borrower_address)
            if inferred_state:
                formatted_data["Borrower1StateOfOrganization"] = inferred_state
                print(f"  🏛️  Inferred state: {inferred_state}")
    
    return formatted_data

# ──────────────────────────────────────────────
# ORIGINAL FUNCTIONS (unchanged)
# ──────────────────────────────────────────────

def read_pdf(path: str) -> str:
    """Extract all text from a PDF file using pdfplumber."""
    text = ""
    try:
        with pdfplumber.open(path) as pdf:
            for i, page in enumerate(pdf.pages):
                page_text = page.extract_text()
                if page_text:
                    text += f"\n--- PAGE {i+1} ---\n{page_text}"
        return text.strip()
    except Exception as e:
        print(f"  ⚠️  Could not read {path}: {e}")
        return ""

def analyze_deal_structure(terms_text: str, memo_text: str, client) -> dict:
    """
    First pass: figure out what kind of deal this is so we only
    extract applicable fields in the next step.
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

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response.content[0].text
    try:
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0]
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0]
        return json.loads(raw.strip())
    except Exception as e:
        print(f"  ⚠️  Could not parse deal structure: {e}")
        return {}

def build_schema(deal: dict) -> dict:
    """
    Return only the fields that are applicable to this deal type.
    This avoids a wall of NOT FOUND on every run.
    """

    # ── Core fields: always present ──
    fields = {
        "SBALoanNumber":        "",
        "SBALoanName":          "",
        "SBAApprovalDate":      "",
        "LoanNumber":           "",
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

    # ── Second borrower ──
    if deal.get("has_second_borrower"):
        fields.update({
            "Borrower2Name":        "",
            "Borrower2Description": "",
            "Borrower2StateOfOrganization": "",
        })

    # ── Personal guarantors ──
    count = deal.get("personal_guarantor_count", 0)
    for i in range(1, min(count + 1, 5)):
        fields[f"PersonalGuarantor{i}"] = ""

    # ── Corporate/company guarantors ──
    cg_count = deal.get("corporate_guarantor_count", 0)
    for i in range(1, min(cg_count + 1, 5)):
        fields.update({
            f"CompanyGuarantor{i}Name":                "",
            f"CompanyGuarantor{i}Description":         "",
            f"CompanyGuarantor{i}StateOfOrganization": "",
            f"CompanyGuarantor{i}Signor":              "",
            f"CompanyGuarantor{i}Title":               "",
        })

    # ── Real estate fields ──
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

    # ── Construction fields ──
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

    # ── Seller fields (asset/stock purchase) ──
    # Always include seller fields for Asset Purchase and Stock Purchase deals
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

    # ── Landlord/Lease fields ──
    if deal.get("has_landlord_lease"):
        fields.update({
            "LeaseDate":          "",
            "LeaseAgreementTitle":"",
            "LandlordName":       "",
            "LandlordDescription":"",
        })

    return fields

def extract_fields(terms_text: str, memo_text: str, schema: dict, deal: dict, client) -> dict:
    """
    Second pass: extract only the fields relevant to this deal.
    Updated to extract raw values that will be formatted later.
    """
    schema_str = json.dumps(schema, indent=2)

    prompt = f"""You are a paralegal extracting data from SBA loan documents for a law firm.

DEAL TYPE: {deal.get('deal_type', 'Unknown')}
LOAN PROGRAM: {deal.get('loan_program', 'Unknown')}

TERMS & CONDITIONS DOCUMENT:
{terms_text}

CREDIT MEMO (if available):
{memo_text if memo_text else "Not provided"}

Extract the following fields and return ONLY a valid JSON object. No explanation, no markdown.

{schema_str}

EXTRACTION RULES:
- Use "" (empty string) for fields genuinely not found
- NEVER make up or guess values
- Dates: extract as found (MM/DD/YYYY, written format, etc.) - will be formatted later
- Amount fields ending in "Short": extract numeric values ONLY (e.g. "4342000.00", no $ or commas)
- Amount fields ending in "Long": extract COMPLETE written format as it appears in document (e.g. "Four Million Three Hundred Forty-Two Thousand and 00/100 Dollars")
- Rate fields ending in "Short": extract numeric values ONLY (e.g. "4.25", no % sign)
- Rate fields ending in "Long": extract written format (e.g. "Four and 25/100")
- PersonalGuarantor fields: full legal name as it appears
- CompanyGuarantor fields: full legal entity name
- Borrower1Description: entity type e.g. "a Wisconsin corporation"
- LenderDescription: entity type e.g. "a New York state chartered bank"
- BorrowerAddress1: street address
- BorrowerAddress2: city, state, zip
- LenderAddress1: street address
- LenderAddress2: city, state, zip
- State: the state where the deal is primarily located

SPECIAL ATTENTION FOR SELLER FIELDS (if present in schema):
- SellerName: Look for "seller", "vendor", company being purchased, business being acquired
- SellerDescription: Entity type of seller (corporation, LLC, etc.)
- SellerSignerName: Person signing on behalf of seller
- SellerSignerTitle: Title of person signing for seller
- InjectionAmountShort: Cash injection amount, owner investment, equity contribution

CRITICAL FOR LONG FORMAT FIELDS:
- Look specifically for written-out dollar amounts in phrases like "the sum of", "amount of", "principal amount"
- Look for written payment amounts in payment sections
- These are often in legal language format like "Four Million Three Hundred Twenty Thousand and 00/100 Dollars"
- Don't leave Long format fields empty if the numeric amount is available - the written form should be somewhere in the document

Return ONLY the JSON object."""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response.content[0].text
    try:
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0]
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0]
        return json.loads(raw.strip())
    except Exception as e:
        print(f"  ⚠️  Could not parse extracted fields: {e}")
        print(f"  Raw response:\n{raw}")
        return {}

# ──────────────────────────────────────────────
# MAIN (Simplified - No SharePoint)
# ──────────────────────────────────────────────

def main():
    print("\n" + "═" * 70)
    print("  SBA Loan Data Extraction Tool - Standalone Version")
    print("═" * 70)

    # Validate arguments
    if len(sys.argv) < 2:
        print("\nUsage: python3 sba_extract_standalone.py terms.pdf [credit_memo.pdf]")
        sys.exit(1)

    terms_path = sys.argv[1]
    memo_path  = sys.argv[2] if len(sys.argv) > 2 else None

    # Validate files exist
    if not Path(terms_path).exists():
        print(f"\n❌ File not found: {terms_path}")
        sys.exit(1)

    # Initialize API client
    if API_KEY == "YOUR_API_KEY_HERE":
        print("\n❌ Please set your Anthropic API key in the script")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=API_KEY)

    # ── Read PDFs ──
    print(f"\n📄 Reading: {terms_path}")
    terms_text = read_pdf(terms_path)
    if not terms_text:
        print("❌ Could not extract text from Terms & Conditions PDF")
        sys.exit(1)
    print(f"   ✅ Extracted {len(terms_text):,} characters")

    memo_text = ""
    if memo_path:
        print(f"\n📄 Reading: {memo_path}")
        memo_text = read_pdf(memo_path)
        print(f"   ✅ Extracted {len(memo_text):,} characters")

    # ── Analyze deal structure ──
    print("\n🔍 Analyzing deal structure...")
    deal = analyze_deal_structure(terms_text, memo_text, client)
    if deal:
        print(f"   ✅ Deal Type:       {deal.get('deal_type', 'Unknown')}")
        print(f"   ✅ Loan Program:    {deal.get('loan_program', 'Unknown')}")
        print(f"   ✅ Real Estate:     {deal.get('has_real_estate', False)}")
        print(f"   ✅ Construction:    {deal.get('has_construction', False)}")
        print(f"   ✅ Has Seller:      {deal.get('has_seller', False)}")
        print(f"   ✅ Personal Guar.:  {deal.get('personal_guarantor_count', 0)}")
        print(f"   ✅ Company Guar.:   {deal.get('corporate_guarantor_count', 0)}")
    else:
        print("   ⚠️  Could not determine structure, using core fields only")

    # ── Build schema ──
    schema = build_schema(deal)
    print(f"\n📋 Extracting {len(schema)} applicable fields...")

    # ── Extract fields ──
    raw_data = extract_fields(terms_text, memo_text, schema, deal, client)

    if not raw_data:
        print("\n❌ Extraction failed")
        sys.exit(1)

    # ── Apply formatting ──
    print("\n🎨 Applying formatting...")
    formatted_data = apply_field_formatting(raw_data)

    # ── Report results ──
    found    = sum(1 for v in formatted_data.values() if v and str(v).strip())
    total    = len(formatted_data)
    not_found= total - found

    print(f"\n{'═' * 70}")
    print(f"  ✅ EXTRACTED & FORMATTED DATA ({found}/{total} fields populated)")
    print(f"{'═' * 70}")
    
    # Show sample of formatted vs raw for key fields
    sample_fields = ["LoanAmountShort", "SpreadShort", "MaturityDate", "FirstPaymentAmountShort"]
    formatting_shown = False
    for field in sample_fields:
        if field in formatted_data and formatted_data[field]:
            raw_val = raw_data.get(field, "")
            formatted_val = formatted_data[field]
            if raw_val != formatted_val:
                if not formatting_shown:
                    print(f"  🎨 FORMATTING EXAMPLES:")
                    formatting_shown = True
                print(f"     {field}: {raw_val} → {formatted_val}")
    
    if formatting_shown:
        print(f"{'─' * 70}")
    
    for field, value in formatted_data.items():
        status = "✅" if value and str(value).strip() else "⬜"
        print(f"  {status} {field:<45} {value if value else '—'}")

    # ── Save outputs ──
    output = {
        "extracted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source_file":  terms_path,
        "credit_memo_file": memo_path,
        "deal_structure": deal,
        "raw_data": raw_data,
        "formatted_data": formatted_data,
        "summary": {
            "fields_populated": found,
            "fields_total": total,
            "fields_empty": not_found,
            "completion_percentage": round((found / total) * 100, 1) if total > 0 else 0
        }
    }

    # Save with timestamp in filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = Path(terms_path).stem
    output_file = f"extracted_{base_name}_{timestamp}.json"
    
    with open(output_file, "w") as f:
        json.dump(output, f, indent=2)

    # Also save just the formatted data in a cleaner format
    clean_output_file = f"formatted_{base_name}_{timestamp}.json"
    with open(clean_output_file, "w") as f:
        json.dump(formatted_data, f, indent=2)

    print(f"\n{'═' * 70}")
    print(f"  💾 Complete data saved to: {output_file}")
    print(f"  📊 Formatted data saved to: {clean_output_file}")
    print(f"  📈 {found} of {total} fields populated ({output['summary']['completion_percentage']}%)")
    print(f"  🎨 All formatting applied successfully")
    print(f"{'═' * 70}\n")

    # Show final summary
    print("💡 READY FOR USE:")
    print(f"   • Use '{clean_output_file}' for clean formatted data")
    print(f"   • Use '{output_file}' for complete extraction details")
    print(f"   • {found} fields ready for any system integration")
    print()


if __name__ == "__main__":
    main()
