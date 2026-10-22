"""
Tests for Targeted Fixes: Dates, Identifiers, Missing Values, and Provenance

Covers the four focused fixes:
1. Date ambiguity, contextual month-year resolution, chronological DOA/DOD, and range calculation.
2. Identifier vs. measurement distinction, SNO/MRD No. heuristics, suppressing misleading metrics.
3. Configurable missing-value tokens (EMPTY, NILL), blank vs. sentinel tracking, per-column overrides.
4. Runtime provenance, module path verification, package version, and report compatibility.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

import ai_csv_data_analyst
from ai_csv_data_analyst.config import ProfilingConfig
from ai_csv_data_analyst.profiler import profile_csv
from ai_csv_data_analyst.types_and_roles import PhysicalType, SemanticRole, infer_column_type_and_role


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


class TestDateAmbiguityAndResolution:
    """Fix 1: Date ambiguity, contextual resolution, and date-range calculations."""

    def test_unambiguous_day_month_year(self) -> None:
        """Verify unambiguous day/month/year dates (day > 12) determine format as DD/MM/YYYY."""
        content = """event_date
25/01/2021
28/01/2021
30/01/2021
"""
        path = create_temp_csv(content)
        try:
            profile = profile_csv(path)
            dt_stats = profile.column_profiles["event_date"].datetime_stats
            assert dt_stats is not None
            assert dt_stats["chosen_format"] == "%d/%m/%Y"
            assert dt_stats["format_resolution_method"] == "unambiguous_samples"
            assert dt_stats["date_range_is_definitive"] is True
            assert dt_stats["min_timestamp"] == "2021-01-25T00:00:00"
            assert dt_stats["max_timestamp"] == "2021-01-30T00:00:00"
            assert dt_stats["coverage_days"] == 5.0
        finally:
            os.unlink(path)

    def test_unambiguous_month_day_year(self) -> None:
        """Verify unambiguous month/day/year dates (month at pos 1, day > 12 at pos 2)."""
        content = """event_date
01/25/2021
01/28/2021
"""
        path = create_temp_csv(content)
        try:
            profile = profile_csv(path)
            dt_stats = profile.column_profiles["event_date"].datetime_stats
            assert dt_stats is not None
            assert dt_stats["chosen_format"] == "%m/%d/%Y"
            assert dt_stats["format_resolution_method"] == "unambiguous_samples"
            assert dt_stats["date_range_is_definitive"] is True
            assert dt_stats["min_timestamp"] == "2021-01-25T00:00:00"
            assert dt_stats["max_timestamp"] == "2021-01-28T00:00:00"
        finally:
            os.unlink(path)

    def test_ambiguous_dates_without_context_withholds_definitive_range(self) -> None:
        """Verify when all dates are ambiguous and no context exists, definitive range is withheld."""
        content = """date_col
04/02/2019
05/03/2019
"""
        path = create_temp_csv(content)
        try:
            profile = profile_csv(path)
            dt_stats = profile.column_profiles["date_col"].datetime_stats
            assert dt_stats is not None
            assert dt_stats["ambiguous_dates_count"] == 2
            assert dt_stats["unresolved_ambiguous_count"] == 2
            assert dt_stats["chosen_format"] is None
            assert dt_stats["format_resolution_method"] == "unresolved"
            assert dt_stats["date_range_is_definitive"] is False
            assert dt_stats["min_timestamp"] is None
            assert dt_stats["max_timestamp"] is None
            assert "withheld" in dt_stats["uncertainty"].lower()
        finally:
            os.unlink(path)

    def test_doa_resolved_via_contextual_month_year(self) -> None:
        """Verify ambiguous D.O.A dates are contextually resolved against 'month year' column."""
        # 04/02/2019 could be 4 Feb (DMY) or 2 Apr (MDY).
        # month year is 'Feb-2019', so month 2 -> resolves as DMY (4 Feb 2019)
        content = """D.O.A,month year
04/02/2019,Feb-2019
08/02/2019,Feb-2019
"""
        path = create_temp_csv(content)
        try:
            profile = profile_csv(path)
            doa_stats = profile.column_profiles["D.O.A"].datetime_stats
            assert doa_stats is not None
            assert doa_stats["chosen_format"] == "%d/%m/%Y"
            assert doa_stats["format_resolution_method"] == "contextual_evidence"
            assert doa_stats["date_range_is_definitive"] is True
            assert doa_stats["contextually_resolved_count"] == 2
            assert doa_stats["unresolved_ambiguous_count"] == 0
            assert doa_stats["min_timestamp"] == "2019-02-04T00:00:00"
            assert doa_stats["max_timestamp"] == "2019-02-08T00:00:00"
        finally:
            os.unlink(path)

    def test_dod_crosses_month_boundary_without_forced_admission_month(self) -> None:
        """Verify D.O.D is not forced to admission month; chronological stay D.O.D >= D.O.A is respected."""
        # Patient admitted 28 Jan 2019, discharged 03 Feb 2019
        content = """D.O.A,D.O.D,month year
28/01/2019,03/02/2019,Jan-2019
"""
        path = create_temp_csv(content)
        try:
            profile = profile_csv(path)
            dod_stats = profile.column_profiles["D.O.D"].datetime_stats
            assert dod_stats is not None
            assert dod_stats["chosen_format"] == "%d/%m/%Y"
            assert dod_stats["min_timestamp"] == "2019-02-03T00:00:00"
        finally:
            os.unlink(path)

    def test_invalid_calendar_date_reported_accurately(self) -> None:
        """Verify invalid date like Feb 31 is accounted under invalid_dates_count, not ambiguous."""
        content = """dt
2023-02-31
"""
        path = create_temp_csv(content)
        try:
            profile = profile_csv(path)
            dt_stats = profile.column_profiles["dt"].datetime_stats
            assert dt_stats is not None
            assert dt_stats["invalid_dates_count"] == 1
            assert dt_stats["valid_timestamp_count"] == 0
        finally:
            os.unlink(path)


class TestIdentifierClassification:
    """Fix 2: Distinguish identifiers from measurements and suppress misleading statistics."""

    def test_sno_classified_as_identifier_without_measurement_stats(self) -> None:
        """Verify sequential SNO column gets identifier role and no numeric mean/std/quartiles."""
        content = "SNO,score\n" + "\n".join(f"{i},{70.0 + (i * 7) % 30}" for i in range(1, 51))
        path = create_temp_csv(content)
        try:
            profile = profile_csv(path)
            sno_col = profile.column_profiles["SNO"]
            assert sno_col.semantic_role == "identifier"
            assert sno_col.physical_type == "integer"
            # Misleading measurement statistics must be suppressed
            assert sno_col.numeric_stats is None
            assert sno_col.outlier_stats is None
            # Identifier-specific stats preserved
            assert sno_col.identifier_stats is not None
            assert sno_col.identifier_stats["is_sequential"] is True
            assert sno_col.identifier_stats["is_candidate_key"] is True

            # The score column remains a genuine measure with numeric statistics
            score_col = profile.column_profiles["score"]
            assert score_col.semantic_role == "measure"
            assert score_col.numeric_stats is not None
            assert score_col.numeric_stats["mean"] is not None
        finally:
            os.unlink(path)

    def test_mrd_no_with_repeated_visits_classified_as_identifier(self) -> None:
        """Verify MRD No. (medical record ID) is recognized as identifier even with repeated values."""
        # Hospital dataset: 10 patients across 15 admission rows (some patients repeat)
        mrd_values = [
            "1001", "1002", "1003", "1004", "1005",
            "1001", "1002", "1006", "1007", "1008",
            "1009", "1010", "1003", "1004", "1005",
        ]
        content = "MRD No.,cost\n" + "\n".join(f"{mrd},{500 + i * 50}" for i, mrd in enumerate(mrd_values))
        path = create_temp_csv(content)
        try:
            profile = profile_csv(path)
            mrd_col = profile.column_profiles["MRD No."]
            assert mrd_col.semantic_role == "identifier"
            assert mrd_col.numeric_stats is None  # no misleading mean/std for medical record IDs
            assert mrd_col.identifier_stats is not None
            assert mrd_col.identifier_stats["distinct_count"] == 10
            assert mrd_col.identifier_stats["duplicate_identifier_count"] == 5
            assert mrd_col.identifier_stats["is_candidate_key"] is False
        finally:
            os.unlink(path)

    def test_numeric_measurement_with_many_distinct_values_remains_measure(self) -> None:
        """Verify a genuine numeric measurement (e.g. blood_pressure, revenue) remains a measure."""
        # 30 distinct float values
        content = "blood_pressure\n" + "\n".join(f"{110.0 + i * 1.5:.1f}" for i in range(30))
        path = create_temp_csv(content)
        try:
            profile = profile_csv(path)
            bp_col = profile.column_profiles["blood_pressure"]
            assert bp_col.semantic_role == "measure"
            assert bp_col.numeric_stats is not None
            assert bp_col.numeric_stats["mean"] > 110.0
            assert bp_col.numeric_stats["median"] > 110.0
        finally:
            os.unlink(path)


class TestConfigurableMissingValues:
    """Fix 3: Configurable missing-value tokens, blank vs sentinel tracking, and reconciliation."""

    def test_empty_and_nill_sentinels_classified_as_missing_when_configured(self) -> None:
        """Verify tokens EMPTY and NILL are classified as sentinel missing when configured."""
        content = """id,status,score
1,ACTIVE,100
2,EMPTY,NILL
3,PENDING,50
4,NILL,EMPTY
"""
        path = create_temp_csv(content)
        try:
            # Unconfigured: EMPTY and NILL are treated as text/invalid
            p_default = profile_csv(path)
            score_col_def = p_default.column_profiles["score"]
            assert score_col_def.value_counts.invalid_count == 2
            assert score_col_def.value_counts.missing_count == 0

            # Configured: EMPTY and NILL are missing sentinels
            cfg = ProfilingConfig(missing_tokens=("EMPTY", "NILL"))
            p_custom = profile_csv(path, config=cfg)
            score_col = p_custom.column_profiles["score"]
            vc = score_col.value_counts
            assert vc.missing_count == 2
            assert vc.sentinel_missing_count == 2
            assert vc.blank_missing_count == 0
            assert vc.valid_count == 2
            assert vc.invalid_count == 0
            assert vc.is_reconciled is True
            assert vc.source_cell_count == 4
        finally:
            os.unlink(path)

    def test_per_column_missing_tokens_override(self) -> None:
        """Verify per-column missing token override allows targeted sentinel policies."""
        # In column 'code', '-' means missing; in column 'notes', '-' is valid text
        content = """code,notes
10,-
-,Patient stable
20,Normal
"""
        path = create_temp_csv(content)
        try:
            cfg = ProfilingConfig(
                per_column_missing_tokens={"code": ("-",)},
            )
            profile = profile_csv(path, config=cfg)
            code_vc = profile.column_profiles["code"].value_counts
            notes_vc = profile.column_profiles["notes"].value_counts

            assert code_vc.missing_count == 1
            assert code_vc.sentinel_missing_count == 1

            assert notes_vc.missing_count == 0
            assert notes_vc.valid_count == 3
        finally:
            os.unlink(path)

    def test_case_insensitive_missing_tokens_preserves_raw_strings(self) -> None:
        """Verify case-insensitive matching recognizes 'null' and 'NULL' without altering raw cell."""
        content = """val
null
NULL
Null
15
"""
        path = create_temp_csv(content)
        try:
            cfg = ProfilingConfig(missing_tokens=("NULL",), case_sensitive_missing=False)
            profile = profile_csv(path, config=cfg)
            val_col = profile.column_profiles["val"]
            vc = val_col.value_counts
            assert vc.missing_count == 3
            assert vc.valid_count == 1
            assert vc.source_cell_count == 4
        finally:
            os.unlink(path)


class TestExecutedSourceAndProvenance:
    """Fix 4: Verify executed module location, package version, and report provenance."""

    def test_provenance_contains_module_path_and_version(self) -> None:
        """Verify provenance and overview contain package_version and source module_path."""
        content = "a,b\n1,2\n"
        path = create_temp_csv(content)
        try:
            profile = profile_csv(path)
            prov = profile.provenance
            assert "module_path" in prov
            assert "package_version" in prov
            assert prov["package_version"] == ai_csv_data_analyst.__version__
            assert "ai_csv_data_analyst" in prov["module_path"]

            # Verify in overview
            assert profile.overview.get("package_version") == ai_csv_data_analyst.__version__
            assert "ai_csv_data_analyst" in profile.overview.get("module_path", "")

            # Verify in to_dict() serialization
            d = profile.to_dict()
            assert "provenance" in d
            assert d["provenance"]["package_version"] == ai_csv_data_analyst.__version__
            assert d["overview"]["module_path"] == prov["module_path"]
        finally:
            os.unlink(path)

    def test_import_location_matches_source_tree(self) -> None:
        """Verify ai_csv_data_analyst module file resolves to existing repository file."""
        mod_path = Path(ai_csv_data_analyst.__file__).resolve()
        assert mod_path.exists()
        assert mod_path.is_file()
        assert "ai_csv_data_analyst" in mod_path.parts
