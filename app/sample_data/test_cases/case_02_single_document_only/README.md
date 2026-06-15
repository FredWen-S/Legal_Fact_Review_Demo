# Case 02：单文书字段抽取模式

## 上传方式

只上传 `single_document.docx` 或 `single_document.pdf`，不要上传基础信息表和证据目录。

## 预期模式

单文书字段抽取模式。

## 预期结果

- 生成待外部复核字段清单。
- 不生成 SOURCE_MISMATCH。
- 不因缺少证据目录生成 EVIDENCE_REFERENCE_MISSING。
- 可用于演示主体、案号、金额、日期、合同编号和证据编号抽取。

## 不应出现

- 不应提示必须上传基础信息表或证据目录。
