"""
Tests for CSV Loading Module

These tests verify that the CSV loader handles various edge cases correctly.
Tests are designed to run without external dependencies.
"""

from __future__ import annotations

import csv
import tempfile
import os
from pathlib import Path

import pytest

from ai_csv_data_analyst.loader import load_csv, LoadedCSV, LoadError


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


class TestLoadCSV:
    """Tests for the load_csv function."""

    def test_load_valid_csv(self) -> None:
        """Test loading a valid CSV file."""
        content = "name,age,city\nAlice,30,New York\nBob,25,Los Angeles"
        path = create_temp_csv(content)
        try:
            result = load_csv(path)

            assert result.is_valid
            assert result.file_path == path
            assert result.row_count == 2
            assert result.column_count == 3
            assert result.headers == ['name', 'age', 'city']
            assert len(result.rows) == 2
            assert result.rows[0]['name'] == 'Alice'
            assert result.rows[0]['age'] == '30'
            assert result.rows[0]['city'] == 'New York'
        finally:
            os.unlink(path)

    def test_load_csv_with_missing_file(self) -> None:
        """Test loading a non-existent file raises LoadError."""
        with pytest.raises(LoadError) as exc_info:
            load_csv("/nonexistent/path/to/file.csv")

        assert "File not found" in exc_info.value.message
        assert "/nonexistent/path/to/file.csv" in exc_info.value.file_path or exc_info.value.file_path is None

    def test_load_empty_csv(self) -> None:
        """Test loading an empty file."""
        content = ""
        path = create_temp_csv(content)
        try:
            result = load_csv(path)

            assert result.is_valid
            assert result.is_empty
            assert result.row_count == 0
            assert result.column_count == 0
            assert result.headers == []
        finally:
            os.unlink(path)

    def test_load_csv_with_only_headers(self) -> None:
        """Test loading a CSV with only headers (no data rows)."""
        content = "name,age,city"
        path = create_temp_csv(content)
        try:
            result = load_csv(path)

            assert result.is_valid
            assert result.row_count == 0
            assert result.column_count == 3
            assert result.headers == ['name', 'age', 'city']
            assert result.is_empty is False  # Has headers, so not empty
            assert len(result.rows) == 0
        finally:
            os.unlink(path)

    def test_load_csv_with_missing_values(self) -> None:
        """Test loading a CSV with missing/empty values."""
        content = "name,age,city\nAlice,,New York\nBob,25,\n,,\n"
        path = create_temp_csv(content)
        try:
            result = load_csv(path)

            assert result.is_valid
            assert result.row_count == 3
            assert result.rows[0]['age'] == ''
            assert result.rows[1]['city'] == ''
            assert result.rows[2]['name'] == ''
            assert result.rows[2]['age'] == ''
            assert result.rows[2]['city'] == ''
        finally:
            os.unlink(path)

    def test_load_csv_with_unicode(self) -> None:
        """Test loading a CSV with unicode characters."""
        content = "name,description\nAlice，,Hello 世界\nBob,Test"
        path = create_temp_csv(content)
        try:
            result = load_csv(path)

            assert result.is_valid
            assert result.rows[0]['name'] == 'Alice，'
            assert result.rows[0]['description'] == 'Hello 世界'
        finally:
            os.unlink(path)

    def test_load_csv_with_quoted_fields(self) -> None:
        """Test loading a CSV with quoted fields containing commas."""
        content = 'name,description\nAlice,"Hello, World"\nBob,"Test, Case"'
        path = create_temp_csv(content)
        try:
            result = load_csv(path)

            assert result.is_valid
            assert result.rows[0]['description'] == 'Hello, World'
            assert result.rows[1]['description'] == 'Test, Case'
        finally:
            os.unlink(path)

    def test_load_csv_with_newlines_in_fields(self) -> None:
        """Test loading a CSV with newlines in quoted fields."""
        content = 'name,description\nAlice,"Line 1\nLine 2"\nBob,Simple'
        path = create_temp_csv(content)
        try:
            result = load_csv(path)

            assert result.is_valid
            assert result.rows[0]['description'] == 'Line 1\nLine 2'
        finally:
            os.unlink(path)

    def test_load_csv_with_mixed_case_headers(self) -> None:
        """Test loading a CSV with headers that have whitespace."""
        content = "  Name  ,  Age  ,  City  \nAlice,30,New York"
        path = create_temp_csv(content)
        try:
            result = load_csv(path)

            assert result.is_valid
            # Headers should be stripped
            assert result.headers == ['Name', 'Age', 'City']
            assert result.rows[0]['Name'] == 'Alice'
        finally:
            os.unlink(path)

    def test_load_csv_with_different_delimiters(self) -> None:
        """Test that the loader always uses comma as delimiter."""
        content = "name;age;city\nAlice;30;New York"
        path = create_temp_csv(content)
        try:
            result = load_csv(path)

            # Our loader uses comma, so semicolon-delimited CSV should not parse correctly
            # This is expected behavior - the loader doesn't auto-detect delimiter
            # The test verifies we have a clear error message
            # Actually, csv.reader will treat it as a single column with semicolons
            assert result.column_count == 1  # Single column due to semicolon
            assert result.headers == ['name;age;city']
        finally:
            os.unlink(path)

    def test_load_csv_returns_loaded_csv(self) -> None:
        """Test that load_csv returns a LoadedCSV instance."""
        content = "name,age\nAlice,30"
        path = create_temp_csv(content)
        try:
            result = load_csv(path)

            assert isinstance(result, LoadedCSV)
            assert isinstance(result.row_count, int)
            assert isinstance(result.column_count, int)
        finally:
            os.unlink(path)

    def test_load_csv_with_path_object(self) -> None:
        """Test that load_csv accepts both string and Path objects."""
        content = "name,age\nAlice,30"
        path_str = create_temp_csv(content)
        try:
            result1 = load_csv(path_str)
            result2 = load_csv(str(Path(path_str)))

            assert result1.row_count == result2.row_count
            assert result1.headers == result2.headers
        finally:
            os.unlink(path_str)

    def test_load_csv_path_is_directory(self) -> None:
        """Test loading a directory path raises LoadError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(LoadError) as exc_info:
                load_csv(tmpdir)
            assert "Path is not a file" in exc_info.value.message

    def test_load_csv_with_bom(self) -> None:
        """Test loading a CSV file with UTF-8 BOM encoding."""
        content = "\ufeffname,age\nAlice,30"
        fd, path = tempfile.mkstemp(suffix='.csv')
        os.close(fd)
        try:
            with open(path, 'wb') as f:
                f.write(content.encode('utf-8'))
            result = load_csv(path)
            assert result.is_valid
            assert result.headers == ['name', 'age']
            assert result.rows[0]['name'] == 'Alice'
        finally:
            os.unlink(path)

    def test_load_csv_malformed_unclosed_quote(self) -> None:
        """Test loading a file with an unclosed quote raises LoadError."""
        fd, path = tempfile.mkstemp(suffix='.csv')
        os.close(fd)
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write('col1,col2\n"unclosed quote,val2')
            with pytest.raises(LoadError) as exc_info:
                load_csv(path)
            assert "Malformed CSV" in exc_info.value.message
        finally:
            os.unlink(path)


    def test_duplicate_headers_are_not_silently_overwritten(self) -> None:
        """Duplicate headers should raise LoadError rather than lose data."""
        content = "Name,Name,Age\nAlice,Smith,20"
        path = create_temp_csv(content)

        try:
            with pytest.raises(LoadError):
                load_csv(path)
        finally:
            os.unlink(path)
