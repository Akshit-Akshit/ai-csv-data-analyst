"""
Decision contract and schema validation for LLM analytical decisions.

Contract specification:
{
  "objective": "string",
  "decision": "recommend_analysis | request_information | abstain",
  "selected_method": "string or null",
  "target_columns": ["string"],
  "profile_evidence": ["string"],
  "rationale": "string",
  "assumptions": ["string"],
  "prerequisites": ["string"],
  "validation_steps": ["string"],
  "limitations": ["string"],
  "risk_level": "low | medium | high",
  "confidence": 0.0 to 1.0
}

Validation Policy:
- Syntax validation, contract schema validation, and decision-quality evaluation
  are strictly separated.
- Rejects booleans, NaN, and Inf for numeric confidence values.
- Confidence must be an explicit numeric value in range [0.0, 1.0].
- Rejects multiple conflicting top-level JSON objects.
- Permissive for extra keys by default (saved in extra_fields), or strict mode flag.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from typing import Any, Optional


VALID_DECISIONS = {"recommend_analysis", "request_information", "abstain"}
VALID_RISK_LEVELS = {"low", "medium", "high"}

REQUIRED_FIELDS = {
    "objective": str,
    "decision": str,
    "selected_method": (str, type(None)),
    "target_columns": list,
    "profile_evidence": list,
    "rationale": str,
    "assumptions": list,
    "prerequisites": list,
    "validation_steps": list,
    "limitations": list,
    "risk_level": str,
    "confidence": (int, float),
}


@dataclass
class DecisionResponse:
    """Structured representation of an analytical decision by the LLM."""
    objective: str
    decision: str
    selected_method: Optional[str]
    target_columns: list[str] = field(default_factory=list)
    profile_evidence: list[str] = field(default_factory=list)
    rationale: str = ""
    assumptions: list[str] = field(default_factory=list)
    prerequisites: list[str] = field(default_factory=list)
    validation_steps: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    risk_level: str = "medium"
    confidence: float = 0.0
    extra_fields: dict[str, Any] = field(default_factory=dict)
    raw_json: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert decision response to a standard dictionary."""
        data: dict[str, Any] = {
            "objective": self.objective,
            "decision": self.decision,
            "selected_method": self.selected_method,
            "target_columns": self.target_columns,
            "profile_evidence": self.profile_evidence,
            "rationale": self.rationale,
            "assumptions": self.assumptions,
            "prerequisites": self.prerequisites,
            "validation_steps": self.validation_steps,
            "limitations": self.limitations,
            "risk_level": self.risk_level,
            "confidence": round(float(self.confidence), 4),
        }
        if self.extra_fields:
            data["extra_fields"] = self.extra_fields
        return data


def extract_json_candidate(raw_text: str) -> tuple[Optional[str], Optional[str]]:
    """
    Extract a single JSON candidate string from raw model output.
    Returns: (candidate_str, error_message)
    """
    if not raw_text or not raw_text.strip():
        return None, "Raw model response is empty"

    cleaned = raw_text.strip()

    # 1. Direct JSON check
    if cleaned.startswith("{") and cleaned.endswith("}"):
        # Check if there are multiple concatenated JSON objects e.g. {"a":1}{"b":2}
        try:
            decoder = json.JSONDecoder()
            obj, idx = decoder.raw_decode(cleaned)
            remaining = cleaned[idx:].strip()
            if remaining and remaining.startswith("{"):
                return None, "Multiple conflicting top-level JSON objects detected in response"
            return cleaned[:idx], None
        except json.JSONDecodeError as e:
            return None, f"Malformed JSON syntax: {str(e)}"

    # 2. Markdown fenced code blocks ```json ... ``` or ``` ... ```
    fence_pattern = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)
    fences = fence_pattern.findall(cleaned)
    if len(fences) > 1:
        return None, "Multiple markdown code blocks found; ambiguous response"
    if len(fences) == 1:
        fenced_content = fences[0].strip()
        first_b = fenced_content.find("{")
        last_b = fenced_content.rfind("}")
        if first_b != -1 and last_b != -1 and last_b > first_b:
            candidate = fenced_content[first_b : last_b + 1].strip()
            return candidate, None
        return None, "Markdown fence does not contain a JSON object"

    # 3. Outer curly braces in explanatory text
    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")
    if first_brace != -1 and last_brace == -1:
        return None, "Truncated or unclosed JSON object in raw model response"
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        candidate = cleaned[first_brace : last_brace + 1].strip()
        # Verify it decodes as a single object
        try:
            decoder = json.JSONDecoder()
            obj, idx = decoder.raw_decode(candidate)
            remaining = candidate[idx:].strip()
            if remaining and remaining.startswith("{"):
                return None, "Multiple conflicting JSON objects detected in response text"
            return candidate[:idx], None
        except json.JSONDecodeError:
            # Return the candidate to let parser report syntax error
            return candidate, None

    return None, "No JSON object found in raw model response"


def validate_decision_dict(data: dict[str, Any], strict: bool = False) -> list[str]:
    """
    Validate a parsed dictionary against the decision contract.
    Returns a list of error messages (empty list if completely valid).
    """
    errors: list[str] = []

    if not isinstance(data, dict):
        return ["Root response must be a JSON object (dictionary)"]

    # 1. Check required fields and basic types
    for key, expected_type in REQUIRED_FIELDS.items():
        if key not in data:
            errors.append(f"Missing required field: '{key}'")
            continue

        val = data[key]

        # Explicitly reject boolean for numeric confidence
        if key == "confidence" and isinstance(val, bool):
            errors.append(f"Field 'confidence' must be a numeric float/int, got boolean")
            continue

        # Check types
        if not isinstance(val, expected_type):
            expected_name = (
                "/".join(t.__name__ for t in expected_type)
                if isinstance(expected_type, tuple)
                else expected_type.__name__
            )
            errors.append(
                f"Field '{key}' expected type {expected_name}, got {type(val).__name__}"
            )

    # 2. Validate enumerated values
    if "decision" in data:
        decision = str(data.get("decision", "")).strip().lower()
        if decision not in VALID_DECISIONS:
            errors.append(
                f"Invalid decision value '{data.get('decision')}'. Must be one of: {sorted(VALID_DECISIONS)}"
            )

    if "risk_level" in data:
        risk = str(data.get("risk_level", "")).strip().lower()
        if risk not in VALID_RISK_LEVELS:
            errors.append(
                f"Invalid risk_level '{data.get('risk_level')}'. Must be one of: {sorted(VALID_RISK_LEVELS)}"
            )

    # 3. Validate confidence bounds [0.0, 1.0], reject NaN and Inf
    if "confidence" in data:
        conf = data.get("confidence")
        if isinstance(conf, bool) or not isinstance(conf, (int, float)):
            errors.append("Confidence must be a numeric value in range [0.0, 1.0]")
        elif math.isnan(conf) or math.isinf(conf):
            errors.append(f"Confidence value cannot be NaN or Infinite: {conf}")
        elif conf < 0.0 or conf > 1.0:
            errors.append(f"Confidence value {conf} out of bounds [0.0, 1.0]")

    # 4. Validate list fields contain strings
    for list_field in (
        "target_columns",
        "profile_evidence",
        "assumptions",
        "prerequisites",
        "validation_steps",
        "limitations",
    ):
        items = data.get(list_field)
        if isinstance(items, list):
            for i, item in enumerate(items):
                if not isinstance(item, str):
                    errors.append(
                        f"Element {i} in list '{list_field}' must be a string, got {type(item).__name__}"
                    )

    # 5. Semantic relationship checks
    decision = str(data.get("decision", "")).strip().lower()
    if decision == "recommend_analysis":
        method = data.get("selected_method")
        if not method or not str(method).strip():
            errors.append(
                "When decision is 'recommend_analysis', 'selected_method' must be a non-empty string"
            )

    # 6. Extra fields check (Strict mode policy)
    if strict:
        extra_keys = set(data.keys()) - set(REQUIRED_FIELDS.keys())
        if extra_keys:
            errors.append(f"Strict mode violation: unexpected extra fields: {sorted(extra_keys)}")

    return errors


def parse_and_validate_decision(
    raw_text: str, strict: bool = False
) -> tuple[Optional[DecisionResponse], list[str], Optional[dict[str, Any]]]:
    """
    Parse and validate raw model output into a DecisionResponse.

    Returns:
        (response_obj, validation_errors, raw_parsed_dict)
    """
    candidate, extract_err = extract_json_candidate(raw_text)
    if not candidate:
        return None, [extract_err or "No JSON object found in raw model response"], None

    try:
        parsed_dict = json.loads(candidate)
    except json.JSONDecodeError as e:
        return None, [f"JSON syntax error: {str(e)}"], None

    if not isinstance(parsed_dict, dict):
        return None, ["Parsed JSON root must be a dictionary"], None

    errors = validate_decision_dict(parsed_dict, strict=strict)

    # Collect extra fields
    known_keys = set(REQUIRED_FIELDS.keys())
    extra_fields = {k: v for k, v in parsed_dict.items() if k not in known_keys}

    if errors:
        return None, errors, parsed_dict

    # Construct clean DecisionResponse
    decision_obj = DecisionResponse(
        objective=str(parsed_dict.get("objective", "")).strip(),
        decision=str(parsed_dict.get("decision", "")).strip().lower(),
        selected_method=parsed_dict.get("selected_method"),
        target_columns=[str(c) for c in parsed_dict.get("target_columns", [])],
        profile_evidence=[str(e) for e in parsed_dict.get("profile_evidence", [])],
        rationale=str(parsed_dict.get("rationale", "")).strip(),
        assumptions=[str(a) for a in parsed_dict.get("assumptions", [])],
        prerequisites=[str(p) for p in parsed_dict.get("prerequisites", [])],
        validation_steps=[str(v) for v in parsed_dict.get("validation_steps", [])],
        limitations=[str(l) for l in parsed_dict.get("limitations", [])],
        risk_level=str(parsed_dict.get("risk_level", "medium")).strip().lower(),
        confidence=float(parsed_dict.get("confidence", 0.0)),
        extra_fields=extra_fields,
        raw_json=parsed_dict,
    )

    return decision_obj, [], parsed_dict
