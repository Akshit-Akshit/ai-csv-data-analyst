"""
Tests for Type Inference, Statistical Profiling, and Data Provenance

Verifies physical type vs semantic role distinction, confidence & evidence,
numeric IQR outliers, datetime metrics, duplicate distinction (excess vs group),
candidate keys, composite keys, provenance metadata, and source preservation.
"""

from __future__ import annotations

import tempfile
import os
from pathlib import Path

import pytest

from ai_csv_data_analyst.config import ProfilingConfig
from ai_csv_data_analyst.profiler import profile_csv
from ai_csv_data_analyst.types_and_roles import (
    PhysicalType,
    SemanticRole,
    infer_column_type_and_role,
)


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


class TestTypesAndProfiling:
    """Test suite for type inference, statistical profiling, and provenance."""

    def test_physical_type_vs_semantic_role_distinction(self) -> None:
        """Verify integer ID column is recognized as PhysicalType.INTEGER and SemanticRole.IDENTIFIER."""
        values = [str(i) for i in range(1001, 1101)]
        res_id = infer_column_type_and_role(values, column_name="customer_id")

        assert res_id.physical_type == PhysicalType.INTEGER
        assert res_id.semantic_role == SemanticRole.IDENTIFIER
        assert res_id.confidence > 0.8
        assert "cardinality_ratio" in res_id.evidence
        assert res_id.evidence["distinct_count"] == 100

        # Continuous numeric measure
        measure_values = [f"{i * 1.5:.2f}" for i in range(100)]
        res_meas = infer_column_type_and_role(measure_values, column_name="revenue")
        assert res_meas.physical_type == PhysicalType.FLOAT
        assert res_meas.semantic_role == SemanticRole.MEASURE

    def test_outlier_candidates_iqr(self) -> None:
        """Verify numeric profiling detects candidate outliers via IQR without modifying values."""
        # 20 typical values around 10-20, plus one extreme outlier 500
        typical = [str(10 + i) for i in range(20)]
        content = "val\n" + "\n".join(typical + ["500"])
        path = create_temp_csv(content)
        try:
            profile = profile_csv(path)
            val_col = profile.column_profiles["val"]
            assert val_col.outlier_stats is not None
            outliers = val_col.outlier_stats
            assert outliers["candidate_count"] == 1
            assert outliers["method"] == "iqr"
            assert outliers["upper_bound"] < 500
        finally:
            os.unlink(path)

    def test_datetime_profiling_and_coverage(self) -> None:
        """Verify datetime column profiling computes min/max timestamps and coverage span."""
        content = """timestamp,event
2024-01-01,login
2024-01-10,view
2024-01-31,logout
"""
        path = create_temp_csv(content)
        try:
            profile = profile_csv(path)
            ts_col = profile.column_profiles["timestamp"]
            assert ts_col.datetime_stats is not None
            dt_stats = ts_col.datetime_stats
            assert dt_stats["valid_timestamp_count"] == 3
            assert dt_stats["min_timestamp"] == "2024-01-01T00:00:00"
            assert dt_stats["max_timestamp"] == "2024-01-31T00:00:00"
            assert dt_stats["coverage_days"] == 30.0
        finally:
            os.unlink(path)

    def test_duplicate_row_metrics_distinguish_excess_vs_groups(self) -> None:
        """
        Verify distinct calculation of excess duplicate rows vs rows in duplicate groups.
        If row A appears 3 times and row B appears 2 times and row C appears 1 time:
        - Excess duplicate rows = (3 - 1) + (2 - 1) = 3
        - Rows in duplicate groups = 3 + 2 = 5
        """
        content = """x,y
A,1
A,1
A,1
B,2
B,2
C,3
"""
        path = create_temp_csv(content)
        try:
            profile = profile_csv(path)
            assert profile.row_count == 6
            assert profile.overview["excess_duplicate_rows"] == 3
            assert profile.overview["rows_in_duplicate_groups"] == 5
            assert profile.overview["duplicate_rows"] == 3  # backward compatible key
            assert profile.summary["duplicate_row_count"] == 3
            assert profile.summary["rows_in_duplicate_groups"] == 5
            assert profile.summary["unique_rows"] == 3  # 6 total - 3 excess = 3
        finally:
            os.unlink(path)

    def test_relational_candidate_keys_and_composite_keys(self) -> None:
        """Verify single candidate keys, composite keys, and constant columns are discovered."""
        content = """user_id,dept_id,role_code,company_name
1,D1,MGR,AcmeCorp
2,D1,DEV,AcmeCorp
3,D2,DEV,AcmeCorp
4,D2,QA,AcmeCorp
"""
        path = create_temp_csv(content)
        try:
            profile = profile_csv(path)
            rel = profile.relational_analysis
            assert "user_id" in rel["candidate_single_keys"]
            assert "dept_id" not in rel["candidate_single_keys"]
            assert "company_name" in rel["constant_columns"]

            # dept_id + role_code is unique (D1-MGR, D1-DEV, D2-DEV, D2-QA)
            comp_pairs = [set(p) for p in rel["candidate_composite_keys"]]
            assert {"dept_id", "role_code"} in comp_pairs
        finally:
            os.unlink(path)

    def test_source_input_data_is_never_modified(self) -> None:
        """Verify profiling never mutates or overwrites source file bytes."""
        original_bytes = b"colA,colB\n12,50\n34,60\n"
        fd, path = tempfile.mkstemp(suffix=".csv")
        try:
            os.write(fd, original_bytes)
            os.close(fd)

            _ = profile_csv(path)

            with open(path, "rb") as f:
                read_bytes = f.read()
            assert read_bytes == original_bytes, "Input file was mutated!"
        finally:
            os.unlink(path)

    def test_provenance_and_audit_metadata_in_profile(self) -> None:
        """Verify provenance metadata includes schema version, file fingerprint, and config."""
        content = "a,b\n1,2\n"
        path = create_temp_csv(content)
        try:
            profile = profile_csv(path)
            prov = profile.provenance
            assert prov["schema_version"] == "1.0.0"
            assert prov["metrics_mode"] == "exact"
            assert "file_fingerprint" in prov
            assert prov["file_fingerprint"] != ""
            assert "generated_at" in prov
            assert "effective_config" in prov

            # Verify in to_dict() serialization
            d = profile.to_dict()
            assert "provenance" in d
            assert "structural_diagnostics" in d
            assert "relational_analysis" in d
        finally:
            os.unlink(path)

