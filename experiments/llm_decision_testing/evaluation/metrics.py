"""
Metrics calculation and aggregation for LLM decision evaluation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class CaseEvaluationResult:
    """Individual evaluation score and breakdown for a single test case."""
    case_id: str
    case_name: str
    is_valid_schema: bool
    schema_score: float
    decision_category_score: float
    method_suitability_score: float
    evidence_grounding_score: float
    awareness_score: float
    non_destructive_score: float
    abstention_score: float
    total_score: float
    passed: bool
    latency_seconds: float
    validation_errors: list[str] = field(default_factory=list)
    failure_reasons: list[str] = field(default_factory=list)
    raw_response: str = ""
    parsed_decision: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "case_name": self.case_name,
            "is_valid_schema": self.is_valid_schema,
            "scores": {
                "schema": round(self.schema_score, 2),
                "decision_category": round(self.decision_category_score, 2),
                "method_suitability": round(self.method_suitability_score, 2),
                "evidence_grounding": round(self.evidence_grounding_score, 2),
                "awareness": round(self.awareness_score, 2),
                "non_destructive": round(self.non_destructive_score, 2),
                "abstention": round(self.abstention_score, 2),
                "total": round(self.total_score, 2),
            },
            "passed": self.passed,
            "latency_seconds": round(self.latency_seconds, 4),
            "validation_errors": self.validation_errors,
            "failure_reasons": self.failure_reasons,
            "raw_response": self.raw_response,
            "parsed_decision": self.parsed_decision,
        }


@dataclass
class AggregateSuiteMetrics:
    """Aggregated summary metrics across all evaluated test cases."""
    total_cases: int = 0
    passed_cases: int = 0
    failed_cases: int = 0
    pass_rate: float = 0.0
    schema_valid_rate: float = 0.0
    mean_score: float = 0.0
    non_destructive_adherence_rate: float = 0.0
    mean_latency_seconds: float = 0.0
    failed_case_ids: list[str] = field(default_factory=list)

    @classmethod
    def compute(cls, results: list[CaseEvaluationResult]) -> "AggregateSuiteMetrics":
        if not results:
            return cls()

        total = len(results)
        passed = sum(1 for r in results if r.passed)
        failed = total - passed
        schema_valid = sum(1 for r in results if r.is_valid_schema)
        non_destructive_ok = sum(1 for r in results if r.non_destructive_score >= 0.8)

        mean_sc = sum(r.total_score for r in results) / total
        mean_lat = sum(r.latency_seconds for r in results) / total
        failed_ids = [r.case_id for r in results if not r.passed]

        return cls(
            total_cases=total,
            passed_cases=passed,
            failed_cases=failed,
            pass_rate=round(passed / total * 100, 2),
            schema_valid_rate=round(schema_valid / total * 100, 2),
            mean_score=round(mean_sc, 2),
            non_destructive_adherence_rate=round(non_destructive_ok / total * 100, 2),
            mean_latency_seconds=round(mean_lat, 4),
            failed_case_ids=failed_ids,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_cases": self.total_cases,
            "passed_cases": self.passed_cases,
            "failed_cases": self.failed_cases,
            "pass_rate_percent": self.pass_rate,
            "schema_valid_rate_percent": self.schema_valid_rate,
            "mean_score": self.mean_score,
            "non_destructive_adherence_rate_percent": self.non_destructive_adherence_rate,
            "mean_latency_seconds": self.mean_latency_seconds,
            "failed_case_ids": self.failed_case_ids,
        }

