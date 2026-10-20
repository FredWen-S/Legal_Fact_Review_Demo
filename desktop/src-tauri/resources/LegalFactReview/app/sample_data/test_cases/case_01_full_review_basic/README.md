# Case 01：完整复核基础场景

## 上传方式

上传 `sample_complaint.docx` 或 `sample_complaint.pdf`，并同时上传 `base_info.xlsx` 和 `evidence_index.xlsx`。

## 预期模式

完整复核模式。

## 预期结果

- 生成多个 findings。
- 至少覆盖 SOURCE_MISMATCH、AMOUNT_INCONSISTENCY、EVIDENCE_REFERENCE_MISSING、PLACEHOLDER_REMAINING、FORMAT_ERROR、DATE_LOGIC_WARNING。
- 可用于演示基础信息比对、证据缺失、金额不一致和日期顺序可疑。

## 不应出现

- 不应因 PDF 是扫描件而要求 OCR。
- 不应包含真实公司、真实案号或真实个人信息。
