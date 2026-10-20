# AI CSV Data Analyst

A local-first analytical application that allows users to explore and profile CSV datasets deterministically without requiring SQL or Python.

## Project Overview

The AI CSV Data Analyst provides a high-performance, deterministic CSV profiling engine and loading pipeline designed to serve as the foundation for natural language data querying.

Key features implemented:
- **Robust CSV Loader** (`loader.py`):
  - Handles custom delimiters (auto-detection support)
  - UTF-8 and UTF-8 with BOM encodings
  - Multiline quoted fields and whitespace normalization in headers
  - Missing value preservation without data modification
- **Deterministic Profiling Engine** (`profiler.py`):
  - Dataset overview: total rows, columns, headers, file size, duplicate rows
  - Data quality metrics: missing value counts, percentages, anomaly indicators
  - Numeric column statistics: valid count, mean, median, std dev, min, max, Q1, Q3, range
  - Handles currency symbols (₹, $, €, £, ¥), thousand commas, and percentages
  - Categorical/text statistics: distinct count, deterministic frequency analysis (top 10 values)
  - Quality issue detection: high-missing (>50%), high cardinality (>20% distinct), duplicates
  - Typed dataclass models (`DatasetProfile`, `ColumnStats`, `LoadedCSV`) with JSON serialization
- **CLI & Module Interface** (`app.py`, `__main__.py`):
  - Formatted terminal output
  - Machine-readable JSON output with `--json`
  - Validation-only mode with `--validate`

## Current Implementation Status

### Implemented (v0.1.0)
- ✅ Project foundation, package structure, and `pyproject.toml`
- ✅ Dynamic CSV loading module (`ai_csv_data_analyst.loader`)
- ✅ Deterministic CSV profiling engine (`ai_csv_data_analyst.profiler`)
- ✅ CLI interface with `--json` and `--validate` options (`ai_csv_data_analyst.app`)
- ✅ Comprehensive test suite (46 automated tests, 100% pass rate)
- ✅ Real-world verification against `demo_data/amazon_extracted/amazon.csv` (1,465 rows, 16 columns)

### Planned (Future Phases)
- ⏳ Natural language query translation with task classification
- ⏳ DuckDB integration for out-of-core queries on large files
- ⏳ Interactive terminal / web UI

## Prerequisites

- Python 3.10 or newer
- Terminal/shell environment

## Installation and Setup

### 1. Clone the repository

```bash
git clone https://github.com/Akshit-Akshit/ai-csv-data-analyst.git
cd ai-csv-data-analyst
```

### 2. Create and Activate Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### 3. Install in Editable Mode with Dev Dependencies

```bash
pip install -e ".[dev]"
```

Alternatively, if running without an editable install:
```bash
export PYTHONPATH=src
```

## Running the Profiler

The application can be run directly via module execution or via the installed CLI entry point.

### Basic Profiling (Formatted Text Output)

```bash
# Using module execution:
python3 -m ai_csv_data_analyst path/to/your_file.csv

# Or using installed CLI command:
ai-csv-data-analyst path/to/your_file.csv
```

### JSON Output (Machine-Readable)

```bash
python3 -m ai_csv_data_analyst path/to/your_file.csv --json
```

### File Validation Only

```bash
python3 -m ai_csv_data_analyst path/to/your_file.csv --validate
```

### Help and Options

```bash
python3 -m ai_csv_data_analyst --help
```

Output:
```
AI CSV Data Analyst - CSV Profiling Tool

Usage: ai-csv-data-analyst <csv_file> [options]

Options:
  --json          Output profile as JSON
  --validate      Validate CSV file without profiling
  --help          Show this help message
```

## Python API Usage

You can also import and use the profiling and loading modules programmatically:

```python
from ai_csv_data_analyst import load_csv, profile_csv

# Load raw CSV
loaded = load_csv("data.csv")
print(f"Loaded {loaded.row_count} rows across {loaded.column_count} columns.")

# Generate structured profile
profile = profile_csv("data.csv")
print(f"Duplicate rows: {profile.overview['duplicate_rows']}")

# Inspect column statistics
for col_name, stats in profile.column_profiles.items():
    print(f"Column '{col_name}': {stats.inferred_type} ({stats.missing_percentage:.1f}% missing)")
    if stats.numeric_stats:
        print(f"  Mean: {stats.numeric_stats['mean']}, Median: {stats.numeric_stats['median']}")

# Export as dictionary / JSON
profile_dict = profile.to_dict()
```

## Real-World Demo Dataset Verification

The profiler was verified using the demo dataset included in `demo_data/amazon_extracted/amazon.csv`:

```bash
python3 -m ai_csv_data_analyst demo_data/amazon_extracted/amazon.csv
```

### Demo Dataset Profile Summary:
- **File**: `demo_data/amazon_extracted/amazon.csv` (4.7 MB)
- **Rows**: 1,465
- **Columns**: 16
- **Duplicate Rows**: 0
- **Missing Cells**: 2 (both in `rating_count`)
- **Inferred Types**:
  - `discounted_price`: `numeric` (Min: ₹39.0, Median: ₹799.0, Mean: ₹3,125.31, Max: ₹77,990.0)
  - `actual_price`: `numeric` (Min: ₹39.0, Median: ₹1,650.0, Mean: ₹5,444.99, Max: ₹139,900.0)
  - `discount_percentage`: `numeric` (Min: 0%, Median: 50.0%, Mean: 47.69%, Max: 94.0%)
  - `rating`: `numeric` (Min: 2.0, Median: 4.1, Mean: 4.10, Max: 5.0) — *gracefully handles real-world non-numeric noise entries such as `'|'`*
  - `rating_count`: `numeric` (Valid values: 1,463, Missing: 2, Min: 2.0, Max: 426,973.0)
  - `category`: `categorical` (211 distinct values)
  - `img_link`, `product_link`: `url`
  - `product_id`, `product_name`, `about_product`, `review_id`, `review_title`, `review_content`, `user_id`, `user_name`: `text`

### Sample JSON Output

```json
{
  "file_path": "demo_data/amazon_extracted/amazon.csv",
  "row_count": 1465,
  "column_count": 16,
  "headers": [
    "product_id",
    "product_name",
    "category",
    "discounted_price",
    "actual_price",
    "discount_percentage",
    "rating",
    "rating_count",
    "about_product",
    "user_id",
    "user_name",
    "review_id",
    "review_title",
    "review_content",
    "img_link",
    "product_link"
  ],
  "overview": {
    "rows": 1465,
    "columns": 16,
    "headers": [...],
    "numeric_columns": 5,
    "categorical_columns": 1,
    "text_columns": 10,
    "duplicate_rows": 0,
    "total_size_bytes": 4744481
  },
  "columns": {
    "discounted_price": {
      "inferred_type": "numeric",
      "missing_count": 0,
      "missing_percentage": 0.0,
      "valid_count": 1465,
      "distinct_count": 550,
      "most_frequent_values": [
        {"value": "₹199", "count": 53},
        {"value": "₹299", "count": 46}
      ],
      "is_empty": false,
      "numeric_stats": {
        "count": 1465,
        "mean": 3125.31,
        "median": 799.0,
        "std_dev": 6944.30,
        "min": 39.0,
        "max": 77990.0,
        "q1": 325.0,
        "q3": 1999.0,
        "range": 77951.0
      },
      "text_stats": {...},
      "has_high_cardinality": true
    }
  },
  "summary": {
    "total_rows": 1465,
    "total_columns": 16,
    "total_missing_cells": 2,
    "missing_percentage": 0.0085,
    "duplicate_row_count": 0,
    "unique_rows": 1465
  },
  "quality_issues": [
    {
      "type": "high_cardinality",
      "column": "product_name",
      "message": "Column 'product_name' has 1337 distinct values (0.0% missing)"
    }
  ]
}
```

## Running Tests

Run the full test suite using `pytest`:

```bash
# Run all tests
pytest

# Run tests with verbose output
pytest -v

# Run with test coverage
pytest -v --cov=src/ai_csv_data_analyst --cov-report=term-missing

# Run a specific test module
pytest tests/test_profiler.py -v
pytest tests/test_loader.py -v
pytest tests/test_demo_data.py -v
pytest tests/test_app.py -v
```

## Assumptions and Limitations

1. **In-Memory Loading**: Files are loaded into memory for parsing. Very large CSV files (e.g. > 1GB) may require future out-of-core engines like DuckDB (planned for Phase 3).
2. **Encodings**: Defaults to UTF-8 with automatic BOM stripping (`utf-8-sig`) and fallback to UTF-8. Non-standard encodings like ISO-8859-1 or Windows-1252 should be converted or handled explicitly.
3. **Delimiter Detection**: Comma `,` is the standard default; automatic delimiter sniffing is supported when requested.
4. **Data Integrity**: Missing values are preserved as empty strings. The loader and profiler never silently fabricate, drop, or alter source data.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
