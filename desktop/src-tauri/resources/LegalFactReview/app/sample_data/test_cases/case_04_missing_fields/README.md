# Case 04：关键字段缺失

## 上传方式

上传 `missing_fields_document.docx`，并同时上传 `base_info.xlsx` 和 `evidence_index.xlsx`。

## 预期模式

完整复核模式。

## 预期结果

- 生成 MISSING_FIELD。
- 仍能抽取已有金额、日期、地址和证据编号。
- 报告导出不应崩溃。
- source_location 不得为空。

## 不应出现

- 不应因为缺少案号、法院名称或合同编号导致解析失败。
