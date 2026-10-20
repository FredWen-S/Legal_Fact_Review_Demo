from __future__ import annotations

import sqlite3
import json
from pathlib import Path

import yaml

from app.config.review_config import (
    ReviewRulesConfig,
    default_config,
    export_config,
    import_config_file,
    load_review_config,
    load_review_config_with_status,
    restore_default_config,
    validate_config_data,
)
from app.config.rule_config_service import import_rules_with_history
from app.models.schemas import BaseInfoItem, EvidenceItem, TextChunk
from app.review_engine import review_document, review_single_document
from app.storage.sqlite_store import get_review_run_detail, list_rule_config_history, save_review_run
from scripts.generate_test_files import generate_test_files


def test_review_rules_config_schema_validates_defaults():
    config = default_config()
    assert isinstance(config, ReviewRulesConfig)
    assert "civil_complaint" in config.document_profiles
    assert config.external_review_rule("company_name")["suggested_action"].startswith("建议人工复核")


def test_invalid_risk_type_rejected():
    data = default_config().model_dump(mode="json")
    data["enabled_risk_types"] = ["NOT_A_RISK"]
    try:
        validate_config_data(data)
    except Exception as exc:
        assert "非法风险类型" in str(exc)
    else:
        raise AssertionError("invalid risk type should fail")


def test_invalid_severity_rejected():
    data = default_config().model_dump(mode="json")
    data["severity_mapping"] = {"SOURCE_MISMATCH": "critical"}
    try:
        validate_config_data(data)
    except Exception as exc:
        assert "severity" in str(exc) or "critical" in str(exc)
    else:
        raise AssertionError("invalid severity should fail")


def test_invalid_regex_patterns_are_rejected():
    data = default_config().model_dump(mode="json")
    data["placeholder_patterns"] = ["("]
    try:
        validate_config_data(data)
    except Exception as exc:
        assert "invalid regex" in str(exc)
    else:
        raise AssertionError("invalid placeholder regex should fail")

    data = default_config().model_dump(mode="json")
    data["field_dictionary"]["amount"]["regex_patterns"] = ["["]
    try:
        validate_config_data(data)
    except Exception as exc:
        assert "invalid regex" in str(exc)
    else:
        raise AssertionError("invalid field regex should fail")


def test_unsafe_suggested_action_rejected():
    data = default_config().model_dump(mode="json")
    data["external_review_sources"]["company_name"]["suggested_action"] = "系统确认错误。"
    try:
        validate_config_data(data)
    except Exception as exc:
        assert "建议人工复核" in str(exc) or "绝对" in str(exc)
    else:
        raise AssertionError("unsafe suggested_action should fail")


def test_broken_config_falls_back_to_default(tmp_path: Path):
    config_path = tmp_path / "broken.yml"
    config_path.write_text("enabled_risk_types: [NOT_A_RISK]\n", encoding="utf-8")

    config = load_review_config_with_status(config_path)

    assert config.fallback_used
    assert "MISSING_FIELD" in config.enabled_risk_types


def test_config_export_import_restore_and_backup(tmp_path: Path):
    target = tmp_path / "review_rules.yml"
    target.write_text(export_config(default_config()), encoding="utf-8")
    data = default_config().model_dump(mode="json")
    data["config_version"] = "custom-test-v1"
    source = tmp_path / "custom.yml"
    source.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")

    imported, backup = import_config_file(source, target_path=target, backup_dir=tmp_path / "backups")
    assert imported.config_version == "custom-test-v1"
    assert backup and backup.exists()

    before = target.read_text(encoding="utf-8")
    bad = tmp_path / "bad.yml"
    bad.write_text("external_review_sources:\n  company_name:\n    suggested_action: 错误\n", encoding="utf-8")
    try:
        import_config_file(bad, target_path=target, backup_dir=tmp_path / "backups")
    except Exception:
        pass
    assert target.read_text(encoding="utf-8") == before

    restored, restore_backup = restore_default_config(target_path=target, backup_dir=tmp_path / "backups")
    assert restored.config_version == "default-v1"
    assert restore_backup and restore_backup.exists()


def test_json_import_success_and_invalid_import_does_not_overwrite(tmp_path: Path):
    target = tmp_path / "review_rules.yml"
    target.write_text(export_config(default_config()), encoding="utf-8")
    before = target.read_text(encoding="utf-8")

    data = default_config().model_dump(mode="json")
    data["config_version"] = "json-import-v1"
    source = tmp_path / "custom.json"
    source.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    imported, _ = import_config_file(source, target_path=target, backup_dir=tmp_path / "backups")
    assert imported.config_version == "json-import-v1"
    assert target.read_text(encoding="utf-8") != before

    current = target.read_text(encoding="utf-8")
    bad_sources = [
        ("broken.yml", "config_version: [\n"),
        ("missing.yml", "field_dictionary:\n  legal_representative:\n    aliases: [负责人]\n"),
        ("bad_risk.yml", "enabled_risk_types: [BAD_RISK]\n"),
        ("bad_severity.yml", "severity_mapping:\n  SOURCE_MISMATCH: critical\n"),
        ("bad_alias.yml", "field_dictionary:\n  legal_representative:\n    display_name: 法定代表人\n    aliases: not-a-list\n"),
    ]
    for filename, text in bad_sources:
        source = tmp_path / filename
        source.write_text(text, encoding="utf-8")
        try:
            import_config_file(source, target_path=target, backup_dir=tmp_path / "backups")
        except Exception:
            pass
        else:
            raise AssertionError(f"{filename} should fail validation")
        assert target.read_text(encoding="utf-8") == current


def test_restore_default_rules_records_history(tmp_path: Path):
    from app.config.rule_config_service import restore_default_rules_with_history

    db_path = tmp_path / "history.sqlite"
    target = tmp_path / "review_rules.yml"
    data = default_config().model_dump(mode="json")
    data["config_version"] = "custom-before-restore"
    target.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")

    restored = restore_default_rules_with_history(target_path=target, db_path=db_path)
    history = list_rule_config_history(path=db_path)

    assert restored.config_version == "default-v1"
    assert history
    assert history[0].config_version == "default-v1"
    assert "恢复默认" in (history[0].change_note or "")


def test_rule_config_history_and_review_run_metadata(tmp_path: Path):
    test_cases_dir = tmp_path / "test_cases"
    generate_test_files(output_dir=test_cases_dir)
    db_path = tmp_path / "reviews.sqlite"
    target = tmp_path / "review_rules.yml"
    target.write_text(export_config(default_config()), encoding="utf-8")
    source = test_cases_dir / "case_09_custom_rules_profile" / "custom_review_rules.yml"

    config = import_rules_with_history(source, target_path=target, db_path=db_path, change_note="case09")
    history = list_rule_config_history(path=db_path)
    review_id = save_review_run([], path=db_path, config_version=config.config_version, document_profile="lawyer_letter")
    detail = get_review_run_detail(review_id, db_path)

    assert history[0].config_version == "case09-custom-v1"
    assert detail.config_version == "case09-custom-v1"
    assert detail.document_profile == "lawyer_letter"


def test_old_sqlite_migration_adds_rule_config_columns_and_preserves_rows(tmp_path: Path):
    from app.storage.sqlite_store import fetch_manual_review_records, init_db, save_manual_review_records
    from app.models.schemas import ManualReviewRecord

    db_path = tmp_path / "old.sqlite"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE review_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                finding_count INTEGER NOT NULL,
                findings_json TEXT NOT NULL
            )
            """
        )
        conn.execute("INSERT INTO review_runs (created_at, finding_count, findings_json) VALUES ('2026-01-01T00:00:00', 0, '[]')")
        conn.execute(
            """
            CREATE TABLE manual_review_records (
                record_id TEXT PRIMARY KEY,
                review_id TEXT NOT NULL,
                field_id TEXT NOT NULL,
                field_type TEXT NOT NULL,
                extracted_value TEXT NOT NULL,
                confirmed_value TEXT,
                review_status TEXT NOT NULL,
                review_source TEXT,
                reviewer_note TEXT,
                source_location TEXT NOT NULL,
                reviewed_at TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO manual_review_records (
                record_id, review_id, field_id, field_type, extracted_value,
                confirmed_value, review_status, review_source, reviewer_note, source_location, reviewed_at
            ) VALUES ('m1', 'review-1', 'f1', '案号', '（2026）沪0115民初1号', NULL, '未复核', NULL, NULL, '段落1', NULL)
            """
        )
        conn.commit()
    finally:
        conn.close()

    init_db(db_path).close()
    init_db(db_path).close()

    conn = sqlite3.connect(db_path)
    try:
        review_columns = {row[1] for row in conn.execute("PRAGMA table_info(review_runs)").fetchall()}
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        old_rows = conn.execute("SELECT COUNT(*) FROM review_runs").fetchone()[0]
    finally:
        conn.close()

    assert {"config_version", "document_profile"}.issubset(review_columns)
    assert "rule_config_history" in tables
    assert old_rows == 1
    assert fetch_manual_review_records("review-1", db_path)[0].record_id == "m1"

    save_manual_review_records(
        [
            ManualReviewRecord(
                record_id="m2",
                review_id="review-1",
                field_id="f2",
                field_type="备注",
                extracted_value="人工记录摘要",
                review_status="未复核",
                source_location="段落2",
            )
        ],
        path=db_path,
    )
    assert len(fetch_manual_review_records("review-1", db_path)) == 2


def test_document_profile_affects_missing_fields():
    config = default_config()
    chunks = [TextChunk(text="原告：上海星澜智能科技有限公司。", location="段落1")]
    base = [BaseInfoItem(field_name="金额", standard_value="人民币100元")]

    findings = review_document(chunks, base, [EvidenceItem(evidence_no="1", evidence_name="合同")], config=config, document_profile="civil_complaint")

    assert any(finding.risk_type == "MISSING_FIELD" and finding.field_name == "金额" for finding in findings)


def test_document_profiles_change_missing_field_scope():
    config = default_config()
    chunks = [TextChunk(text="原告：上海星澜智能科技有限公司。案号：（2026）沪0115民初1号。", location="段落1")]
    base = [
        BaseInfoItem(field_name="金额", standard_value="人民币100元"),
        BaseInfoItem(field_name="合同编号", standard_value="HT-2026-001"),
        BaseInfoItem(field_name="证据编号", standard_value="1"),
    ]

    civil = review_document(chunks, base, [EvidenceItem(evidence_no="1", evidence_name="合同")], config=config, document_profile="civil_complaint")
    contract = review_document(chunks, base, [EvidenceItem(evidence_no="1", evidence_name="合同")], config=config, document_profile="contract_review")

    civil_missing = {finding.field_name for finding in civil if finding.risk_type == "MISSING_FIELD"}
    contract_missing = {finding.field_name for finding in contract if finding.risk_type == "MISSING_FIELD"}
    assert "证据编号" in civil_missing
    assert "合同编号" in contract_missing


def test_disable_risk_and_severity_mapping_and_placeholder_patterns():
    config = default_config().model_copy(
        update={
            "enabled_risk_types": ["FORMAT_ERROR"],
            "severity_mapping": {"FORMAT_ERROR": "low"},
            "severity_overrides": {"FORMAT_ERROR": "low"},
        }
    )
    findings = review_single_document([TextChunk(text="案号：（202X）沪0115民初ABC号。其他事项：待补充。", location="段落1")], config=config)

    assert findings
    assert {finding.risk_type for finding in findings} == {"FORMAT_ERROR"}
    assert all(finding.severity == "low" for finding in findings)

    custom = default_config().model_copy(update={"placeholder_patterns": ["【请律师确认】"]})
    placeholder_findings = review_single_document([TextChunk(text="事项：【请律师确认】", location="段落1")], config=custom)
    assert any(finding.risk_type == "PLACEHOLDER_REMAINING" for finding in placeholder_findings)


def test_case_09_custom_rules_can_run(tmp_path: Path):
    test_cases_dir = tmp_path / "test_cases"
    generate_test_files(output_dir=test_cases_dir)
    config_path = test_cases_dir / "case_09_custom_rules_profile" / "custom_review_rules.yml"
    config = load_review_config(config_path)
    chunks = [TextChunk(text="其他事项：【请律师确认】", location="段落1")]
    findings = review_single_document(chunks, config=config)

    assert config.config_version == "case09-custom-v1"
    assert "PLACEHOLDER_REMAINING" not in {finding.risk_type for finding in findings}
