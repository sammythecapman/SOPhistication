"""Field registry loaded from terms_definitions.csv.

Single source of truth for the firm's 7(a) field schema. Used by
extraction.schemas.build_schema() to drive what Claude is asked to extract.

This module also contains the safe applicable_when condition evaluator
(see :func:`evaluate_condition`). The evaluator is a hand-written
recursive-descent parser; no dynamic Python execution is used. The
companion test file enforces this with a source-text check.
"""

import csv
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

CSV_PATH = Path(__file__).parent / "terms_definitions.csv"

# Allowlist for the applicable_when DSL. Any other variable name in an
# expression raises ValueError. Mirrors the registry-context keys produced
# by extraction.models.DealStructure (post wire-through).
_ALLOWED_VARS: Set[str] = {
    "borrower_count",
    "company_guarantor_count",
    "personal_guarantor_count",
    "has_lease",
    "deal_involves_real_estate",
    "requires_equity_injection",
    "requires_life_insurance",
    "has_interest_reserve",
    "deal_type",
}


class FieldDefinition(BaseModel):
    field_name: str
    category: str
    display_name: str
    data_type: str
    enum_values: Optional[List[str]] = None
    source_documents: List[str] = Field(default_factory=list)
    applicable_deal_types: List[str] = Field(default_factory=list)
    applicable_when: Optional[str] = None
    required: bool
    sharepoint_column_name: Optional[str] = None


# ──────────────────────────────────────────────────────────────────────
# Safe applicable_when evaluator
#
# Grammar:
#   expr        := or_expr
#   or_expr     := and_expr ('or' and_expr)*
#   and_expr    := comparison ('and' comparison)*
#   comparison  := var OP value | var 'in' '[' value (',' value)* ']'
#   OP          := '==' | '!=' | '>=' | '<=' | '>' | '<'
#   value       := integer | "'string'" | True | False
#
# No dynamic execution — see tests/test_condition_evaluator for the
# source-level assertion.
# ──────────────────────────────────────────────────────────────────────

_TOKEN_RE = re.compile(
    r"\s*(?:"
    r"(?P<NUM>-?\d+)"
    r"|(?P<STR>'[^']*')"
    r"|(?P<OP>==|!=|>=|<=|>|<|\[|\]|,)"
    r"|(?P<WORD>[A-Za-z_][A-Za-z_0-9]*)"
    r")"
)


def _tokenize(expr: str) -> List[Tuple[str, str]]:
    pos = 0
    tokens: List[Tuple[str, str]] = []
    while pos < len(expr):
        if expr[pos].isspace():
            pos += 1
            continue
        m = _TOKEN_RE.match(expr, pos)
        if not m or m.start() != pos:
            raise ValueError(
                f"Unexpected character {expr[pos]!r} at position {pos} in {expr!r}"
            )
        kind = m.lastgroup
        if kind is None:
            raise ValueError(f"Tokenizer failure at position {pos} in {expr!r}")
        tokens.append((kind, m.group(kind)))
        pos = m.end()
    return tokens


class _Parser:
    def __init__(self, tokens: List[Tuple[str, str]], context: Dict[str, Any]) -> None:
        self.tokens = tokens
        self.pos = 0
        self.ctx = context

    def _peek(self) -> Optional[Tuple[str, str]]:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def _consume(self) -> Tuple[str, str]:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def parse(self) -> bool:
        result = self._or_expr()
        if self.pos != len(self.tokens):
            raise ValueError(
                f"Trailing tokens after expression: {self.tokens[self.pos:]}"
            )
        return result

    def _or_expr(self) -> bool:
        left = self._and_expr()
        while self._peek() == ("WORD", "or"):
            self._consume()
            right = self._and_expr()
            left = bool(left) or bool(right)
        return left

    def _and_expr(self) -> bool:
        left = self._comparison()
        while self._peek() == ("WORD", "and"):
            self._consume()
            right = self._comparison()
            left = bool(left) and bool(right)
        return left

    def _comparison(self) -> bool:
        var_tok = self._consume()
        if var_tok[0] != "WORD":
            raise ValueError(f"Expected variable name, got {var_tok!r}")
        var_name = var_tok[1]
        if var_name not in _ALLOWED_VARS:
            raise ValueError(
                f"Unknown variable {var_name!r} in applicable_when (allowed: "
                f"{sorted(_ALLOWED_VARS)})"
            )
        if var_name not in self.ctx:
            raise KeyError(var_name)
        var_val = self.ctx[var_name]

        nxt = self._peek()
        if nxt == ("WORD", "in"):
            self._consume()
            opener = self._consume()
            if opener != ("OP", "["):
                raise ValueError(f"Expected '[' after 'in', got {opener!r}")
            values: List[Any] = [self._value()]
            while self._peek() == ("OP", ","):
                self._consume()
                values.append(self._value())
            closer = self._consume()
            if closer != ("OP", "]"):
                raise ValueError(f"Expected ']' to close 'in' list, got {closer!r}")
            try:
                return var_val in values
            except TypeError as e:
                raise TypeError(
                    f"Type mismatch in 'in' for {var_name!r}: {e}"
                ) from e

        if nxt is None or nxt[0] != "OP":
            raise ValueError(f"Expected operator after {var_name!r}, got {nxt!r}")
        op = self._consume()[1]
        if op not in {"==", "!=", ">=", "<=", ">", "<"}:
            raise ValueError(f"Unsupported operator {op!r}")
        rhs = self._value()
        try:
            if op == "==":
                return var_val == rhs
            if op == "!=":
                return var_val != rhs
            if op == ">=":
                return var_val >= rhs  # type: ignore[operator]
            if op == "<=":
                return var_val <= rhs  # type: ignore[operator]
            if op == ">":
                return var_val > rhs  # type: ignore[operator]
            if op == "<":
                return var_val < rhs  # type: ignore[operator]
        except TypeError as e:
            raise TypeError(
                f"Type mismatch comparing {var_name!r} {op} {rhs!r}: {e}"
            ) from e
        raise ValueError(f"Unreachable: unhandled operator {op!r}")

    def _value(self) -> Any:
        tok = self._consume()
        if tok[0] == "NUM":
            return int(tok[1])
        if tok[0] == "STR":
            return tok[1][1:-1]
        if tok[0] == "WORD":
            if tok[1] == "True":
                return True
            if tok[1] == "False":
                return False
            raise ValueError(
                f"Unexpected identifier as value: {tok[1]!r} "
                "(expected integer, 'string', True, or False)"
            )
        raise ValueError(f"Expected literal value, got {tok!r}")


def evaluate_condition(expr: Optional[str], context: Dict[str, Any]) -> bool:
    """Evaluate an applicable_when expression against a deal-analysis dict.

    Returns True when expr is None or empty/whitespace-only. Raises
    ValueError on bad grammar or unknown variable, KeyError when a
    referenced variable is not present in ``context``, TypeError on a
    type mismatch (e.g. ``deal_type >= 1``).
    """
    if expr is None or not expr.strip():
        return True
    tokens = _tokenize(expr)
    if not tokens:
        return True
    return _Parser(tokens, context).parse()


# ──────────────────────────────────────────────────────────────────────
# Registry
# ──────────────────────────────────────────────────────────────────────


def _split_pipe(cell: str) -> List[str]:
    if not cell or not cell.strip():
        return []
    return [p.strip() for p in cell.split("|") if p.strip()]


def _parse_bool(cell: str) -> bool:
    return cell.strip().upper() == "TRUE"


def _parse_data_type(raw: str) -> Tuple[str, Optional[List[str]]]:
    raw = raw.strip()
    if raw.startswith("enum:"):
        return "enum", _split_pipe(raw.split(":", 1)[1])
    return raw, None


def _row_to_definition(row: Dict[str, str]) -> FieldDefinition:
    cleaned = {k: (v.strip() if isinstance(v, str) else v) for k, v in row.items()}
    data_type, enum_values = _parse_data_type(cleaned.get("data_type", ""))
    return FieldDefinition(
        field_name=cleaned["field_name"],
        category=cleaned["category"],
        display_name=cleaned["display_name"],
        data_type=data_type,
        enum_values=enum_values,
        source_documents=_split_pipe(cleaned.get("source_documents", "")),
        applicable_deal_types=_split_pipe(cleaned.get("applicable_deal_types", "")),
        applicable_when=(cleaned.get("applicable_when") or "").strip() or None,
        required=_parse_bool(cleaned.get("required", "FALSE")),
        sharepoint_column_name=(cleaned.get("sharepoint_column_name") or "").strip()
        or None,
    )


class FieldRegistry:
    """Module-level singleton. Loaded once at import time."""

    _definitions: List[FieldDefinition] = []
    _by_name: Dict[str, FieldDefinition] = {}

    @classmethod
    def _load(cls, path: Path = CSV_PATH) -> None:
        with open(path, "r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            cls._definitions = [_row_to_definition(row) for row in reader]
        cls._by_name = {d.field_name: d for d in cls._definitions}
        logger.info(
            "FieldRegistry loaded %d field definition(s) from %s",
            len(cls._definitions), path,
        )

    @classmethod
    def get_all(cls) -> List[FieldDefinition]:
        return list(cls._definitions)

    @classmethod
    def canonical_field_names(cls) -> List[str]:
        """All CSV-defined field names in CSV (definition) order.

        This is the registry-driven backbone of the stable output schema.
        Adding or removing a CSV row automatically changes this list, so the
        canonical output schema stays in sync with the firm's field set with
        no second edit. DERIVED/LOOKUP rows are intentionally included — they
        are part of the firm's documented field set and are emitted as ""
        when unpopulated (e.g. Month/Year/NotaryBlockMonth).
        """
        return [d.field_name for d in cls._definitions]

    @classmethod
    def repeating_group_ceilings(cls) -> Dict[str, int]:
        """Hard ceilings for each repeating party group, derived from the CSV.

        Counts the numbered slots present in the field set rather than
        hardcoding 2/4/4 — if the firm ever adds/removes a Borrower or
        Guarantor slot in the CSV, the overflow guard tracks it automatically.

        Returns a dict keyed by group name with the highest slot index seen:
          {"borrower": 2, "personal_guarantor": 4, "company_guarantor": 4}
        """
        borrower: Set[int] = set()
        personal: Set[int] = set()
        company: Set[int] = set()
        for d in cls._definitions:
            name = d.field_name
            m = re.match(r"PersonalGuarantor(\d+)", name)
            if m:
                personal.add(int(m.group(1)))
                continue
            m = re.match(r"CompanyGuarantor(\d+)", name)
            if m:
                company.add(int(m.group(1)))
                continue
            m = re.match(r"Borrower(\d+)", name)
            if m:
                borrower.add(int(m.group(1)))
        return {
            "borrower": max(borrower) if borrower else 0,
            "personal_guarantor": max(personal) if personal else 0,
            "company_guarantor": max(company) if company else 0,
        }

    @classmethod
    def get(cls, field_name: str) -> FieldDefinition:
        return cls._by_name[field_name]

    @classmethod
    def fields_for_deal(cls, deal_analysis: dict) -> List[FieldDefinition]:
        return [
            d for d in cls._definitions
            if evaluate_condition(d.applicable_when, deal_analysis)
        ]

    @classmethod
    def fields_in_document(cls, doc_type: str) -> List[FieldDefinition]:
        # DERIVED and LOOKUP fields have empty source_documents and are not
        # extracted from any document — exclude them defensively as well.
        return [
            d for d in cls._definitions
            if d.data_type not in ("DERIVED", "LOOKUP")
            and doc_type in d.source_documents
        ]

    @classmethod
    def categories(cls) -> List[str]:
        seen: Set[str] = set()
        out: List[str] = []
        for d in cls._definitions:
            if d.category not in seen:
                seen.add(d.category)
                out.append(d.category)
        return out

    @classmethod
    def is_derived(cls, field_name: str) -> bool:
        d = cls._by_name.get(field_name)
        return bool(d and d.data_type == "DERIVED")

    @classmethod
    def is_lookup(cls, field_name: str) -> bool:
        d = cls._by_name.get(field_name)
        return bool(d and d.data_type == "LOOKUP")


FieldRegistry._load()
