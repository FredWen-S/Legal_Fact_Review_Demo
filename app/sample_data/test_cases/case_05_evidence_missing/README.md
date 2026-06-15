# Case 05：证据目录问题

## 上传方式

上传 `evidence_problem_document.docx`，并同时上传 `base_info.xlsx` 和 `evidence_index.xlsx`。

## 预期模式

完整复核模式。

## 预期结果

- 生成 EVIDENCE_REFERENCE_MISSING。
- 能展示缺失的证据4、证据8或附件8。
- 证据目录存在重复编号时程序不应崩溃。

## 不应出现

- 不应把证据目录重复行当作致命解析错误。
