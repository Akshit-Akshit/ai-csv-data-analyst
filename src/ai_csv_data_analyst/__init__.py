"""
AI CSV Data Analyst Package

A local-first analytical application that allows users to explore CSV datasets
through natural-language questions without requiring SQL or Python.

This package provides:
- A deterministic CSV profiler
- A lightweight local language model for task classification (planned)
- A typed task-planning layer (planned)
- A registry of trusted analytical operations (planned)
- DuckDB for scalable CSV processing (planned)

Public API:
    - loader.load_csv(): Load and parse a CSV file
    - profiler.profile_csv(): Generate a structured profile for a CSV file
    - DatasetProfile: Dataclass representing a complete CSV profile
    - LoadError: Exception raised when CSV loading fails
"""

from __future__ import annotations

__version__ = "0.1.0"
__author__ = "Akshit"

from ai_csv_data_analyst.loader import load_csv, LoadedCSV, LoadError
from ai_csv_data_analyst.profiler import (
    profile_csv,
    DatasetProfile,
    ColumnStats,
)

__all__ = [
    "load_csv",
    "LoadedCSV",
    "LoadError",
    "profile_csv",
    "DatasetProfile",
    "ColumnStats",
    "__version__",
    "__author__",
]
