# Experimental Profile Fixtures

This directory contains synthetic dataset profile fixtures used to deterministically evaluate LLM analytical decision-making capabilities.

## Isolation and Integrity Notice
- These fixtures are strictly self-contained within `experiments/llm_decision_testing/fixtures/`.
- No pre-existing production datasets or fixtures in the root repository were modified or replaced.
- All fixtures conform to the output schema produced by `ai_csv_data_analyst.profiler.DatasetProfile.to_dict()`.

## Fixture Descriptions

| Fixture | Scenario | Target Columns | Profile Attributes Tested |
| :--- | :--- | :--- | :--- |
| `case_01_profile.json` | High Cardinality | `Name` | 11,493 distinct strings, 0 missing, flagged with high cardinality |
| `case_02_profile.json` | Sales Outliers | `sales` | 215 IQR outlier candidates, positive skew |
| `case_03_profile.json` | Invalid Year Values | `Year` | 100 values (5.0%) violating integer format with violating sample tokens |
| `case_04_profile.json` | Missing Numeric Values | `income` | 600 missing values (15.0%) disaggregated by blank and sentinel counts |
| `case_05_profile.json` | Numeric Association | `ad_spend`, `revenue` | Two continuous numeric measures with distribution statistics |
| `case_06_profile.json` | Identifier vs Measurement | `Customer_ID` | Integer physical type with `identifier` semantic role and duplicate occurrences |
| `case_07_profile.json` | Insufficient Evidence | N/A | Inventory profile lacking marketing channel / ROI data |
| `case_08_profile.json` | Conflicting Metadata | `transaction_date` | Date format ambiguity (DD/MM vs MM/DD), conflicting dates count, withheld range |

