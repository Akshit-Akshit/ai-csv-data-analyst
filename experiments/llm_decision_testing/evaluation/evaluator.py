"""
Deterministic rule-based Evaluator for LLM analytical decisions.

Evaluates:
1. Schema & format contract validity.
2. Decision category correctness.
3. Analytical method suitability.
4. Profile evidence grounding.
5. Assumption, prerequisite & limitation awareness.
6. Adherence to non-destructive principles.
7. Appropriate abstention on insufficient/conflicting evidence.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from decision_schema import DecisionResponse, parse_and_validate_decision
from evaluation.metrics import CaseEvaluationResult
from profile_adapter import ProfileAdapter


class DecisionEvaluator:
    """Evaluates an LLM decision against expected behaviors and profile evidence."""

    def __init__(self, pass_threshold: float = 70.0):
        self.pass_threshold = pass_threshold

    def evaluate_case(
        self,
        case_id: str,
        case_name: str,
        raw_response: str,
        expected_behavior: dict[str, Any],
        profile_adapter: ProfileAdapter,
        latency_seconds: float = 0.0,
    ) -> CaseEvaluationResult:
        """
        Evaluate raw LLM output against deterministic rules and profile context.
        """
        failure_reasons: list[str] = []

        # 1. Schema Validation (20 points)
        decision_obj, schema_errors, raw_dict = parse_and_validate_decision(raw_response)
        is_valid_schema = (decision_obj is not None and len(schema_errors) == 0)
        schema_score = 20.0 if is_valid_schema else 0.0

        if not is_valid_schema:
            failure_reasons.append(f"Schema validation failed: {'; '.join(schema_errors[:3])}")
            return CaseEvaluationResult(
                case_id=case_id,
                case_name=case_name,
                is_valid_schema=False,
                schema_score=0.0,
                decision_category_score=0.0,
                method_suitability_score=0.0,
                evidence_grounding_score=0.0,
                awareness_score=0.0,
                non_destructive_score=0.0,
                abstention_score=0.0,
                total_score=0.0,
                passed=False,
                latency_seconds=latency_seconds,
                validation_errors=schema_errors,
                failure_reasons=failure_reasons,
                raw_response=raw_response,
                parsed_decision=raw_dict,
            )

        assert decision_obj is not None

        # 2. Decision Category Correctness (20 points)
        allowed_decisions = expected_behavior.get("allowed_decisions", [])
        actual_decision = decision_obj.decision.lower().strip()
        if actual_decision in [d.lower() for d in allowed_decisions]:
            decision_category_score = 20.0
        else:
            decision_category_score = 0.0
            failure_reasons.append(
                f"Decision '{actual_decision}' not in allowed decisions: {allowed_decisions}"
            )

        # 3. Method Suitability (15 points)
        method_suitability_score = 15.0
        selected_method = str(decision_obj.selected_method or "").lower()
        prohibited_methods = expected_behavior.get("prohibited_methods", [])

        # Check for prohibited methods
        for pm in prohibited_methods:
            if pm.lower() in selected_method or pm.lower() in decision_obj.rationale.lower():
                method_suitability_score = 0.0
                failure_reasons.append(f"Prohibited method/action detected: '{pm}'")
                break

        # Check prohibited conclusions
        prohibited_conclusions = expected_behavior.get("prohibited_conclusions", [])
        combined_text = (decision_obj.rationale + " " + " ".join(decision_obj.profile_evidence)).lower()
        for pc in prohibited_conclusions:
            if pc.lower() in combined_text:
                method_suitability_score = max(0.0, method_suitability_score - 10.0)
                failure_reasons.append(f"Prohibited conclusion detected: '{pc}'")

        # 4. Profile Evidence Grounding (15 points)
        evidence_grounding_score = 15.0
        profile_headers = set(profile_adapter.headers)

        # Check target columns actually exist in profile (unless case expects target_columns to be empty)
        if decision_obj.target_columns:
            for tc in decision_obj.target_columns:
                if tc not in profile_headers:
                    evidence_grounding_score = max(0.0, evidence_grounding_score - 5.0)
                    failure_reasons.append(f"Target column '{tc}' not found in profile headers")

        # Check required concepts in rationale or evidence
        required_concepts = expected_behavior.get("required_concepts", [])
        if required_concepts:
            found_count = sum(1 for c in required_concepts if c.lower() in combined_text)
            concept_ratio = found_count / len(required_concepts)
            if concept_ratio < 0.3:
                evidence_grounding_score = max(0.0, evidence_grounding_score - 7.0)
                failure_reasons.append(
                    f"Profile rationale lacks key analytical concepts (matched {found_count}/{len(required_concepts)})"
                )

        # Evidence list must not be empty
        if not decision_obj.profile_evidence:
            evidence_grounding_score = max(0.0, evidence_grounding_score - 5.0)
            failure_reasons.append("profile_evidence list is empty")

        # 5. Assumption, Prerequisite & Limitation Awareness (10 points)
        awareness_score = 10.0
        missing_sections = []
        if not decision_obj.assumptions:
            missing_sections.append("assumptions")
        if not decision_obj.prerequisites and actual_decision == "recommend_analysis":
            missing_sections.append("prerequisites")
        if not decision_obj.validation_steps:
            missing_sections.append("validation_steps")
        if not decision_obj.limitations:
            missing_sections.append("limitations")

        if missing_sections:
            deduction = min(8.0, len(missing_sections) * 2.5)
            awareness_score = max(0.0, awareness_score - deduction)
            failure_reasons.append(f"Incomplete analytical framing; missing: {', '.join(missing_sections)}")

        # 6. Adherence to Non-Destructive Principles (10 points)
        non_destructive_score = 10.0
        destructive_patterns = [
            r"\bdelete\s+(all\s+)?(outliers?|rows?|records?|column)\b",
            r"\bdrop\s+(all\s+)?(outliers?|rows?|records?|column)\b",
            r"\bremove\s+(all\s+)?(outliers?|rows?|column)\b",
            r"\bpurge\b",
        ]
        for pattern in destructive_patterns:
            if re.search(pattern, combined_text, re.IGNORECASE):
                # Check if it was advising AGAINST it
                if not re.search(r"\b(do\s+not|never|avoid|without|instead\s+of)\s+[^.]*" + pattern, combined_text, re.IGNORECASE):
                    non_destructive_score = 0.0
                    failure_reasons.append("Destructive recommendation detected (dropping/deleting raw observations)")
                    break

        # 7. Appropriate Abstention & Confidence Calibration (10 points)
        abstention_score = 10.0
        abstention_expected = expected_behavior.get("abstention_expected", False)
        if abstention_expected:
            if actual_decision in ("request_information", "abstain"):
                abstention_score = 10.0
            else:
                abstention_score = 0.0
                failure_reasons.append("Case expected abstention or request_information due to lack of evidence")
        else:
            if actual_decision == "abstain":
                abstention_score = 5.0  # partial credit for caution, but case had sufficient evidence

        # Total Score
        total_score = round(
            schema_score
            + decision_category_score
            + method_suitability_score
            + evidence_grounding_score
            + awareness_score
            + non_destructive_score
            + abstention_score,
            2,
        )

        passed = (total_score >= self.pass_threshold) and is_valid_schema

        return CaseEvaluationResult(
            case_id=case_id,
            case_name=case_name,
            is_valid_schema=is_valid_schema,
            schema_score=schema_score,
            decision_category_score=decision_category_score,
            method_suitability_score=method_suitability_score,
            evidence_grounding_score=evidence_grounding_score,
            awareness_score=awareness_score,
            non_destructive_score=non_destructive_score,
            abstention_score=abstention_score,
            total_score=total_score,
            passed=passed,
            latency_seconds=latency_seconds,
            validation_errors=schema_errors,
            failure_reasons=failure_reasons,
            raw_response=raw_response,
            parsed_decision=decision_obj.to_dict(),
        )

