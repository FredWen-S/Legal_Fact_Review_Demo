# Case 09：自定义规则与文书类型模板

## 上传方式

在“规则配置中心”导入 `custom_review_rules.yml`，再上传 `lawyer_letter.docx` 或 `contract_review.docx` 运行复核。

## 预期模式

可选择律师函或合同审查模板。

## 预期结果

- 自定义配置禁用 PLACEHOLDER_REMAINING 后，占位符不再输出为 finding。
- SOURCE_MISMATCH 默认等级调整为 medium。
- 律师函模板新增 required_fields，可影响 MISSING_FIELD。
- 恢复默认配置后行为恢复。
