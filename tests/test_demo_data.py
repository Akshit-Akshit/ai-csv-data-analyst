"""
Tests for Demo Data Verification

These tests verify that the profiler works correctly with the demo CSV files
in the demo_data directory. Tests are designed to dynamically discover and profile
available demo files without hardcoding file paths or schemas.
"""

from __future__ import annotations

import os
import json
from pathlib import Path
from typing import Any

import pytest

from ai_csv_data_analyst.profiler import profile_csv, DatasetProfile


def find_demo_csv_files() -> list[Path]:
    """Find all CSV files in demo_data, recursively searching subdirectories."""
    demo_dir = Path(__file__).parent.parent / "demo_data"
    if not demo_dir.exists():
        return []
    return sorted(list(demo_dir.rglob("*.csv")))


class TestDemoData:
    """Tests for demo data profiling."""

    def test_demo_data_file_exists(self) -> None:
        """Verify that at least one demo CSV file exists and is accessible."""
        csv_files = find_demo_csv_files()
        assert len(csv_files) > 0, "No demo CSV files found in demo_data/"
        for f in csv_files:
            assert f.exists()
            assert f.is_file()

    def test_profile_amazon_csv(self) -> None:
        """Test profiling the Amazon CSV demo file or primary demo dataset."""
        csv_files = find_demo_csv_files()
        assert len(csv_files) > 0, "Demo CSV file not found"
        
        # Pick the amazon file or first available demo file
        target_csv = next((f for f in csv_files if "amazon" in f.name.lower()), csv_files[0])
        assert target_csv.exists(), f"Demo file not found: {target_csv}"
        
        profile = profile_csv(str(target_csv))
        
        # Verify basic structure
        assert profile is not None
        assert profile.file_path is not None
        assert profile.row_count > 0
        assert profile.column_count > 0
        assert profile.headers is not None
        assert len(profile.headers) == profile.column_count
        
        # Verify overview exists
        assert 'columns' in profile.overview
        assert 'rows' in profile.overview
        assert profile.overview['rows'] == profile.row_count
        assert profile.overview['columns'] == profile.column_count
        
        # Verify column profiles exist
        assert len(profile.column_profiles) == profile.column_count
        
        # Verify summary exists
        assert profile.summary is not None
        assert profile.summary['total_rows'] == profile.row_count
        assert profile.summary['total_columns'] == profile.column_count
        
        # Verify quality issues list exists
        assert isinstance(profile.quality_issues, list)
        
        # Check that we have both numeric and non-numeric columns
        column_types = {
            name: stats.inferred_type
            for name, stats in profile.column_profiles.items()
        }
        
        numeric_columns = [
            name for name, typ in column_types.items()
            if typ == 'numeric'
        ]
        text_or_cat_columns = [
            name for name, typ in column_types.items()
            if typ in ('text', 'categorical', 'url', 'mixed')
        ]
        
        # Real-world dataset should have both
        assert len(numeric_columns) > 0
        assert len(text_or_cat_columns) > 0
        
        # Verify serialization
        profile_dict = profile.to_dict()
        assert isinstance(profile_dict, dict)
        assert profile_dict['row_count'] == profile.row_count
        assert profile_dict['column_count'] == profile.column_count


def test_demo_data_structure() -> None:
    """
    Test that all discovered demo data files have valid profile structure.
    """
    csv_files = find_demo_csv_files()
    if not csv_files:
        pytest.skip("No demo CSV files available")
    
    for csv_file in csv_files:
        profile = profile_csv(str(csv_file))
        assert profile.column_count > 0
        assert profile.row_count >= 0
        
        for col_name, col_stats in profile.column_profiles.items():
            assert col_stats.name == col_name
            assert col_stats.inferred_type in ('numeric', 'categorical', 'text', 'url', 'mixed', 'unknown')
            assert col_stats.missing_count >= 0
            assert col_stats.valid_count >= 0
            assert col_stats.distinct_count >= 0
            assert 0.0 <= col_stats.missing_percentage <= 100.0


def test_demo_data_available() -> None:
    """Test that demo data is available in the repository."""
    csv_files = find_demo_csv_files()
    assert len(csv_files) > 0, "Demo data files should be present in demo_data/"
