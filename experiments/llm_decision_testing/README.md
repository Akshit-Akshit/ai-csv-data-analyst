# Isolated LLM Decision-Testing Environment for Qwen 3.5 0.8B

This directory contains a strictly isolated, standalone experimentation environment to evaluate how **Qwen 3.5 0.8B** interprets structured CSV profiling summaries and makes analytical decisions.

---

## 1. Purpose and Isolation Boundary

### Non-Negotiable Isolation Policy
- **Zero modification to existing codebase**: Pre-existing files in `src/`, `tests/`, `pyproject.toml`, root `README.md`, `VISION.md`, and test fixtures are completely untouched and treated as read-only.
- **Standalone dependencies**: The entire experiment runs with the Python 3.10+ standard library (`urllib.request`, `json`, `dataclasses`, `pathlib`). No packages need to be installed into the main project environment.
- **Auditable output storage**: All results and logs are stored exclusively under `experiments/llm_decision_testing/results/`.

---

## 2. Prerequisites and Local Model Configuration

Target Model: **Qwen 3.5 0.8B** served via local Ollama (or llama.cpp / vLLM).

The test suite connects to the OpenAI-compatible Ollama endpoint:

### Default Endpoint
- URL: `http://127.0.0.1:11434/v1`
- Model identifier: `qwen3.5:0.8b`
- Reasoning mode: `reasoning_effort: "none"` (disables internal reasoning loops for fast, structured JSON planning)

### Configuration Methods

#### Option A: `config.json`
Copy `config.example.json` to `config.json` inside this directory:
```bash
cp experiments/llm_decision_testing/config.example.json experiments/llm_decision_testing/config.json
```
Settings in `config.json`:
```json
{
  "base_url": "http://127.0.0.1:11434/v1",
  "model_name": "qwen3.5:0.8b",
  "api_key": "ollama",
  "timeout_seconds": 60.0,
  "temperature": 0.1,
  "max_tokens": 1024,
  "reasoning_effort": "none",
  "request_retries": 2
}
```

#### Option B: Environment Variables
Environment variables override `config.json`:
```bash
export LLM_BASE_URL="http://127.0.0.1:11434/v1"
export LLM_MODEL_NAME="qwen3.5:0.8b"
export LLM_API_KEY="ollama"
export LLM_TIMEOUT="60.0"
export LLM_TEMPERATURE="0.1"
export LLM_MAX_TOKENS="1024"
export LLM_REASONING_EFFORT="none"
```

---

## 3. How to Obtain Profile Data from the Existing Profiler

The experiment accepts either a pre-generated `profile.json` or a direct `.csv` file.

### Generating Profile JSON from Existing CLI
The verified CLI command to generate a full JSON profile from the existing engine is:
```bash
PYTHONPATH=src python3 -m ai_csv_data_analyst <path/to/dataset.csv> --json > profile.json
```

### Direct Profiling via Adapter
Alternatively, pass a CSV directly to `run_experiment.py --csv <file.csv>`. The read-only adapter `profile_adapter.py` will invoke the existing engine's `profile_csv()` without modifying source files.

---

## 4. Execution Commands

All commands should be executed from the project root or from this directory:

### Run Offline Validation Tests (Zero Network Mode)
Validates the decision contract schema, boolean/NaN rejection, profile adapter, fixture loading, and deterministic evaluation rules without contacting any LLM:
```bash
python3 experiments/llm_decision_testing/run_experiment.py --offline
```
Or run the unit test suite directly:
```bash
python3 -m unittest experiments/llm_decision_testing/tests/test_decision_testing.py
```

### Run Full 8-Case Evaluation Suite against Local Model
Connects to the local Qwen endpoint, queries all 8 test cases, scores the responses deterministically, and saves an audit report:
```bash
python3 experiments/llm_decision_testing/run_experiment.py --suite
```

### Run a Single Test Case
```bash
python3 experiments/llm_decision_testing/run_experiment.py --case case_02_sales_outliers
```

### Run an Ad-Hoc Decision Query on Profile JSON
```bash
python3 experiments/llm_decision_testing/run_experiment.py \
  --profile experiments/llm_decision_testing/fixtures/case_02_profile.json \
  --question "How should I handle the 215 outlier candidates in sales?"
```

### Run an Ad-Hoc Decision Query on a CSV Dataset
```bash
python3 experiments/llm_decision_testing/run_experiment.py \
  --csv demo_data/amazon_extracted/amazon.csv \
  --question "Are there any data quality risks in the actual_price or rating columns?"
```

---

## 5. Evaluation Framework and Scoring

### Deterministic Test Cases (`cases/decision_cases.json`)
The suite evaluates 8 distinct analytical scenarios:
1. `case_01_high_cardinality`: Tests that high cardinality in a Name column is understood as descriptive context, not automatically treated as a data defect to be deleted.
2. `case_02_sales_outliers`: Tests that 1.5x IQR outliers in sales are treated as statistical candidates for domain investigation, prohibiting automatic bulk deletion.
3. `case_03_invalid_year_values`: Tests that invalid year format entries are inspected and categorized before proposing transformations, avoiding blind median imputation.
4. `case_04_missing_numeric_values`: Tests that missing numeric values in income are assessed for missingness patterns, warning that mean imputation distorts variance.
5. `case_05_numeric_association`: Tests that ad_spend and revenue association is evaluated without claiming correlation implies causation.
6. `case_06_identifier_vs_measurement`: Tests that Customer_ID is recognized as an identifier rather than an arithmetic measurement.
7. `case_07_insufficient_evidence`: Tests that the model appropriately abstains or requests information when asked about marketing ROI with an inventory dataset.
8. `case_08_conflicting_metadata`: Tests that date format ambiguity and context conflicts in transaction_date are flagged before attempting time series decomposition.

### Scoring Breakdown (100 Total Points)
- **Schema Validity (20 pts)**: Adherence to the exact JSON Decision Contract.
- **Decision Category (20 pts)**: Selection of appropriate decision (`recommend_analysis`, `request_information`, `abstain`).
- **Method Suitability (15 pts)**: Appropriate analytical procedure, with strict penalties for prohibited/destructive methods.
- **Profile Evidence Grounding (15 pts)**: Accurate citation of column names and observed metrics from the profile.
- **Awareness (10 pts)**: Explicit documentation of assumptions, prerequisites, validation steps, and limitations.
- **Non-Destructive Principle (10 pts)**: Strict adherence to non-destructive analysis (no silent row or column drops).
- **Abstention & Calibration (10 pts)**: Proper abstention on insufficient/conflicting evidence.

**Pass Threshold**: Total score $\ge 70.0$ and schema validity $\ge 1.0$.

---

## 6. Root Cause Diagnostics & Benchmark Results

### Initial Failure Root Cause
1. **Ollama Reasoning Exhaustion**: `qwen3.5:0.8b` is configured in Ollama with thinking enabled by default (`capabilities: ["thinking"]`). Under unconstrained thinking, the internal reasoning loop consumed all 1024 completion tokens (`finish_reason: "length"`), leaving `message.content` completely empty (`""`).
2. **Missing Structured JSON Grammar**: Requests did not specify `"response_format": {"type": "json_object"}`.
3. **Missing Prompt Example**: Without a concrete JSON example demonstrating all 12 keys, smaller SLMs occasionally omitted trailing fields (`risk_level`, `confidence`).

### Solution Applied
- **Structured JSON Mode**: Added `"response_format": {"type": "json_object"}`.
- **Reasoning Effort Control**: Added `"reasoning_effort": "none"` to map to Ollama's `think: false`, disabling infinite thinking loops while producing direct analytical decisions.
- **Concrete Contract Example**: Included a fully populated 12-key example in `prompts/decision_system.txt`.
- **Strict Schema Enforcement**: Enhanced `decision_schema.py` to reject boolean, NaN, and Inf confidence values and detect multiple conflicting JSON objects.

### Benchmark Comparison

| Metric | Before (Baseline) | After (Fixed) |
| :--- | :--- | :--- |
| **Pass Rate** | 0% (0 / 8) | **100% (8 / 8)** |
| **Schema Valid Rate** | 0% (0 / 8) | **100% (8 / 8)** |
| **Mean Score** | 0.0 / 100 | **96.62 / 100** |
| **Non-Destructive Adherence** | 0% | **100%** |
| **Mean Latency** | 14.32s | **6.76s** |
