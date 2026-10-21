"""Tests for the AI CSV Data Analyst application.

These tests verify the application entry point behaves as expected.
Tests are designed to run without internet access, LLMs, or datasets.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import pytest


def test_app_runs_as_module() -> None:
    """Test that the application can be launched via python -m ai_csv_data_analyst."""
    env = os.environ.copy()
    src_dir = str(Path(__file__).parent.parent / "src")
    if "PYTHONPATH" in env:
        env["PYTHONPATH"] = f"{src_dir}:{env['PYTHONPATH']}"
    else:
        env["PYTHONPATH"] = src_dir

    result = subprocess.run(
        [sys.executable, "-m", "ai_csv_data_analyst"],
        capture_output=True,
        text=True,
        timeout=10,
        env=env
    )
    
    assert result.returncode == 0
    assert "AI CSV Data Analyst" in result.stdout
    assert "initialized" in result.stdout.lower()


def test_app_importable() -> None:
    """Test that the ai_csv_data_analyst package is importable."""
    import ai_csv_data_analyst
    
    assert hasattr(ai_csv_data_analyst, "__version__")
    assert ai_csv_data_analyst.__version__ == "0.1.0"


def test_main_function_exists() -> None:
    """Test that the main() function exists and is callable."""
    from ai_csv_data_analyst.app import main
    
    assert callable(main)
    
    # Call main directly and check output
    main()
    # Note: Direct import test doesn't capture stdout without special setup
    # The subprocess test above handles the output verification


def test_cli_profile_csv_text_output(tmp_path: Path) -> None:
    """Test CLI profiling produces formatted text output."""
    csv_file = tmp_path / "test.csv"
    csv_file.write_text("name,age\nAlice,30\nBob,25\n", encoding="utf-8")

    env = os.environ.copy()
    src_dir = str(Path(__file__).parent.parent / "src")
    env["PYTHONPATH"] = f"{src_dir}:{env.get('PYTHONPATH', '')}"

    result = subprocess.run(
        [sys.executable, "-m", "ai_csv_data_analyst", str(csv_file)],
        capture_output=True,
        text=True,
        timeout=10,
        env=env
    )
    assert result.returncode == 0
    assert "CSV Profile:" in result.stdout
    assert "OVERVIEW" in result.stdout
    assert "SUMMARY" in result.stdout
    assert "COLUMN PROFILES" in result.stdout


def test_cli_profile_csv_json_output(tmp_path: Path) -> None:
    """Test CLI profiling with --json produces valid JSON output."""
    import json
    csv_file = tmp_path / "test.csv"
    csv_file.write_text("name,score\nAlice,95\nBob,88\n", encoding="utf-8")

    env = os.environ.copy()
    src_dir = str(Path(__file__).parent.parent / "src")
    env["PYTHONPATH"] = f"{src_dir}:{env.get('PYTHONPATH', '')}"

    result = subprocess.run(
        [sys.executable, "-m", "ai_csv_data_analyst", str(csv_file), "--json"],
        capture_output=True,
        text=True,
        timeout=10,
        env=env
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["row_count"] == 2
    assert data["column_count"] == 2
    assert "columns" in data
    assert "score" in data["columns"]
    assert data["columns"]["score"]["inferred_type"] == "numeric"


def test_cli_validate_flag(tmp_path: Path) -> None:
    """Test CLI with --validate flag."""
    csv_file = tmp_path / "test.csv"
    csv_file.write_text("a,b,c\n1,2,3\n", encoding="utf-8")

    env = os.environ.copy()
    src_dir = str(Path(__file__).parent.parent / "src")
    env["PYTHONPATH"] = f"{src_dir}:{env.get('PYTHONPATH', '')}"

    result = subprocess.run(
        [sys.executable, "-m", "ai_csv_data_analyst", str(csv_file), "--validate"],
        capture_output=True,
        text=True,
        timeout=10,
        env=env
    )
    assert result.returncode == 0
    assert "File validated" in result.stdout
    assert "Rows: 1" in result.stdout
    assert "Columns: 3" in result.stdout


def test_cli_help_flag() -> None:
    """Test CLI with --help flag."""
    env = os.environ.copy()
    src_dir = str(Path(__file__).parent.parent / "src")
    env["PYTHONPATH"] = f"{src_dir}:{env.get('PYTHONPATH', '')}"

    result = subprocess.run(
        [sys.executable, "-m", "ai_csv_data_analyst", "--help"],
        capture_output=True,
        text=True,
        timeout=10,
        env=env
    )
    assert result.returncode == 0
    assert "Usage:" in result.stdout
    assert "--json" in result.stdout


def test_cli_missing_file() -> None:
    """Test CLI with missing file reports error gracefully."""
    env = os.environ.copy()
    src_dir = str(Path(__file__).parent.parent / "src")
    env["PYTHONPATH"] = f"{src_dir}:{env.get('PYTHONPATH', '')}"

    result = subprocess.run(
        [sys.executable, "-m", "ai_csv_data_analyst", "/path/to/missing.csv"],
        capture_output=True,
        text=True,
        timeout=10,
        env=env
    )
    assert result.returncode == 0
    assert "Error:" in result.stdout
    assert "File not found" in result.stdout

