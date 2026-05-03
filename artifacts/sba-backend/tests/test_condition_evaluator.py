"""Tests for the safe applicable_when evaluator in extraction.field_registry."""

import inspect
import unittest

from extraction import field_registry
from extraction.field_registry import evaluate_condition


CTX = {
    "borrower_count": 2,
    "company_guarantor_count": 0,
    "personal_guarantor_count": 1,
    "has_lease": True,
    "deal_involves_real_estate": False,
    "requires_equity_injection": True,
    "requires_life_insurance": False,
    "has_interest_reserve": False,
    "deal_type": "asset_purchase",
}


class TestConditionEvaluator(unittest.TestCase):
    def test_none_or_empty_returns_true(self):
        self.assertTrue(evaluate_condition(None, CTX))
        self.assertTrue(evaluate_condition("", CTX))
        self.assertTrue(evaluate_condition("   ", CTX))

    def test_simple_comparisons(self):
        self.assertTrue(evaluate_condition("borrower_count == 2", CTX))
        self.assertFalse(evaluate_condition("borrower_count == 3", CTX))
        self.assertTrue(evaluate_condition("borrower_count != 3", CTX))
        self.assertFalse(evaluate_condition("borrower_count != 2", CTX))
        self.assertTrue(evaluate_condition("borrower_count >= 2", CTX))
        self.assertTrue(evaluate_condition("borrower_count <= 2", CTX))
        self.assertTrue(evaluate_condition("borrower_count > 1", CTX))
        self.assertTrue(evaluate_condition("borrower_count < 3", CTX))
        self.assertFalse(evaluate_condition("personal_guarantor_count >= 3", CTX))

    def test_in_with_string_list(self):
        self.assertTrue(evaluate_condition(
            "deal_type in ['asset_purchase','stock_purchase']", CTX))
        self.assertFalse(evaluate_condition(
            "deal_type in ['construction','working_capital']", CTX))

    def test_compound_and(self):
        self.assertTrue(evaluate_condition(
            "borrower_count >= 2 and personal_guarantor_count >= 1", CTX))
        self.assertFalse(evaluate_condition(
            "borrower_count >= 2 and personal_guarantor_count >= 5", CTX))

    def test_compound_or(self):
        self.assertTrue(evaluate_condition(
            "borrower_count >= 5 or has_lease == True", CTX))
        self.assertFalse(evaluate_condition(
            "borrower_count >= 5 or personal_guarantor_count >= 5", CTX))

    def test_boolean_literal_comparison(self):
        self.assertTrue(evaluate_condition("has_lease == True", CTX))
        self.assertFalse(evaluate_condition("has_lease == False", CTX))
        self.assertTrue(evaluate_condition(
            "requires_equity_injection == True", CTX))

    def test_unknown_variable_raises_value_error(self):
        with self.assertRaises(ValueError) as cm:
            evaluate_condition("not_a_real_var == 1", CTX)
        self.assertIn("not_a_real_var", str(cm.exception))

    def test_missing_variable_raises_key_error(self):
        with self.assertRaises(KeyError) as cm:
            evaluate_condition("borrower_count >= 1", {})
        self.assertIn("borrower_count", str(cm.exception))

    def test_no_dynamic_execution_in_source(self):
        """Belt-and-braces: the evaluator's source must not contain any
        dynamic-execution constructs. Catches accidental future regressions
        like a contributor swapping the parser for a one-liner.
        """
        src = inspect.getsource(field_registry)
        # Only the dynamic-execution constructs called out in the spec.
        # Note: `re.compile(` is intentionally NOT forbidden — that's
        # regex compilation, used legitimately by the tokenizer; only
        # bare `compile(` followed by `exec/eval` constitutes dynamic
        # Python execution and is already covered by the `eval(`/`exec(`
        # checks below.
        forbidden = ["eval(", "exec(", "literal_eval", "__import__"]
        for tok in forbidden:
            self.assertNotIn(
                tok, src,
                f"field_registry.py source contains forbidden construct {tok!r}",
            )


if __name__ == "__main__":
    unittest.main()
