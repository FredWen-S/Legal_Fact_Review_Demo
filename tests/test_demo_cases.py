from __future__ import annotations

import json
from pathlib import Path

from app.evaluation.demo_cases import (
    DEFAULT_MANIFEST_PATH,
    build_summary,
    ensure_case_files,
    list_cases,
    load_manifest,
    main,
    resolve_case_path,
    run_cases,
)


def test_demo_cases_manifest_loads_and_has_required_schema():
    manifest = load_manifest()
    cases = list_cases(manifest)

    assert manifest["schema_version"] == "demo-cases-v1"
    assert len(cases) >= 5
    assert {case["case_id"] for case in cases} >= {
        "clean_contract_pass",
        "missing_required_fields",
        "client_profile_mismatch",
        "missing_standard_clause",
        "llm_fallback_privacy_export",
    }
    for case in cases:
        assert case["description"]
        assert isinstance(case["expected"], dict)


def test_demo_case_manifest_paths_exist_after_generation():
    manifest = load_manifest()
    cases = list_cases(manifest)
    ensure_case_files(cases)

    for case in cases:
        for key in ["document_path", "base_info_path", "evidence_index_path"]:
            if case.get(key):
                assert resolve_case_path(case[key]).exists(), f"{case['case_id']} missing {key}"


def test_all_demo_cases_run_and_match_expected_assertions():
    results = run_cases()
    summary = build_summary(results)

    assert summary["failed"] == 0, json.dumps(summary, ensure_ascii=False, indent=2)
    assert summary["passed"] == len(results)


def test_clean_case_has_no_high_severity_and_forbidden_issue_types_absent():
    result = run_cases(case_id="clean_contract_pass")[0]

    assert result.passed, result.failures
    assert result.severity_summary.get("high", 0) == 0
    assert result.issue_type_summary.get("SOURCE_MISMATCH", 0) == 0
    assert result.issue_type_summary.get("CLIENT_PROFILE_MISMATCH", 0) == 0
    assert result.retrieval_status_summary["client"] == "matched"


def test_mismatch_case_produces_rag_client_profile_mismatch():
    result = run_cases(case_id="client_profile_mismatch")[0]

    assert result.passed, result.failures
    assert result.retrieval_status_summary["client"] == "matched"
    assert result.issue_type_summary.get("CLIENT_PROFILE_MISMATCH", 0) >= 1


def test_missing_clause_case_produces_missing_standard_clause():
    result = run_cases(case_id="missing_standard_clause")[0]

    assert result.passed, result.failures
    assert result.retrieval_status_summary["template"] == "matched"
    assert result.issue_type_summary.get("MISSING_STANDARD_CLAUSE", 0) >= 1


def test_fallback_privacy_export_case_has_mock_fallback_and_privacy_summary():
    result = run_cases(case_id="llm_fallback_privacy_export")[0]

    assert result.passed, result.failures
    assert result.llm_mode == "mock"
    assert result.fallback_reason == "no_api_key"
    assert result.privacy_summary == {
        "html": True,
        "excel": True,
        "docx": True,
        "zip": True,
    }


def test_demo_runner_json_output_is_parseable(capsys):
    exit_code = main(["--case", "client_profile_mismatch", "--json"])
    output = capsys.readouterr().out
    payload = json.loads(output)

    assert exit_code == 0
    assert payload["total"] == 1
    assert payload["cases"][0]["case_id"] == "client_profile_mismatch"


def test_demo_runner_failure_returns_nonzero_for_failed_expectation(tmp_path: Path, capsys):
    manifest = load_manifest()
    failing_manifest = dict(manifest)
    failing_manifest["cases"] = [dict(case) for case in manifest["cases"]]
    for case in failing_manifest["cases"]:
        if case["case_id"] == "client_profile_mismatch":
            expected = dict(case["expected"])
            expected["expected_issue_types"] = ["PLACEHOLDER_REMAINING"]
            case["expected"] = expected
            break
    manifest_path = tmp_path / "failing_manifest.json"
    manifest_path.write_text(json.dumps(failing_manifest, ensure_ascii=False), encoding="utf-8")

    exit_code = main(["--manifest", str(manifest_path), "--case", "client_profile_mismatch", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["failed"] == 1


def test_default_manifest_path_exists():
    assert DEFAULT_MANIFEST_PATH.exists()
