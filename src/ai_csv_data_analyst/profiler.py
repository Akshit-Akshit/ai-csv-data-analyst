"""
CSV Profiling Engine

Generates structured profiles for CSV datasets including:
- Dataset overview (rows, columns, inferred types)
- Data quality metrics (missing values, duplicates)
- Numeric column statistics (mean, median, std, quartiles)
- Categorical column statistics (distinct values, frequencies)
- General column statistics

The profiler handles:
- Null/empty values (preserved without modification)
- Duplicate rows (counted and reported)
- Type inference (numeric, categorical, text, url, mixed, unknown)
- High-cardinality columns (frequency limited display)
- Empty columns (columns with all missing values)
- Deterministic results (sorted operations for reproducibility)
"""

from __future__ import annotations

import statistics
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ColumnStats:
    """Statistics for a single column."""
    name: str
    inferred_type: str  # 'numeric', 'categorical', 'text', 'url', 'mixed', 'unknown'
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


@dataclass
class DatasetProfile:
    """Complete profile for a CSV dataset."""
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
    
    def to_dict(self) -> dict[str, Any]:
        """Convert profile to dictionary for JSON serialization."""
        return {
            'file_path': self.file_path,
            'row_count': self.row_count,
            'column_count': self.column_count,
            'headers': self.headers,
            'overview': self.overview,
            'columns': {
                name: {
                    'inferred_type': profile.inferred_type,
                    'missing_count': profile.missing_count,
                    'missing_percentage': profile.missing_percentage,
                    'valid_count': profile.valid_count,
                    'distinct_count': profile.distinct_count,
                    'most_frequent_values': profile.most_frequent_values[:10],
                    'is_empty': profile.is_empty,
                    'numeric_stats': profile.numeric_stats,
                    'text_stats': profile.text_stats,
                    'has_high_cardinality': profile.has_high_cardinality
                }
                for name, profile in sorted(self.column_profiles.items())
            },
            'summary': self.summary,
            'quality_issues': self.quality_issues
        }


def parse_numeric(val: Any) -> float | None:
    """
    Attempt to parse a value as numeric, handling common formatting
    such as currency symbols, commas as thousand separators, and percentages.
    
    Returns float if successfully parsed, None otherwise.
    """
    if val is None:
        return None
    
    str_val = str(val).strip()
    if not str_val:
        return None
    
    # Check for direct float/int parsing first
    try:
        f = float(str_val)
        if not (f != f or f == float('inf') or f == float('-inf')):
            return f
    except ValueError:
        pass
    
    # Clean common currency symbols, thousand commas, and percent signs
    cleaned = (
        str_val.replace('₹', '')
               .replace('$', '')
               .replace('€', '')
               .replace('£', '')
               .replace('¥', '')
               .replace(',', '')
               .replace('%', '')
               .strip()
    )
    if not cleaned:
        return None
    
    try:
        f = float(cleaned)
        if not (f != f or f == float('inf') or f == float('-inf')):
            return f
    except ValueError:
        pass
        
    return None


def detect_value_type(val: str) -> str:
    """
    Detect the type of an individual string value.
    Returns: 'empty', 'url', 'numeric', 'boolean', 'text'
    """
    if not val or not val.strip():
        return 'empty'
    
    cleaned = val.strip()
    if cleaned.startswith(('http://', 'https://', 'ftp://')):
        return 'url'
    
    if parse_numeric(cleaned) is not None:
        return 'numeric'
        
    if cleaned.lower() in ('true', 'false', 'yes', 'no'):
        return 'boolean'
        
    return 'text'


def detect_column_type(values: list[str], column_name: str = "") -> str:
    """
    Detect the type of a column based on its list of string values.
    
    Args:
        values: List of string values for the column.
        column_name: Optional column name for context.
        
    Returns:
        Inferred type: 'numeric', 'categorical', 'text', 'url', 'mixed', 'unknown'
    """
    non_empty = [v for v in values if v is not None and str(v).strip() != '']
    if not non_empty:
        return 'unknown'
    
    total_non_empty = len(non_empty)
    numeric_count = sum(1 for v in non_empty if parse_numeric(v) is not None)
    url_count = sum(1 for v in non_empty if str(v).strip().startswith(('http://', 'https://', 'ftp://')))
    bool_count = sum(1 for v in non_empty if str(v).strip().lower() in ('true', 'false', 'yes', 'no'))
    
    # If URLs dominate
    if url_count / total_non_empty >= 0.5:
        return 'url'
    
    # If 100% numeric or overwhelmingly numeric with occasional noise (e.g. >= 80%)
    if numeric_count == total_non_empty:
        return 'numeric'
    if numeric_count / total_non_empty >= 0.8:
        return 'numeric'
    if numeric_count > 0 and (numeric_count / total_non_empty) >= 0.2:
        return 'mixed'
    
    # Check distinct values for categorical vs text
    distinct_count = len(set(non_empty))
    if bool_count / total_non_empty >= 0.8:
        return 'categorical'
        
    # If distinct values is small or ratio is low
    if distinct_count <= 20 or (distinct_count / total_non_empty <= 0.3):
        return 'categorical'
    
    return 'text'


def calculate_numeric_stats(values: list[str], column_name: str = "") -> dict[str, Any] | None:
    """
    Calculate numeric statistics for a column from valid numeric values.
    
    Args:
        values: List of string values (may include currency symbols, commas, nulls).
        column_name: Optional column name.
        
    Returns:
        Dictionary with numeric statistics or None if no valid numeric values.
    """
    numeric_values: list[float] = []
    for v in values:
        num = parse_numeric(v)
        if num is not None:
            numeric_values.append(num)
            
    if not numeric_values:
        return None
    
    count = len(numeric_values)
    mean_val = statistics.mean(numeric_values)
    median_val = statistics.median(numeric_values)
    min_val = min(numeric_values)
    max_val = max(numeric_values)
    std_val = statistics.stdev(numeric_values) if count > 1 else 0.0
    
    # Calculate quartiles deterministically
    if count >= 4:
        # Use inclusive method which aligns with standard quartile definitions (min, Q1, median, Q3, max)
        quantiles = statistics.quantiles(numeric_values, n=4, method='inclusive')
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
    else:  # count == 1
        q1_val = min_val
        q3_val = max_val
        
    return {
        'count': count,
        'mean': mean_val,
        'median': median_val,
        'std_dev': std_val,
        'min': min_val,
        'max': max_val,
        'q1': q1_val,
        'q3': q3_val,
        'range': max_val - min_val
    }


def calculate_text_stats(values: list[str]) -> dict[str, Any]:
    """
    Calculate categorical/text statistics for a column.
    
    Args:
        values: List of string values.
        
    Returns:
        Dictionary with distinct_count and most_frequent_values.
    """
    non_empty = [str(v) for v in values if v is not None and str(v).strip() != '']
    if not non_empty:
        return {
            'distinct_count': 0,
            'most_frequent_values': []
        }
    
    distinct_count = len(set(non_empty))
    counter = Counter(non_empty)
    # Deterministic sort: highest frequency first, then alphabetically by value
    most_frequent = sorted(
        counter.items(),
        key=lambda x: (-x[1], x[0])
    )
    
    return {
        'distinct_count': distinct_count,
        'most_frequent_values': [
            {'value': value, 'count': count}
            for value, count in most_frequent[:10]
        ]
    }


def profile_csv(file_path: str | Path) -> DatasetProfile:
    """
    Generate a structured profile for a CSV file.
    
    Args:
        file_path: Path to the CSV file to profile.
        
    Returns:
        DatasetProfile: Complete structured profile of the dataset.
    """
    from ai_csv_data_analyst.loader import load_csv, LoadError
    
    loaded = load_csv(file_path)
    
    if not loaded.is_valid:
        return DatasetProfile(
            file_path=str(file_path),
            row_count=loaded.row_count,
            column_count=loaded.column_count,
            headers=loaded.headers,
            overview={'rows': 0, 'columns': loaded.column_count, 'headers': loaded.headers, 'error': loaded.error.message if loaded.error else 'Unknown error'},
            column_profiles={},
            summary={},
            quality_issues=[]
        )
    
    headers = loaded.headers
    rows = loaded.rows
    row_count = loaded.row_count
    column_count = loaded.column_count
    
    # Handle empty dataset (no rows)
    if row_count == 0:
        col_profiles: dict[str, ColumnStats] = {}
        for h in headers:
            col_profiles[h] = ColumnStats(
                name=h,
                inferred_type='unknown',
                missing_count=0,
                missing_percentage=0.0,
                valid_count=0,
                distinct_count=0,
                most_frequent_values=[],
                is_empty=True,
                numeric_stats=None,
                text_stats={'distinct_count': 0, 'most_frequent_values': []},
                has_high_cardinality=False
            )
        return DatasetProfile(
            file_path=str(file_path),
            row_count=0,
            column_count=column_count,
            headers=headers,
            overview={
                'rows': 0,
                'columns': column_count,
                'headers': headers,
                'duplicate_rows': 0,
                'numeric_columns': 0,
                'categorical_columns': 0,
                'text_columns': 0
            },
            column_profiles=col_profiles,
            summary={
                'total_rows': 0,
                'total_columns': column_count,
                'total_missing_cells': 0,
                'missing_percentage': 0.0,
                'duplicate_row_count': 0,
                'unique_rows': 0
            },
            quality_issues=[]
        )
    
    # Detect duplicate rows deterministically
    row_signatures = [tuple(sorted(row.items())) for row in rows]
    signature_counts = Counter(row_signatures)
    duplicate_count = sum(c - 1 for c in signature_counts.values() if c > 1)
    unique_rows = row_count - duplicate_count
    
    column_profiles: dict[str, ColumnStats] = {}
    quality_issues: list[dict[str, Any]] = []
    
    for header in headers:
        column_values = [str(row.get(header, '')) for row in rows]
        
        # Missing values: empty string or whitespace
        missing_count = sum(1 for v in column_values if not v or v.strip() == '')
        missing_percentage = (missing_count / row_count * 100) if row_count > 0 else 0.0
        valid_count = row_count - missing_count
        is_empty = (missing_count == row_count)
        
        # Distinct non-empty values
        non_empty_values = [v for v in column_values if v and v.strip() != '']
        distinct_set = set(non_empty_values)
        distinct_count = len(distinct_set)
        
        # Inferred column type
        inferred_type = detect_column_type(column_values, header)
        
        # High cardinality threshold: > 20% distinct values
        has_high_cardinality = (distinct_count / row_count > 0.2) if row_count > 0 else False
        
        # Calculate statistics
        numeric_stats = None
        text_stats = None
        
        if inferred_type in ('numeric', 'mixed'):
            numeric_stats = calculate_numeric_stats(column_values, header)
            if numeric_stats is not None:
                # Also provide frequency info for numbers if mixed or categorical-like
                text_stats = calculate_text_stats(column_values)
            else:
                text_stats = calculate_text_stats(column_values)
        else:
            text_stats = calculate_text_stats(column_values)
            
        most_frequent_values = text_stats['most_frequent_values'] if text_stats else []
        
        # Data quality checks per column
        if missing_count > row_count * 0.5:
            quality_issues.append({
                'type': 'high_missing_values',
                'column': header,
                'message': f"Column '{header}' has {missing_percentage:.1f}% missing values"
            })
            
        if has_high_cardinality and inferred_type not in ('numeric', 'unknown'):
            quality_issues.append({
                'type': 'high_cardinality',
                'column': header,
                'message': f"Column '{header}' has {distinct_count} distinct values ({missing_percentage:.1f}% missing)"
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
            has_high_cardinality=has_high_cardinality
        )
    
    # Dataset overview metrics
    numeric_columns = [h for h, col in column_profiles.items() if col.inferred_type == 'numeric']
    categorical_columns = [h for h, col in column_profiles.items() if col.inferred_type == 'categorical']
    text_columns = [h for h, col in column_profiles.items() if col.inferred_type in ('text', 'url')]
    
    overview = {
        'rows': row_count,
        'columns': column_count,
        'headers': headers,
        'numeric_columns': len(numeric_columns),
        'categorical_columns': len(categorical_columns),
        'text_columns': len(text_columns),
        'duplicate_rows': duplicate_count,
        'total_size_bytes': Path(file_path).stat().st_size if Path(file_path).exists() else 0
    }
    
    total_missing_cells = sum(col.missing_count for col in column_profiles.values())
    total_cells = row_count * column_count
    overall_missing_pct = (total_missing_cells / total_cells * 100) if total_cells > 0 else 0.0
    
    summary = {
        'total_rows': row_count,
        'total_columns': column_count,
        'total_missing_cells': total_missing_cells,
        'missing_percentage': overall_missing_pct,
        'duplicate_row_count': duplicate_count,
        'unique_rows': unique_rows
    }
    
    if duplicate_count > 0:
        quality_issues.append({
            'type': 'duplicate_rows',
            'column': 'all',
            'message': f"Dataset has {duplicate_count} duplicate rows ({duplicate_count / row_count * 100:.1f}%)"
        })
        
    quality_issues.sort(key=lambda x: (x['type'], x.get('column', '')))
    
    return DatasetProfile(
        file_path=str(file_path),
        row_count=row_count,
        column_count=column_count,
        headers=headers,
        overview=overview,
        column_profiles=column_profiles,
        summary=summary,
        quality_issues=quality_issues
    )
