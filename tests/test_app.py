"""Tests for the AI CSV Data Analyst application.

These tests verify the application entry point behaves as expected.
Tests are designed to run without internet access, LLMs, or datasets.
"""

from __future__ import annotations

import subprocess
import sys
import pytest


def test_app_runs_as_module() -> None:
    """Test that the application can be launched via python -m ai_csv_data_analyst."""
    result = subprocess.run(
        [sys.executable, "-m", "ai_csv_data_analyst"],
        capture_output=True,
        text=True,
        timeout=10
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

