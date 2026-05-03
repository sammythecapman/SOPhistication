"""Tests for extraction.field_registry.FieldRegistry."""

import unittest

from extraction.field_registry import FieldDefinition, FieldRegistry


# Default registry-context dict used by fields_for_deal-related tests.
# Keys mirror the allowlist in field_registry._ALLOWED_VARS so any
# applicable_when expression in the CSV can be evaluated cleanly.
DEFAULTS = {
    "borrower_count": 1,
    "company_guarantor_count": 0,
    "personal_guarantor_count": 0,
    "has_lease": False,
    "deal_involves_real_estate": False,
    "requires_equity_injection": False,
    "requires_life_insurance": False,
    "has_interest_reserve": False,
    "deal_type": "working_capital",
}


class TestFieldRegistry(unittest.TestCase):
    def test_csv_loads_103_definitions(self):
        all_defs = FieldRegistry.get_all()
        self.assertEqual(len(all_defs), 103)
        self.assertTrue(all(isinstance(d, FieldDefinition) for d in all_defs))

    def test_categories_in_order_no_duplicates(self):
        cats = FieldRegistry.categories()
        self.assertEqual(len(cats), len(set(cats)),
                         "categories() must be deduplicated")
        self.assertEqual(cats[0], "Dating the Doc Set")
        self.assertEqual(cats[1], "SBA Loan Info")

    def test_get_loan_amount_short(self):
        d = FieldRegistry.get("LoanAmountShort")
        self.assertEqual(d.display_name, "Loan Amount (Numeric)")
        self.assertEqual(d.data_type, "currency")
        self.assertIn("terms_conditions", d.source_documents)
        self.assertTrue(d.required)

    def test_fields_in_terms_conditions_excludes_derived_lookup(self):
        defs = FieldRegistry.fields_in_document("terms_conditions")
        self.assertGreater(len(defs), 0)
        for d in defs:
            self.assertNotIn(d.data_type, ("DERIVED", "LOOKUP"))

    def test_is_derived(self):
        self.assertTrue(FieldRegistry.is_derived("Month"))
        self.assertFalse(FieldRegistry.is_derived("LoanAmountShort"))

    def test_is_lookup(self):
        self.assertTrue(FieldRegistry.is_lookup("LenderSignerName"))
        self.assertFalse(FieldRegistry.is_lookup("LenderName"))

    def test_enum_with_inline_values(self):
        d = FieldRegistry.get("LimitedLiabilityCompany/Corporation")
        self.assertEqual(d.data_type, "enum")
        self.assertEqual(d.enum_values, ["LLC", "Corporation"])

    def test_borrower2_excluded_when_count_is_1(self):
        ctx = dict(DEFAULTS, borrower_count=1)
        names = {d.field_name for d in FieldRegistry.fields_for_deal(ctx)}
        self.assertNotIn("Borrower2Name", names)

    def test_borrower2_included_when_count_is_2(self):
        ctx = dict(DEFAULTS, borrower_count=2)
        names = {d.field_name for d in FieldRegistry.fields_for_deal(ctx)}
        self.assertIn("Borrower2Name", names)

    def test_general_contractor_included_for_construction(self):
        ctx = dict(DEFAULTS, deal_type="construction")
        names = {d.field_name for d in FieldRegistry.fields_for_deal(ctx)}
        self.assertIn("GeneralContractorName", names)

    def test_general_contractor_excluded_for_working_capital(self):
        ctx = dict(DEFAULTS, deal_type="working_capital")
        names = {d.field_name for d in FieldRegistry.fields_for_deal(ctx)}
        self.assertNotIn("GeneralContractorName", names)


if __name__ == "__main__":
    unittest.main()
