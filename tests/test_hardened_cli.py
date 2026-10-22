"""
Tests for Enhanced CLI Options

Verifies that new CLI flags (--strict, --delimiter, --encoding, --missing-tokens)
behave accurately and retain backward compatibility.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    """Execute CLI in subprocess with PYTHONPATH set."""
    env = os.environ.copy()
    src_dir = str(Path(__file__).parent.parent / "src")
    env["PYTHONPATH"] = f"{src_dir}:{env.get('PYTHONPATH', '')}"

    return subprocess.run(
        [sys.executable, "-m", "ai_csv_data_analyst", *args],
        capture_output=True,
        text=True,
        timeout=15,
        env=env,
    )


class TestHardenedCLI:
    """Test suite for CLI enhancements."""

    def test_cli_strict_flag_rejects_malformed_row(self, tmp_path: Path) -> None:
        """Verify CLI with --strict outputs error for surplus fields."""
        csv_file = tmp_path / "bad.csv"
        csv_file.write_text("a,b\n1,2\n3,4,extra\n", encoding="utf-8")

        res = run_cli(str(csv_file), "--strict")
        assert "Error:" in res.stdout
        assert "surplus" in res.stdout.lower()

    def test_cli_custom_delimiter(self, tmp_path: Path) -> None:
        """Verify CLI with --delimiter parses non-comma files."""
        csv_file = tmp_path / "pipe.csv"
        csv_file.write_text("col1|col2\nval1|val2\n", encoding="utf-8")

        res = run_cli(str(csv_file), "--delimiter", "|", "--json")
        assert res.returncode == 0
        data = json.loads(res.stdout)
        assert data["column_count"] == 2
        assert data["headers"] == ["col1", "col2"]

    def test_cli_missing_tokens_flag(self, tmp_path: Path) -> None:
        """Verify CLI with --missing-tokens classifies tokens as missing."""
        csv_file = tmp_path / "tokens.csv"
        csv_file.write_text("id,val\n1,10\n2,NA\n3,NULL\n", encoding="utf-8")

        res = run_cli(str(csv_file), "--missing-tokens", "NA,NULL", "--json")
        assert res.returncode == 0
        data = json.loads(res.stdout)
        assert data["columns"]["val"]["missing_count"] == 2

    def test_cli_encoding_flag(self, tmp_path: Path) -> None:
        """Verify CLI with explicit --encoding works on latin-1 encoded files."""
        csv_file = tmp_path / "latin.csv"
        csv_file.write_bytes("nom,ville\nRen\xe9,Gen\xe8ve\n".encode("latin-1"))

        res = run_cli(str(csv_file), "--encoding", "latin-1", "--validate")
        assert res.returncode == 0
        assert "File validated" in res.stdout
        assert "Rows: 1" in res.stdout

