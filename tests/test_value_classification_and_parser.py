"""
Tests for Value Classification and Auditable Parsing

Verifies the cell classification invariant (source == missing + valid + invalid + unclassified),
auditable numeric parsing, currency/percentage rules, non-finite values, and datetime ambiguity.
"""

from __future__ import annotations

import math
import tempfile
import os

import pytest

from ai_csv_data_analyst.config import ProfilingConfig
from ai_csv_data_analyst.diagnostics import ColumnValueCounts, ValueCategory
from ai_csv_data_analyst.parser import (
    parse_boolean_auditable,
    parse_datetime_auditable,
    parse_numeric_auditable,
)
from ai_csv_data_analyst.profiler import profile_csv


def create_temp_csv(content: str) -> str:
    """Create a temporary CSV file with given content."""
    fd, path = tempfile.mkstemp(suffix=".csv")
    try:
        os.write(fd, content.encode("utf-8"))
        os.close(fd)
        return path
    except Exception:
        os.close(fd)
        os.unlink(path)
        raise


class TestValueClassificationAndParser:
    """Test suite for value classification and parser auditability."""

    def test_invariant_reconciliation_enforced(self) -> None:
        """Verify source_cell_count == missing + valid + invalid + unclassified across columns."""
        content = """numeric_col,bool_col,text_col
100,true,apple
N/A,false,banana
50,,cherry
corrupt,yes,
75,maybe,date
,true,elderberry
"""
        path = create_temp_csv(content)
        try:
            # Without N/A in missing tokens, N/A in numeric_col is invalid
            profile = profile_csv(path)
            for col_name, col_stats in profile.column_profiles.items():
                vc = col_stats.value_counts
                assert vc is not None
                assert vc.is_reconciled is True
                assert vc.source_cell_count == (
                    vc.missing_count + vc.valid_count + vc.invalid_count + vc.unclassified_count
                )
                assert vc.source_cell_count == 6

            # Check rates
            num_vc = profile.column_profiles["numeric_col"].value_counts
            assert num_vc.missing_count == 1  # the empty cell on row 6
            assert num_vc.valid_count == 3    # 100, 50, 75
            assert num_vc.invalid_count == 2  # 'N/A' and 'corrupt'
            assert num_vc.missing_rate == round(1 / 6, 6)
            assert num_vc.invalid_rate == round(2 / 6, 6)
        finally:
            os.unlink(path)

    def test_configurable_missing_value_tokens(self) -> None:
        """Verify tokens like 'N/A' and 'NULL' are classified as missing only when configured."""
        content = """code,status
10,ACTIVE
NA,PENDING
20,NA
30,NULL
"""
        path = create_temp_csv(content)
        try:
            # Default config: 'NA' and 'NULL' are NOT missing
            p_default = profile_csv(path)
            assert p_default.column_profiles["code"].missing_count == 0
            assert p_default.column_profiles["status"].missing_count == 0

            # Configured config: 'NA' and 'NULL' are missing
            cfg = ProfilingConfig(missing_tokens=("NA", "NULL"))
            p_custom = profile_csv(path, config=cfg)
            assert p_custom.column_profiles["code"].missing_count == 1
            assert p_custom.column_profiles["status"].missing_count == 2
        finally:
            os.unlink(path)

    def test_numeric_parsing_rules_and_preservation(self) -> None:
        """Verify raw value preservation, rule application, percentages, and currencies."""
        # Exact integer
        r_int = parse_numeric_auditable("42")
        assert r_int.is_valid and r_int.parsed_value == 42
        assert r_int.rule_applied == "exact_integer"

        # Percentage: preserves number and notes rule
        r_pct = parse_numeric_auditable("85.5%")
        assert r_pct.is_valid and r_pct.parsed_value == 85.5
        assert "percentage_symbol_stripped" in r_pct.rule_applied

        # Currency
        r_curr = parse_numeric_auditable("$1,250.00")
        assert r_curr.is_valid and r_curr.parsed_value == 1250.0
        assert "currency_symbol_prefix_stripped" in r_curr.rule_applied

        # Ambiguous comma as decimal
        r_amb = parse_numeric_auditable("12,5")
        assert r_amb.is_valid
        assert r_amb.is_ambiguous is True
        assert r_amb.parsed_value == 12.5

        # European format
        r_eur = parse_numeric_auditable("1.250,50")
        assert r_eur.is_valid and r_eur.parsed_value == 1250.50
        assert "european_thousands_dot_and_comma_decimal" in r_eur.rule_applied

    def test_non_finite_numeric_values_are_invalid_with_diagnostics(self) -> None:
        """Verify NaN and Inf are classified as invalid rather than silent missing or crash."""
        r_nan = parse_numeric_auditable("NaN")
        assert r_nan.is_valid is False
        assert r_nan.category == ValueCategory.INVALID
        assert math.isnan(r_nan.parsed_value)

        r_inf = parse_numeric_auditable("+Infinity")
        assert r_inf.is_valid is False
        assert r_inf.category == ValueCategory.INVALID
        assert math.isinf(r_inf.parsed_value)

    def test_datetime_parsing_iso_and_ambiguity(self) -> None:
        """Verify ISO parsing, calendar validation, and ambiguous date flagging."""
        # Valid ISO date
        r_iso = parse_datetime_auditable("2023-08-15")
        assert r_iso.is_valid
        assert r_iso.parsed_value.year == 2023
        assert r_iso.parsed_value.month == 8
        assert r_iso.parsed_value.day == 15
        assert r_iso.is_ambiguous is False

        # Invalid calendar date (Feb 31)
        r_inv = parse_datetime_auditable("2023-02-31")
        assert r_inv.is_valid is False
        assert r_inv.category == ValueCategory.INVALID
        assert "invalid_calendar_date" in r_inv.rule_applied

        # Ambiguous slash date (03/04/2021 -> day 3 month 4 or month 3 day 4)
        r_amb = parse_datetime_auditable("03/04/2021")
        assert r_amb.is_valid is True
        assert r_amb.is_ambiguous is True
        assert len(r_amb.alternatives) > 0

        # Unambiguous slash date (25/12/2021 -> 25 cannot be month)
        r_unamb = parse_datetime_auditable("25/12/2021")
        assert r_unamb.is_valid is True
        assert r_unamb.is_ambiguous is False
        assert r_unamb.parsed_value.day == 25
        assert r_unamb.parsed_value.month == 12

    def test_boolean_auditable_parsing(self) -> None:
        """Verify boolean tokens parse accurately with audit rules."""
        assert parse_boolean_auditable("true").parsed_value is True
        assert parse_boolean_auditable("yes").parsed_value is True
        assert parse_boolean_auditable("false").parsed_value is False
        assert parse_boolean_auditable("no").parsed_value is False
        assert parse_boolean_auditable("invalid_bool").is_valid is False

