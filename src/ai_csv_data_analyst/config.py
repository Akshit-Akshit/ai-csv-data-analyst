"""
Configuration Module for CSV Loading and Profiling

Defines configuration options for deterministic CSV ingestion, parsing,
type inference, statistical profiling, and resource limits.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence


@dataclass(frozen=True)
class ProfilingConfig:
    """
    Configuration for CSV loading and dataset profiling.

    Enforces deterministic and auditable behavior across all ingestion,
    parsing, classification, and profiling phases.
    """
    # Encoding options
    encoding: str | None = None  # None indicates auto-detection with fallback
    fallback_encodings: tuple[str, ...] = ("utf-8-sig", "utf-8", "latin-1", "cp1252", "iso-8859-1")

    # Delimiter options
    delimiter: str | None = ","  # Default to comma for backward compatibility; None or 'auto' for sniff
    candidate_delimiters: tuple[str, ...] = (",", ";", "\t", "|")

    # Loading mode
    strict_mode: bool = False  # If True, structural errors raise LoadError; if False, tolerant with diagnostics

    # Missing-value tokens (empty string and pure whitespace are always missing)
    missing_tokens: tuple[str, ...] = ()  # Global tokens, e.g. ("NA", "N/A", "null", "none", "EMPTY", "NILL", "-")
    per_column_missing_tokens: dict[str, tuple[str, ...]] = field(default_factory=dict)
    case_sensitive_missing: bool = False

    # Numeric parsing options
    decimal_separator: str = "."
    thousands_separator: str = ","
    allow_currency_symbols: bool = True
    allow_percentage: bool = True

    # Datetime options
    datetime_formats: tuple[str, ...] | None = None

    # Thresholds
    high_cardinality_threshold: float = 0.2
    numeric_inference_threshold: float = 0.8
    mixed_type_threshold: float = 0.2
    url_dominance_threshold: float = 0.5
    boolean_dominance_threshold: float = 0.8
    iqr_outlier_factor: float = 1.5

    # Resource limits
    max_file_size_bytes: int | None = None
    max_rows: int | None = None
    max_fields: int | None = None
    max_columns_relational: int = 25
    max_composite_key_columns: int = 10

    # Provenance
    schema_version: str = "1.0.0"

    def is_missing_token(self, val: str, column_name: str = "") -> bool:
        """Check whether a string token matches configured missing value criteria."""
        if val is None:
            return True
        s = val.strip()
        if not s:
            return True

        # Check column-specific override first if specified
        tokens = ()
        if column_name and column_name in self.per_column_missing_tokens:
            tokens = self.per_column_missing_tokens[column_name]
        elif self.missing_tokens:
            tokens = self.missing_tokens

        if not tokens:
            return False
        if self.case_sensitive_missing:
            return s in tokens
        s_lower = s.lower()
        return any(s_lower == token.lower() for token in tokens)

    def classify_missing_token(self, val: str, column_name: str = "") -> str | None:
        """
        Classify missing value type:
        - 'blank': empty or whitespace-only
        - 'sentinel': matched a configured missing sentinel token
        - None: not missing
        """
        if val is None:
            return "blank"
        s = str(val).strip()
        if not s:
            return "blank"
        if self.is_missing_token(val, column_name):
            return "sentinel"
        return None

