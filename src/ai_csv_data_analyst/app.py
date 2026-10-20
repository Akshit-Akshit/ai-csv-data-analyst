"""
AI CSV Data Analyst Application Entry Point

This module provides the main entry point for the AI CSV Data Analyst application.
It now includes CLI support for CSV profiling.

Features:
- Load and profile CSV files
- Output profile as JSON or formatted text
- Validate CSV files
"""

from __future__ import annotations

import json
import sys
from typing import Any

from ai_csv_data_analyst.loader import load_csv, LoadError
from ai_csv_data_analyst.profiler import profile_csv, DatasetProfile


def main() -> None:
    """
    Main entry point for the AI CSV Data Analyst application.
    
    Supports both:
    1. Running as module: python -m ai_csv_data_analyst
    2. Running as CLI: ai-csv-data-analyst [options] <csv_file>
    
    Usage:
        python -m ai_csv_data_analyst
            Or
        ai-csv-data-analyst <csv_file> [--json] [--validate]
    
    Args from CLI:
        csv_file: Path to the CSV file to profile (required for profiling mode)
        --json: Output profile as JSON (default: formatted text)
        --validate: Only validate and print file info, don't profile
        --help: Show this help message
    
    Returns:
        None
    """
    # Parse CLI arguments
    args: list[str] = sys.argv[1:]
    flags = {a for a in args if a.startswith("-")}
    positional = [a for a in args if not a.startswith("-")]
    
    # Check for JSON flag early
    output_json = "--json" in flags
    
    if not output_json:
        app_name = "AI CSV Data Analyst"
        print(f"{app_name}")
        print("Project foundation initialized.")
        print()
    
    if not args:
        # No arguments - show help and run basic version check
        print("Usage:")
        print("  python -m ai_csv_data_analyst")
        print("    Or:")
        print("  ai-csv-data-analyst <csv_file> [options]")
        print()
        print("Options:")
        print("  --json          Output profile as JSON")
        print("  --validate      Validate CSV file without profiling")
        print("  --help          Show this help message")
        print()
        
        # Run basic validation
        from ai_csv_data_analyst import __version__
        print(f"Version: {__version__}")
        return
    
    # Check for help flag
    if "--help" in flags or "-h" in flags:
        print("AI CSV Data Analyst - CSV Profiling Tool")
        print()
        print("Usage: ai-csv-data-analyst <csv_file> [options]")
        print()
        print("Options:")
        print("  --json          Output profile as JSON")
        print("  --validate      Validate CSV file without profiling")
        print("  --help          Show this help message")
        return
    
    if not positional:
        print("✗ Error: Missing required <csv_file> path.")
        return
        
    # Get the CSV file path
    csv_file = positional[0]
    
    # Check for validate flag
    validate_only = "--validate" in flags
    
    try:
        if validate_only:
            # Validate only
            loaded = load_csv(csv_file)
            if loaded.is_valid:
                print(f"✓ File validated: {csv_file}")
                print(f"  Rows: {loaded.row_count}")
                print(f"  Columns: {loaded.column_count}")
                print(f"  Headers: {', '.join(loaded.headers)}")
            else:
                print(f"✗ Validation failed: {csv_file}")
                if loaded.error:
                    print(f"  Error: {loaded.error.message}")
            return
        
        # Profile the CSV
        profile = profile_csv(csv_file)
        
        # Output format
        if output_json:
            print(json.dumps(profile.to_dict(), indent=2, ensure_ascii=False))
        else:
            # Formatted text output
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
    print()
    
    # Summary
    print("SUMMARY")
    print("-" * 40)
    summary = profile.summary
    print(f"  Total Missing Cells: {summary.get('total_missing_cells', 'N/A')}")
    print(f"  Missing Percentage:  {summary.get('missing_percentage', 'N/A'):.2f}%")
    print(f"  Unique Rows:         {summary.get('unique_rows', 'N/A')}")
    print()
    
    # Column profiles
    print("COLUMN PROFILES")
    print("-" * 40)
    for col_name in sorted(profile.column_profiles.keys()):
        col = profile.column_profiles[col_name]
        print(f"\n  [{col.inferred_type.upper()}] {col.name}")
        print(f"    Missing:        {col.missing_count} ({col.missing_percentage:.1f}%)")
        print(f"    Valid Values:   {col.valid_count}")
        print(f"    Distinct Values: {col.distinct_count}")
        
        if col.numeric_stats:
            stats = col.numeric_stats
            print(f"    Mean:            {stats.get('mean', 'N/A'):.2f}")
            print(f"    Median:          {stats.get('median', 'N/A'):.2f}")
            print(f"    Std Dev:         {stats.get('std_dev', 'N/A'):.2f}")
            print(f"    Min:             {stats.get('min', 'N/A')}")
            print(f"    Max:             {stats.get('max', 'N/A')}")
            print(f"    Q1:              {stats.get('q1', 'N/A'):.2f}")
            print(f"    Q3:              {stats.get('q3', 'N/A'):.2f}")
        
        if col.text_stats:
            stats = col.text_stats
            print(f"    Top Values:")
            for i, item in enumerate(stats.get('most_frequent_values', [])[:5], 1):
                print(f"      {i}. {item.get('value', 'N/A')[:30]}... ({item.get('count', 0)} occurrences)")
        
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
