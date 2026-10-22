"""
Read-only Profile Adapter for the AI CSV Data Analyst profiling engine.

This adapter extracts and structures profile information from:
1. An existing profile.json file.
2. A direct CSV file profiled via ai_csv_data_analyst.profiler.profile_csv.

Guarantees:
- Never modifies, mutates, or rewrites any CSV or JSON profile.
- Strictly preserves source profile values and statistics.
- Explicitly marks missing fields as 'unavailable' without fabricating data.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Optional


def load_profile_from_json(json_path: str | Path) -> dict[str, Any]:
    """Load a profile JSON file produced by the profiling engine."""
    path = Path(json_path)
    if not path.exists():
        raise FileNotFoundError(f"Profile JSON file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError(f"Profile JSON must be an object at root: {path}")

    return data


def generate_profile_from_csv(csv_path: str | Path) -> dict[str, Any]:
    """
    Generate a profile directly from a CSV file using the existing profiler.
    Imports existing profiler read-only without modifying any project files.
    """
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")

    # Ensure src directory is in sys.path
    project_root = Path(__file__).resolve().parent.parent.parent
    src_dir = project_root / "src"
    if str(src_dir) not in sys.path and src_dir.exists():
        sys.path.insert(0, str(src_dir))

    try:
        from ai_csv_data_analyst.profiler import profile_csv
    except ImportError as e:
        raise ImportError(
            f"Could not import 'ai_csv_data_analyst.profiler': {e}. "
            "Ensure existing project source is accessible in 'src/'."
        ) from e

    profile_obj = profile_csv(str(path))
    return profile_obj.to_dict()


class ProfileAdapter:
    """
    Read-only adapter that extracts focused metadata for LLM analytical decision making.
    """

    def __init__(self, raw_profile: dict[str, Any], source_ref: str = ""):
        self.raw_profile = raw_profile
        self.source_ref = source_ref
        self._normalize_columns()

    def _normalize_columns(self) -> None:
        """Normalize columns dictionary (handles 'columns' vs 'column_profiles')."""
        if "columns" in self.raw_profile and isinstance(self.raw_profile["columns"], dict):
            self.columns: dict[str, dict[str, Any]] = self.raw_profile["columns"]
        elif "column_profiles" in self.raw_profile and isinstance(self.raw_profile["column_profiles"], dict):
            self.columns = self.raw_profile["column_profiles"]
        else:
            self.columns = {}

    @property
    def row_count(self) -> int:
        return int(self.raw_profile.get("row_count", 0))

    @property
    def column_count(self) -> int:
        return int(self.raw_profile.get("column_count", len(self.columns)))

    @property
    def headers(self) -> list[str]:
        return list(self.raw_profile.get("headers", list(self.columns.keys())))

    @property
    def quality_issues(self) -> list[dict[str, Any]]:
        return list(self.raw_profile.get("quality_issues", []))

    @property
    def relational_analysis(self) -> dict[str, Any]:
        return dict(self.raw_profile.get("relational_analysis", {}))

    def get_column_summary(self, col_name: str) -> dict[str, Any]:
        """Extract relevant metrics for a single column."""
        if col_name not in self.columns:
            return {"column_name": col_name, "status": "unavailable"}

        c = self.columns[col_name]
        summary: dict[str, Any] = {
            "name": col_name,
            "inferred_type": c.get("inferred_type", "unavailable"),
            "physical_type": c.get("physical_type", "unavailable"),
            "semantic_role": c.get("semantic_role", "unavailable"),
            "missing_count": c.get("missing_count", "unavailable"),
            "missing_percentage": c.get("missing_percentage", "unavailable"),
            "distinct_count": c.get("distinct_count", "unavailable"),
            "has_high_cardinality": c.get("has_high_cardinality", False),
        }

        # Value classification
        val_cls = c.get("value_classification")
        if isinstance(val_cls, dict):
            summary["invalid_count"] = val_cls.get("invalid_count", 0)
            summary["invalid_rate"] = val_cls.get("invalid_rate", 0.0)
            summary["blank_missing_count"] = val_cls.get("blank_missing_count", 0)
            summary["sentinel_missing_count"] = val_cls.get("sentinel_missing_count", 0)

        # Numeric stats if available
        if c.get("numeric_stats"):
            ns = c["numeric_stats"]
            summary["numeric_stats"] = {
                "mean": ns.get("mean"),
                "std_dev": ns.get("std_dev"),
                "median": ns.get("median"),
                "min": ns.get("min"),
                "max": ns.get("max"),
                "q1": ns.get("q1"),
                "q3": ns.get("q3"),
            }

        # Outlier stats if available
        if c.get("outlier_stats"):
            os_data = c["outlier_stats"]
            summary["outlier_stats"] = {
                "candidate_count": os_data.get("candidate_count"),
                "candidate_rate": os_data.get("candidate_rate"),
                "lower_bound": os_data.get("lower_bound"),
                "upper_bound": os_data.get("upper_bound"),
                "method": os_data.get("method", "iqr"),
            }

        # Datetime stats if available
        if c.get("datetime_stats"):
            dt = c["datetime_stats"]
            summary["datetime_stats"] = {
                "valid_timestamp_count": dt.get("valid_timestamp_count"),
                "min_timestamp": dt.get("min_timestamp"),
                "max_timestamp": dt.get("max_timestamp"),
                "ambiguous_dates_count": dt.get("ambiguous_dates_count"),
                "invalid_dates_count": dt.get("invalid_dates_count"),
                "chosen_format": dt.get("chosen_format"),
                "date_range_is_definitive": dt.get("date_range_is_definitive"),
                "uncertainty": dt.get("uncertainty"),
            }

        # Identifier stats if available
        if c.get("identifier_stats"):
            id_data = c["identifier_stats"]
            summary["identifier_stats"] = {
                "is_candidate_key": id_data.get("is_candidate_key"),
                "is_sequential": id_data.get("is_sequential"),
                "duplicate_count": id_data.get("duplicate_identifier_count"),
            }

        # Top values / frequent values
        mfv = c.get("most_frequent_values") or []
        if mfv:
            summary["top_values"] = mfv[:5]

        # Specific quality issues for this column
        col_issues = [
            iss.get("message", iss.get("type", ""))
            for iss in self.quality_issues
            if iss.get("column") == col_name
        ]
        if col_issues:
            summary["quality_issues"] = col_issues

        return summary

    def build_llm_context(self, target_columns: Optional[list[str]] = None) -> str:
        """
        Build an analytical summary string formatted for LLM consumption.
        If target_columns is specified, focuses on those columns; otherwise includes all columns.
        """
        cols_to_include = target_columns if target_columns else self.headers

        lines = [
            "=== DATASET PROFILE SUMMARY ===",
            f"Source: {self.source_ref or self.raw_profile.get('file_path', 'unknown')}",
            f"Total Rows: {self.row_count}",
            f"Total Columns: {self.column_count}",
            f"Headers: {', '.join(self.headers)}",
        ]

        # Overview metadata
        overview = self.raw_profile.get("overview", {})
        if overview:
            lines.append(
                f"Duplicate Rows: {overview.get('duplicate_rows', overview.get('excess_duplicate_rows', 0))} "
                f"| Unique Rows: {overview.get('unique_rows', 'unavailable')}"
            )

        # Relational keys
        cand_keys = self.relational_analysis.get("candidate_single_keys", [])
        if cand_keys:
            lines.append(f"Candidate Single Keys: {', '.join(cand_keys)}")

        lines.append("\n=== COLUMN PROFILES ===")
        for col in cols_to_include:
            summary = self.get_column_summary(col)
            lines.append(f"\n[Column: {col}]")
            for k, v in summary.items():
                if k == "name":
                    continue
                if isinstance(v, dict):
                    v_str = ", ".join(f"{sub_k}: {sub_v}" for sub_k, sub_v in v.items() if sub_v is not None)
                    lines.append(f"  {k}: {{{v_str}}}")
                elif isinstance(v, list):
                    lines.append(f"  {k}: {v}")
                else:
                    lines.append(f"  {k}: {v}")

        # Quality issues summary
        if self.quality_issues:
            lines.append("\n=== DATASET QUALITY ISSUES ===")
            for iss in self.quality_issues[:15]:
                col_part = f"[{iss.get('column')}] " if iss.get("column") else ""
                lines.append(f"- {iss.get('type', 'issue')}: {col_part}{iss.get('message', '')}")

        return "\n".join(lines)


def load_adapter(source: str | Path) -> ProfileAdapter:
    """Helper to load either a JSON profile or a CSV file into a ProfileAdapter."""
    path = Path(source)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    if path.suffix.lower() == ".json":
        data = load_profile_from_json(path)
        return ProfileAdapter(data, source_ref=str(path))
    elif path.suffix.lower() == ".csv":
        data = generate_profile_from_csv(path)
        return ProfileAdapter(data, source_ref=str(path))
    else:
        # Default try json then error
        try:
            data = load_profile_from_json(path)
            return ProfileAdapter(data, source_ref=str(path))
        except Exception:
            raise ValueError(f"Unsupported file format for profile adapter: {path} (expected .json or .csv)")

