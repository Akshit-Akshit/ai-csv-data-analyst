# AI CSV Data Analyst

A local-first analytical application that allows users to explore CSV datasets through natural-language questions without requiring SQL or Python.

## Project Overview

The AI CSV Data Analyst is designed to be a local-first application that enables users to analyze CSV datasets using natural language. The long-term vision includes:

- A deterministic CSV profiler
- A lightweight local language model (potentially Laya) for task classification
- A typed task-planning layer
- A registry of trusted analytical operations
- DuckDB for scalable CSV processing
- Validation, execution, and result verification

## Current Implementation Status

### Implemented
- ✅ Project foundation and structure
- ✅ Basic application entry point (`main()` function)
- ✅ Test suite with unit tests
- ✅ Python project configuration with `pyproject.toml`

### Planned (Not Implemented)
- ❌ CSV profiling capabilities
- ❌ Natural language query processing
- ❌ Local language model integration (Laya)
- ❌ Task classification and execution
- ❌ Large-file processing with DuckDB
- ❌ User interface

## Prerequisites

- Python 3.10 or newer
- Git (for version control)
- A terminal/shell environment

## Installation

### Primary Method: Editable Install with Dev Dependencies

```bash
# Clone the repository
git clone <repository-url>
cd ai-csv-data-analyst

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/macOS, or .venv\Scripts\activate on Windows

# Install the package in editable mode with development dependencies
pip install -e ".[dev]"
```

**What this does:**
- Installs the package in editable mode (changes to source code are reflected immediately)
- Installs all dependencies from `pyproject.toml` including:
  - Runtime dependencies (currently none, but can be added)
  - Development dependencies: pytest, pytest-cov, pytest-xdist

### Alternative: Requirements.txt (for runtime-only installation)

```bash
# Only for runtime dependencies, does NOT install the package itself
pip install -r requirements.txt
```

**Note:** This method does NOT install the `ai-csv-data-analyst` package. Use only for development environments where the package is installed separately.

### Verification

```bash
# Verify package is installed and importable
python -c "import ai_csv_data_analyst; print(ai_csv_data_analyst.__version__)"

# Verify CLI entry point is available
ai-csv-data-analyst
```

## Running the Application

```bash
# Recommended: Run as a module
python -m ai_csv_data_analyst

# Direct script execution
python src/ai_csv_data_analyst/app.py

# Using the CLI entry point (if installed)
ai-csv-data-analyst
```

Expected output:
```
AI CSV Data Analyst
Project foundation initialized.
```

## Running Tests

```bash
# Run all tests with pytest
pytest -v

# Run with coverage report
pytest -v --cov=src/ai_csv_data_analyst --cov-report=term-missing

# Run specific test file
pytest tests/test_app.py -v
```

## Project Structure

```
ai-csv-data-analyst/
├── .gitignore              # Git ignore rules
├── LICENSE                 # MIT License
├── README.md               # This file
├── pyproject.toml          # Project configuration and metadata
├── requirements.txt        # Python dependencies (runtime + dev)
├── src/
│   └── ai_csv_data_analyst/
│       ├── __init__.py     # Package initialization
│       ├── __main__.py     # Module entry point for `python -m ai_csv_data_analyst`
│       └── app.py          # Application entry point with main() function
└── tests/
    └── test_app.py         # Unit tests
```

## Roadmap

### Phase 1: Foundation (Current)
- [x] Project structure and configuration
- [x] Basic application entry point
- [x] Test suite
- [ ] Documentation

### Phase 2: Core Capabilities
- [ ] CSV file loading and validation
- [ ] Basic data profiling (column types, null counts, value ranges)
- [ ] Simple query parsing and execution
- [ ] Result formatting and output

### Phase 3: Advanced Features
- [ ] Natural language query interface
- [ ] Task classification system
- [ ] DuckDB integration for large files
- [ ] Caching and performance optimization

### Phase 4: Production Readiness
- [ ] Comprehensive error handling
- [ ] Logging and monitoring
- [ ] Docker containerization
- [ ] API endpoints (optional)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues.

## Acknowledgments

- Python community for the robust ecosystem
- DuckDB for the excellent analytical database
