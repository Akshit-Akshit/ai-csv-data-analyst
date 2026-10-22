"""
CSV Profiling Engine

Generates structured profiles for CSV datasets including:
- Dataset overview (rows, columns, inferred types, structural health)
- Invariant-reconciled cell value classification (missing, valid, invalid, unclassified)
- Type inference distinguishing physical type from analytical semantic role
- Numeric column statistics (mean, median, std, quartiles, IQR outliers)
- Categorical and text statistics (distinct values, frequencies, string length metrics)
- Datetime column statistics (temporal coverage, validity, ambiguity)
- Relational diagnostics (candidate keys, composite keys, constant columns)
- Audit provenance and execution metadata for blueprint-driven analytical planning
"""

from __future__ import annotations

import hashlib
import math
import re
import statistics
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

from ai_csv_data_analyst.config import ProfilingConfig
from ai_csv_data_analyst.diagnostics import (
    ColumnValueCounts,
    ValueCategory,
)
from ai_csv_data_analyst.loader import LoadedCSV, LoadError, load_csv
from ai_csv_data_analyst.parser import (
    parse_boolean_auditable,
    parse_datetime_auditable,
    parse_month_year_token,
    parse_numeric_auditable,
)
from ai_csv_data_analyst.types_and_roles import (
    PhysicalType,
    SemanticRole,
    TypeInferenceResult,
    infer_column_type_and_role,
)


@dataclass
class ColumnStats:
    """Statistics and analytical classification for a single column."""
    name: str
    inferred_type: str  # Legacy: 'numeric', 'categorical', 'text', 'url', 'mixed', 'unknown'
    missing_count: int
    missing_percentage: float
    valid_count: int
    distinct_count: int
    most_frequent_values: list[dict[str, Any]]  # list of {value, count}
    is_empty: bool = False  # All values are missing

    # Numeric statistics (only for numeric columns)
    numeric_stats: dict[str, Any] | None = None

    # Text statistics (for text/categorical columns)
    text_stats: dict[str, Any] | None = None

    # High-cardinality warning
    has_high_cardinality: bool = False

    # Enhanced attributes for blueprint-driven analytics
    physical_type: str = "unknown"
    semantic_role: str = "unknown"
    type_confidence: float = 1.0
    type_evidence: dict[str, Any] = field(default_factory=dict)
    value_counts: ColumnValueCounts | None = None
    datetime_stats: dict[str, Any] | None = None
    outlier_stats: dict[str, Any] | None = None
    identifier_stats: dict[str, Any] | None = None


@dataclass
class DatasetProfile:
    """Complete structured profile for a CSV dataset."""
    file_path: str
    row_count: int
    column_count: int
    headers: list[str]

    # Dataset overview
    overview: dict[str, Any] = field(default_factory=dict)

    # Column profiles
    column_profiles: dict[str, ColumnStats] = field(default_factory=dict)

    # Summary statistics
    summary: dict[str, Any] = field(default_factory=dict)

    # Data quality issues
    quality_issues: list[dict[str, Any]] = field(default_factory=list)

    # Enhanced metadata for blueprint selection and audit
    provenance: dict[str, Any] = field(default_factory=dict)
    structural_diagnostics: list[dict[str, Any]] = field(default_factory=list)
    relational_analysis: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert profile to dictionary for JSON serialization."""
        return {
            "file_path": self.file_path,
            "row_count": self.row_count,
            "column_count": self.column_count,
            "headers": self.headers,
            "overview": self.overview,
            "columns": {
                name: {
                    "inferred_type": profile.inferred_type,
                    "missing_count": profile.missing_count,
                    "missing_percentage": profile.missing_percentage,
                    "valid_count": profile.valid_count,
                    "distinct_count": profile.distinct_count,
                    "most_frequent_values": profile.most_frequent_values[:10],
                    "is_empty": profile.is_empty,
                    "numeric_stats": profile.numeric_stats,
                    "text_stats": profile.text_stats,
                    "has_high_cardinality": profile.has_high_cardinality,
                    "physical_type": profile.physical_type,
                    "semantic_role": profile.semantic_role,
                    "type_confidence": profile.type_confidence,
                    "type_evidence": profile.type_evidence,
                    "value_classification": profile.value_counts.to_dict() if profile.value_counts else None,
                    "datetime_stats": profile.datetime_stats,
                    "outlier_stats": profile.outlier_stats,
                    "identifier_stats": profile.identifier_stats,
                }
                for name, profile in sorted(self.column_profiles.items())
            },
            "summary": self.summary,
            "quality_issues": self.quality_issues,
            "provenance": self.provenance,
            "structural_diagnostics": self.structural_diagnostics,
            "relational_analysis": self.relational_analysis,
        }


def parse_numeric(val: Any) -> float | None:
    """
    Attempt to parse a value as numeric.
    Backward-compatible public wrapper around parse_numeric_auditable.
    """
    res = parse_numeric_auditable(val)
    if res.is_valid:
        return float(res.parsed_value)
    return None


def detect_value_type(val: str) -> str:
    """
    Detect the type of an individual string value.
    Returns: 'empty', 'url', 'numeric', 'boolean', 'text'
    """
    if not val or not val.strip():
        return "empty"
    cleaned = val.strip()
    if cleaned.startswith(("http://", "https://", "ftp://")):
        return "url"
    if parse_numeric(cleaned) is not None:
        return "numeric"
    if cleaned.lower() in ("true", "false", "yes", "no"):
        return "boolean"
    return "text"


def detect_column_type(values: list[str], column_name: str = "") -> str:
    """
    Detect legacy type of a column ('numeric', 'categorical', 'text', 'url', 'mixed', 'unknown').
    Backward-compatible wrapper around infer_column_type_and_role.
    """
    res = infer_column_type_and_role(values, column_name)
    return res.legacy_inferred_type


def calculate_numeric_stats(
    values: Sequence[str],
    column_name: str = "",
    config: ProfilingConfig | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """
    Calculate numeric statistics and outlier candidates from valid numeric values.
    Returns: (numeric_stats, outlier_stats)
    """
    cfg = config or ProfilingConfig()
    numeric_values: list[float] = []

    for v in values:
        res = parse_numeric_auditable(v, cfg)
        if res.is_valid:
            numeric_values.append(float(res.parsed_value))

    if not numeric_values:
        return None, None

    count = len(numeric_values)
    mean_val = statistics.mean(numeric_values)
    median_val = statistics.median(numeric_values)
    min_val = min(numeric_values)
    max_val = max(numeric_values)
    std_val = statistics.stdev(numeric_values) if count > 1 else 0.0

    # Calculate quartiles deterministically
    if count >= 4:
        quantiles = statistics.quantiles(numeric_values, n=4, method="inclusive")
        q1_val = quantiles[0]
        q3_val = quantiles[2]
    elif count == 3:
        sorted_v = sorted(numeric_values)
        q1_val = sorted_v[0]
        q3_val = sorted_v[2]
    elif count == 2:
        sorted_v = sorted(numeric_values)
        q1_val = sorted_v[0]
        q3_val = sorted_v[1]
    else:
        q1_val = min_val
        q3_val = max_val

    iqr = q3_val - q1_val
    lower_bound = q1_val - (cfg.iqr_outlier_factor * iqr)
    upper_bound = q3_val + (cfg.iqr_outlier_factor * iqr)
    outliers = [x for x in numeric_values if x < lower_bound or x > upper_bound]

    outlier_stats = {
        "method": "iqr",
        "factor": cfg.iqr_outlier_factor,
        "iqr": iqr,
        "lower_bound": lower_bound,
        "upper_bound": upper_bound,
        "candidate_count": len(outliers),
        "candidate_rate": round(len(outliers) / count, 6) if count > 0 else 0.0,
        "note": "Outlier candidates for investigation; not automatically classified as errors",
    }

    numeric_stats = {
        "count": count,
        "mean": mean_val,
        "median": median_val,
        "std_dev": std_val,
        "min": min_val,
        "max": max_val,
        "q1": q1_val,
        "q3": q3_val,
        "range": max_val - min_val,
    }

    return numeric_stats, outlier_stats


def calculate_text_stats(values: Sequence[str]) -> dict[str, Any]:
    """Calculate categorical/text statistics and string length metrics."""
    non_empty = [str(v) for v in values if v is not None and str(v).strip() != ""]
    if not non_empty:
        return {
            "distinct_count": 0,
            "most_frequent_values": [],
            "empty_string_count": sum(1 for v in values if v == ""),
            "whitespace_count": sum(1 for v in values if v is not None and v != "" and v.strip() == ""),
            "min_length": 0,
            "max_length": 0,
            "mean_length": 0.0,
        }

    distinct_count = len(set(non_empty))
    counter = Counter(non_empty)
    most_frequent = sorted(
        counter.items(),
        key=lambda x: (-x[1], x[0]),
    )

    lengths = [len(v) for v in non_empty]
    empty_str_count = sum(1 for v in values if v == "")
    ws_count = sum(1 for v in values if v is not None and v != "" and v.strip() == "")

    # Top 10 with safe string truncation (max 100 chars per value) to prevent leaking bulk data
    formatted_frequent = [
        {"value": value[:100], "count": count}
        for value, count in most_frequent[:10]
    ]

    return {
        "distinct_count": distinct_count,
        "most_frequent_values": formatted_frequent,
        "empty_string_count": empty_str_count,
        "whitespace_count": ws_count,
        "min_length": min(lengths) if lengths else 0,
        "max_length": max(lengths) if lengths else 0,
        "mean_length": round(statistics.mean(lengths), 2) if lengths else 0.0,
    }


def calculate_datetime_stats(
    values: Sequence[str],
    column_name: str = "",
    config: ProfilingConfig | None = None,
    rows: list[dict[str, Any]] | None = None,
    headers: list[str] | None = None,
) -> dict[str, Any] | None:
    """
    Calculate datetime coverage and parsing metrics with context-aware format resolution.

    - Resolves ambiguous slash dates using column-level unambiguous samples,
      contextual 'month year' columns (for admission dates like D.O.A), and
      chronological sequence (e.g. D.O.D >= D.O.A).
    - Preserves raw values.
    - Excludes unresolved ambiguous dates from definitive min/max ranges.
    - Reports separate counts for valid, ambiguous, contextually resolved,
      unresolved, invalid, and conflicting dates.
    """
    cfg = config or ProfilingConfig()

    # Find candidate context columns if present
    month_year_col = None
    doa_col = None
    if headers:
        for h in headers:
            if re.search(r"(?:month[ _\-]?year|monthyear)", h, re.IGNORECASE):
                month_year_col = h
            elif re.search(r"(?:^|[_ .\-/])(d\.?o\.?a|admission[ _\-]?date|date[ _\-]?of[ _\-]?admission)(?:$|[_ .\-/])", h, re.IGNORECASE):
                doa_col = h

    is_doa = bool(re.search(r"(?:^|[_ .\-/])(d\.?o\.?a|admission[ _\-]?date|date[ _\-]?of[ _\-]?admission)(?:$|[_ .\-/])", column_name, re.IGNORECASE))
    is_dod = bool(re.search(r"(?:^|[_ .\-/])(d\.?o\.?d|discharge[ _\-]?date|date[ _\-]?of[ _\-]?discharge|death[ _\-]?date)(?:$|[_ .\-/])", column_name, re.IGNORECASE))

    total_non_missing = 0
    count_unambiguous_dmy = 0
    count_unambiguous_mdy = 0
    count_unambiguous_iso = 0
    count_ambiguous = 0
    count_invalid = 0
    context_dmy_votes = 0
    context_mdy_votes = 0
    context_conflicts = 0

    parsed_records: list[dict[str, Any]] = []

    for idx, v in enumerate(values):
        if cfg.is_missing_token(v, column_name):
            continue
        total_non_missing += 1
        s = str(v).strip()

        # Check ISO 8601: YYYY-MM-DD
        iso_m = re.match(r"^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?)?", s)
        if iso_m:
            y, m, d = int(iso_m.group(1)), int(iso_m.group(2)), int(iso_m.group(3))
            try:
                dt = datetime(y, m, d)
                count_unambiguous_iso += 1
                parsed_records.append({"raw": s, "dt_iso": dt, "status": "iso"})
            except ValueError:
                count_invalid += 1
                parsed_records.append({"raw": s, "status": "invalid"})
            continue

        # Check slash or dash dates: P1 / P2 / P3
        slash_m = re.match(r"^(\d{1,4})[/-](\d{1,2})[/-](\d{1,4})", s)
        if slash_m:
            p1, p2, p3 = int(slash_m.group(1)), int(slash_m.group(2)), int(slash_m.group(3))
            if p3 >= 1000:
                year = p3
                dmy_valid = False
                mdy_valid = False
                dt_dmy = None
                dt_mdy = None
                try:
                    dt_dmy = datetime(year, p2, p1)
                    dmy_valid = True
                except ValueError:
                    pass
                try:
                    dt_mdy = datetime(year, p1, p2)
                    mdy_valid = True
                except ValueError:
                    pass

                if not dmy_valid and not mdy_valid:
                    count_invalid += 1
                    parsed_records.append({"raw": s, "status": "invalid"})
                    continue

                if dmy_valid and not mdy_valid:
                    count_unambiguous_dmy += 1
                    parsed_records.append({"raw": s, "dt_dmy": dt_dmy, "status": "unambiguous_dmy"})
                    continue

                if mdy_valid and not dmy_valid:
                    count_unambiguous_mdy += 1
                    parsed_records.append({"raw": s, "dt_mdy": dt_mdy, "status": "unambiguous_mdy"})
                    continue

                # Both are valid calendar dates (p1 <= 12 and p2 <= 12)
                if p1 == p2:
                    parsed_records.append({"raw": s, "dt_dmy": dt_dmy, "dt_mdy": dt_mdy, "status": "symmetric"})
                    continue

                count_ambiguous += 1
                row_resolved = None

                # Check contextual evidence from month_year_col
                if month_year_col and rows and idx < len(rows):
                    my_str = rows[idx].get(month_year_col)
                    my_token = parse_month_year_token(my_str)
                    if my_token:
                        exp_m, exp_y = my_token
                        dmy_matches = (p2 == exp_m and (year == exp_y or year % 100 == exp_y % 100))
                        mdy_matches = (p1 == exp_m and (year == exp_y or year % 100 == exp_y % 100))
                        if dmy_matches and not mdy_matches:
                            context_dmy_votes += 1
                            row_resolved = "context_dmy"
                        elif mdy_matches and not dmy_matches:
                            context_mdy_votes += 1
                            row_resolved = "context_mdy"
                        elif not dmy_matches and not mdy_matches:
                            context_conflicts += 1

                # Check contextual evidence from DOA if this is DOD
                if is_dod and doa_col and rows and idx < len(rows) and row_resolved is None:
                    doa_str = rows[idx].get(doa_col)
                    doa_res = parse_datetime_auditable(doa_str, cfg)
                    if doa_res.is_valid and isinstance(doa_res.parsed_value, datetime) and dt_dmy and dt_mdy:
                        doa_dt = doa_res.parsed_value
                        dmy_chron = (dt_dmy >= doa_dt and (dt_dmy - doa_dt).days <= 365)
                        mdy_chron = (dt_mdy >= doa_dt and (dt_mdy - doa_dt).days <= 365)
                        if dmy_chron and not mdy_chron:
                            context_dmy_votes += 1
                            row_resolved = "context_dmy"
                        elif mdy_chron and not dmy_chron:
                            context_mdy_votes += 1
                            row_resolved = "context_mdy"

                parsed_records.append({
                    "raw": s,
                    "dt_dmy": dt_dmy,
                    "dt_mdy": dt_mdy,
                    "status": "ambiguous",
                    "row_resolved": row_resolved,
                })
                continue

        count_invalid += 1
        parsed_records.append({"raw": s, "status": "invalid"})

    if total_non_missing == 0:
        return None

    # Check cross-column convention evidence: if DOD has ambiguous dates, check if DOA has unambiguous samples
    if is_dod and doa_col and rows and (context_dmy_votes == 0 and context_mdy_votes == 0):
        doa_values = [str(r.get(doa_col, "")) for r in rows if r.get(doa_col)]
        has_doa_dmy = any(
            re.match(r"^(\d{1,4})[/-](\d{1,2})[/-](\d{1,4})", v) and int(re.match(r"^(\d{1,4})[/-](\d{1,2})[/-](\d{1,4})", v).group(1)) > 12
            for v in doa_values
        )
        has_doa_mdy = any(
            re.match(r"^(\d{1,4})[/-](\d{1,2})[/-](\d{1,4})", v) and int(re.match(r"^(\d{1,4})[/-](\d{1,2})[/-](\d{1,4})", v).group(2)) > 12
            for v in doa_values
        )
        if has_doa_dmy and not has_doa_mdy:
            context_dmy_votes += 1
        elif has_doa_mdy and not has_doa_dmy:
            context_mdy_votes += 1

    # Determine chosen format from evidence
    chosen_format = None
    resolution_method = "unresolved"

    if cfg.datetime_formats:
        chosen_format = cfg.datetime_formats[0]
        resolution_method = "configured_format"
    elif count_unambiguous_iso > 0 and count_unambiguous_dmy == 0 and count_unambiguous_mdy == 0 and count_ambiguous == 0:
        chosen_format = "%Y-%m-%d"
        resolution_method = "iso_8601"
    elif count_unambiguous_dmy > 0 and count_unambiguous_mdy == 0:
        chosen_format = "%d/%m/%Y"
        resolution_method = "unambiguous_samples"
    elif count_unambiguous_mdy > 0 and count_unambiguous_dmy == 0:
        chosen_format = "%m/%d/%Y"
        resolution_method = "unambiguous_samples"
    elif context_dmy_votes > 0 and context_mdy_votes == 0:
        chosen_format = "%d/%m/%Y"
        resolution_method = "contextual_evidence"
    elif context_mdy_votes > 0 and context_dmy_votes == 0:
        chosen_format = "%m/%d/%Y"
        resolution_method = "contextual_evidence"

    # Compute resolved dates under chosen format
    resolved_dates: list[datetime] = []
    contextually_resolved_count = 0
    unresolved_ambiguous_count = 0

    for rec in parsed_records:
        status = rec.get("status")
        if status == "iso" and (chosen_format == "%Y-%m-%d" or chosen_format is None):
            resolved_dates.append(rec["dt_iso"])
        elif status == "unambiguous_dmy":
            if chosen_format == "%d/%m/%Y":
                resolved_dates.append(rec["dt_dmy"])
        elif status == "unambiguous_mdy":
            if chosen_format == "%m/%d/%Y":
                resolved_dates.append(rec["dt_mdy"])
        elif status == "symmetric":
            if chosen_format in ("%d/%m/%Y", "%m/%d/%Y"):
                resolved_dates.append(rec["dt_dmy"])
        elif status == "ambiguous":
            row_res = rec.get("row_resolved")
            if row_res == "context_dmy" or (chosen_format == "%d/%m/%Y" and resolution_method in ("unambiguous_samples", "contextual_evidence", "configured_format")):
                resolved_dates.append(rec["dt_dmy"])
                contextually_resolved_count += 1
            elif row_res == "context_mdy" or (chosen_format == "%m/%d/%Y" and resolution_method in ("unambiguous_samples", "contextual_evidence", "configured_format")):
                resolved_dates.append(rec["dt_mdy"])
                contextually_resolved_count += 1
            else:
                unresolved_ambiguous_count += 1

    if resolved_dates and chosen_format is not None:
        min_dt = min(resolved_dates)
        max_dt = max(resolved_dates)
        span_days = round((max_dt - min_dt).total_seconds() / 86400.0, 2)
        min_ts = min_dt.isoformat()
        max_ts = max_dt.isoformat()
        is_definitive = True
        uncertainty = None
    else:
        min_ts = None
        max_ts = None
        span_days = 0.0
        is_definitive = False
        uncertainty = "Date format remains ambiguous (could be DD/MM/YYYY or MM/DD/YYYY); definitive date range withheld."

    return {
        "valid_timestamp_count": len(resolved_dates),
        "min_timestamp": min_ts,
        "max_timestamp": max_ts,
        "coverage_days": span_days,
        "ambiguous_dates_count": count_ambiguous,
        "contextually_resolved_count": contextually_resolved_count,
        "unresolved_ambiguous_count": unresolved_ambiguous_count,
        "invalid_dates_count": count_invalid,
        "conflicting_dates_count": context_conflicts,
        "chosen_format": chosen_format,
        "format_resolution_method": resolution_method,
        "date_range_is_definitive": is_definitive,
        "uncertainty": uncertainty,
    }


def _classify_column_values(
    values: Sequence[str],
    inferred_type: str,
    physical_type: PhysicalType,
    config: ProfilingConfig,
    column_name: str = "",
) -> ColumnValueCounts:
    """
    Perform mutually exclusive 4-way cell value classification:
    missing, valid, invalid, unclassified.
    Enforces invariant: source_cell_count == missing + valid + invalid + unclassified
    where missing_count == blank_missing_count + sentinel_missing_count.
    """
    source_cell_count = len(values)
    missing_count = 0
    blank_missing_count = 0
    sentinel_missing_count = 0
    valid_count = 0
    invalid_count = 0
    unclassified_count = 0

    for val in values:
        # 1. Missing check (differentiating blank vs configured sentinel)
        missing_kind = config.classify_missing_token(val, column_name)
        if missing_kind == "blank":
            blank_missing_count += 1
            missing_count += 1
            continue
        elif missing_kind == "sentinel":
            sentinel_missing_count += 1
            missing_count += 1
            continue

        # 2. Type-specific validity check
        if inferred_type in ("numeric", "mixed") or physical_type in (PhysicalType.INTEGER, PhysicalType.FLOAT):
            res = parse_numeric_auditable(val, config)
            if res.is_valid:
                valid_count += 1
            else:
                invalid_count += 1
        elif physical_type == PhysicalType.DATETIME:
            res = parse_datetime_auditable(val, config)
            if res.is_valid:
                valid_count += 1
            else:
                invalid_count += 1
        elif physical_type == PhysicalType.BOOLEAN:
            res = parse_boolean_auditable(val, config)
            if res.is_valid:
                valid_count += 1
            else:
                invalid_count += 1
        elif inferred_type == "url":
            if str(val).strip().startswith(("http://", "https://", "ftp://")):
                valid_count += 1
            else:
                invalid_count += 1
        elif inferred_type in ("categorical", "text"):
            # Any non-missing text is valid text representation
            valid_count += 1
        else:
            # Unknown
            unclassified_count += 1

    counts = ColumnValueCounts(
        source_cell_count=source_cell_count,
        missing_count=missing_count,
        valid_count=valid_count,
        invalid_count=invalid_count,
        unclassified_count=unclassified_count,
        blank_missing_count=blank_missing_count,
        sentinel_missing_count=sentinel_missing_count,
    )
    # Enforce invariant
    assert counts.is_reconciled, (
        f"Cell count mismatch: source ({source_cell_count}) != "
        f"missing({missing_count}) + valid({valid_count}) + "
        f"invalid({invalid_count}) + unclassified({unclassified_count})"
    )
    return counts


def _analyze_relational_structure(
    headers: list[str],
    rows: list[dict[str, Any]],
    column_profiles: dict[str, ColumnStats],
    config: ProfilingConfig,
) -> dict[str, Any]:
    """
    Analyze candidate keys, composite keys, and constant columns with resource boundaries.
    """
    row_count = len(rows)
    if row_count <= 1:
        return {
            "candidate_single_keys": [],
            "candidate_composite_keys": [],
            "constant_columns": [h for h, col in column_profiles.items() if col.distinct_count == 1],
            "skipped_checks": "insufficient_rows",
        }

    # Single-column candidate keys (100% unique and 0 missing)
    candidate_keys: list[str] = []
    constant_cols: list[str] = []

    for h, col in column_profiles.items():
        if col.missing_count == 0 and col.distinct_count == row_count:
            candidate_keys.append(h)
        if col.distinct_count == 1:
            constant_cols.append(h)

    # Candidate composite keys (pairs of columns)
    # Bound to candidate columns to avoid O(N^2) combinatorial explosion on wide tables
    candidate_composite_keys: list[list[str]] = []
    eligible_cols = [
        h for h in headers
        if h in column_profiles
        and column_profiles[h].missing_count == 0
        and column_profiles[h].distinct_count > 1
        and h not in candidate_keys
    ][:config.max_composite_key_columns]

    skipped_reason: str | None = None
    if len(headers) > config.max_columns_relational:
        skipped_reason = f"Wide table with {len(headers)} columns exceeds relational check limit of {config.max_columns_relational}"

    if len(eligible_cols) >= 2 and row_count <= 50000:
        for i in range(len(eligible_cols)):
            for j in range(i + 1, len(eligible_cols)):
                c1, c2 = eligible_cols[i], eligible_cols[j]
                pair_signatures = {
                    (str(row.get(c1, "")), str(row.get(c2, "")))
                    for row in rows
                }
                if len(pair_signatures) == row_count:
                    candidate_composite_keys.append([c1, c2])
                    if len(candidate_composite_keys) >= 5:
                        break
            if len(candidate_composite_keys) >= 5:
                break

    return {
        "candidate_single_keys": candidate_keys,
        "candidate_composite_keys": candidate_composite_keys,
        "constant_columns": constant_cols,
        "skipped_checks": skipped_reason,
    }


def _compute_fingerprint(file_path: Path) -> str:
    """Compute SHA-256 fingerprint from file header without reading whole file."""
    if not file_path.exists():
        return "file_not_found"
    try:
        size = file_path.stat().st_size
        h = hashlib.sha256()
        h.update(str(size).encode())
        with open(file_path, "rb") as f:
            chunk = f.read(65536)
            h.update(chunk)
        return h.hexdigest()
    except Exception:
        return "unknown"


def profile_csv(
    file_path: str | Path,
    config: ProfilingConfig | None = None,
    delimiter: str | None = ",",
    strict_mode: bool | None = None,
) -> DatasetProfile:
    """
    Generate an auditable, deterministic profile for a CSV file.

    Args:
        file_path: Path to the CSV file to profile.
        config: Optional ProfilingConfig instance.
        delimiter: Column delimiter. Defaults to ','. If None, attempts auto-detection.
        strict_mode: Strict loading mode.

    Returns:
        DatasetProfile: Complete structured profile of the dataset.
    """
    cfg = config or ProfilingConfig()
    path_obj = Path(file_path)

    loaded: LoadedCSV = load_csv(
        file_path=file_path,
        delimiter=delimiter,
        config=cfg,
        strict_mode=strict_mode,
    )

    fingerprint = _compute_fingerprint(path_obj)

    git_commit = None
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
            cwd=str(Path(__file__).parent.parent.parent),
        )
        if proc.returncode == 0:
            git_commit = proc.stdout.strip()
    except Exception:
        git_commit = None

    import ai_csv_data_analyst
    module_path = getattr(ai_csv_data_analyst, "__file__", str(Path(__file__).resolve()))

    provenance = {
        "schema_version": cfg.schema_version,
        "package_version": getattr(ai_csv_data_analyst, "__version__", "0.1.0"),
        "module_path": str(Path(module_path).resolve()),
        "git_commit": git_commit,
        "python_version": sys.version.split()[0],
        "generated_at": datetime.now().isoformat(),
        "file_fingerprint": fingerprint,
        "metrics_mode": "exact",
        "effective_config": {
            "strict_mode": strict_mode if strict_mode is not None else cfg.strict_mode,
            "delimiter": loaded.delimiter,
            "encoding": loaded.encoding_info.get("selected_encoding"),
            "missing_tokens": list(cfg.missing_tokens),
            "per_column_missing_tokens": cfg.per_column_missing_tokens,
            "decimal_separator": cfg.decimal_separator,
        },
    }

    structural_diags = [d.to_dict() for d in loaded.structural_diagnostics]

    # Handle loading errors or invalid state
    if not loaded.is_valid:
        return DatasetProfile(
            file_path=str(file_path),
            row_count=loaded.row_count,
            column_count=loaded.column_count,
            headers=loaded.headers,
            overview={
                "rows": 0,
                "columns": loaded.column_count,
                "headers": loaded.headers,
                "error": loaded.error.message if loaded.error else "Unknown error",
            },
            column_profiles={},
            summary={},
            quality_issues=[],
            provenance=provenance,
            structural_diagnostics=structural_diags,
            relational_analysis={},
        )

    headers = loaded.headers
    rows = loaded.rows
    row_count = loaded.row_count
    column_count = loaded.column_count

    # Handle empty dataset or header-only file
    if row_count == 0:
        col_profiles: dict[str, ColumnStats] = {}
        for h in headers:
            col_profiles[h] = ColumnStats(
                name=h,
                inferred_type="unknown",
                missing_count=0,
                missing_percentage=0.0,
                valid_count=0,
                distinct_count=0,
                most_frequent_values=[],
                is_empty=True,
                numeric_stats=None,
                text_stats={"distinct_count": 0, "most_frequent_values": []},
                has_high_cardinality=False,
                physical_type=PhysicalType.UNKNOWN.value,
                semantic_role=SemanticRole.UNKNOWN.value,
                value_counts=ColumnValueCounts(0, 0, 0, 0, 0),
            )
        return DatasetProfile(
            file_path=str(file_path),
            row_count=0,
            column_count=column_count,
            headers=headers,
            overview={
                "rows": 0,
                "columns": column_count,
                "headers": headers,
                "duplicate_rows": 0,
                "numeric_columns": 0,
                "categorical_columns": 0,
                "text_columns": 0,
                "file_type": loaded.file_type,
            },
            column_profiles=col_profiles,
            summary={
                "total_rows": 0,
                "total_columns": column_count,
                "total_missing_cells": 0,
                "missing_percentage": 0.0,
                "duplicate_row_count": 0,
                "unique_rows": 0,
            },
            quality_issues=[],
            provenance=provenance,
            structural_diagnostics=structural_diags,
            relational_analysis={},
        )

    # Detect duplicate rows deterministically
    # Distinguish excess duplicate rows from rows participating in duplicate groups
    row_signatures = [
        tuple(str(row.get(h, "")) for h in headers)
        for row in rows
    ]
    signature_counts = Counter(row_signatures)
    excess_duplicates = sum(c - 1 for c in signature_counts.values() if c > 1)
    rows_in_duplicate_groups = sum(c for c in signature_counts.values() if c > 1)
    unique_rows = row_count - excess_duplicates

    column_profiles: dict[str, ColumnStats] = {}
    quality_issues: list[dict[str, Any]] = []

    for header in headers:
        column_values = [str(row.get(header, "")) for row in rows]

        # 1. Type inference with evidence and confidence
        inference_res = infer_column_type_and_role(column_values, header, cfg)
        inferred_type = inference_res.legacy_inferred_type

        # 2. Value classification and invariant enforcement
        value_counts = _classify_column_values(
            values=column_values,
            inferred_type=inferred_type,
            physical_type=inference_res.physical_type,
            config=cfg,
            column_name=header,
        )

        missing_count = value_counts.missing_count
        missing_percentage = (missing_count / row_count * 100) if row_count > 0 else 0.0
        valid_count = value_counts.valid_count
        is_empty = (missing_count == row_count)

        # Distinct non-empty values
        non_empty_values = [v for v in column_values if not cfg.is_missing_token(v, header)]
        distinct_count = len(set(non_empty_values))
        has_high_cardinality = (distinct_count / row_count > cfg.high_cardinality_threshold) if row_count > 0 else False

        # 3. Calculate statistics
        numeric_stats = None
        outlier_stats = None
        text_stats = None
        dt_stats = None
        identifier_stats = None

        if inference_res.semantic_role == SemanticRole.IDENTIFIER:
            # Suppress misleading measurement statistics for identifiers by default
            numeric_stats = None
            outlier_stats = None
            text_stats = calculate_text_stats(column_values)
            identifier_stats = {
                "distinct_count": distinct_count,
                "missing_count": missing_count,
                "duplicate_identifier_count": len(column_values) - missing_count - distinct_count,
                "is_candidate_key": (missing_count == 0 and distinct_count == row_count),
                "is_sequential": inference_res.evidence.get("is_sequential", False),
            }
        elif inferred_type in ("numeric", "mixed"):
            numeric_stats, outlier_stats = calculate_numeric_stats(column_values, header, cfg)
            text_stats = calculate_text_stats(column_values)
        elif inference_res.physical_type == PhysicalType.DATETIME or re.search(r"(?:^|[_ .\-/])(dt|d\.?o\.?a|d\.?o\.?d|dob|date|time|timestamp)(?:$|[_ .\-/])", header, re.IGNORECASE):
            dt_stats = calculate_datetime_stats(column_values, header, cfg, rows, headers)
            if dt_stats and (dt_stats.get("valid_timestamp_count", 0) > 0 or dt_stats.get("invalid_dates_count", 0) > 0 or dt_stats.get("ambiguous_dates_count", 0) > 0):
                inference_res.physical_type = PhysicalType.DATETIME
                inference_res.semantic_role = SemanticRole.TIMESTAMP
            text_stats = calculate_text_stats(column_values)
        else:
            text_stats = calculate_text_stats(column_values)

        most_frequent_values = text_stats["most_frequent_values"] if text_stats else []

        # 4. Data quality checks
        if missing_count > row_count * 0.5:
            quality_issues.append({
                "type": "high_missing_values",
                "column": header,
                "message": f"Column '{header}' has {missing_percentage:.1f}% missing values",
            })

        if has_high_cardinality and inferred_type not in ("numeric", "unknown") and inference_res.semantic_role != SemanticRole.IDENTIFIER:
            quality_issues.append({
                "type": "high_cardinality",
                "column": header,
                "message": f"Column '{header}' has {distinct_count} distinct values ({missing_percentage:.1f}% missing)",
            })

        if value_counts.invalid_count > 0:
            quality_issues.append({
                "type": "invalid_values",
                "column": header,
                "message": f"Column '{header}' contains {value_counts.invalid_count} values ({value_counts.invalid_rate * 100:.1f}%) violating declared {inferred_type} format",
            })

        if outlier_stats and outlier_stats["candidate_count"] > 0:
            quality_issues.append({
                "type": "outlier_candidates",
                "column": header,
                "message": f"Column '{header}' has {outlier_stats['candidate_count']} candidate outliers based on 1.5x IQR",
            })

        if dt_stats and dt_stats.get("conflicting_dates_count", 0) > 0:
            quality_issues.append({
                "type": "date_context_conflict",
                "column": header,
                "message": f"Column '{header}' has {dt_stats['conflicting_dates_count']} dates conflicting with contextual column evidence",
            })

        if dt_stats and dt_stats.get("unresolved_ambiguous_count", 0) > 0:
            quality_issues.append({
                "type": "ambiguous_dates_unresolved",
                "column": header,
                "message": f"Column '{header}' has {dt_stats['unresolved_ambiguous_count']} dates with unresolved format ambiguity",
            })

        column_profiles[header] = ColumnStats(
            name=header,
            inferred_type=inferred_type,
            missing_count=missing_count,
            missing_percentage=missing_percentage,
            valid_count=valid_count,
            distinct_count=distinct_count,
            most_frequent_values=most_frequent_values,
            is_empty=is_empty,
            numeric_stats=numeric_stats,
            text_stats=text_stats,
            has_high_cardinality=has_high_cardinality,
            physical_type=inference_res.physical_type.value,
            semantic_role=inference_res.semantic_role.value,
            type_confidence=inference_res.confidence,
            type_evidence=inference_res.evidence,
            value_counts=value_counts,
            datetime_stats=dt_stats,
            outlier_stats=outlier_stats,
            identifier_stats=identifier_stats,
        )

    # Dataset overview metrics
    numeric_columns = [h for h, col in column_profiles.items() if col.inferred_type == "numeric"]
    categorical_columns = [h for h, col in column_profiles.items() if col.inferred_type == "categorical"]
    text_columns = [h for h, col in column_profiles.items() if col.inferred_type in ("text", "url")]

    overview = {
        "rows": row_count,
        "columns": column_count,
        "headers": headers,
        "numeric_columns": len(numeric_columns),
        "categorical_columns": len(categorical_columns),
        "text_columns": len(text_columns),
        "duplicate_rows": excess_duplicates,
        "excess_duplicate_rows": excess_duplicates,
        "rows_in_duplicate_groups": rows_in_duplicate_groups,
        "unique_rows": unique_rows,
        "total_size_bytes": path_obj.stat().st_size if path_obj.exists() else 0,
        "file_type": loaded.file_type,
        "package_version": provenance["package_version"],
        "module_path": provenance["module_path"],
    }

    total_missing_cells = sum(col.missing_count for col in column_profiles.values())
    total_cells = row_count * column_count
    overall_missing_pct = (total_missing_cells / total_cells * 100) if total_cells > 0 else 0.0

    summary = {
        "total_rows": row_count,
        "total_columns": column_count,
        "total_missing_cells": total_missing_cells,
        "missing_percentage": overall_missing_pct,
        "duplicate_row_count": excess_duplicates,
        "rows_in_duplicate_groups": rows_in_duplicate_groups,
        "unique_rows": unique_rows,
    }

    if excess_duplicates > 0:
        quality_issues.append({
            "type": "duplicate_rows",
            "column": "all",
            "message": f"Dataset has {excess_duplicates} excess duplicate rows ({rows_in_duplicate_groups} rows in duplicate groups)",
        })

    # Relational & Cross-column structure analysis
    relational_analysis = _analyze_relational_structure(headers, rows, column_profiles, cfg)

    # Sort quality issues deterministically
    quality_issues.sort(key=lambda x: (x["type"], x.get("column", "")))

    return DatasetProfile(
        file_path=str(file_path),
        row_count=row_count,
        column_count=column_count,
        headers=headers,
        overview=overview,
        column_profiles=column_profiles,
        summary=summary,
        quality_issues=quality_issues,
        provenance=provenance,
        structural_diagnostics=structural_diags,
        relational_analysis=relational_analysis,
    )
