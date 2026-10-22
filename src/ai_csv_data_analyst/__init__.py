"""
AI CSV Data Analyst Package

A local-first analytical application that allows users to explore CSV datasets
through natural-language questions without requiring SQL or Python.

Public API:
    - loader.load_csv(): Load and parse a CSV file under declared policies
    - profiler.profile_csv(): Generate an auditable, structured profile for a CSV file
    - DatasetProfile: Dataclass representing a complete CSV profile
    - ColumnStats: Dataclass representing column-level profiling statistics
    - LoadError: Exception raised when CSV loading fails
    - ProfilingConfig: Configuration options for ingestion and profiling
    - ColumnValueCounts: Invariant-reconciled cell value classification
    - StructuralDiagnostic: Diagnostic records for structural CSV anomalies
"""

from __future__ import annotations

__version__ = "0.1.0"
__author__ = "Akshit"

from ai_csv_data_analyst.config import ProfilingConfig
from ai_csv_data_analyst.diagnostics import (
    AnomalySeverity,
    ColumnValueCounts,
    StructuralAnomalyType,
    StructuralDiagnostic,
    ValueCategory,
)
from ai_csv_data_analyst.loader import (
    LoadedCSV,
    LoadError,
    load_csv,
)
from ai_csv_data_analyst.parser import (
    ParseResult,
    parse_boolean_auditable,
    parse_datetime_auditable,
    parse_numeric_auditable,
)
from ai_csv_data_analyst.profiler import (
    ColumnStats,
    DatasetProfile,
    detect_column_type,
    detect_value_type,
    parse_numeric,
    profile_csv,
)
from ai_csv_data_analyst.types_and_roles import (
    PhysicalType,
    SemanticRole,
    TypeInferenceResult,
    infer_column_type_and_role,
)

__all__ = [
    "load_csv",
    "LoadedCSV",
    "LoadError",
    "profile_csv",
    "DatasetProfile",
    "ColumnStats",
    "ProfilingConfig",
    "ColumnValueCounts",
    "StructuralDiagnostic",
    "StructuralAnomalyType",
    "AnomalySeverity",
    "ValueCategory",
    "PhysicalType",
    "SemanticRole",
    "TypeInferenceResult",
    "infer_column_type_and_role",
    "parse_numeric",
    "parse_numeric_auditable",
    "parse_datetime_auditable",
    "parse_boolean_auditable",
    "ParseResult",
    "detect_column_type",
    "detect_value_type",
    "__version__",
    "__author__",
]
