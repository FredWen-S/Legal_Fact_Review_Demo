# Case 03：高冲突文书

## 上传方式

上传 `conflict_document.docx`，并同时上传 `base_info.xlsx` 和 `evidence_index.xlsx`。

## 预期模式

完整复核模式。

## 预期结果

- INTERNAL_CONFLICT 明显。
- AMOUNT_INCONSISTENCY 明显。
- PLACEHOLDER_REMAINING 明显。
- high 风险数量较多。

## 不应出现

- 不应因证据目录跳号或重复导致程序崩溃。
