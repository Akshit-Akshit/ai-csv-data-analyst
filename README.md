# AI CSV Data Analyst

A robust, deterministic CSV profiling engine that analyzes tabular datasets and generates comprehensive reports without modifying source data.

## Overview

The AI CSV Data Analyst is a Python-based data exploration tool designed to:
- **Stream and load** CSV files efficiently with automatic encoding detection
- **Profile columns** with type inference (numeric, categorical, text, URL, boolean)
- **Compute statistics** including mean, median, quartiles, and frequency distributions
- **Detect data quality issues** such as missing values, duplicates, and high cardinality
- **Output structured JSON profiles** for downstream analysis

The tool is built for accuracy and explainability, making it suitable for business intelligence, data science exploration, and validation workflows.

---

## Project Structure

```
ai-csv-data-analyst/
├── src/ai_csv_data_analyst/
│   ├── __init__.py          # Package initialization with public API
│   ├── __main__.py          # CLI entry point
│   ├── loader.py            # CSV file loading with encoding handling
│   ├── profiler.py          # Column profiling and statistics computation
│   └── app.py               # CLI interface
├── tests/                   # Test suite
│   ├── test_loader.py
│   ├── test_profiler.py
│   ├── test_app.py
│   └── test_demo_data.py
├── demo_data/               # Real-world validation datasets
├── pyproject.toml           # Project metadata and dependencies
├── requirements.txt         # Development dependencies
└── README.md
```

---

## Installation & Setup

### 1. Clone the Repository

```bash
git clone https://github.com/Akshit-Akshit/ai-csv-data-analyst.git
cd ai-csv-data-analyst
```

### 2. Create and Activate Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### 3. Install Development Dependencies

```bash
pip install -e ".[dev]"
```

Or install without dev dependencies:
```bash
pip install -e "."
```

### 4. Verify Installation

```bash
python -m ai_csv_data_analyst --help
```

---

## Command-Line Interface

### Basic Usage

```bash
# Profile a CSV file (formatted text output)
python -m ai_csv_data_analyst <path_to_csv>

# Output as JSON
python -m ai_csv_data_analyst <path_to_csv> --json

# Validate without profiling
python -m ai_csv_data_analyst <path_to_csv> --validate
```

### CLI Options

| Flag | Description |
| :--- | :--- |
| `--json` | Output complete profile as JSON |
| `--validate` | Quick validation: print file info without full profiling |
| `--help` | Display usage instructions |

### Usage Examples

```bash
# Formatted terminal profile
python -m ai_csv_data_analyst demo_data/boston.csv

# Machine-readable JSON output
python -m ai_csv_data_analyst demo_data/boston.csv --json

# Fast validation
python -m ai_csv_data_analyst demo_data/WA_Fn-UseC_-Telco-Customer-Churn.csv --validate
```

---

## Python API

```python
from ai_csv_data_analyst import load_csv, profile_csv

# Load a CSV file
loaded = load_csv("data.csv")

# Generate a profile
profile = profile_csv("data.csv")

# Access dataset metrics
print(f"Rows: {profile.row_count}")
print(f"Columns: {profile.column_count}")
print(f"Duplicates: {profile.overview.get('duplicate_rows', 0)}")

# Inspect column statistics
for col_name, stats in profile.column_profiles.items():
    print(f"Column '{col_name}':")
    print(f"  Type: {stats.inferred_type}")
    print(f"  Missing: {stats.missing_count} ({stats.missing_percentage:.1f}%)")
    if stats.numeric_stats:
        print(f"  Mean: {stats.numeric_stats['mean']:.2f}, Median: {stats.numeric_stats['median']:.2f}")
    if stats.text_stats:
        print(f"  Distinct values: {stats.text_stats['distinct_count']}")
```

---

## Output Schema

The profiler outputs a structured dictionary with the following hierarchy:

```json
{
  "file_path": "data.csv",
  "row_count": 506,
  "column_count": 14,
  "headers": ["CRIM", "ZN", ...],
  "overview": {
    "rows": 506,
    "columns": 14,
    "duplicate_rows": 0,
    "numeric_columns": 10,
    "categorical_columns": 0,
    "text_columns": 4,
    "total_size_bytes": 41359
  },
  "columns": {
    "CHAS": {
      "inferred_type": "numeric",
      "missing_count": 0,
      "missing_percentage": 0.0,
      "valid_count": 506,
      "distinct_count": 2,
      "numeric_stats": {
        "mean": 0.06917,
        "median": 0.0,
        "std_dev": 0.25399,
        "min": 0,
        "max": 1,
        "q1": 0.0,
        "q3": 0.0
      }
    }
  },
  "summary": {
    "total_missing_cells": 0,
    "missing_percentage": 0.0,
    "duplicate_row_count": 0,
    "unique_rows": 506
  },
  "quality_issues": []
}
```

---

## Profiling Capabilities

### 1. Type Inference

Automatically detects column types:
- **numeric**: Integer or float values
- **categorical**: Low-cardinality categories
- **text**: High-cardinality free text
- **url**: URL strings
- **boolean**: True/False or Yes/No values
- **mixed**: Multiple types present

### 2. Numeric Statistics

For numeric columns:
- Count, mean, median
- Sample standard deviation (Bessel-corrected)
- Min, max, Q1, Q3, range
- Zero and negative value counts

### 3. Categorical Statistics

For categorical/text columns:
- Distinct value count
- Top-10 frequency distribution (sorted by count desc, then alphabetically)
- Text length metrics

### 4. Data Quality Detection

The profiler identifies:
- **High missingness**: Columns with >50% missing values
- **High cardinality**: Categorical columns with >20% distinct values
- **Duplicate rows**: Identical full-row records
- **Empty columns**: Columns where all values are missing

---

## Real-World Validation

The profiler has been tested on diverse datasets including:

| Dataset | Size | Description |
| :--- | :--- | :--- |
| `boston.csv` | 41 KB | Boston Housing dataset |
| `WA_Fn-UseC_-Telco-Customer-Churn.csv` | 977 KB | Customer churn data |
| `creditcard-selected-columns.csv` | 2.5 MB | Credit card transactions |
| `netflix_titles.csv` | 3.4 MB | Netflix catalog |
| `adult.csv` | 4.1 MB | Census income data |
| `zomato.csv` | 547 MB | Restaurant reviews |

*All demo files are preserved unchanged.*

---

## Running Tests

```bash
# Run the complete test suite
pytest

# Run with verbose output
pytest -v

# Run specific test modules
pytest tests/test_profiler.py -v
pytest tests/test_loader.py -v
```

---

## Technical Details

### CSV Loading

- **Encoding**: Supports UTF-8 with BOM, UTF-8, Latin-1, and CP1252
- **Delimiter**: Auto-detects from common delimiters (`,`;`\t`|`)
- **Multi-line fields**: Preserves quoted fields with embedded newlines
- **Empty file handling**: Returns empty dataset structure

### Type Detection

- **Numeric parsing**: Handles currency symbols, thousand separators, and percentages
- **URL detection**: Identifies http/https/ftp URLs
- **Boolean recognition**: Detects true/false/yes/no variants
- **Mixed type handling**: Reports when multiple types exist in a column

### Statistics Computation

- **Quartiles**: Uses inclusive linear interpolation (Tukey boxplot method)
- **Deterministic sorting**: Results are reproducible (ties broken alphabetically)
- **Precision**: Maintains exact integer counts for reconciliation

---

## Limitations

1. **Memory**: Processes datasets in-memory using streaming file handles
2. **Bounded profiling**: Large datasets (>100 MB) can use `--max-rows` for sampling
3. **Encoding**: Specialized encodings should be converted to UTF-8 before ingestion

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## Contributing

Contributions are welcome!

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes
4. Push to the branch
5. Open a Pull Request

---

## Support

- **Documentation**: See [README.md](README.md) for usage examples
- **Testing**: Run `pytest` to execute the test suite
- **Issues**: Report bugs and feature requests via GitHub Issues
