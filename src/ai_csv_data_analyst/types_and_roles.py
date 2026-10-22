"""
Type Inference and Semantic Role Classification

Distinguishes physical representation (integer, float, datetime, boolean, string)
from analytical semantic role (identifier, measure, category, timestamp, free_text, url, boolean_flag).
Exposes confidence scores, supporting evidence, violating counts, and alternative interpretations.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Sequence

from ai_csv_data_analyst.config import ProfilingConfig
from ai_csv_data_analyst.parser import (
    parse_numeric_auditable,
    parse_datetime_auditable,
    parse_boolean_auditable,
)


class PhysicalType(str, Enum):
    """The underlying physical parseable data type."""
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    DATETIME = "datetime"
    STRING = "string"
    UNKNOWN = "unknown"


class SemanticRole(str, Enum):
    """The analytical interpretation and intended usage."""
    IDENTIFIER = "identifier"
    MEASURE = "measure"
    CATEGORY = "category"
    TIMESTAMP = "timestamp"
    FREE_TEXT = "free_text"
    URL = "url"
    BOOLEAN_FLAG = "boolean_flag"
    UNKNOWN = "unknown"


@dataclass
class TypeInferenceResult:
    """Detailed result of type inference and semantic role assignment."""
    # Legacy type for 100% backward compatibility
    # ('numeric', 'categorical', 'text', 'url', 'mixed', 'unknown')
    legacy_inferred_type: str

    physical_type: PhysicalType
    semantic_role: SemanticRole
    confidence: float
    evidence: dict[str, Any]
    alternative_interpretations: list[dict[str, Any]] = field(default_factory=list)
    violating_values_count: int = 0
    violating_samples: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert inference result to a dictionary."""
        return {
            "legacy_inferred_type": self.legacy_inferred_type,
            "physical_type": self.physical_type.value,
            "semantic_role": self.semantic_role.value,
            "confidence": round(self.confidence, 4),
            "evidence": self.evidence,
            "alternative_interpretations": self.alternative_interpretations,
            "violating_values_count": self.violating_values_count,
            "violating_samples": self.violating_samples[:5],
        }


# Column name patterns as supporting evidence
_ID_NAME_RE = re.compile(
    r"(?:^|[_ .\-/])(id|uuid|guid|code|sku|key|pk|fk|postal|zip|sno|s\.no|sr\.?no|serial|mrd|mrd[ _.\-]?no|acc|account|ref|patient[ _.\-]?no|case[ _.\-]?no|record[ _.\-]?no|roll[ _.\-]?no)(?:$|[_ .\-/])"
    r"|(?:^|[_ .\-/])(no|no\.|num|number)$",
    re.IGNORECASE,
)
_TIME_NAME_RE = re.compile(r"(?:^|[_ .\-/])(dt|d\.?o\.?a|d\.?o\.?d|dob|date|time|timestamp|created|updated|at|year|month|day)(?:$|[_ .\-/])", re.IGNORECASE)
_URL_NAME_RE = re.compile(r"(?:^|[_ -])(url|link|href|website|site)(?:$|[_ -])", re.IGNORECASE)
_FLAG_NAME_RE = re.compile(r"(?:^|[_ -])(is_|has_|can_|active|enabled|flag)", re.IGNORECASE)


def infer_column_type_and_role(
    values: Sequence[str],
    column_name: str = "",
    config: ProfilingConfig | None = None,
) -> TypeInferenceResult:
    """
    Infer the physical type and semantic role for a column with evidence and confidence.
    """
    cfg = config or ProfilingConfig()
    total_rows = len(values)

    # Filter out missing tokens and empty values
    non_missing: list[str] = []
    missing_count = 0
    for v in values:
        if cfg.is_missing_token(v):
            missing_count += 1
        else:
            non_missing.append(str(v))

    non_missing_count = len(non_missing)
    if non_missing_count == 0:
        return TypeInferenceResult(
            legacy_inferred_type="unknown",
            physical_type=PhysicalType.UNKNOWN,
            semantic_role=SemanticRole.UNKNOWN,
            confidence=1.0,
            evidence={
                "total_rows": total_rows,
                "non_missing_count": 0,
                "missing_count": missing_count,
                "reason": "All values in column are missing or blank",
            },
        )

    # Count distinct values
    distinct_vals = set(non_missing)
    distinct_count = len(distinct_vals)
    cardinality_ratio = distinct_count / non_missing_count
    uniqueness_ratio = distinct_count / total_rows if total_rows > 0 else 0.0

    # 1. Test URL patterns
    url_count = sum(1 for v in non_missing if v.strip().startswith(("http://", "https://", "ftp://")))
    url_ratio = url_count / non_missing_count

    # 2. Test Numeric parsing
    numeric_results = [parse_numeric_auditable(v, cfg) for v in non_missing]
    valid_numerics = [r for r in numeric_results if r.is_valid]
    valid_numeric_count = len(valid_numerics)
    numeric_ratio = valid_numeric_count / non_missing_count
    integer_count = sum(1 for r in valid_numerics if r.rule_applied in ("exact_integer",))

    # 3. Test Boolean parsing
    bool_results = [parse_boolean_auditable(v, cfg) for v in non_missing]
    valid_bool_count = sum(1 for r in bool_results if r.is_valid)
    bool_ratio = valid_bool_count / non_missing_count

    # 4. Test Datetime parsing
    dt_results = [parse_datetime_auditable(v, cfg) for v in non_missing]
    valid_dt_count = sum(1 for r in dt_results if r.is_valid)
    dt_ratio = valid_dt_count / non_missing_count

    # 5. String length characteristics
    lengths = [len(v) for v in non_missing]
    avg_len = sum(lengths) / non_missing_count if non_missing_count > 0 else 0.0
    max_len = max(lengths) if lengths else 0

    evidence = {
        "total_rows": total_rows,
        "non_missing_count": non_missing_count,
        "missing_count": missing_count,
        "distinct_count": distinct_count,
        "cardinality_ratio": round(cardinality_ratio, 4),
        "uniqueness_ratio": round(uniqueness_ratio, 4),
        "numeric_ratio": round(numeric_ratio, 4),
        "boolean_ratio": round(bool_ratio, 4),
        "datetime_ratio": round(dt_ratio, 4),
        "url_ratio": round(url_ratio, 4),
        "avg_length": round(avg_len, 2),
        "max_length": max_len,
    }

    # Name clues
    is_id_name = bool(_ID_NAME_RE.search(column_name))
    is_time_name = bool(_TIME_NAME_RE.search(column_name))
    is_url_name = bool(_URL_NAME_RE.search(column_name))
    is_flag_name = bool(_FLAG_NAME_RE.search(column_name))

    # Evaluate candidates
    # Priority A: URL
    if url_ratio >= cfg.url_dominance_threshold or (is_url_name and url_ratio > 0.3):
        violating = [v for v in non_missing if not v.strip().startswith(("http://", "https://", "ftp://"))]
        return TypeInferenceResult(
            legacy_inferred_type="url",
            physical_type=PhysicalType.STRING,
            semantic_role=SemanticRole.URL,
            confidence=url_ratio,
            evidence=evidence,
            violating_values_count=len(violating),
            violating_samples=violating[:5],
            alternative_interpretations=[{"type": "text", "confidence": 1.0 - url_ratio}],
        )

    # Priority B: Boolean
    if bool_ratio >= cfg.boolean_dominance_threshold or (is_flag_name and bool_ratio >= 0.5):
        violating = [r.raw_value for r in bool_results if not r.is_valid]
        return TypeInferenceResult(
            legacy_inferred_type="categorical",
            physical_type=PhysicalType.BOOLEAN,
            semantic_role=SemanticRole.BOOLEAN_FLAG,
            confidence=bool_ratio,
            evidence=evidence,
            violating_values_count=len(violating),
            violating_samples=violating[:5],
            alternative_interpretations=[{"type": "categorical", "confidence": 1.0 - bool_ratio}],
        )

    # Priority C: Datetime
    if dt_ratio >= 0.8 or (is_time_name and dt_ratio >= 0.5):
        violating = [r.raw_value for r in dt_results if not r.is_valid]
        return TypeInferenceResult(
            legacy_inferred_type="text",  # For backward compatibility, dates mapped to text/categorical
            physical_type=PhysicalType.DATETIME,
            semantic_role=SemanticRole.TIMESTAMP,
            confidence=dt_ratio,
            evidence=evidence,
            violating_values_count=len(violating),
            violating_samples=violating[:5],
            alternative_interpretations=[{"type": "text", "confidence": 1.0 - dt_ratio}],
        )

    # Priority D: Numeric
    if numeric_ratio >= cfg.numeric_inference_threshold:
        violating = [r.raw_value for r in numeric_results if not r.is_valid]
        physical = PhysicalType.INTEGER if (integer_count == valid_numeric_count) else PhysicalType.FLOAT

        # Check sequential numbering pattern (e.g. SNO)
        is_sequential = False
        if integer_count == valid_numeric_count and valid_numeric_count >= 3:
            int_vals = [r.parsed_value for r in valid_numerics]
            is_sequential = all(int_vals[i + 1] == int_vals[i] + 1 for i in range(len(int_vals) - 1))

        # Check leading zeros in numeric strings (e.g. "001", "002")
        has_leading_zeros = any(len(s.strip()) > 1 and s.strip().startswith("0") and s.strip().isdigit() for s in non_missing)

        evidence["is_sequential"] = is_sequential
        evidence["has_leading_zeros"] = has_leading_zeros
        evidence["is_id_name"] = is_id_name

        # Distinguish Semantic Role: MEASURE vs IDENTIFIER vs CATEGORY
        if is_sequential and (is_id_name or int_vals[0] in (0, 1)):
            role = SemanticRole.IDENTIFIER
        elif has_leading_zeros:
            role = SemanticRole.IDENTIFIER
        elif is_id_name and (uniqueness_ratio >= 0.4 or distinct_count >= 10):
            # Identifiers like MRD No. may repeat if patient has multiple visits
            role = SemanticRole.IDENTIFIER
        elif distinct_count <= 10 or (distinct_count <= 20 and cardinality_ratio < 0.05):
            role = SemanticRole.CATEGORY
        else:
            role = SemanticRole.MEASURE

        return TypeInferenceResult(
            legacy_inferred_type="numeric",
            physical_type=physical,
            semantic_role=role,
            confidence=numeric_ratio,
            evidence=evidence,
            violating_values_count=len(violating),
            violating_samples=violating[:5],
            alternative_interpretations=[
                {"type": "mixed", "confidence": 1.0 - numeric_ratio} if numeric_ratio < 1.0 else {}
            ],
        )

    # Priority E: Mixed numeric / text
    if numeric_ratio >= cfg.mixed_type_threshold:
        violating = [r.raw_value for r in numeric_results if not r.is_valid]
        return TypeInferenceResult(
            legacy_inferred_type="mixed",
            physical_type=PhysicalType.STRING,
            semantic_role=SemanticRole.CATEGORY if distinct_count <= 20 else SemanticRole.FREE_TEXT,
            confidence=numeric_ratio,
            evidence=evidence,
            violating_values_count=len(violating),
            violating_samples=violating[:5],
            alternative_interpretations=[{"type": "numeric", "confidence": numeric_ratio}],
        )

    # Priority F: Categorical vs Free Text
    # Categorical if low cardinality: <= 20 distinct or <= 30% distinct
    if distinct_count <= 20 or (cardinality_ratio <= 0.3):
        return TypeInferenceResult(
            legacy_inferred_type="categorical",
            physical_type=PhysicalType.STRING,
            semantic_role=SemanticRole.CATEGORY,
            confidence=1.0 - cardinality_ratio,
            evidence=evidence,
            violating_values_count=0,
            violating_samples=[],
            alternative_interpretations=[{"type": "text", "confidence": cardinality_ratio}],
        )

    # If identifier-like string (high uniqueness, e.g. GUID or SKU or ID column name)
    if is_id_name or uniqueness_ratio >= 0.9:
        role = SemanticRole.IDENTIFIER
    elif avg_len > 100 or max_len > 250:
        role = SemanticRole.FREE_TEXT
    else:
        role = SemanticRole.FREE_TEXT

    return TypeInferenceResult(
        legacy_inferred_type="text",
        physical_type=PhysicalType.STRING,
        semantic_role=role,
        confidence=0.85,
        evidence=evidence,
        violating_values_count=0,
        violating_samples=[],
        alternative_interpretations=[{"type": "categorical", "confidence": 0.15}],
    )

