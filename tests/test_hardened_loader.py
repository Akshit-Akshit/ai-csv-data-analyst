"""
Tests for Hardened CSV Loader

Verifies structural integrity, strict vs tolerant modes, encoding fallbacks,
header resolution (duplicate, blank, collision), delimiter detection, and resource limits.
"""

from __future__ import annotations

import tempfile
import os
from pathlib import Path

import pytest

from ai_csv_data_analyst.config import ProfilingConfig
from ai_csv_data_analyst.diagnostics import StructuralAnomalyType
from ai_csv_data_analyst.loader import LoadError, LoadedCSV, load_csv


def create_temp_file(content: bytes, suffix: str = ".csv") -> str:
    """Create a temporary binary file with exact byte content."""
    fd, path = tempfile.mkstemp(suffix=suffix)
    try:
        os.write(fd, content)
        os.close(fd)
        return path
    except Exception:
        os.close(fd)
        os.unlink(path)
        raise


class TestHardenedLoader:
    """Test suite for hardened loader capabilities."""

    def test_differentiate_zero_byte_and_whitespace_and_header_only(self) -> None:
        """Verify zero-byte, whitespace-only, and header-only files produce distinguishable results."""
        # 0-byte file
        p0 = create_temp_file(b"")
        try:
            res0 = load_csv(p0)
            assert res0.is_empty is True
            assert res0.row_count == 0
            assert res0.column_count == 0
            assert res0.file_type == "empty_file"
        finally:
            os.unlink(p0)

        # Whitespace-only file
        p_ws = create_temp_file(b"   \n\t  \r\n  ")
        try:
            res_ws = load_csv(p_ws)
            assert res_ws.is_empty is True
            assert res_ws.row_count == 0
            assert res_ws.column_count == 0
            assert res_ws.file_type == "whitespace_only"
        finally:
            os.unlink(p_ws)

        # Header-only file
        p_hdr = create_temp_file(b"col1,col2,col3\n")
        try:
            res_hdr = load_csv(p_hdr)
            assert res_hdr.is_empty is False
            assert res_hdr.row_count == 0
            assert res_hdr.column_count == 3
            assert res_hdr.headers == ["col1", "col2", "col3"]
            assert res_hdr.file_type == "header_only"
        finally:
            os.unlink(p_hdr)

    def test_duplicate_headers_do_not_overwrite_values(self) -> None:
        """Verify duplicate headers are disambiguated and no column data is lost in records."""
        content = b"id,val,id\n1,first,2\n3,second,4\n"
        path = create_temp_file(content)
        try:
            res = load_csv(path)
            assert res.is_valid
            assert res.column_count == 3
            assert res.column_identifiers == ["id", "val", "id_2"]
            assert res.rows[0]["id"] == "1"
            assert res.rows[0]["val"] == "first"
            assert res.rows[0]["id_2"] == "2"

            # Check diagnostic was logged
            dup_diags = [
                d for d in res.structural_diagnostics
                if d.anomaly_type == StructuralAnomalyType.DUPLICATE_HEADER
            ]
            assert len(dup_diags) == 1
            assert "id_2" in dup_diags[0].message
        finally:
            os.unlink(path)

    def test_blank_and_colliding_headers(self) -> None:
        """Verify blank headers get stable identifiers and collisions are diagnosed."""
        content = b" ,col2, Col2 \n10,20,30\n"
        path = create_temp_file(content)
        try:
            res = load_csv(path)
            assert res.is_valid
            assert res.column_identifiers[0] == "unnamed_0"
            assert res.rows[0]["unnamed_0"] == "10"

            types = {d.anomaly_type for d in res.structural_diagnostics}
            assert StructuralAnomalyType.BLANK_HEADER in types
            assert StructuralAnomalyType.HEADER_COLLISION in types
        finally:
            os.unlink(path)

    def test_strict_mode_rejects_surplus_fields(self) -> None:
        """Verify strict mode raises LoadError for rows with surplus fields."""
        content = b"a,b\n1,2\n3,4,extra\n"
        path = create_temp_file(content)
        try:
            with pytest.raises(LoadError) as exc_info:
                load_csv(path, strict_mode=True)
            assert "surplus" in exc_info.value.message.lower()
            assert exc_info.value.line_number == 3
        finally:
            os.unlink(path)

    def test_tolerant_mode_preserves_surplus_fields_with_diagnostics(self) -> None:
        """Verify tolerant mode retains surplus field diagnostic and unmerged fields."""
        content = b"a,b\n1,2\n3,4,extra\n"
        path = create_temp_file(content)
        try:
            res = load_csv(path, strict_mode=False)
            assert res.is_valid
            assert res.row_count == 2
            surplus_diags = [
                d for d in res.structural_diagnostics
                if d.anomaly_type == StructuralAnomalyType.SURPLUS_FIELDS
            ]
            assert len(surplus_diags) == 1
            assert surplus_diags[0].line_number == 3
            # Check raw unmerged records preserved
            assert res.raw_records[1] == ["3", "4", "extra"]
        finally:
            os.unlink(path)

    def test_strict_mode_rejects_deficit_fields(self) -> None:
        """Verify strict mode raises LoadError for rows with deficit fields."""
        content = b"a,b,c\n1,2,3\n4,5\n"
        path = create_temp_file(content)
        try:
            with pytest.raises(LoadError) as exc_info:
                load_csv(path, strict_mode=True)
            assert "missing" in exc_info.value.message.lower()
            assert exc_info.value.line_number == 3
        finally:
            os.unlink(path)

    def test_tolerant_mode_pads_deficit_fields_with_diagnostics(self) -> None:
        """Verify tolerant mode pads deficit fields with empty string and logs diagnostic."""
        content = b"a,b,c\n1,2,3\n4,5\n"
        path = create_temp_file(content)
        try:
            res = load_csv(path, strict_mode=False)
            assert res.is_valid
            assert res.rows[1]["c"] == ""
            deficit_diags = [
                d for d in res.structural_diagnostics
                if d.anomaly_type == StructuralAnomalyType.DEFICIT_FIELDS
            ]
            assert len(deficit_diags) == 1
            assert deficit_diags[0].line_number == 3
        finally:
            os.unlink(path)

    def test_encoding_fallback_to_latin1(self) -> None:
        """Verify non-UTF8 files (e.g. latin-1 with accented characters) fall back cleanly."""
        # \xe9 is é in ISO-8859-1 / Latin-1, invalid in UTF-8
        content = "name,city\nRen\xe9,Montr\xe9al\n".encode("latin-1")
        path = create_temp_file(content)
        try:
            res = load_csv(path)
            assert res.is_valid
            assert res.rows[0]["name"] == "René"
            assert res.rows[0]["city"] == "Montréal"
            assert res.encoding_info["selected_encoding"] in ("latin-1", "iso-8859-1", "cp1252")
        finally:
            os.unlink(path)

    def test_delimiter_auto_detection(self) -> None:
        """Verify sniffing detects semicolon, tab, and pipe delimiters when auto-detection is enabled."""
        # Semicolon
        p_semi = create_temp_file(b"x;y;z\n10;20;30\n40;50;60\n")
        try:
            res = load_csv(p_semi, delimiter="auto")
            assert res.delimiter == ";"
            assert res.column_count == 3
            assert res.headers == ["x", "y", "z"]
        finally:
            os.unlink(p_semi)

        # Tab
        p_tab = create_temp_file(b"x\ty\tz\n10\t20\t30\n")
        try:
            res = load_csv(p_tab, delimiter="auto")
            assert res.delimiter == "\t"
            assert res.column_count == 3
        finally:
            os.unlink(p_tab)

        # Pipe
        p_pipe = create_temp_file(b"x|y|z\n10|20|30\n")
        try:
            res = load_csv(p_pipe, delimiter="auto")
            assert res.delimiter == "|"
            assert res.column_count == 3
        finally:
            os.unlink(p_pipe)

    def test_max_file_size_limit_enforced(self) -> None:
        """Verify max_file_size_bytes raises LoadError before loading."""
        content = b"a,b\n1,2\n" * 100
        path = create_temp_file(content)
        try:
            cfg = ProfilingConfig(max_file_size_bytes=50)
            with pytest.raises(LoadError) as exc_info:
                load_csv(path, config=cfg)
            assert "exceeds configured maximum limit" in exc_info.value.message
        finally:
            os.unlink(path)

    def test_max_rows_truncates_traceably(self) -> None:
        """Verify max_rows limits records loaded and adds diagnostic."""
        content = b"num\n" + b"".join(f"{i}\n".encode() for i in range(100))
        path = create_temp_file(content)
        try:
            cfg = ProfilingConfig(max_rows=15)
            res = load_csv(path, config=cfg)
            assert res.row_count == 15
            types = {d.anomaly_type for d in res.structural_diagnostics}
            assert StructuralAnomalyType.RESOURCE_LIMIT_EXCEEDED in types
        finally:
            os.unlink(path)

