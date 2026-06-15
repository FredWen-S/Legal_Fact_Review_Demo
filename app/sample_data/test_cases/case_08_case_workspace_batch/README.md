# Case 08：案件工作区批量复核

## 上传方式

先创建一个案件工作区，再在批量复核中同时上传 `batch_document_v1.docx`、`batch_document_v2.docx` 和 `batch_document_clean.docx`，并上传 `base_info.xlsx` 与 `evidence_index.xlsx`。

## 预期模式

完整复核模式，且所有 review_id 关联到同一个案件。

## 预期结果

- 至少 2 份文书复核成功。
- `batch_document_v2.docx` 会出现主体名称、金额、证据编号和占位符相关提示。
- 案件内字段差异提示应展示主体名称和金额在不同文书间不一致。
- `batch_document_clean.docx` 可作为较干净文书对照。

## 不应出现

- 单份文书失败不应影响其他文书生成 review_id。
- 案件级复核包不应包含完整原文书内容。
