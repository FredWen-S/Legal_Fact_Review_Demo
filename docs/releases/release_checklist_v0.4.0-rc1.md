# v0.4.0-rc1 Release Checklist

## Windows Portable

- [ ] 干净 Windows 机器可双击 `start.bat` 启动。
- [ ] Python 版本为 3.10-3.12，推荐 3.11 或 3.12。
- [ ] Python 3.13 不作为默认交付运行版本。
- [ ] wheelhouse 与目标 Python 版本匹配，离线安装可完成。
- [ ] 端口占用时可自动尝试 8502-8510。
- [ ] `requirements-ocr.txt` 随包提供，OCR 仍为可选能力。

## 规则配置中心

- [ ] UI 显示配置版本、fallback 状态、当前文书类型模板、启用 risk_type 数量、字段 alias 数量。
- [ ] UI 不显示 Python traceback。
- [ ] YAML 导出可读，且不包含上传文书正文、SQLite 数据或用户文书内容。
- [ ] 合法 YAML 可导入，导入后 `config_version` 更新并写入历史。
- [ ] 合法 JSON 可导入，导入后复核流程仍可运行。
- [ ] 非法 YAML、非法 risk_type、非法 severity、非法 alias 导入失败且不覆盖旧配置。
- [ ] 恢复默认后配置回到默认值，并写入 `rule_config_history`。
- [ ] 禁用 `PLACEHOLDER_REMAINING` 后对应 finding 不出现，恢复后重新出现。
- [ ] severity mapping 会影响 finding 等级和报告风险统计。
- [ ] 文书类型模板会影响 `MISSING_FIELD` 检查范围。
- [ ] 字段 alias 会影响标签式字段抽取。

## SQLite Migration

- [ ] 旧库缺少 `review_runs.config_version` 时自动补列。
- [ ] 旧库缺少 `review_runs.document_profile` 时自动补列。
- [ ] 旧库缺少 `rule_config_history` 时自动建表。
- [ ] `init_db()` 可重复执行。
- [ ] 旧 `review_runs` 不被删除。
- [ ] 旧 `manual_review_records` 不被删除。
- [ ] 不保存完整原文书正文。

## Reports

- [ ] Excel 复核工作底稿显示 `config_version` 和 `document_profile`。
- [ ] HTML 复核报告显示 `config_version` 和 `document_profile`。
- [ ] Word 复核摘要显示 `config_version` 和 `document_profile`。
- [ ] ZIP 复核包包含带元数据的 Excel / HTML / Word 报告。
- [ ] 案件级复核包显示配置版本和文书类型模板。
- [ ] 报告不显示完整原文正文。
- [ ] 敏感号码按脱敏策略展示。
- [ ] 文案保持“建议人工复核”“待确认”“需人工判断”等稳妥表述。

## Core Flows

- [ ] DOCX 完整复核流程通过。
- [ ] DOCX 单文书字段抽取流程通过。
- [ ] PDF 摘要导出流程通过。
- [ ] Word 复核提示版旧流程仍可生成。
- [ ] 案件工作区、批量复核、历史记录可用。
- [ ] 历史记录可重新导出摘要类报告，并显示当次配置版本。

## Release ZIP

- [ ] `dist/LegalFactReview_v0.4.0-rc1_windows_portable.zip` 已生成。
- [ ] `dist/LegalFactReview_v0.4.0-rc1_windows_portable.sha256.txt` 已生成。
- [ ] 包内包含 `start.bat`、`README_快速启动.md`、`app/config/review_rules.yml`。
- [ ] 包内包含 `docs/规则配置说明.md`、`docs/用户使用说明书.md` 和 sample test cases。
- [ ] 包内不包含 `.git`、`.venv`、`__pycache__`、`.pytest_cache`。
- [ ] 包内不包含 `data/review_runs.sqlite`、旧导出文件或用户上传文件。

## Sign-off

- [ ] `python -m pytest -q` 通过。
- [ ] `python scripts/acceptance_check.py` 通过。
- [ ] `python scripts/build_release_zip.py --version v0.4.0-rc1` 通过。
- [ ] release notes 已回填文件名、大小和 SHA256。
