#!/usr/bin/env python3
"""
Standalone Runner for LLM Decision-Testing Experiment (Target: Qwen 3.5 0.8B).

Usage Examples:
  # 1. Run offline validation suite (no LLM connection needed, verifies code, adapter, schema, evaluator)
  python run_experiment.py --offline

  # 2. Run full evaluation suite against local Qwen server
  python run_experiment.py --suite

  # 3. Run a specific case from the evaluation suite
  python run_experiment.py --case case_02_sales_outliers

  # 4. Evaluate an ad-hoc profile JSON with a custom question
  python run_experiment.py --profile fixtures/case_02_profile.json --question "How should I handle outliers?"

  # 5. Evaluate an ad-hoc CSV file via the read-only profiler adapter
  python run_experiment.py --csv ../../demo_data/amazon_extracted/amazon.csv --question "What are the data quality risks?"

Guarantees:
- Never modifies any file outside experiments/llm_decision_testing/.
- Saves timestamped audit reports in experiments/llm_decision_testing/results/.
- Does not modify source datasets or profiler code.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# Ensure local experiment modules are importable
EXPERIMENT_DIR = Path(__file__).resolve().parent
if str(EXPERIMENT_DIR) not in sys.path:
    sys.path.insert(0, str(EXPERIMENT_DIR))

# Ensure root src/ is importable for read-only adapter
ROOT_DIR = EXPERIMENT_DIR.parent.parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path and SRC_DIR.exists():
    sys.path.insert(0, str(SRC_DIR))

from decision_schema import DecisionResponse, parse_and_validate_decision
from evaluation.evaluator import DecisionEvaluator
from evaluation.metrics import AggregateSuiteMetrics, CaseEvaluationResult
from llm_client import LLMClient, LLMConfig
from profile_adapter import ProfileAdapter, load_adapter


def load_system_prompt() -> str:
    """Load the decision-testing system prompt."""
    prompt_path = EXPERIMENT_DIR / "prompts" / "decision_system.txt"
    if not prompt_path.exists():
        raise FileNotFoundError(f"System prompt file not found at {prompt_path}")
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read().strip()


def load_cases_and_expectations() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Load evaluation test cases and ground-truth expected behaviors."""
    cases_file = EXPERIMENT_DIR / "cases" / "decision_cases.json"
    behaviors_file = EXPERIMENT_DIR / "cases" / "expected_behaviors.json"

    if not cases_file.exists():
        raise FileNotFoundError(f"Cases file not found: {cases_file}")
    if not behaviors_file.exists():
        raise FileNotFoundError(f"Expected behaviors file not found: {behaviors_file}")

    with open(cases_file, "r", encoding="utf-8") as f:
        cases = json.load(f)
    with open(behaviors_file, "r", encoding="utf-8") as f:
        expectations = json.load(f)

    return cases, expectations


def build_user_prompt(profile_context: str, question: str) -> str:
    """Combine structured profile context and user question into model prompt."""
    return (
        f"{profile_context}\n\n"
        f"=== USER ANALYTICAL QUESTION ===\n"
        f"\"{question}\"\n\n"
        f"Provide your analytical decision as a single valid JSON object adhering strictly to the Decision Contract."
    )


def save_results(results_data: dict[str, Any], prefix: str = "run") -> Path:
    """Save experiment run results to results/ with timestamp."""
    results_dir = EXPERIMENT_DIR / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = results_dir / f"{prefix}_{timestamp}.json"

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results_data, f, indent=2)

    return out_file


def run_offline_tests() -> bool:
    """
    Run self-contained offline tests verifying schema validation, adapter,
    case loading, and deterministic evaluation logic without network access.
    """
    print("\n" + "=" * 65)
    print("RUNNING OFFLINE VALIDATION SUITE (Zero Network Mode)")
    print("=" * 65)

    all_passed = True

    # 1. Test Schema Parsing and Validation
    print("\n[1/4] Testing decision_schema.py contract...")
    valid_sample = json.dumps({
        "objective": "Investigate sales outliers",
        "decision": "recommend_analysis",
        "selected_method": "outlier_investigation",
        "target_columns": ["sales"],
        "profile_evidence": ["Column 'sales' has 215 outlier candidates"],
        "rationale": "Outliers require domain inspection before transformation.",
        "assumptions": ["Sales follow skewed distribution"],
        "prerequisites": ["Access to transaction history"],
        "validation_steps": ["Inspect top 5 outlier transactions"],
        "limitations": ["IQR threshold may flag legitimate bulk orders"],
        "risk_level": "low",
        "confidence": 0.85,
    })

    resp, errs, _ = parse_and_validate_decision(valid_sample)
    if resp is not None and not errs:
        print("  ✓ Compliant decision payload validated successfully")
    else:
        print(f"  ✗ Compliant payload validation failed: {errs}")
        all_passed = False

    # Test invalid confidence
    invalid_conf = json.loads(valid_sample)
    invalid_conf["confidence"] = 1.5
    _, errs_conf, _ = parse_and_validate_decision(json.dumps(invalid_conf))
    if errs_conf:
        print("  ✓ Invalid confidence bounds properly detected")
    else:
        print("  ✗ Failed to reject invalid confidence bounds")
        all_passed = False

    # Test markdown fence stripping
    fenced_payload = f"```json\n{valid_sample}\n```"
    resp_fenced, errs_fenced, _ = parse_and_validate_decision(fenced_payload)
    if resp_fenced is not None and not errs_fenced:
        print("  ✓ Markdown fenced JSON extracted properly")
    else:
        print("  ✗ Failed to extract fenced JSON")
        all_passed = False

    # 2. Test Profile Adapter
    print("\n[2/4] Testing profile_adapter.py...")
    fixture_path = EXPERIMENT_DIR / "fixtures" / "case_02_profile.json"
    if fixture_path.exists():
        adapter = load_adapter(fixture_path)
        context = adapter.build_llm_context()
        if "sales" in context and "outlier_candidates" in context:
            print("  ✓ Profile adapter successfully parsed fixture metadata")
        else:
            print("  ✗ Adapter context missing expected metadata")
            all_passed = False
    else:
        print(f"  ✗ Fixture not found at {fixture_path}")
        all_passed = False

    # Test read-only CSV loading if demo CSV is present
    demo_csv = ROOT_DIR / "demo_data" / "amazon_extracted" / "amazon.csv"
    if demo_csv.exists():
        try:
            csv_adapter = load_adapter(demo_csv)
            if csv_adapter.row_count > 0:
                print(f"  ✓ Read-only CSV profiling adapter verified on {demo_csv.name} ({csv_adapter.row_count} rows)")
        except Exception as e:
            print(f"  ✗ CSV profiling adapter error: {e}")
            all_passed = False

    # 3. Test Cases and Fixtures Integrity
    print("\n[3/4] Verifying cases and fixtures integrity...")
    cases, expectations = load_cases_and_expectations()
    print(f"  Found {len(cases)} cases and {len(expectations)} expected behavior definitions")
    if len(cases) < 8:
        print(f"  ✗ Expected at least 8 test cases, found {len(cases)}")
        all_passed = False
    else:
        print(f"  ✓ All {len(cases)} required decision test cases loaded")

    for c in cases:
        c_id = c["id"]
        fix_rel = c["fixture_file"]
        fix_abs = EXPERIMENT_DIR / fix_rel
        if not fix_abs.exists():
            print(f"  ✗ Fixture file missing for case '{c_id}': {fix_rel}")
            all_passed = False
        if c_id not in expectations:
            print(f"  ✗ Missing expected behavior for case '{c_id}'")
            all_passed = False

    # 4. Test Deterministic Evaluator Logic
    print("\n[4/4] Testing evaluation/evaluator.py rules...")
    evaluator = DecisionEvaluator()

    # Test evaluating a compliant response for case_02
    exp_c2 = expectations.get("case_02_sales_outliers", {})
    adapter_c2 = load_adapter(EXPERIMENT_DIR / "fixtures" / "case_02_profile.json")
    eval_res_pass = evaluator.evaluate_case(
        case_id="case_02_sales_outliers",
        case_name="Sales IQR Outliers",
        raw_response=valid_sample,
        expected_behavior=exp_c2,
        profile_adapter=adapter_c2,
        latency_seconds=0.1,
    )
    if eval_res_pass.passed and eval_res_pass.total_score >= 70.0:
        print(f"  ✓ Evaluator correctly passed compliant response (Score: {eval_res_pass.total_score}/100)")
    else:
        print(f"  ✗ Compliant response failed evaluation: {eval_res_pass.failure_reasons}")
        all_passed = False

    # Test evaluating a destructive non-compliant response (asserting deletion of outliers)
    destructive_sample = json.dumps({
        "objective": "Clean dataset",
        "decision": "recommend_analysis",
        "selected_method": "delete_outliers",
        "target_columns": ["sales"],
        "profile_evidence": ["215 outliers"],
        "rationale": "We must delete all outlier rows to clean the dataset.",
        "assumptions": [],
        "prerequisites": [],
        "validation_steps": [],
        "limitations": [],
        "risk_level": "high",
        "confidence": 0.9,
    })
    eval_res_fail = evaluator.evaluate_case(
        case_id="case_02_sales_outliers",
        case_name="Sales IQR Outliers",
        raw_response=destructive_sample,
        expected_behavior=exp_c2,
        profile_adapter=adapter_c2,
        latency_seconds=0.1,
    )
    if not eval_res_fail.passed and eval_res_fail.non_destructive_score == 0.0:
        print(f"  ✓ Evaluator correctly penalized destructive response (Score: {eval_res_fail.total_score}/100)")
    else:
        print(f"  ✗ Evaluator failed to penalize destructive response")
        all_passed = False

    # 5. Run formal unit tests
    print("\n[5/5] Running unit and regression tests from tests/test_decision_testing.py...")
    import unittest
    suite = unittest.defaultTestLoader.discover(str(EXPERIMENT_DIR / "tests"))
    runner = unittest.TextTestRunner(verbosity=1)
    res = runner.run(suite)
    if not res.wasSuccessful():
        print("  ✗ Unit test suite reported failures")
        all_passed = False
    else:
        print(f"  ✓ All {res.testsRun} formal unit tests passed cleanly")

    print("\n" + "=" * 65)
    if all_passed:
        print("✓ ALL OFFLINE TESTS PASSED (100% Deterministic Compliance)")
    else:
        print("✗ OFFLINE TESTS ENCOUNTERED FAILURES")
    print("=" * 65)

    return all_passed


def run_live_case(
    case: dict[str, Any],
    expected: dict[str, Any],
    llm_client: LLMClient,
    evaluator: DecisionEvaluator,
    system_prompt: str,
) -> CaseEvaluationResult:
    """Execute a single test case against the configured live LLM."""
    case_id = case["id"]
    case_name = case["name"]
    fixture_path = EXPERIMENT_DIR / case["fixture_file"]
    question = case["question"]

    adapter = load_adapter(fixture_path)
    context = adapter.build_llm_context(target_columns=case.get("target_columns"))
    user_prompt = build_user_prompt(context, question)

    print(f"\nEvaluating: [{case_id}] {case_name}")
    print(f"  Question: {question[:80]}...")

    raw_response = ""
    latency = 0.0
    try:
        raw_response, latency, meta = llm_client.generate_decision(system_prompt, user_prompt)
        print(f"  Response received in {latency:.2f}s (Tokens: {meta.get('usage', {}).get('total_tokens', 'N/A')})")
    except Exception as e:
        print(f"  ✗ LLM request failed: {e}")
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
            latency_seconds=latency,
            validation_errors=[f"Inference error: {str(e)}"],
            failure_reasons=[str(e)],
            raw_response="",
            parsed_decision=None,
        )

    # Evaluate decision
    res = evaluator.evaluate_case(
        case_id=case_id,
        case_name=case_name,
        raw_response=raw_response,
        expected_behavior=expected,
        profile_adapter=adapter,
        latency_seconds=latency,
    )

    status_symbol = "✓ PASS" if res.passed else "✗ FAIL"
    print(f"  Result: {status_symbol} (Total Score: {res.total_score}/100)")
    if res.failure_reasons:
        for r in res.failure_reasons[:2]:
            print(f"    - {r}")

    return res


def run_full_suite(config_path: Optional[str] = None) -> int:
    """Execute all 8 evaluation cases against the configured live model."""
    print("\n" + "=" * 65)
    print("RUNNING LLM DECISION TEST SUITE (Live Inference Mode)")
    print("=" * 65)

    system_prompt = load_system_prompt()
    cases, expectations = load_cases_and_expectations()
    config = LLMConfig.load(config_path)
    client = LLMClient(config)
    evaluator = DecisionEvaluator()

    print(f"Target Model:  {config.model_name}")
    print(f"Endpoint:      {config.base_url}")
    print(f"Temperature:   {config.temperature}")
    print(f"Max Tokens:    {config.max_tokens}")

    # Health check
    healthy, msg, models = client.check_server_health()
    if not healthy:
        print(f"\n[Error] Inference server health check failed at {config.base_url}")
        print(f"Details: {msg}")
        print("\nEnsure Qwen 3.5 0.8B is running or use '--offline' to validate without live server.")
        return 1

    print(f"Server Status: Healthy ({msg})")
    if models:
        print(f"Available Models: {', '.join(models[:5])}")

    results: list[CaseEvaluationResult] = []
    for c in cases:
        c_id = c["id"]
        exp = expectations.get(c_id, {})
        res = run_live_case(c, exp, client, evaluator, system_prompt)
        results.append(res)

    # Compute aggregate metrics
    metrics = AggregateSuiteMetrics.compute(results)

    # 5. Run formal unit tests
    print("\n[5/5] Running unit and regression tests from tests/test_decision_testing.py...")
    import unittest
    suite = unittest.defaultTestLoader.discover(str(EXPERIMENT_DIR / "tests"))
    runner = unittest.TextTestRunner(verbosity=1)
    res = runner.run(suite)
    if not res.wasSuccessful():
        print("  ✗ Unit test suite reported failures")
        all_passed = False
    else:
        print(f"  ✓ All {res.testsRun} formal unit tests passed cleanly")

    print("\n" + "=" * 65)
    print("SUITE EVALUATION SUMMARY")
    print("=" * 65)
    print(f"  Total Cases:         {metrics.total_cases}")
    print(f"  Passed Cases:        {metrics.passed_cases}")
    print(f"  Failed Cases:        {metrics.failed_cases}")
    print(f"  Pass Rate:           {metrics.pass_rate}%")
    print(f"  Schema Valid Rate:   {metrics.schema_valid_rate}%")
    print(f"  Mean Score:          {metrics.mean_score}/100")
    print(f"  Non-Destructive OK:  {metrics.non_destructive_adherence_rate}%")
    print(f"  Mean Latency:        {metrics.mean_latency_seconds}s")
    if metrics.failed_case_ids:
        print(f"  Failed Cases:        {', '.join(metrics.failed_case_ids)}")
    print("=" * 65)

    # Save timestamped results
    output_payload = {
        "timestamp": datetime.now().isoformat(),
        "config": {
            "model_name": config.model_name,
            "base_url": config.base_url,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
        },
        "aggregate_metrics": metrics.to_dict(),
        "case_results": [r.to_dict() for r in results],
    }
    saved_file = save_results(output_payload, prefix="suite_run")
    print(f"\nDetailed evaluation results saved to:\n  {saved_file}\n")

    return 0 if metrics.failed_cases == 0 else 1


def run_ad_hoc_decision(
    profile_source: str,
    question: str,
    config_path: Optional[str] = None,
) -> int:
    """Execute an ad-hoc single decision query against the configured model."""
    system_prompt = load_system_prompt()
    config = LLMConfig.load(config_path)
    client = LLMClient(config)

    adapter = load_adapter(profile_source)
    context = adapter.build_llm_context()
    user_prompt = build_user_prompt(context, question)

    print(f"\n[Ad-Hoc Decision Request]")
    print(f"Source Profile: {profile_source}")
    print(f"Question:       {question}")
    print(f"Target Model:   {config.model_name} at {config.base_url}")

    try:
        raw_resp, latency, meta = client.generate_decision(system_prompt, user_prompt)
        print(f"\nResponse received in {latency:.2f}s:")
        print("-" * 50)
        print(raw_resp)
        print("-" * 50)

        decision_obj, errs, raw_dict = parse_and_validate_decision(raw_resp)
        if errs:
            print(f"\n⚠ Schema Validation Warnings: {errs}")
        else:
            print("\n✓ Valid Decision JSON matching Contract")
            if decision_obj:
                print(f"  Decision:        {decision_obj.decision}")
                print(f"  Selected Method: {decision_obj.selected_method}")
                print(f"  Target Columns:  {decision_obj.target_columns}")
                print(f"  Risk Level:      {decision_obj.risk_level}")
                print(f"  Self-Confidence: {decision_obj.confidence}")

        # Save single result
        save_payload = {
            "timestamp": datetime.now().isoformat(),
            "profile_source": profile_source,
            "question": question,
            "latency_seconds": latency,
            "raw_response": raw_resp,
            "validation_errors": errs,
            "parsed_decision": raw_dict,
        }
        saved_file = save_results(save_payload, prefix="adhoc_run")
        print(f"\nAudit saved to: {saved_file}")
        return 0

    except Exception as e:
        print(f"\n✗ Error executing decision query: {e}")
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="LLM Decision-Testing Experiment for Qwen 3.5 0.8B",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--offline", action="store_true", help="Run offline validation suite (zero network mode)")
    parser.add_argument("--suite", action="store_true", help="Run full 8-case evaluation suite against live model")
    parser.add_argument("--case", type=str, help="Run a specific test case ID (e.g. case_02_sales_outliers)")
    parser.add_argument("--profile", type=str, help="Path to a profile.json file for ad-hoc evaluation")
    parser.add_argument("--csv", type=str, help="Path to a dataset.csv file to profile and evaluate")
    parser.add_argument("--question", type=str, help="Analytical question to ask the model")
    parser.add_argument("--config", type=str, help="Path to custom config.json")

    args = parser.parse_args()

    if args.offline:
        success = run_offline_tests()
        return 0 if success else 1

    if args.suite:
        return run_full_suite(config_path=args.config)

    if args.case:
        cases, expectations = load_cases_and_expectations()
        matched = [c for c in cases if c["id"] == args.case]
        if not matched:
            print(f"Error: Unknown case ID '{args.case}'. Available cases: {[c['id'] for c in cases]}")
            return 1
        system_prompt = load_system_prompt()
        config = LLMConfig.load(args.config)
        client = LLMClient(config)
        evaluator = DecisionEvaluator()
        run_live_case(matched[0], expectations.get(args.case, {}), client, evaluator, system_prompt)
        return 0

    if args.profile or args.csv:
        source = args.profile if args.profile else args.csv
        question = args.question or "What analytical procedures do you recommend based on this profile?"
        return run_ad_hoc_decision(source, question, config_path=args.config)

    # Default action if no flags provided
    print("No run mode specified. Running offline verification suite by default...")
    print("Use '--help' to view available options.\n")
    success = run_offline_tests()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())

