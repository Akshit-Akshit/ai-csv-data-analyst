"""
Tests for CSV Profiling Engine

These tests verify that the CSV profiler generates accurate and complete profiles.
Tests cover various edge cases including empty files, missing values, duplicates,
and high-cardinality columns.
"""

from __future__ import annotations

import csv
import tempfile
import os
import statistics

import pytest

from ai_csv_data_analyst.profiler import profile_csv, DatasetProfile, ColumnStats


def create_temp_csv(content: str) -> str:
    """Create a temporary CSV file with the given content."""
    fd, path = tempfile.mkstemp(suffix='.csv')
    try:
        os.write(fd, content.encode('utf-8'))
        os.close(fd)
        return path
    except:
        os.close(fd)
        os.unlink(path)
        raise


class TestProfileCSV:
    """Tests for the profile_csv function."""

    def test_profile_valid_csv(self) -> None:
        """Test profiling a valid CSV with numeric and categorical columns."""
        content = """name,age,city,salary,is_active
Alice,30,New York,50000,true
Bob,25,Los Angeles,60000,false
Charlie,35,Chicago,70000,true
Diana,28,New York,55000,true
Eve,32,Seattle,65000,false
"""
        path = create_temp_csv(content)
        try:
            profile = profile_csv(path)
            
            # Check overview
            assert profile.row_count == 5
            assert profile.column_count == 5
            assert profile.overview['rows'] == 5
            assert profile.overview['columns'] == 5
            
            # Check column types
            assert profile.column_profiles['name'].inferred_type in ('categorical', 'text')
            assert profile.column_profiles['age'].inferred_type == 'numeric'
            assert profile.column_profiles['city'].inferred_type in ('categorical', 'text')
            assert profile.column_profiles['salary'].inferred_type == 'numeric'
            assert profile.column_profiles['is_active'].inferred_type in ('categorical', 'text')
            
            # Check age column statistics
            age_profile = profile.column_profiles['age']
            assert age_profile.inferred_type == 'numeric'
            assert age_profile.numeric_stats is not None
            assert age_profile.numeric_stats['count'] == 5
            assert age_profile.numeric_stats['min'] == 25
            assert age_profile.numeric_stats['max'] == 35
            
            # Check missing values
            assert profile.column_profiles['name'].missing_count == 0
            assert profile.column_profiles['age'].missing_count == 0
            
        finally:
            os.unlink(path)

    def test_profile_csv_with_missing_values(self) -> None:
        """Test profiling a CSV with missing values."""
        content = """name,age,city,salary
Alice,,New York,50000
Bob,25,,60000
Charlie,35,Chicago,
Diana,28,New York,55000
"""
        path = create_temp_csv(content)
        try:
            profile = profile_csv(path)
            
            assert profile.row_count == 4
            
            # Check missing value counts
            assert profile.column_profiles['name'].missing_count == 0
            assert profile.column_profiles['age'].missing_count == 1
            assert profile.column_profiles['city'].missing_count == 1
            assert profile.column_profiles['salary'].missing_count == 1
            
            # Check missing percentages
            assert profile.column_profiles['age'].missing_percentage > 0
            assert profile.column_profiles['city'].missing_percentage > 0
            assert profile.column_profiles['salary'].missing_percentage > 0
            
            # Verify missing percentage is correct
            expected_age_missing = 1 / 4 * 100
            assert abs(profile.column_profiles['age'].missing_percentage - expected_age_missing) < 0.01
            
        finally:
            os.unlink(path)

    def test_profile_csv_with_duplicate_rows(self) -> None:
        """Test profiling a CSV with duplicate rows."""
        content = """name,age,city
Alice,30,New York
Bob,25,Los Angeles
Alice,30,New York
Charlie,35,Chicago
Alice,30,New York
"""
        path = create_temp_csv(content)
        try:
            profile = profile_csv(path)
            
            assert profile.row_count == 5
            # Should detect 2 duplicates (Alice,30,New York appears 3 times)
            assert profile.overview['duplicate_rows'] == 2
            assert profile.summary['duplicate_row_count'] == 2
            assert profile.summary['unique_rows'] == 3
            
        finally:
            os.unlink(path)

    def test_profile_csv_with_empty_file(self) -> None:
        """Test profiling an empty CSV file."""
        content = ""
        path = create_temp_csv(content)
        try:
            profile = profile_csv(path)
            
            assert profile.row_count == 0
            assert profile.column_count == 0
            assert profile.overview['rows'] == 0
            assert profile.overview['columns'] == 0
            
        finally:
            os.unlink(path)

    def test_profile_csv_with_only_headers(self) -> None:
        """Test profiling a CSV with only headers."""
        content = "name,age,city"
        path = create_temp_csv(content)
        try:
            profile = profile_csv(path)
            
            assert profile.row_count == 0
            assert profile.column_count == 3
            assert profile.overview['rows'] == 0
            assert profile.overview['columns'] == 3
            assert profile.headers == ['name', 'age', 'city']
            
        finally:
            os.unlink(path)

    def test_profile_csv_with_numeric_statistics(self) -> None:
        """Test that numeric statistics are calculated correctly."""
        content = """name,value
A,10
B,20
C,30
D,40
E,50
"""
        path = create_temp_csv(content)
        try:
            profile = profile_csv(path)
            
            value_profile = profile.column_profiles['value']
            assert value_profile.inferred_type == 'numeric'
            assert value_profile.numeric_stats is not None
            
            stats = value_profile.numeric_stats
            assert stats['count'] == 5
            assert stats['mean'] == 30.0
            assert stats['median'] == 30.0
            assert stats['min'] == 10
            assert stats['max'] == 50
            assert stats['std_dev'] == statistics.stdev([10, 20, 30, 40, 50])
            
            # Check quartiles
            assert stats['q1'] == 20  # 25th percentile
            assert stats['q3'] == 40  # 75th percentile
            
        finally:
            os.unlink(path)

    def test_profile_csv_with_text_column(self) -> None:
        """Test that text columns are profiled correctly."""
        content = """name,description
Alice,Hello
Bob,World
Charlie,Test
Diana,Example
Eve,Sample
"""
        path = create_temp_csv(content)
        try:
            profile = profile_csv(path)
            
            name_profile = profile.column_profiles['name']
            assert name_profile.inferred_type in ('categorical', 'text')
            assert name_profile.numeric_stats is None
            assert name_profile.text_stats is not None
            
            text_stats = name_profile.text_stats
            assert text_stats['distinct_count'] == 5
            
            # Check most frequent values
            assert len(text_stats['most_frequent_values']) == 5
            
        finally:
            os.unlink(path)

    def test_profile_csv_with_empty_column(self) -> None:
        """Test profiling a column where some values are missing."""
        content = """name,value
Alice,10
Bob,20
Charlie,
Diana,
Eve,
"""
        path = create_temp_csv(content)
        try:
            profile = profile_csv(path)
            
            value_profile = profile.column_profiles['value']
            assert value_profile.missing_count == 3
            assert value_profile.missing_percentage == 60.0  # 3/5 * 100
            assert value_profile.valid_count == 2
            
            # Column is not marked as empty since it has some valid values
            assert value_profile.is_empty is False
            
            # Numeric stats should be None or calculated from valid values only
            # Actually, since it has some valid values, it should be detected as numeric
            # Let's check the detected type
            assert value_profile.inferred_type == 'mixed' or value_profile.inferred_type == 'numeric'
            
        finally:
            os.unlink(path)

    def test_profile_csv_with_high_cardinality_column(self) -> None:
        """Test profiling a column with high cardinality (>20% distinct values)."""
        content = """id,value
1,A
2,B
3,C
4,D
5,E
6,F
7,G
8,H
9,I
10,J
"""
        path = create_temp_csv(content)
        try:
            profile = profile_csv(path)
            
            value_profile = profile.column_profiles['value']
            # 10 distinct values out of 10 rows = 100% > 20%
            assert value_profile.has_high_cardinality is True
            assert value_profile.distinct_count == 10
            
        finally:
            os.unlink(path)

    def test_profile_csv_with_currency_symbols(self) -> None:
        """Test that currency symbols are handled correctly."""
        content = """product,price
Widget,₹100
Gadget,₹200
Gizmo,₹150
"""
        path = create_temp_csv(content)
        try:
            profile = profile_csv(path)
            
            price_profile = profile.column_profiles['price']
            assert price_profile.inferred_type == 'numeric'
            assert price_profile.numeric_stats is not None
            
            stats = price_profile.numeric_stats
            assert stats['min'] == 100.0
            assert stats['max'] == 200.0
            assert stats['mean'] == 150.0
            
        finally:
            os.unlink(path)

    def test_profile_csv_with_commas_in_numbers(self) -> None:
        """Test that numbers with commas are handled correctly."""
        content = """product,price
Widget,1,000
Gadget,2,000
Gizmo,1,500
"""
        path = create_temp_csv(content)
        try:
            profile = profile_csv(path)
            
            price_profile = profile.column_profiles['price']
            # Should be detected as numeric with comma handling
            assert price_profile.inferred_type == 'numeric'
            assert price_profile.numeric_stats is not None
            
            stats = price_profile.numeric_stats
            # Values should be parsed as 1000, 2000, 1500
            assert stats['min'] == 1000.0
            assert stats['max'] == 2000.0
            
        finally:
            os.unlink(path)

    def test_profile_csv_to_dict(self) -> None:
        """Test that profile.to_dict() returns a valid dictionary."""
        content = """name,value
Alice,10
Bob,20
"""
        path = create_temp_csv(content)
        try:
            profile = profile_csv(path)
            result = profile.to_dict()
            
            assert isinstance(result, dict)
            assert 'file_path' in result
            assert 'row_count' in result
            assert 'column_count' in result
            assert 'headers' in result
            assert 'columns' in result
            assert 'summary' in result
            assert 'quality_issues' in result
            
            # Check columns structure
            for col_name, col_data in result['columns'].items():
                assert 'inferred_type' in col_data
                assert 'missing_count' in col_data
                assert 'numeric_stats' in col_data
                assert 'text_stats' in col_data
            
        finally:
            os.unlink(path)

    def test_profile_csv_empty_numeric_column(self) -> None:
        """Test profiling a column with only missing values."""
        content = """name,value
Alice,
Bob,
Charlie,
"""
        path = create_temp_csv(content)
        try:
            profile = profile_csv(path)
            
            value_profile = profile.column_profiles['value']
            assert value_profile.missing_count == 3
            assert value_profile.missing_percentage == 100.0
            assert value_profile.valid_count == 0
            assert value_profile.distinct_count == 0
            
        finally:
            os.unlink(path)

    def test_profile_csv_deterministic_ordering(self) -> None:
        """Test that results are deterministic (sorted operations)."""
        content = """z_col,a_col,m_col
Z,1,10
A,2,20
M,3,30
Z,4,40
"""
        path = create_temp_csv(content)
        try:
            profile1 = profile_csv(path)
            profile2 = profile_csv(path)
            
            # Results should be identical
            assert profile1.overview == profile2.overview
            assert profile1.summary == profile2.summary
            assert sorted(profile1.column_profiles.keys()) == sorted(profile2.column_profiles.keys())
            
            # Column profiles should have same structure
            for col_name in profile1.column_profiles.keys():
                assert profile1.column_profiles[col_name].inferred_type == profile2.column_profiles[col_name].inferred_type
            
        finally:
            os.unlink(path)

    def test_profile_csv_with_missing_file_path(self) -> None:
        """Test profiling a non-existent file."""
        from ai_csv_data_analyst.loader import LoadError
        with pytest.raises(LoadError):
            profile_csv("/nonexistent/file.csv")

    def test_profile_csv_with_mixed_invalid_numeric_values(self) -> None:
        """Test profiling a column containing a mix of valid numbers, invalid text, and nulls."""
        content = """id,score
1,100
2,N/A
3,50
4,corrupt_data
5,75
6,
"""
        path = create_temp_csv(content)
        try:
            profile = profile_csv(path)
            score_col = profile.column_profiles['score']
            assert score_col.inferred_type in ('numeric', 'mixed')
            assert score_col.numeric_stats is not None
            assert score_col.numeric_stats['count'] == 3
            assert score_col.numeric_stats['min'] == 50.0
            assert score_col.numeric_stats['max'] == 100.0
            assert score_col.numeric_stats['mean'] == 75.0
            assert score_col.missing_count == 1
        finally:
            os.unlink(path)

    def test_profile_csv_with_negative_and_decimal_numbers(self) -> None:
        """Test profiling negative, decimal, and zero numeric values."""
        content = """measurement
-10.5
0.0
20.5
30.0
"""
        path = create_temp_csv(content)
        try:
            profile = profile_csv(path)
            meas_col = profile.column_profiles['measurement']
            assert meas_col.inferred_type == 'numeric'
            assert meas_col.numeric_stats is not None
            assert meas_col.numeric_stats['min'] == -10.5
            assert meas_col.numeric_stats['max'] == 30.0
            assert meas_col.numeric_stats['mean'] == 10.0
            assert meas_col.numeric_stats['median'] == 10.25
        finally:
            os.unlink(path)

    def test_profile_csv_frequency_limit_top_10(self) -> None:
        """Test that frequency statistics are capped at top 10 values."""
        # Create 15 distinct categories
        rows = [f"item_{i % 15}" for i in range(100)]
        content = "category\n" + "\n".join(rows)
        path = create_temp_csv(content)
        try:
            profile = profile_csv(path)
            cat_col = profile.column_profiles['category']
            assert cat_col.distinct_count == 15
            assert len(cat_col.most_frequent_values) <= 10
            # Test in to_dict() as well
            d = profile.to_dict()
            assert len(d['columns']['category']['most_frequent_values']) <= 10
        finally:
            os.unlink(path)

    def test_profile_csv_with_utf8_bom(self) -> None:
        """Test that CSV with UTF-8 BOM headers is profiled cleanly without BOM artifact."""
        content = "\ufeffid,amount\n1,10\n2,20"
        fd, path = tempfile.mkstemp(suffix='.csv')
        os.close(fd)
        try:
            with open(path, 'wb') as f:
                f.write(content.encode('utf-8'))
            profile = profile_csv(path)
            assert 'id' in profile.column_profiles
            assert '\ufeffid' not in profile.column_profiles
            assert profile.column_profiles['amount'].numeric_stats['count'] == 2
        finally:
            os.unlink(path)
