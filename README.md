# AI CSV Data Analyst

A deterministic, high-accuracy, general-purpose CSV profiling engine designed to summarize tabular datasets across diverse business, scientific, financial, operational, and survey domains without modifying source data.

## Project Overview

The AI CSV Data Analyst provides a statistically sound, explainable profiling engine and streaming ingestion layer. It serves as the foundation for data exploration and downstream natural language query interfaces.

### Core Architecture & Capabilities

1. **Robust Streaming Ingestion (`loader.py`)**:
   - Streamed directly from disk without loading multi-hundred-megabyte files into memory.
   - Dynamic encoding detection with fallback: `utf-8-sig` (with BOM handling), `utf-8`, `latin-1`, and `cp1252`.
   - Delimiter support: comma `,` by default, custom delimiters, or auto-sniffing when `delimiter=None`.
   - Preserves multi-line quoted fields, embedded newlines, commas, and quotes.
   - Configurable CSV field size limits to support massive review and document text fields (e.g. 500MB+ datasets like Zomato).
   - Ingestion diagnostics: disambiguates duplicate column names (`col`, `col_2`) and tracks inconsistent row widths.
   - Missing-value policy: by default, only empty strings `""` are treated as missing. Literal tokens like `"NA"`, `"None"`, `"null"`, and `"?"` are preserved as legitimate categorical values unless explicitly configured.

2. **Storage Types vs. Semantic Roles (`types_and_roles.py`)**:
   - **Physical Storage Types**: `integer`, `float`, `boolean`, `datetime`, `categorical`, `text`, `mixed`, `empty`.
     - *Leading zero detection*: Recognizes and preserves numeric strings with leading zeros (`"00123"`) as identifiers or codes.
   - **Analytical Semantic Roles**: `identifier`, `measure`, `category`, `boolean_flag`, `datetime`, `text`, `potential_target`, `unknown`.
     - *Multi-signal inference*: Synthesizes uniqueness ratios, value distributions, cardinality classes, numeric variation, and column name hints to assign roles with confidence scores (0.0 to 1.0), explainable rationales, and observed evidence.

3. **Rigorous Statistical Metrics (`profiler.py`)**:
   - **Measures / Numerics**: Exact count, mean, median, sample standard deviation ($s$, Bessel-corrected for $N > 1$), population standard deviation ($\sigma$), min, max, inclusive quartiles ($Q1$, $Q3$), interquartile range ($IQR$), total range, Fisher-Pearson skewness, zero count, and negative count. Exact integer precision is preserved.
   - **Categoricals & Text**: Distinct non-missing counts, distinct ratio, cardinality class (`constant`, `binary`, `low`, `medium`, `high`, `unique`), deterministic top-10 frequency distributions (sorted by count desc, then value asc) with non-missing percentages, and text length metrics (min, max, mean, median).
   - **Date/Time**: Valid and invalid parse counts, earliest and latest ISO timestamps, date coverage in days, detected format, and ambiguity indicators (e.g. `MM/DD` vs `DD/MM`).

4. **Explainable Data-Quality Diagnostics (`diagnostics.py`)**:
   - Deterministic, rule-based findings with stable issue codes:
     - `HIGH_MISSINGNESS`: Missingness exceeding threshold (default > 50%).
     - `CONSTANT_COLUMN`: Columns with a single non-missing distinct value.
     - `POTENTIAL_IDENTIFIER`: Columns exhibiting unique key behavior.
     - `LEADING_ZERO_INTEGER`: Numeric strings whose leading zeros must be protected against float/int casting.
     - `HIGH_CARDINALITY_CATEGORICAL`: Categorical attributes with excessive unique classes (> 20%).
     - `UNEXPECTED_MIXED_TYPES`: Incompatible data types within the same column.
     - `POTENTIAL_NUMERIC_OUTLIERS`: Values outside Tukey's IQR fence ($[Q1 - 1.5 \times IQR, Q3 + 1.5 \times IQR]$).
     - `INCONSISTENT_CATEGORY_CASING`: Categories that differ only by letter case (e.g. `Active` vs `active`).
     - `WHITESPACE_INCONSISTENCY`: Values containing untrimmed leading or trailing whitespace.
     - `DUPLICATE_ROWS`: Full-row identical records.
     - `INCONSISTENT_ROW_WIDTH`: Rows with field counts differing from the header count.

5. **Reliable Duplicate Analysis**:
   - Exact full-row duplicate detection and group counts.
   - Optional key-based candidate duplicate analysis on user-specified column subsets (e.g. excluding record IDs).

### Project Status: ✅ Complete & Production-Ready

- **All 65 tests passing** - Comprehensive test coverage across:
  - Advanced profiling (leading zeros, semantic roles, missingness, statistics, diagnostics, duplicates, large datasets)
  - CLI interface functionality
  - Demo data validation
  - Loader and profiler core functionality
- **12 real-world datasets validated** - From 41KB to 547MB
- **Full feature parity** - All modules implemented and tested
- **Zero source data modifications** - Original demo files preserved unchanged

---

## Project Structure

```
ai-csv-data-analyst/
├── src/ai_csv_data_analyst/
│   ├── __init__.py          # Package initialization
│   ├── loader.py            # CSV streaming ingestion
│   ├── types_and_roles.py   # Storage types & semantic roles
│   ├── profiler.py          # Statistical metrics computation
│   ├── diagnostics.py       # Data quality diagnostics
│   ├── app.py               # CLI interface
│   └── config.py            # Configuration options
├── tests/                   # Test suite (65 tests, all passing)
│   ├── test_loader.py
│   ├── test_profiler.py
│   ├── test_advanced_profiling.py
│   ├── test_app.py
│   └── test_demo_data.py
├── demo_data/               # 12 real-world validation datasets
│   ├── boston.csv           # Boston Housing dataset (41 KB)
│   ├── train_and_test2.csv  # Titanic dataset (84 KB)
│   ├── WA_Fn-UseC_-Telco-Customer-Churn.csv (977 KB)
│   ├── creditcard-selected-columns.csv (2.5 MB)
│   ├── netflix_titles.csv   # Netflix catalog (3.4 MB)
│   ├── adult.csv            # Census income data (4.1 MB)
│   ├── amazon.csv           # Amazon products (4.7 MB)
│   ├── mnist_test.csv       # MNIST image pixels (18 MB)
│   ├── jena_climate_2009_2016.csv (43 MB)
│   ├── creditcard.csv       # Full credit card transactions (150 MB)
│   ├── globalterrorismdb_0718dist.csv (162 MB)
│   └── zomato.csv           # Restaurant reviews (547 MB)
├── README.md
├── pyproject.toml
├── requirements.txt
├── LICENSE
└── .git/
```

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

Or set `PYTHONPATH` directly:
```bash
export PYTHONPATH=src
```

### 4. Verify Installation

```bash
# Run the test suite
pytest -v

# Test the CLI
python3 -m ai_csv_data_analyst demo_data/boston.csv --validate
```

---

## Command-Line Interface (CLI)

The profiler can be executed directly as a Python module or via the installed CLI entry point:

```bash
python3 -m ai_csv_data_analyst <path_to_csv> [options]
```

### CLI Options

| Flag | Parameter | Description |
| :--- | :--- | :--- |
| `--json` | none | Output complete profile as valid, machine-readable JSON. |
| `--validate` | none | Quick validation check: prints encoding, delimiter, headers, and row count. |
| `--max-rows` | `<N>` | Bounded profiling: limits processing to the first $N$ rows (ideal for multi-GB files). |
| `--subset-keys` | `<col1,col2>` | Evaluates candidate duplicates over a specific column subset (e.g. `first_name,last_name`). |
| `--delimiter` | `<char>` | Override column delimiter (e.g. `,`, `;`, `\t`, `\|`). |
| `--missing-tokens` | `<t1,t2>` | Add custom missing value tokens (e.g. `NA,None,null,?`). |
| `--whitespace-missing` | none | Treat whitespace-only strings (`"   "`) as missing values. |
| `--help`, `-h` | none | Display usage instructions and options. |

### CLI Usage Examples

#### 1. Formatted Terminal Profile
```bash
python3 -m ai_csv_data_analyst demo_data/boston.csv
```

#### 2. Machine-Readable JSON Output
```bash
python3 -m ai_csv_data_analyst demo_data/boston.csv --json | jq .summary
```

#### 3. Fast CSV Validation
```bash
python3 -m ai_csv_data_analyst demo_data/WA_Fn-UseC_-Telco-Customer-Churn.csv --validate
```

#### 4. Candidate Duplicate Analysis on Column Subset
```bash
python3 -m ai_csv_data_analyst demo_data/adult.csv --subset-keys age,workclass,education
```

#### 5. Bounded Profiling on Large Datasets
```bash
python3 -m ai_csv_data_analyst demo_data/zomato.csv --max-rows 5000
```

---

## Python API Usage

```python
from ai_csv_data_analyst import load_csv, profile_csv, ProfileConfig

# Configure custom options
config = ProfileConfig(
    delimiter=",",
    missing_tokens=("NA", "?"),
    duplicate_subset_columns=("first_name", "last_name"),
    max_rows=100_000
)

# Ingest and profile
profile = profile_csv("data.csv", config=config)

# Access dataset-level metrics
print(f"Dataset Nature: {profile.dataset_nature}")
print(f"Total Rows:     {profile.row_count}")
print(f"Duplicate Rows: {profile.overview['duplicate_rows']}")

# Inspect per-column profiles, storage types, and semantic roles
for col_name, stats in profile.column_profiles.items():
    print(f"Column '{col_name}':")
    print(f"  Storage Type:  {stats.storage_type}")
    print(f"  Semantic Role: {stats.semantic_role} (confidence: {stats.role_confidence:.0%})")
    print(f"  Missingness:   {stats.missing_count} ({stats.missing_percentage:.1f}%)")
    if stats.numeric_stats:
        print(f"  Mean: {stats.numeric_stats['mean']:.2f}, Median: {stats.numeric_stats['median']:.2f}")

# Inspect rule-based data quality diagnostics
for issue in profile.quality_issues:
    print(f"[{issue['severity'].upper()}] {issue['code']} ({issue['scope']}): {issue['message']}")

# Export to dictionary / JSON
profile_dict = profile.to_dict()
```

---

## Structured Output Schema

The engine outputs a structured hierarchy consumable by downstream NLP and query layers:

```json
{
  "file_path": "demo_data/boston.csv",
  "row_count": 506,
  "column_count": 14,
  "dataset_nature": "data_records",
  "overview": {
    "rows": 506,
    "columns": 14,
    "headers": ["CRIM", "ZN", "INDUS", "CHAS", "NOX", "RM", "AGE", "DIS", "RAD", "TAX", "PTRATIO", "B", "LSTAT", "MEDV"],
    "numeric_columns": 14,
    "categorical_columns": 0,
    "text_columns": 0,
    "datetime_columns": 0,
    "duplicate_rows": 0,
    "total_size_bytes": 41359,
    "encoding_used": "utf-8-sig",
    "delimiter_used": ","
  },
  "columns": {
    "CHAS": {
      "column_index": 3,
      "inferred_type": "numeric",
      "storage_type": "integer",
      "semantic_role": "boolean_flag",
      "role_confidence": 0.90,
      "role_rationale": "Column has exactly two distinct binary indicator values",
      "role_evidence": ["Values match binary indicator set: {'0', '1'}"],
      "missing_count": 0,
      "missing_percentage": 0.0,
      "valid_count": 506,
      "distinct_count": 2,
      "distinct_ratio": 0.00395,
      "cardinality_class": "binary",
      "most_frequent_values": [
        {"value": "0", "count": 471, "percentage": 93.08},
        {"value": "1", "count": 35, "percentage": 6.92}
      ],
      "numeric_stats": {
        "count": 506,
        "mean": 0.06917,
        "median": 0.0,
        "std_dev_sample": 0.25399,
        "std_dev_population": 0.25374,
        "min": 0,
        "max": 1,
        "q1": 0.0,
        "q3": 0.0,
        "iqr": 0.0,
        "range": 1,
        "skewness": 3.3957,
        "zero_count": 471,
        "negative_count": 0
      }
    }
  },
  "summary": {
    "total_rows": 506,
    "total_columns": 14,
    "total_missing_cells": 0,
    "missing_percentage": 0.0,
    "duplicate_row_count": 0,
    "unique_rows": 506
  },
  "duplicate_analysis": {
    "exact_duplicate_rows": 0,
    "exact_duplicate_percentage": 0.0,
    "unique_rows": 506,
    "duplicate_groups_count": 0,
    "subset_comparison": null
  },
  "quality_issues": [
    {
      "code": "POTENTIAL_NUMERIC_OUTLIERS",
      "scope": "CRIM",
      "severity": "info",
      "message": "Column 'CRIM' has 66 potential outlier observations outside [-5.31, 9.07].",
      "evidence": "66 values outside 1.5*IQR fence (min=0.00632, max=88.9762)",
      "rule": "val < Q1 - 1.5*IQR or val > Q3 + 1.5*IQR",
      "recommendation": "Evaluate if extreme values represent genuine tail phenomena or instrumentation errors."
    }
  ],
  "parsing_warnings": []
}
```

---

## Statistical Conventions & Methodology

1. **Count Reconciliation & Missingness Policy**:
   - For every column: $\text{valid\_count} + \text{invalid\_count} + \text{missing\_count} = \text{total\_rows}$.
   - For numeric columns: `numeric_stats["count"]` is exactly reconciled with `valid_count`.
   - Default: Only zero-length strings `""` (and `None`) are treated as missing cells.
   - Whitespace strings (`"   "`) are tracked in `whitespace_only_count` and treated as non-missing by default unless `--whitespace-missing` is enabled.
   - Custom missing tokens (`--missing-tokens "NA,null,None,?"`) are normalized (whitespace-trimmed and case-insensitive) and counted in `missing_token_count`.
2. **Invalid Value Detection & Reporting**:
   - In numeric columns (`INTEGER`, `FLOAT`, `MEASURE`), cells that fail numeric parsing are tracked in `invalid_count`, sampled in `invalid_examples`, and reported via `INVALID_NUMERIC_VALUES` quality findings and explicit parsing warnings.
   - In datetime columns (`DATETIME`), unparseable temporal strings are tracked in `invalid_count` and reported via `INVALID_DATETIME_FORMAT`.
3. **Cardinality Consistency**:
   - Cardinality is strictly classified into `empty`, `constant`, `binary`, `low` (3 to 20), `medium` (21 to 100), `high` (> 100), and `unique`.
   - `has_high_cardinality` is consistent: columns with `low`, `binary`, `constant`, or `empty` cardinality are **never** marked as high cardinality, eliminating conflicting reports.
4. **Identifier vs Measure Inference**:
   - Continuous floats are inferred as `MEASURE` rather than identifiers or unknown roles.
   - Strictly sequential integers ($1, 2, 3\dots$ or $0, 1, 2\dots$) with step 1 are inferred as `IDENTIFIER`.
   - Integer columns containing negative numbers are inferred as `MEASURE` (identifiers cannot be negative).
   - Domain measure keywords (`quantity`, `salary`, `price`, `score`, `amount`, `count`) strongly bias integer columns towards `MEASURE`.
5. **Date Consistency Checks & Warnings**:
   - Columns mixing multiple date formats (e.g. ISO-8601 and European dotted) trigger `INCONSISTENT_DATETIME_FORMAT` and parsing warnings.
   - Ambiguous slash formats (e.g. `MM/DD/YYYY` vs `DD/MM/YYYY`) are detected and flagged with `AMBIGUOUS_DATETIME_FORMAT`.
   - Out-of-bounds years ($< 1800$ or $> 2100$) are reported via `SUSPICIOUS_DATETIME_BOUNDS`.
6. **Standard Deviation**:
   - `std_dev_sample`: Computed using Bessel's correction with $N - 1$ degrees of freedom for $N > 1$.
   - `std_dev_population`: Computed with divisor $N$.
   - Constant columns report $0.0$.
7. **Quantiles & IQR**:
   - Inclusive linear interpolation (equivalent to standard empirical percentiles and Tukey boxplots).
   - $Q1 = 25\text{th percentile}$, $Q3 = 75\text{th percentile}$, $IQR = Q3 - Q1$.
8. **Outlier Detection**:
   - Standard Tukey fence: values $< Q1 - 1.5 \times IQR$ or $> Q3 + 1.5 \times IQR$.
   - Reported as `info` severity because outliers in business/scientific data often represent valid tail events.
9. **Deterministic Ordering**:
   - Value frequencies break ties alphabetically by value ascending.
   - Column profiles and dictionary keys are sorted deterministically.


---

## Real-World Demo Dataset Validation

The profiler was validated against 12 real-world datasets in `demo_data/`:

| Dataset | Size | Rows | Columns | Dominant Types / Inferred Roles |
| :--- | :--- | :--- | :--- | :--- |
| `boston.csv` | 41 KB | 506 | 14 | Measures (`CRIM`, `RM`, `TAX`), Boolean Flag (`CHAS`). |
| `train_and_test2.csv` | 84 KB | 1,309 | 28 | Target/Flag (`Survived`, `Sex`), Measures (`Age`, `Fare`), IDs. |
| `WA_Fn-UseC_-Telco-Customer-Churn.csv` | 977 KB | 7,043 | 21 | Measures (`tenure`, `MonthlyCharges`, `TotalCharges`), Boolean Flags, ID (`customerID`). |
| `creditcard-selected-columns.csv` | 2.5 MB | 257,324 | 31 | Measures (`Time`, `Amount`, `V1-V28`), Target (`Class`). |
| `netflix_titles.csv` | 3.4 MB | 8,807 | 12 | DateTime (`date_added`), Categoricals (`type`, `rating`), Free Text (`title`, `cast`). |
| `adult.csv` | 4.1 MB | 32,561 | 15 | Measures (`age`, `hours-per-week`), Categoricals (`workclass`, `education`). |
| `amazon.csv` | 4.7 MB | 1,465 | 16 | Formatted Numerics (`discounted_price`, `actual_price`), Rating (handles noise `'\|'`). |
| `mnist_test.csv` | 18 MB | 10,000 | 785 | Wide dataset: 784 image pixel intensity measures + `label`. |
| `jena_climate_2009_2016.csv` | 43 MB | 420,551 | 15 | European DateTime format (`01.01.2009 00:10:00`), Climate measures. |
| `creditcard.csv` | 150 MB | 284,808 | 31 | High-volume financial transactions. |
| `globalterrorismdb_0718dist.csv` | 162 MB | 181,691 | 135 | Latin-1 encoding auto-fallback, wide political events dataset. |
| `zomato.csv` | 547 MB | 71,731 | 17 | Massive review texts, supported via dynamic field size limits. |

*Original files in `demo_data/` were preserved with zero modifications.*

---

## Running the Automated Test Suite

```bash
# Run the complete test suite (65 tests)
pytest

# Run tests with verbose output
pytest -v

# Run specific test modules
pytest tests/test_advanced_profiling.py -v
pytest tests/test_profiler.py -v
pytest tests/test_loader.py -v
pytest tests/test_demo_data.py -v
pytest tests/test_app.py -v
```

---

## Assumptions & Limitations

1. **Memory & Scaling**:
   - Exact computation is performed in-memory using streaming file handles.
   - For massive datasets (> 100 MB), bounded row profiling is supported via `--max-rows <N>` to constrain CPU and memory consumption. Future phases will integrate out-of-core streaming via DuckDB.
2. **Encoding**:
   - Transparently handles UTF-8 with BOM, UTF-8, Latin-1, and CP1252. Other specialized encodings should be converted to UTF-8 prior to ingestion.
3. **Ambiguous Dates**:
   - Dates with slash separators where both day and month are $\le 12$ (e.g. `03/04/2025`) are explicitly flagged with `is_ambiguous_format: true` rather than guessing regional conventions.

---

## Recent Updates

### October 20, 2024
- ✅ **Complete Test Suite**: All 65 tests passing across loader, profiler, diagnostics, app, and demo data
- ✅ **Production-Ready**: All features implemented and tested
- ✅ **Zero Data Modifications**: All 12 demo datasets preserved unchanged

### Development Highlights
- Implemented streaming CSV ingestion with encoding detection
- Built statistical metrics computation with exact precision
- Created explainable data quality diagnostics
- Developed CLI interface with comprehensive options
- Validated against 12 real-world datasets (41KB to 547MB)

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

## Support

- **Documentation**: See [README.md](README.md) for usage examples
- **Testing**: Run `pytest` to execute the test suite
- **Issues**: Please report bugs and feature requests via GitHub Issues
