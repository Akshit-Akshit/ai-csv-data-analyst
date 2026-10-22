"""
AI CSV Data Analyst Application Entry Point

Provides CLI commands and programmatic interface for CSV loading,
validation, profiling, and diagnostics.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from ai_csv_data_analyst.config import ProfilingConfig
from ai_csv_data_analyst.loader import LoadedCSV, LoadError, load_csv
from ai_csv_data_analyst.profiler import DatasetProfile, profile_csv


def main() -> None:
    """
    Main entry point for the AI CSV Data Analyst application.

    Supports:
        python -m ai_csv_data_analyst
        ai-csv-data-analyst <csv_file> [options]

    Options:
        --json                Output profile as JSON (default: formatted text)
        --validate            Validate CSV file without profiling
        --strict              Strict loading mode (reject structurally invalid rows)
        --tolerant            Tolerant loading mode (default)
        --delimiter <delim>   Column delimiter (or 'auto' for sniffing)
        --encoding <enc>      File encoding
        --missing-tokens <t>  Comma-separated custom missing tokens (e.g. 'NA,N/A,null')
        --help                Show help message
    """
    raw_args = sys.argv[1:]

    # Parse arguments
    output_json = "--json" in raw_args
    validate_only = "--validate" in raw_args
    strict_mode = "--strict" in raw_args
    show_help = "--help" in raw_args or "-h" in raw_args

    delimiter_val = ","
    encoding_val = None
    missing_tokens: list[str] = []
    per_col_missing_tokens: dict[str, tuple[str, ...]] = {}

    # Parse parameterized flags
    positional: list[str] = []
    i = 0
    while i < len(raw_args):
        arg = raw_args[i]
        if arg == "--delimiter" and i + 1 < len(raw_args):
            delimiter_val = raw_args[i + 1]
            i += 2
        elif arg == "--encoding" and i + 1 < len(raw_args):
            encoding_val = raw_args[i + 1]
            i += 2
        elif arg == "--missing-tokens" and i + 1 < len(raw_args):
            missing_tokens = [t.strip() for t in raw_args[i + 1].split(",") if t.strip()]
            i += 2
        elif arg == "--col-missing-tokens" and i + 1 < len(raw_args):
            col_specs = raw_args[i + 1].split(";")
            for cs in col_specs:
                if ":" in cs:
                    cname, ctokens = cs.split(":", 1)
                    per_col_missing_tokens[cname.strip()] = tuple(t.strip() for t in ctokens.split(",") if t.strip())
            i += 2
        elif arg.startswith("-"):
            i += 1
        else:
            positional.append(arg)
            i += 1

    if not output_json:
        app_name = "AI CSV Data Analyst"
        print(f"{app_name}")
        import ai_csv_data_analyst
        mod_file = getattr(ai_csv_data_analyst, "__file__", "unknown")
        print(f"Loaded from: {mod_file}")
        print("Project foundation initialized.")
        print()

    if not raw_args:
        print("Usage:")
        print("  python -m ai_csv_data_analyst")
        print("    Or:")
        print("  ai-csv-data-analyst <csv_file> [options]")
        print()
        print("Options:")
        print("  --json                Output profile as JSON")
        print("  --validate            Validate CSV file without profiling")
        print("  --strict              Enforce strict structural validation")
        print("  --delimiter <delim>   Specify column delimiter or 'auto'")
        print("  --encoding <enc>      Specify file encoding")
        print("  --missing-tokens <t>  Comma-separated missing value tokens")
        print("  --help                Show this help message")
        print()
        from ai_csv_data_analyst import __version__
        print(f"Version: {__version__}")
        return

    if show_help:
        print("AI CSV Data Analyst - CSV Profiling Tool")
        print()
        print("Usage: ai-csv-data-analyst <csv_file> [options]")
        print()
        print("Options:")
        print("  --json                Output profile as JSON")
        print("  --validate            Validate CSV file without profiling")
        print("  --strict              Enforce strict structural validation")
        print("  --delimiter <delim>   Specify column delimiter or 'auto'")
        print("  --encoding <enc>      Specify file encoding")
        print("  --missing-tokens <t>  Comma-separated missing value tokens")
        print("  --help                Show this help message")
        return

    if not positional:
        print("✗ Error: Missing required <csv_file> path.")
        return

    csv_file = positional[0]

    cfg = ProfilingConfig(
        strict_mode=strict_mode,
        encoding=encoding_val,
        delimiter=delimiter_val,
        missing_tokens=tuple(missing_tokens),
        per_column_missing_tokens=per_col_missing_tokens,
    )

    try:
        if validate_only:
            loaded = load_csv(csv_file, delimiter=delimiter_val, config=cfg, strict_mode=strict_mode)
            if loaded.is_valid:
                print(f"✓ File validated: {csv_file}")
                print(f"  Rows: {loaded.row_count}")
                print(f"  Columns: {loaded.column_count}")
                print(f"  Headers: {', '.join(loaded.headers)}")
                if loaded.structural_diagnostics:
                    print(f"  Structural Diagnostics: {len(loaded.structural_diagnostics)} issue(s) detected")
                    for d in loaded.structural_diagnostics[:5]:
                        print(f"    - [{d.severity.value}] {d.message}")
            else:
                print(f"✗ Validation failed: {csv_file}")
                if loaded.error:
                    print(f"  Error: {loaded.error.message}")
            return

        # Profile CSV
        profile = profile_csv(csv_file, config=cfg, delimiter=delimiter_val, strict_mode=strict_mode)

        if output_json:
            print(json.dumps(profile.to_dict(), indent=2, ensure_ascii=False))
        else:
            _print_profile(profile)

    except LoadError as e:
        print(f"✗ Error: {e.message}")
        if e.file_path:
            print(f"   File: {e.file_path}")
    except Exception as e:
        print(f"✗ Unexpected error: {type(e).__name__}: {e}")


def _print_profile(profile: DatasetProfile) -> None:
    """Print a formatted profile of a CSV dataset."""
    print("=" * 60)
    print(f"CSV Profile: {profile.file_path}")
    print("=" * 60)
    print()

    # Overview
    print("OVERVIEW")
    print("-" * 40)
    print(f"  Total Rows:    {profile.overview.get('rows', 'N/A')}")
    print(f"  Total Columns: {profile.overview.get('columns', 'N/A')}")
    print(f"  Duplicate Rows: {profile.overview.get('duplicate_rows', 0)}")
    if "rows_in_duplicate_groups" in profile.overview:
        print(f"  Rows in Duplicate Groups: {profile.overview['rows_in_duplicate_groups']}")
    if "file_type" in profile.overview:
        print(f"  File Classification:     {profile.overview['file_type']}")
    if "package_version" in profile.overview:
        print(f"  Engine Version:          {profile.overview['package_version']}")
    if "module_path" in profile.overview:
        print(f"  Source Module:           {profile.overview['module_path']}")
    print()

    # Summary
    print("SUMMARY")
    print("-" * 40)
    summary = profile.summary
    print(f"  Total Missing Cells: {summary.get('total_missing_cells', 'N/A')}")
    print(f"  Missing Percentage:  {summary.get('missing_percentage', 0.0):.2f}%")
    print(f"  Unique Rows:         {summary.get('unique_rows', 'N/A')}")
    print()

    # Relational Analysis
    if profile.relational_analysis:
        rel = profile.relational_analysis
        cand_keys = rel.get("candidate_single_keys", [])
        comp_keys = rel.get("candidate_composite_keys", [])
        if cand_keys or comp_keys:
            print("RELATIONAL STRUCTURE")
            print("-" * 40)
            if cand_keys:
                print(f"  Candidate Single Keys: {', '.join(cand_keys)}")
            if comp_keys:
                print(f"  Candidate Composite Keys: {', '.join('+'.join(p) for p in comp_keys)}")
            print()

    # Column profiles
    print("COLUMN PROFILES")
    print("-" * 40)
    for col_name in sorted(profile.column_profiles.keys()):
        col = profile.column_profiles[col_name]
        type_str = col.inferred_type.upper()
        role_str = f" / {col.semantic_role.upper()}" if col.semantic_role != "unknown" else ""
        print(f"\n  [{type_str}{role_str}] {col.name}")
        print(f"    Missing:        {col.missing_count} ({col.missing_percentage:.1f}%)")
        print(f"    Valid Values:   {col.valid_count}")
        print(f"    Distinct Values: {col.distinct_count}")

        if col.value_counts:
            vc = col.value_counts
            sentinel_msg = f", {vc.sentinel_missing_count} sentinel" if vc.sentinel_missing_count > 0 else ""
            print(f"    Reconciled:     {vc.valid_count} valid, {vc.missing_count} missing{sentinel_msg}, {vc.invalid_count} invalid (Invariant: {'✓' if vc.is_reconciled else '✗'})")

        if col.identifier_stats:
            istats = col.identifier_stats
            print(f"    Identifier:     Distinct: {istats['distinct_count']}, Duplicates: {istats['duplicate_identifier_count']}, Candidate Key: {'Yes' if istats['is_candidate_key'] else 'No'}")

        if col.numeric_stats:
            stats = col.numeric_stats
            print(f"    Mean:            {stats.get('mean', 'N/A'):.2f}")
            print(f"    Median:          {stats.get('median', 'N/A'):.2f}")
            print(f"    Std Dev:         {stats.get('std_dev', 'N/A'):.2f}")
            print(f"    Min:             {stats.get('min', 'N/A')}")
            print(f"    Max:             {stats.get('max', 'N/A')}")
            print(f"    Q1:              {stats.get('q1', 'N/A'):.2f}")
            print(f"    Q3:              {stats.get('q3', 'N/A'):.2f}")

        if col.outlier_stats and col.outlier_stats.get("candidate_count", 0) > 0:
            os_stats = col.outlier_stats
            print(f"    Outlier Candidates: {os_stats['candidate_count']} (IQR bounds: [{os_stats['lower_bound']:.2f}, {os_stats['upper_bound']:.2f}])")

        if col.datetime_stats:
            dt = col.datetime_stats
            if dt.get("date_range_is_definitive"):
                print(f"    Date Range:      {dt.get('min_timestamp', 'N/A')} to {dt.get('max_timestamp', 'N/A')} ({dt.get('coverage_days', 0)} days)")
                print(f"    Resolution:      {dt.get('format_resolution_method')} ({dt.get('chosen_format')})")
            else:
                print(f"    Date Range:      Unresolved ({dt.get('uncertainty', 'Ambiguous')})")
            if dt.get("ambiguous_dates_count", 0) > 0:
                print(f"    Ambiguous Dates: {dt['ambiguous_dates_count']} ({dt.get('contextually_resolved_count', 0)} contextually resolved, {dt.get('unresolved_ambiguous_count', 0)} unresolved)")
            if dt.get("conflicting_dates_count", 0) > 0:
                print(f"    Conflicts:       {dt['conflicting_dates_count']} cross-column conflicts")

        if col.text_stats:
            stats = col.text_stats
            top_vals = stats.get("most_frequent_values", [])
            if top_vals:
                print("    Top Values:")
                for i, item in enumerate(top_vals[:5], 1):
                    val_str = str(item.get("value", "N/A"))[:30]
                    print(f"      {i}. {val_str}... ({item.get('count', 0)} occurrences)")

        if col.has_high_cardinality:
            print(f"    ⚠ High Cardinality: {col.distinct_count} distinct values")

    # Quality Issues
    if profile.quality_issues:
        print()
        print("QUALITY ISSUES")
        print("-" * 40)
        for issue in profile.quality_issues:
            print(f"  ✗ [{issue.get('type', 'unknown')}] {issue.get('column', 'N/A')}: {issue.get('message', '')}")

    print()
    print("=" * 60)
    print("Profile complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
