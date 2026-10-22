"""
Auditable Value Parsers for Numeric, Datetime, and Boolean Types

Provides explicit, rule-based parsing with auditability, ambiguity detection,
and raw-to-interpreted value preservation.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ai_csv_data_analyst.config import ProfilingConfig
from ai_csv_data_analyst.diagnostics import ValueCategory


@dataclass
class ParseResult:
    """Result of parsing an individual cell value under declared rules."""
    is_valid: bool
    parsed_value: Any
    raw_value: str
    category: ValueCategory
    rule_applied: str
    error_message: str | None = None
    is_ambiguous: bool = False
    alternatives: list[Any] = field(default_factory=list)


# Regex patterns for numeric detection
_INT_RE = re.compile(r"^[+-]?\d+$")
_FLOAT_STD_RE = re.compile(r"^[+-]?\d+\.\d+(?:[eE][+-]?\d+)?$")
_EXP_ONLY_RE = re.compile(r"^[+-]?\d+(?:[eE][+-]?\d+)$")
_CURRENCY_PREFIX_RE = re.compile(r"^[₹$€£¥]\s*(.+)$")
_CURRENCY_SUFFIX_RE = re.compile(r"^(.+)\s*[₹$€£¥]$")
_THOUSANDS_COMMA_RE = re.compile(r"^[+-]?\d{1,3}(?:,\d{3})+(?:\.\d+)?$")
_THOUSANDS_DOT_RE = re.compile(r"^[+-]?\d{1,3}(?:\.\d{3})+(?:,\d+)?$")
_DECIMAL_COMMA_RE = re.compile(r"^[+-]?\d+,\d+$")


def parse_numeric_auditable(
    raw: Any,
    config: ProfilingConfig | None = None,
) -> ParseResult:
    """
    Attempt to parse a raw value as numeric under explicit, auditable rules.

    Distinguishes:
    - Standard integers and floats
    - Formatted numbers with valid thousand separators
    - Currency symbols (with declared currency rule)
    - Percentages (preserves original number and notes percentage rule)
    - Ambiguous numbers (e.g., 12,5 when decimal separator is uncertain)
    - Non-finite numbers (NaN, Inf)
    """
    cfg = config or ProfilingConfig()
    raw_str = "" if raw is None else str(raw)
    stripped = raw_str.strip()

    if not stripped or cfg.is_missing_token(raw_str):
        return ParseResult(
            is_valid=False,
            parsed_value=None,
            raw_value=raw_str,
            category=ValueCategory.MISSING,
            rule_applied="missing_token_or_blank",
        )

    # Check for non-finite values
    lower_s = stripped.lower()
    if lower_s in ("nan", "+nan", "-nan"):
        return ParseResult(
            is_valid=False,
            parsed_value=math.nan,
            raw_value=raw_str,
            category=ValueCategory.INVALID,
            rule_applied="non_finite_nan",
            error_message="Value is NaN (non-finite numeric)",
        )
    if lower_s in ("inf", "+inf", "-inf", "infinity", "+infinity", "-infinity"):
        val = -math.inf if "-" in lower_s else math.inf
        return ParseResult(
            is_valid=False,
            parsed_value=val,
            raw_value=raw_str,
            category=ValueCategory.INVALID,
            rule_applied="non_finite_inf",
            error_message="Value is Infinite (non-finite numeric)",
        )

    # Check for direct integer
    if _INT_RE.match(stripped):
        try:
            val = int(stripped)
            return ParseResult(
                is_valid=True,
                parsed_value=val,
                raw_value=raw_str,
                category=ValueCategory.VALID,
                rule_applied="exact_integer",
            )
        except ValueError:
            pass

    # Check for standard float (with optional exponent)
    if _FLOAT_STD_RE.match(stripped) or _EXP_ONLY_RE.match(stripped):
        try:
            val = float(stripped)
            if not math.isnan(val) and not math.isinf(val):
                return ParseResult(
                    is_valid=True,
                    parsed_value=val,
                    raw_value=raw_str,
                    category=ValueCategory.VALID,
                    rule_applied="exact_float_dot_decimal",
                )
        except ValueError:
            pass

    working_str = stripped
    rule_notes: list[str] = []

    # Check for currency symbols if allowed
    if cfg.allow_currency_symbols:
        prefix_match = _CURRENCY_PREFIX_RE.match(working_str)
        if prefix_match:
            working_str = prefix_match.group(1).strip()
            rule_notes.append("currency_symbol_prefix_stripped")
        else:
            suffix_match = _CURRENCY_SUFFIX_RE.match(working_str)
            if suffix_match:
                working_str = suffix_match.group(1).strip()
                rule_notes.append("currency_symbol_suffix_stripped")

    # Check for percentage if allowed
    is_percentage = False
    if cfg.allow_percentage and working_str.endswith("%"):
        working_str = working_str[:-1].strip()
        is_percentage = True
        rule_notes.append("percentage_symbol_stripped")

    # Check standard thousands comma with dot decimal: e.g. 1,000 or 1,234.56
    if _THOUSANDS_COMMA_RE.match(working_str):
        clean_num = working_str.replace(",", "")
        try:
            val = float(clean_num)
            rule_notes.append("thousands_comma_removed")
            return ParseResult(
                is_valid=True,
                parsed_value=val,
                raw_value=raw_str,
                category=ValueCategory.VALID,
                rule_applied="+".join(rule_notes) or "thousands_comma_removed",
                is_ambiguous=False,
            )
        except ValueError:
            pass

    # Check European format thousands dot with comma decimal: e.g. 1.234,56
    if _THOUSANDS_DOT_RE.match(working_str):
        clean_num = working_str.replace(".", "").replace(",", ".")
        try:
            val = float(clean_num)
            rule_notes.append("european_thousands_dot_and_comma_decimal")
            return ParseResult(
                is_valid=True,
                parsed_value=val,
                raw_value=raw_str,
                category=ValueCategory.VALID,
                rule_applied="+".join(rule_notes),
                is_ambiguous=False,
            )
        except ValueError:
            pass

    # Check simple comma decimal e.g. 12,5
    if _DECIMAL_COMMA_RE.match(working_str):
        parts = working_str.split(",")
        # If decimal separator is configured as ",", interpret as float
        if cfg.decimal_separator == ",":
            val = float(working_str.replace(",", "."))
            rule_notes.append("configured_comma_decimal")
            return ParseResult(
                is_valid=True,
                parsed_value=val,
                raw_value=raw_str,
                category=ValueCategory.VALID,
                rule_applied="+".join(rule_notes),
                is_ambiguous=False,
            )
        # If decimal separator is ".", and fractional part length is not 3 (not thousands),
        # flag ambiguity rather than silently assuming comma is decimal or thousands
        val_as_decimal = float(f"{parts[0]}.{parts[1]}")
        return ParseResult(
            is_valid=True,
            parsed_value=val_as_decimal,
            raw_value=raw_str,
            category=ValueCategory.VALID,
            rule_applied="+".join(rule_notes + ["ambiguous_comma_as_decimal"]),
            is_ambiguous=True,
            alternatives=[parts[0] + parts[1]],
        )

    # Try remaining cleaned number if rules were applied (e.g. $100 or 50%)
    if rule_notes and working_str:
        try:
            val = float(working_str)
            if not math.isnan(val) and not math.isinf(val):
                return ParseResult(
                    is_valid=True,
                    parsed_value=val,
                    raw_value=raw_str,
                    category=ValueCategory.VALID,
                    rule_applied="+".join(rule_notes),
                )
        except ValueError:
            pass

    # Cannot parse as numeric
    return ParseResult(
        is_valid=False,
        parsed_value=None,
        raw_value=raw_str,
        category=ValueCategory.INVALID,
        rule_applied="numeric_parse_failure",
        error_message=f"Cannot parse '{raw_str}' as numeric under active rules",
    )


# Datetime patterns
_ISO_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_ISO_DATETIME_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?$")
_SLASH_DATE_RE = re.compile(r"^(\d{1,4})[/-](\d{1,2})[/-](\d{1,4})(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?$")


def parse_datetime_auditable(
    raw: Any,
    config: ProfilingConfig | None = None,
) -> ParseResult:
    """
    Attempt to parse a raw value as datetime under declared formats.

    Preserves original strings, detects date format ambiguity (e.g. 03/04/2021),
    and validates calendar constraints without silent coercion.
    """
    cfg = config or ProfilingConfig()
    raw_str = "" if raw is None else str(raw)
    stripped = raw_str.strip()

    if not stripped or cfg.is_missing_token(raw_str):
        return ParseResult(
            is_valid=False,
            parsed_value=None,
            raw_value=raw_str,
            category=ValueCategory.MISSING,
            rule_applied="missing_token_or_blank",
        )

    # If explicit formats are provided in config, try each strictly
    if cfg.datetime_formats:
        for fmt in cfg.datetime_formats:
            try:
                dt = datetime.strptime(stripped, fmt)
                return ParseResult(
                    is_valid=True,
                    parsed_value=dt,
                    raw_value=raw_str,
                    category=ValueCategory.VALID,
                    rule_applied=f"explicit_format:{fmt}",
                )
            except ValueError:
                continue
        return ParseResult(
            is_valid=False,
            parsed_value=None,
            raw_value=raw_str,
            category=ValueCategory.INVALID,
            rule_applied="explicit_datetime_formats_mismatch",
            error_message=f"Value '{raw_str}' did not match any declared datetime format",
        )

    # Check ISO 8601 date: YYYY-MM-DD
    iso_date_m = _ISO_DATE_RE.match(stripped)
    if iso_date_m:
        year, month, day = int(iso_date_m.group(1)), int(iso_date_m.group(2)), int(iso_date_m.group(3))
        try:
            dt = datetime(year, month, day)
            return ParseResult(
                is_valid=True,
                parsed_value=dt,
                raw_value=raw_str,
                category=ValueCategory.VALID,
                rule_applied="iso_8601_date",
            )
        except ValueError as e:
            return ParseResult(
                is_valid=False,
                parsed_value=None,
                raw_value=raw_str,
                category=ValueCategory.INVALID,
                rule_applied="invalid_calendar_date",
                error_message=str(e),
            )

    # Check ISO 8601 datetime
    if _ISO_DATETIME_RE.match(stripped):
        clean_iso = stripped.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(clean_iso)
            return ParseResult(
                is_valid=True,
                parsed_value=dt,
                raw_value=raw_str,
                category=ValueCategory.VALID,
                rule_applied="iso_8601_datetime",
            )
        except ValueError as e:
            return ParseResult(
                is_valid=False,
                parsed_value=None,
                raw_value=raw_str,
                category=ValueCategory.INVALID,
                rule_applied="invalid_iso_datetime",
                error_message=str(e),
            )

    # Check separated dates like DD/MM/YYYY or MM/DD/YYYY
    slash_m = _SLASH_DATE_RE.match(stripped)
    if slash_m:
        p1, p2, p3 = int(slash_m.group(1)), int(slash_m.group(2)), int(slash_m.group(3))
        # If p3 is 4-digit year: e.g. D/M/YYYY or M/D/YYYY
        if p3 >= 1000:
            year = p3
            # Ambiguity check: both p1 and p2 <= 12
            if 1 <= p1 <= 12 and 1 <= p2 <= 12 and p1 != p2:
                # Ambiguous: could be DD/MM/YYYY or MM/DD/YYYY
                try:
                    dt_mdy = datetime(year, p1, p2)
                    dt_dmy = datetime(year, p2, p1)
                    return ParseResult(
                        is_valid=True,
                        parsed_value=dt_mdy,
                        raw_value=raw_str,
                        category=ValueCategory.VALID,
                        rule_applied="ambiguous_date_slash_4digit_year",
                        is_ambiguous=True,
                        alternatives=[dt_dmy.isoformat()],
                    )
                except ValueError:
                    pass
            elif 1 <= p1 <= 12 and 13 <= p2 <= 31:
                # Must be MM/DD/YYYY
                try:
                    dt = datetime(year, p1, p2)
                    return ParseResult(
                        is_valid=True,
                        parsed_value=dt,
                        raw_value=raw_str,
                        category=ValueCategory.VALID,
                        rule_applied="unambiguous_mm_dd_yyyy",
                    )
                except ValueError as e:
                    return ParseResult(
                        is_valid=False,
                        parsed_value=None,
                        raw_value=raw_str,
                        category=ValueCategory.INVALID,
                        rule_applied="invalid_calendar_date",
                        error_message=str(e),
                    )
            elif 13 <= p1 <= 31 and 1 <= p2 <= 12:
                # Must be DD/MM/YYYY
                try:
                    dt = datetime(year, p2, p1)
                    return ParseResult(
                        is_valid=True,
                        parsed_value=dt,
                        raw_value=raw_str,
                        category=ValueCategory.VALID,
                        rule_applied="unambiguous_dd_mm_yyyy",
                    )
                except ValueError as e:
                    return ParseResult(
                        is_valid=False,
                        parsed_value=None,
                        raw_value=raw_str,
                        category=ValueCategory.INVALID,
                        rule_applied="invalid_calendar_date",
                        error_message=str(e),
                    )

    return ParseResult(
        is_valid=False,
        parsed_value=None,
        raw_value=raw_str,
        category=ValueCategory.INVALID,
        rule_applied="datetime_parse_failure",
        error_message=f"Cannot parse '{raw_str}' as datetime under declared formats",
    )


_BOOLEAN_TRUE = frozenset(("true", "yes", "1", "t"))
_BOOLEAN_FALSE = frozenset(("false", "no", "0", "f"))


def parse_boolean_auditable(
    raw: Any,
    config: ProfilingConfig | None = None,
) -> ParseResult:
    """Attempt to parse a raw value as boolean."""
    cfg = config or ProfilingConfig()
    raw_str = "" if raw is None else str(raw)
    stripped = raw_str.strip()

    if not stripped or cfg.is_missing_token(raw_str):
        return ParseResult(
            is_valid=False,
            parsed_value=None,
            raw_value=raw_str,
            category=ValueCategory.MISSING,
            rule_applied="missing_token_or_blank",
        )

    lower_s = stripped.lower()
    if lower_s in _BOOLEAN_TRUE:
        return ParseResult(
            is_valid=True,
            parsed_value=True,
            raw_value=raw_str,
            category=ValueCategory.VALID,
            rule_applied="boolean_true_token",
        )
    if lower_s in _BOOLEAN_FALSE:
        return ParseResult(
            is_valid=True,
            parsed_value=False,
            raw_value=raw_str,
            category=ValueCategory.VALID,
            rule_applied="boolean_false_token",
        )

    return ParseResult(
        is_valid=False,
        parsed_value=None,
        raw_value=raw_str,
        category=ValueCategory.INVALID,
        rule_applied="boolean_parse_failure",
        error_message=f"Cannot parse '{raw_str}' as boolean",
    )


_MONTH_NAME_TO_INT = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}
_MY_TOKEN_RE = re.compile(r"^([a-zA-Z]+|\d{1,2})[ \-_/](\d{2,4})$")
_YM_TOKEN_RE = re.compile(r"^(\d{4})[ \-_/]([a-zA-Z]+|\d{1,2})$")


def parse_month_year_token(val: Any) -> tuple[int, int] | None:
    """
    Parse a month-year string into (month, year) integer tuple.
    Handles 'Feb-2019', 'February 2019', '02/2019', '2019-02', etc.
    """
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None

    m = _MY_TOKEN_RE.match(s)
    if m:
        m_part, y_part = m.group(1).lower(), m.group(2)
        month = None
        if m_part in _MONTH_NAME_TO_INT:
            month = _MONTH_NAME_TO_INT[m_part]
        elif m_part.isdigit() and 1 <= int(m_part) <= 12:
            month = int(m_part)

        if month is not None:
            year = int(y_part)
            if year < 100:
                year += 2000 if year < 70 else 1900
            return (month, year)

    m2 = _YM_TOKEN_RE.match(s)
    if m2:
        y_part, m_part = m2.group(1), m2.group(2).lower()
        month = None
        if m_part in _MONTH_NAME_TO_INT:
            month = _MONTH_NAME_TO_INT[m_part]
        elif m_part.isdigit() and 1 <= int(m_part) <= 12:
            month = int(m_part)
        if month is not None:
            return (month, int(y_part))

    return None

