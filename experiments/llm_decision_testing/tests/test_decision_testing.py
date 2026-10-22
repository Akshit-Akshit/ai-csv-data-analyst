"""
Comprehensive Unit & Regression Tests for LLM Decision-Testing Framework.

Covers:
- Valid JSON objects
- JSON surrounded by explanatory text
- Markdown-fenced JSON
- Nested objects and escaped strings
- Missing required fields
- Missing or invalid confidence (strings, booleans, NaN, Inf, out-of-bounds)
- Invalid or truncated JSON
- Conflicting or multiple JSON objects
- Invalid enum values
- API errors, timeouts, and empty model responses
- Responses that parse correctly but fail semantic evaluation (e.g., destructive actions)
"""

from __future__ import annotations

import json
import math
import sys
import unittest
from pathlib import Path

# Ensure experiments/llm_decision_testing is in sys.path
TEST_DIR = Path(__file__).resolve().parent
EXP_DIR = TEST_DIR.parent
if str(EXP_DIR) not in sys.path:
    sys.path.insert(0, str(EXP_DIR))

from decision_schema import (
    DecisionResponse,
    extract_json_candidate,
    parse_and_validate_decision,
    validate_decision_dict,
)
from evaluation.evaluator import DecisionEvaluator
from evaluation.metrics import AggregateSuiteMetrics, CaseEvaluationResult
from profile_adapter import ProfileAdapter, load_adapter


VALID_DECISION_PAYLOAD = {
    "objective": "Investigate distribution and potential anomalies in sales",
    "decision": "recommend_analysis",
    "selected_method": "outlier_investigation",
    "target_columns": ["sales"],
    "profile_evidence": ["Column 'sales' has 215 outlier candidates via 1.5x IQR"],
    "rationale": "Statistical outliers should be inspected for domain context before transformation.",
    "assumptions": ["Sales distribution is right-skewed"],
    "prerequisites": ["Access to transaction details"],
    "validation_steps": ["Inspect top transactions exceeding upper bound"],
    "limitations": ["IQR threshold may flag legitimate high-value purchases"],
    "risk_level": "low",
    "confidence": 0.85,
}


class TestDecisionSchemaValidation(unittest.TestCase):
    """Test schema parsing, validation rules, and contract enforcement."""

    def test_valid_json_object(self):
        raw = json.dumps(VALID_DECISION_PAYLOAD)
        resp, errors, _ = parse_and_validate_decision(raw)
        self.assertIsNotNone(resp)
        self.assertEqual(len(errors), 0)
        self.assertEqual(resp.decision, "recommend_analysis")
        self.assertEqual(resp.confidence, 0.85)
        self.assertEqual(resp.risk_level, "low")

    def test_json_surrounded_by_explanatory_text(self):
        raw = f"Here is my analysis:\n{json.dumps(VALID_DECISION_PAYLOAD)}\nHope this helps!"
        resp, errors, _ = parse_and_validate_decision(raw)
        self.assertIsNotNone(resp)
        self.assertEqual(len(errors), 0)
        self.assertEqual(resp.selected_method, "outlier_investigation")

    def test_markdown_fenced_json(self):
        raw = f"```json\n{json.dumps(VALID_DECISION_PAYLOAD, indent=2)}\n```"
        resp, errors, _ = parse_and_validate_decision(raw)
        self.assertIsNotNone(resp)
        self.assertEqual(len(errors), 0)

    def test_nested_objects_and_escaped_strings(self):
        payload = dict(VALID_DECISION_PAYLOAD)
        payload["rationale"] = 'Reason with "quotes", newlines\nand backslashes \\.'
        payload["profile_evidence"] = ['Column "sales" [₹999 - ₹85,000] contains 15% \\ special chars']
        raw = json.dumps(payload)
        resp, errors, _ = parse_and_validate_decision(raw)
        self.assertIsNotNone(resp)
        self.assertEqual(len(errors), 0)
        self.assertIn("quotes", resp.rationale)

    def test_missing_required_fields(self):
        # Missing objective
        p1 = dict(VALID_DECISION_PAYLOAD)
        del p1["objective"]
        resp, errors, _ = parse_and_validate_decision(json.dumps(p1))
        self.assertIsNone(resp)
        self.assertTrue(any("objective" in e for e in errors))

        # Missing confidence
        p2 = dict(VALID_DECISION_PAYLOAD)
        del p2["confidence"]
        resp, errors, _ = parse_and_validate_decision(json.dumps(p2))
        self.assertIsNone(resp)
        self.assertTrue(any("confidence" in e for e in errors))

    def test_missing_or_invalid_confidence_types(self):
        # String confidence
        p_str = dict(VALID_DECISION_PAYLOAD)
        p_str["confidence"] = "0.85"
        resp, errors, _ = parse_and_validate_decision(json.dumps(p_str))
        self.assertIsNone(resp)
        self.assertTrue(any("confidence" in e.lower() for e in errors))

        # Percentage string
        p_pct = dict(VALID_DECISION_PAYLOAD)
        p_pct["confidence"] = "85%"
        resp, errors, _ = parse_and_validate_decision(json.dumps(p_pct))
        self.assertIsNone(resp)

    def test_boolean_confidence_rejected(self):
        # Python booleans are subclasses of int, must be explicitly rejected
        p_bool_true = dict(VALID_DECISION_PAYLOAD)
        p_bool_true["confidence"] = True
        resp, errors, _ = parse_and_validate_decision(json.dumps(p_bool_true))
        self.assertIsNone(resp)
        self.assertTrue(any("boolean" in e.lower() or "confidence" in e.lower() for e in errors))

        p_bool_false = dict(VALID_DECISION_PAYLOAD)
        p_bool_false["confidence"] = False
        resp, errors, _ = parse_and_validate_decision(json.dumps(p_bool_false))
        self.assertIsNone(resp)

    def test_nan_and_infinite_confidence_rejected(self):
        p_nan = dict(VALID_DECISION_PAYLOAD)
        p_nan["confidence"] = float("nan")
        # json.dumps converts NaN to NaN which is valid in Python json module
        raw = json.dumps(p_nan)
        resp, errors, _ = parse_and_validate_decision(raw)
        self.assertIsNone(resp)
        self.assertTrue(any("nan" in e.lower() for e in errors))

        p_inf = dict(VALID_DECISION_PAYLOAD)
        p_inf["confidence"] = float("inf")
        raw_inf = json.dumps(p_inf)
        resp, errors, _ = parse_and_validate_decision(raw_inf)
        self.assertIsNone(resp)
        self.assertTrue(any("inf" in e.lower() for e in errors))

    def test_out_of_bounds_confidence(self):
        # Negative
        p_neg = dict(VALID_DECISION_PAYLOAD)
        p_neg["confidence"] = -0.1
        resp, errors, _ = parse_and_validate_decision(json.dumps(p_neg))
        self.assertIsNone(resp)
        self.assertTrue(any("out of bounds" in e.lower() for e in errors))

        # Greater than 1.0
        p_high = dict(VALID_DECISION_PAYLOAD)
        p_high["confidence"] = 1.05
        resp, errors, _ = parse_and_validate_decision(json.dumps(p_high))
        self.assertIsNone(resp)
        self.assertTrue(any("out of bounds" in e.lower() for e in errors))

    def test_invalid_truncated_json(self):
        truncated = '{"objective": "Investigate sales", "decision": "recommend_analysis", "target_col'
        resp, errors, _ = parse_and_validate_decision(truncated)
        self.assertIsNone(resp)
        self.assertTrue(any("syntax error" in e.lower() or "malformed" in e.lower() or "truncated" in e.lower() or "unclosed" in e.lower() for e in errors))

    def test_conflicting_multiple_json_objects(self):
        multi = '{"objective": "One", "decision": "abstain"}\n{"objective": "Two", "decision": "recommend_analysis"}'
        candidate, err = extract_json_candidate(multi)
        self.assertIsNone(candidate)
        self.assertIn("multiple conflicting", err.lower())

    def test_invalid_enum_values(self):
        # Invalid decision
        p_dec = dict(VALID_DECISION_PAYLOAD)
        p_dec["decision"] = "execute_sql_query"
        resp, errors, _ = parse_and_validate_decision(json.dumps(p_dec))
        self.assertIsNone(resp)
        self.assertTrue(any("decision" in e.lower() for e in errors))

        # Invalid risk level
        p_risk = dict(VALID_DECISION_PAYLOAD)
        p_risk["risk_level"] = "critical_emergency"
        resp, errors, _ = parse_and_validate_decision(json.dumps(p_risk))
        self.assertIsNone(resp)
        self.assertTrue(any("risk_level" in e.lower() for e in errors))

    def test_empty_or_whitespace_response(self):
        resp, errors, _ = parse_and_validate_decision("")
        self.assertIsNone(resp)
        self.assertTrue(any("empty" in e.lower() for e in errors))

        resp, errors, _ = parse_and_validate_decision("   \n\t  ")
        self.assertIsNone(resp)


class TestSemanticEvaluation(unittest.TestCase):
    """Test deterministic evaluation rules and scoring logic."""

    def setUp(self):
        self.evaluator = DecisionEvaluator()
        self.fixture_adapter = load_adapter(EXP_DIR / "fixtures" / "case_02_profile.json")
        with open(EXP_DIR / "cases" / "expected_behaviors.json") as f:
            self.expectations = json.load(f)

    def test_compliant_response_passes(self):
        exp = self.expectations["case_02_sales_outliers"]
        res = self.evaluator.evaluate_case(
            case_id="case_02_sales_outliers",
            case_name="Sales IQR Outliers",
            raw_response=json.dumps(VALID_DECISION_PAYLOAD),
            expected_behavior=exp,
            profile_adapter=self.fixture_adapter,
            latency_seconds=1.2,
        )
        self.assertTrue(res.passed)
        self.assertGreaterEqual(res.total_score, 70.0)
        self.assertEqual(len(res.validation_errors), 0)

    def test_destructive_recommendation_fails(self):
        destructive = dict(VALID_DECISION_PAYLOAD)
        destructive["selected_method"] = "delete_outliers"
        destructive["rationale"] = "We must delete all outlier rows from the dataset."

        exp = self.expectations["case_02_sales_outliers"]
        res = self.evaluator.evaluate_case(
            case_id="case_02_sales_outliers",
            case_name="Sales IQR Outliers",
            raw_response=json.dumps(destructive),
            expected_behavior=exp,
            profile_adapter=self.fixture_adapter,
            latency_seconds=1.0,
        )
        self.assertFalse(res.passed)
        self.assertEqual(res.non_destructive_score, 0.0)
        self.assertTrue(any("prohibited" in r.lower() or "destructive" in r.lower() for r in res.failure_reasons))

    def test_abstention_on_insufficient_evidence(self):
        adapter_c7 = load_adapter(EXP_DIR / "fixtures" / "case_07_profile.json")
        exp_c7 = self.expectations["case_07_insufficient_evidence"]

        # Abstaining appropriately
        c7_payload = dict(VALID_DECISION_PAYLOAD)
        c7_payload["decision"] = "request_information"
        c7_payload["selected_method"] = None
        c7_payload["rationale"] = "Dataset profile has no marketing channel or ROI information."
        c7_payload["profile_evidence"] = ["Profile contains only inventory columns: item_sku, warehouse_location, units_in_stock"]

        res = self.evaluator.evaluate_case(
            case_id="case_07_insufficient_evidence",
            case_name="Insufficient Evidence",
            raw_response=json.dumps(c7_payload),
            expected_behavior=exp_c7,
            profile_adapter=adapter_c7,
            latency_seconds=0.8,
        )
        self.assertTrue(res.passed)
        self.assertEqual(res.abstention_score, 10.0)

    def test_failure_to_abstain_penalized(self):
        adapter_c7 = load_adapter(EXP_DIR / "fixtures" / "case_07_profile.json")
        exp_c7 = self.expectations["case_07_insufficient_evidence"]

        # Hallucinating analysis without data
        c7_bad = dict(VALID_DECISION_PAYLOAD)
        c7_bad["decision"] = "recommend_analysis"
        c7_bad["selected_method"] = "hallucinate_roi"
        c7_bad["rationale"] = "Channel with highest ROI is social media."

        res = self.evaluator.evaluate_case(
            case_id="case_07_insufficient_evidence",
            case_name="Insufficient Evidence",
            raw_response=json.dumps(c7_bad),
            expected_behavior=exp_c7,
            profile_adapter=adapter_c7,
            latency_seconds=0.8,
        )
        self.assertFalse(res.passed)
        self.assertEqual(res.abstention_score, 0.0)


if __name__ == "__main__":
    unittest.main()
