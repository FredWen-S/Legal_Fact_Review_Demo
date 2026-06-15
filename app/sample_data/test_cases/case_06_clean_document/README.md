# Case 06：基本干净文书

## 上传方式

上传 `clean_document.docx`，并同时上传 `base_info.xlsx` 和 `evidence_index.xlsx`。

## 预期模式

完整复核模式。

## 预期结果

- findings 数量较少。
- 可用于测试“无明显风险”或“低风险”展示。
- 系统应正常导出 Excel、HTML、Word 和 ZIP。

## 不应出现

- 不应出现 SOURCE_MISMATCH。
- 不应出现 EVIDENCE_REFERENCE_MISSING。
- 不应出现 PLACEHOLDER_REMAINING。
