from __future__ import annotations

from pathlib import Path

from app.config.review_config import DEFAULT_CONFIG_PATH, ReviewRulesConfig, export_config, import_config_file, restore_default_config
from app.storage.sqlite_store import save_rule_config_history


def import_rules_with_history(
    source_path: str | Path,
    target_path: str | Path = DEFAULT_CONFIG_PATH,
    db_path: str | Path = "data/review_runs.sqlite",
    change_note: str | None = None,
) -> ReviewRulesConfig:
    config, backup_path = import_config_file(source_path, target_path=target_path, change_note=change_note)
    save_rule_config_history(
        config_version=config.config_version,
        active_config_path=str(target_path),
        change_note=change_note or "导入规则配置",
        backup_path=str(backup_path) if backup_path else None,
        path=db_path,
    )
    return config


def restore_default_rules_with_history(
    target_path: str | Path = DEFAULT_CONFIG_PATH,
    db_path: str | Path = "data/review_runs.sqlite",
) -> ReviewRulesConfig:
    config, backup_path = restore_default_config(target_path=target_path)
    save_rule_config_history(
        config_version=config.config_version,
        active_config_path=str(target_path),
        change_note="恢复默认规则配置",
        backup_path=str(backup_path) if backup_path else None,
        path=db_path,
    )
    return config


def export_rules_text(config: ReviewRulesConfig | None = None) -> str:
    return export_config(config)
