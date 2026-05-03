"""Tests for extraction.lender_registry.LenderRegistry.

Two scenarios are exercised:

  1. The repo currently ships without lenders.csv. Verify the graceful
     missing-file path: registry loads, lookup() returns None, warning
     is logged.
  2. With a temporary lenders.csv written next to the package, verify
     exact, case-insensitive, whitespace-collapsed, and alias matches.
"""

import unittest
from pathlib import Path

from extraction import lender_registry as lr_module
from extraction.lender_registry import LenderRegistry


class TestLenderRegistryMissingFile(unittest.TestCase):
    """Default state: lenders.csv is absent."""

    @classmethod
    def setUpClass(cls):
        # Ensure the registry is in its "missing file" state for these tests.
        LenderRegistry._load(path=Path("/tmp/__nonexistent_lenders.csv"))

    def test_lookup_returns_none(self):
        self.assertIsNone(LenderRegistry.lookup("Live Oak Banking Company"))

    def test_all_lenders_empty(self):
        self.assertEqual(LenderRegistry.all_lenders(), [])

    def test_canonical_names_empty(self):
        self.assertEqual(LenderRegistry.canonical_names(), [])

    def test_warning_logged_on_missing_file(self):
        bogus = Path("/tmp/__definitely_does_not_exist_lenders.csv")
        with self.assertLogs("extraction.lender_registry", level="WARNING") as cap:
            LenderRegistry._load(path=bogus)
        joined = "\n".join(cap.output)
        self.assertIn("lenders.csv not found", joined)


class TestLenderRegistryWithFile(unittest.TestCase):
    """Write a temporary CSV next to the package, then reload against it."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = Path(lr_module.__file__).parent / "_test_lenders.csv"
        cls._tmp.write_text(
            "lender_name,lender_description,lender_address_1,lender_address_2,"
            "lender_signer_name,lender_signer_title,aliases\n"
            "Live Oak Banking Company,a national bank,1741 Tiburon Dr,Suite 200,"
            "Jane Doe,VP,LOBC|Live Oak\n"
            "Pierpoint Bank,a state bank,1009 S Wall St,,John Smith,SVP,\n",
            encoding="utf-8",
        )
        LenderRegistry._load(path=cls._tmp)

    @classmethod
    def tearDownClass(cls):
        if cls._tmp.exists():
            cls._tmp.unlink()
        # Restore default missing-file state.
        LenderRegistry._load(path=Path("/tmp/__nonexistent_lenders.csv"))

    def test_exact_match(self):
        rec = LenderRegistry.lookup("Live Oak Banking Company")
        self.assertIsNotNone(rec)
        self.assertEqual(rec.lender_name, "Live Oak Banking Company")
        self.assertEqual(rec.lender_signer_title, "VP")

    def test_case_insensitive_match(self):
        rec = LenderRegistry.lookup("live oak banking company")
        self.assertIsNotNone(rec)
        self.assertEqual(rec.lender_name, "Live Oak Banking Company")

    def test_whitespace_collapsed_match(self):
        rec = LenderRegistry.lookup("Live  Oak   Banking    Company")
        self.assertIsNotNone(rec)
        self.assertEqual(rec.lender_name, "Live Oak Banking Company")

    def test_alias_match(self):
        rec1 = LenderRegistry.lookup("LOBC")
        self.assertIsNotNone(rec1)
        self.assertEqual(rec1.lender_name, "Live Oak Banking Company")
        rec2 = LenderRegistry.lookup("live oak")
        self.assertIsNotNone(rec2)
        self.assertEqual(rec2.lender_name, "Live Oak Banking Company")

    def test_no_match_returns_none(self):
        self.assertIsNone(LenderRegistry.lookup("Bank Of Nowhere"))

    def test_all_lenders_returns_records(self):
        names = [r.lender_name for r in LenderRegistry.all_lenders()]
        self.assertEqual(set(names), {"Live Oak Banking Company", "Pierpoint Bank"})

    def test_canonical_names(self):
        self.assertEqual(
            set(LenderRegistry.canonical_names()),
            {"Live Oak Banking Company", "Pierpoint Bank"},
        )


if __name__ == "__main__":
    unittest.main()
