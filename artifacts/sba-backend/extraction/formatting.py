"""
Formatting functions for SBA loan extraction fields.
Handles currency, percentage, date, and number-to-words formatting.
"""

import re
from typing import Dict, Any


def format_currency_short(amount_str: str) -> str:
    if not amount_str or str(amount_str).strip() == "":
        return ""
    try:
        clean_amount = re.sub(r'[,$\s]', '', str(amount_str))
        amount = float(clean_amount)
        return f"${amount:,.2f}"
    except (ValueError, TypeError):
        return str(amount_str)


def format_percentage_short(rate_str: str) -> str:
    if not rate_str or str(rate_str).strip() == "":
        return ""
    try:
        clean_rate = re.sub(r'[%\s]', '', str(rate_str))
        rate = float(clean_rate)
        return f"{rate:.2f}%"
    except (ValueError, TypeError):
        return str(rate_str)


def format_date_long(date_str: str) -> str:
    if not date_str or str(date_str).strip() == "":
        return ""

    months = [
        "", "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December"
    ]

    try:
        date_str = str(date_str).strip()

        if "/" in date_str:
            parts = date_str.split("/")
            if len(parts) == 3:
                month = int(parts[0])
                day = int(parts[1])
                year = int(parts[2])
                if year < 100:
                    year += 2000 if year < 50 else 1900
                return f"{months[month]} {day}, {year}"

        elif "-" in date_str:
            parts = date_str.split("-")
            if len(parts) == 3:
                year = int(parts[0])
                month = int(parts[1])
                day = int(parts[2])
                return f"{months[month]} {day}, {year}"

        elif any(m in date_str for m in months[1:]):
            return date_str

        return date_str
    except (ValueError, IndexError):
        return str(date_str)


def percentage_to_words(rate_str: str) -> str:
    if not rate_str or str(rate_str).strip() == "":
        return ""

    try:
        clean_rate = re.sub(r'[%\s]', '', str(rate_str))
        rate = float(clean_rate)

        whole_part = int(rate)
        decimal_part = rate - whole_part

        ones = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
                "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
                "Seventeen", "Eighteen", "Nineteen"]
        tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]

        def convert_whole(num):
            if num == 0:
                return "Zero"
            elif num < 20:
                return ones[num]
            elif num < 100:
                r = tens[num // 10]
                if num % 10 > 0:
                    r += "-" + ones[num % 10].lower()
                return r
            else:
                hundreds = num // 100
                remainder = num % 100
                r = ones[hundreds] + " hundred"
                if remainder > 0:
                    r += " " + convert_whole(remainder).lower()
                return r

        whole_words = convert_whole(whole_part) if whole_part != 0 else ""

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
            hundredths = round(decimal_part * 100)
            if hundredths > 0:
                if hundredths < 20:
                    decimal_words = ones[hundredths].lower() + " hundredths"
                else:
                    decimal_words = (
                        tens[hundredths // 10] +
                        ("-" + ones[hundredths % 10].lower() if hundredths % 10 > 0 else "")
                    ).lower() + " hundredths"

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
        return ""


def number_to_words(amount_str: str) -> str:
    if not amount_str or str(amount_str).strip() == "":
        return ""

    try:
        clean_amount = re.sub(r'[,$\s]', '', str(amount_str))
        amount = float(clean_amount)

        dollars = int(amount)
        cents = int(round((amount - dollars) * 100))

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
            if num >= 1_000_000_000:
                result += convert_hundreds(num // 1_000_000_000) + " Billion"
                num %= 1_000_000_000
                if num > 0:
                    result += " "
            if num >= 1_000_000:
                result += convert_hundreds(num // 1_000_000) + " Million"
                num %= 1_000_000
                if num > 0:
                    result += " "
            if num >= 1000:
                result += convert_hundreds(num // 1000) + " Thousand"
                num %= 1000
                if num > 0:
                    result += " "
            if num > 0:
                result += convert_hundreds(num)
            return result.strip()

        dollar_words = convert_number(dollars) if dollars != 0 else "Zero"
        return f"{dollar_words} and {cents:02d}/100 Dollars"

    except (ValueError, TypeError):
        return ""


def infer_state_from_address(address: str) -> str:
    if not address or str(address).strip() == "":
        return ""

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

    match = re.search(r'\b([A-Z]{2})\s+\d{5}', str(address))
    if match:
        abbrev = match.group(1)
        return state_map.get(abbrev, abbrev)

    match = re.search(r'\b([A-Z]{2})\b\s*$', str(address))
    if match:
        abbrev = match.group(1)
        return state_map.get(abbrev, abbrev)

    return ""


def apply_field_formatting(data: Dict[str, Any]) -> Dict[str, Any]:
    formatted_data = {}

    # FIRST PASS: Generate long-format fields from short fields
    for field_name, value in data.items():
        if "Long" in field_name:
            short_field_name = field_name.replace("Long", "Short")
            if short_field_name in data and data[short_field_name] and str(data[short_field_name]).strip():
                if any(x in field_name for x in ["SpreadLong", "InitialRateLong"]):
                    written = percentage_to_words(data[short_field_name])
                    formatted_data[field_name] = written
                else:
                    written = number_to_words(data[short_field_name])
                    formatted_data[field_name] = written
            elif value and str(value).strip():
                formatted_data[field_name] = str(value)
            else:
                formatted_data[field_name] = ""

    # SECOND PASS: Apply formatting to all fields
    for field_name, value in data.items():
        if not value or str(value).strip() == "":
            if field_name not in formatted_data:
                formatted_data[field_name] = ""
            continue

        if "Long" in field_name:
            continue

        if any(x in field_name for x in [
            "AmountShort", "LoanAmountShort", "FirstPaymentAmountShort",
            "InterestReserveAmountShort", "InjectionAmountShort", "ConstructionContractAmountShort"
        ]):
            formatted_data[field_name] = format_currency_short(value)

        elif any(x in field_name for x in ["SpreadShort", "InitialRateShort"]):
            formatted_data[field_name] = format_percentage_short(value)

        elif any(x in field_name for x in [
            "Date", "MaturityDate", "InitialPaymentDate", "SBAApprovalDate",
            "LeaseDate", "ConstructionContractDate", "ArchitectContractDate"
        ]):
            formatted_data[field_name] = format_date_long(value)

        else:
            formatted_data[field_name] = str(value)

    # Infer state from address if missing
    if not formatted_data.get("Borrower1StateOfOrganization"):
        borrower_address = formatted_data.get("BorrowerAddress2", "")
        if borrower_address:
            inferred = infer_state_from_address(borrower_address)
            if inferred:
                formatted_data["Borrower1StateOfOrganization"] = inferred

    return formatted_data
