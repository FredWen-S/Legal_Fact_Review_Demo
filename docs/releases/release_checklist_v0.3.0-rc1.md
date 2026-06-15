# v0.3.0-rc1 Release Checklist

## Windows Portable

- [ ] 在干净 Windows 机器解压 release zip。
- [ ] 确认 Python 版本为 3.10-3.12，推荐 Python 3.12。
- [ ] 如使用 wheelhouse，确认 wheelhouse tag 与 Python 版本匹配。
- [ ] 双击 `start.bat`，确认可启动。
- [ ] 确认端口占用时可自动切换到 8502-8510。
- [ ] 确认日志写入 `logs/startup.log`。

## Word 复核提示版专项

- [ ] DOCX 完整复核：使用 Case 01 上传 DOCX、基础信息表和证据目录。
- [ ] 下载 Word 复核提示版，确认文件名为 `<原文件名>_复核提示版.docx`。
- [ ] 确认原始 DOCX 未被覆盖。
- [ ] 打开提示版 Word，确认存在 `【复核提示】`。
- [ ] 确认提示内容包含“建议人工复核”。
- [ ] 确认文末包含固定免责声明。
- [ ] 确认高风险 finding 出现在文末汇总。
- [ ] 确认未定位提示进入“未定位复核提示”。
- [ ] DOCX 单文书模式：只上传单文书 DOCX，确认外部复核字段进入汇总。
- [ ] 确认单文书模式不出现 SOURCE_MISMATCH 或 EVIDENCE_REFERENCE_MISSING 误报。
- [ ] PDF 场景：确认可下载 Word 摘要，但 Word 复核提示版按钮不可用。
- [ ] 历史记录：确认提示“历史记录不保存原文正文，因此不能重新生成提示版”。

## 导出与内容

- [ ] DOCX 当前会话导出的 ZIP 包含 `复核提示版文书/`。
- [ ] PDF 场景导出的 ZIP 不包含 `复核提示版文书/`。
- [ ] Excel / HTML / Word 中文显示正常。
- [ ] 案件级复核包仍可生成。
- [ ] ZIP 不包含 `.git`、`.venv`、`__pycache__`、`.pytest_cache`、用户 SQLite 数据或旧导出文件。

## 隐私与文案

- [ ] UI 与报告文案保持“建议人工复核”“待确认”“需人工判断”等稳妥表述。
- [ ] 确认隐私声明说明：不接入外部 API、不保存完整原文正文、不构成法律意见。
- [ ] 确认提示版 Word 包含原文内容，用户需妥善保存。
