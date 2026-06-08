"""Tests for the stable canonical output schema and the overflow guard.

Covers:
  - canonical_output_fields() == registry superset + injected LoanType
  - project_to_canonical() produces byte-identical key sets/order across
    different deal shapes, fills missing keys with "", drops unknown keys,
    and is idempotent
  - FieldRegistry.repeating_group_ceilings() reflects the CSV ceilings
  - overflow detection fires at count > ceiling and not at count == ceiling
"""

import unittest

from extraction.field_registry import FieldRegistry
from extraction.schemas import canonical_output_fields, project_to_canonical


class TestCanonicalSchema(unittest.TestCase):
    def test_canonical_equals_registry_superset_plus_loantype(self):
        canonical = canonical_output_fields()
        csv_names = FieldRegistry.canonical_field_names()
        # Exactly one extra key (LoanType) beyond the CSV definitions.
        self.assertEqual(len(canonical), len(csv_names) + 1)
        self.assertIn("LoanType", canonical)
        # Every CSV field is present, in its original relative order.
        self.assertEqual([n for n in canonical if n != "LoanType"], csv_names)

    def test_loantype_inserted_at_loan_details_head(self):
        canonical = canonical_output_fields()
        self.assertEqual(
            canonical[canonical.index("LoanType") + 1], "LoanAmountLong"
        )

    def test_canonical_is_deterministic(self):
        self.assertEqual(canonical_output_fields(), canonical_output_fields())

    def test_different_deal_shapes_yield_identical_keys_and_order(self):
        # A narrow 1-borrower deal vs. a maximal multi-party deal.
        narrow = {"Borrower1Name": "Bob's Burgers LLC", "LoanType": "7(a)"}
        wide = {
            "Borrower1Name": "Acme Co",
            "Borrower2Name": "Beta Co",
            "PersonalGuarantor1": "Jane Doe",
            "CompanyGuarantor1Name": "Holdings LLC",
            "GeneralContractorName": "BuildCo",
            "LoanType": "504",
        }
        pn = project_to_canonical(narrow)
        pw = project_to_canonical(wide)
        # Byte-identical key sets AND ordering.
        self.assertEqual(list(pn.keys()), list(pw.keys()))
        self.assertEqual(list(pn.keys()), canonical_output_fields())

    def test_missing_keys_filled_with_empty_string(self):
        projected = project_to_canonical({"Borrower1Name": "X"})
        self.assertEqual(projected["Borrower1Name"], "X")
        # A field absent from the input is present as "".
        self.assertIn("Borrower2Name", projected)
        self.assertEqual(projected["Borrower2Name"], "")

    def test_unknown_keys_dropped(self):
        projected = project_to_canonical({"NotARealField": "junk"})
        self.assertNotIn("NotARealField", projected)
        self.assertEqual(set(projected.keys()), set(canonical_output_fields()))

    def test_projection_is_idempotent(self):
        once = project_to_canonical({"Borrower1Name": "X"})
        twice = project_to_canonical(once)
        self.assertEqual(once, twice)
        self.assertEqual(list(once.keys()), list(twice.keys()))

    def test_legacy_row_anomalies_coerced_to_string(self):
        # A legacy/malformed blob with a null value, a non-string value, an
        # extra unknown key, and missing keys must still project to the exact
        # canonical key set/order with every value a string ("" for null/missing).
        legacy = {
            "Borrower1Name": "Acme",
            "LoanAmountShort": None,
            "Year": 2025,
            "DroppedExtraField": "junk",
        }
        projected = project_to_canonical(legacy)
        self.assertEqual(list(projected.keys()), canonical_output_fields())
        self.assertEqual(projected["Borrower1Name"], "Acme")
        self.assertEqual(projected["LoanAmountShort"], "")
        self.assertEqual(projected["Year"], "2025")
        self.assertNotIn("DroppedExtraField", projected)
        self.assertTrue(all(isinstance(v, str) for v in projected.values()))

    def test_non_dict_input_does_not_raise(self):
        # Malformed historical data (e.g. a list) must not 500 a download.
        for bad in ([], "x", 0):
            projected = project_to_canonical(bad)  # type: ignore[arg-type]
            self.assertEqual(list(projected.keys()), canonical_output_fields())
            self.assertTrue(all(v == "" for v in projected.values()))

    def test_empty_and_none_input(self):
        self.assertEqual(
            list(project_to_canonical({}).keys()), canonical_output_fields()
        )
        self.assertEqual(
            list(project_to_canonical(None).keys()), canonical_output_fields()
        )
        # All values default to "".
        self.assertTrue(all(v == "" for v in project_to_canonical({}).values()))


class TestRepeatingGroupCeilings(unittest.TestCase):
    def test_ceilings_match_csv(self):
        ceilings = FieldRegistry.repeating_group_ceilings()
        self.assertEqual(ceilings["borrower"], 2)
        self.assertEqual(ceilings["personal_guarantor"], 4)
        self.assertEqual(ceilings["company_guarantor"], 4)


class TestOverflowDetection(unittest.TestCase):
    """Mirror the pipeline's overflow comparison logic.

    The detection lives inline in run_extraction_pipeline (it depends on the
    live deal-analysis output), so we exercise the same comparison contract
    here against the registry-derived ceilings: overflow fires strictly when
    reported > ceiling, never at reported == ceiling.
    """

    def _overflow(self, deal):
        ceilings = FieldRegistry.repeating_group_ceilings()
        checks = [
            ("borrower", "borrower_count"),
            ("personal_guarantor", "personal_guarantor_count"),
            ("company_guarantor", "company_guarantor_count"),
        ]
        out = []
        for group, key in checks:
            ceiling = ceilings.get(group, 0)
            reported = deal.get(key)
            if isinstance(reported, int) and ceiling and reported > ceiling:
                out.append(group)
        return out

    def test_no_overflow_at_ceiling(self):
        deal = {
            "borrower_count": 2,
            "personal_guarantor_count": 4,
            "company_guarantor_count": 4,
        }
        self.assertEqual(self._overflow(deal), [])

    def test_no_overflow_below_ceiling(self):
        deal = {
            "borrower_count": 1,
            "personal_guarantor_count": 0,
            "company_guarantor_count": 0,
        }
        self.assertEqual(self._overflow(deal), [])

    def test_overflow_above_ceiling(self):
        deal = {
            "borrower_count": 3,
            "personal_guarantor_count": 6,
            "company_guarantor_count": 4,
        }
        self.assertEqual(
            self._overflow(deal), ["borrower", "personal_guarantor"]
        )

    def test_missing_counts_do_not_overflow(self):
        # Deal-analysis failure leaves deal == {} -> no counts -> no overflow.
        self.assertEqual(self._overflow({}), [])


if __name__ == "__main__":
    unittest.main()
