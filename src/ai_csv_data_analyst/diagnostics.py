"""
Diagnostics and Value Classification Models

Defines structured diagnostics for structural CSV anomalies, mutually
exclusive cell value classifications (missing, valid, invalid, unclassified),
and invariant reconciliation checks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class StructuralAnomalyType(str, Enum):
    """Types of structural anomalies observed in CSV files."""
    ROW_WIDTH_MISMATCH = "row_width_mismatch"
    SURPLUS_FIELDS = "surplus_fields"
    DEFICIT_FIELDS = "deficit_fields"
    DUPLICATE_HEADER = "duplicate_header"
    BLANK_HEADER = "blank_header"
    HEADER_COLLISION = "header_collision"
    ENCODING_FALLBACK = "encoding_fallback"
    ENCODING_ERROR = "encoding_error"
    MALFORMED_ROW = "malformed_row"
    RESOURCE_LIMIT_EXCEEDED = "resource_limit_exceeded"
    DELIMITER_AMBIGUITY = "delimiter_ambiguity"


class AnomalySeverity(str, Enum):
    """Severity of a detected anomaly."""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class StructuralDiagnostic:
    """Diagnostic record for a structural CSV anomaly."""
    anomaly_type: StructuralAnomalyType
    message: str
    line_number: int | None = None
    record_index: int | None = None
    severity: AnomalySeverity = AnomalySeverity.WARNING
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert diagnostic to dictionary representation."""
        res: dict[str, Any] = {
            "type": self.anomaly_type.value,
            "severity": self.severity.value,
            "message": self.message,
        }
        if self.line_number is not None:
            res["line_number"] = self.line_number
        if self.record_index is not None:
            res["record_index"] = self.record_index
        if self.details:
            res["details"] = self.details
        return res


class ValueCategory(str, Enum):
    """
    Mutually exclusive value classification categories.

    - MISSING: Blank or matches configured missing-value token.
    - VALID: Value successfully interpreted under applicable column rules.
    - INVALID: Value fails applicable interpretation or validation rule.
    - UNCLASSIFIED: Value whose interpretation cannot be established with confidence.
    """
    MISSING = "missing"
    VALID = "valid"
    INVALID = "invalid"
    UNCLASSIFIED = "unclassified"


@dataclass
class ColumnValueCounts:
    """
    Reconciled cell classification counts and rates for a column.

    Enforces the invariant:
    source_cell_count == missing_count + valid_count + invalid_count + unclassified_count
    where missing_count == blank_missing_count + sentinel_missing_count
    """
    source_cell_count: int
    missing_count: int
    valid_count: int
    invalid_count: int
    unclassified_count: int = 0
    missing_rate: float = 0.0
    invalid_rate: float = 0.0
    blank_missing_count: int = 0
    sentinel_missing_count: int = 0

    def __post_init__(self) -> None:
        if self.source_cell_count > 0:
            self.missing_rate = round(self.missing_count / self.source_cell_count, 6)
            self.invalid_rate = round(self.invalid_count / self.source_cell_count, 6)
        else:
            self.missing_rate = 0.0
            self.invalid_rate = 0.0

    @property
    def is_reconciled(self) -> bool:
        """Check whether the cell classification invariant holds exactly."""
        return self.source_cell_count == (
            self.missing_count
            + self.valid_count
            + self.invalid_count
            + self.unclassified_count
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert classification counts to a dictionary."""
        return {
            "source_cell_count": self.source_cell_count,
            "missing_count": self.missing_count,
            "blank_missing_count": self.blank_missing_count,
            "sentinel_missing_count": self.sentinel_missing_count,
            "valid_count": self.valid_count,
            "invalid_count": self.invalid_count,
            "unclassified_count": self.unclassified_count,
            "missing_rate": self.missing_rate,
            "invalid_rate": self.invalid_rate,
            "is_reconciled": self.is_reconciled,
        }

