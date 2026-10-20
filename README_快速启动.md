# 律师文书基础信息与关键事实复核助手：快速启动

当前演示候选版本：`v0.6.0-rc1`。旧版 `v0.5.0` portable 包的启动方式仍可参考本文对应说明。

## 1. 如何启动

运行要求：Python 3.10-3.12，推荐 Python 3.12；不支持 Python 3.13。若交付包包含 `wheelhouse/`，wheelhouse 必须与目标 Python 版本匹配，例如 cp312 wheelhouse 必须使用 Python 3.12。

1. 解压 `LegalFactReview_v0.5.0_windows_portable.zip`。
2. 打开 `LegalFactReview` 文件夹。
3. 双击 `start.bat`。
4. 首次启动会自动创建 `.venv` 并安装依赖，可能需要几分钟。
5. 如果交付包内包含 `wheelhouse/`，会优先使用离线依赖安装，不需要联网。
6. 浏览器打开启动窗口显示的地址后即可使用，默认通常是 `http://localhost:8501`。

如果浏览器没有自动打开，请手动访问：

```text
http://localhost:8501
```

如果 8501 端口被占用，程序会自动尝试 8502-8510，实际地址会显示在启动窗口中。

## 2. 如何上传文件

- 只上传 Word / PDF 文书：进入“单文书字段抽取模式”。
- 同时上传文书、基础信息表、证据目录：进入“完整复核模式”。
- 如果 PDF 是扫描版，页面可能提示启用 OCR。OCR 需要额外安装可选依赖。
- 如需按案件管理多份文书，可先在侧边栏进入“案件工作区”创建案件，再回到“单次复核”或“批量复核”。
- 未配置 LLM API key 时，系统会使用本地 mock structured extraction，仍可完成离线 synthetic demo。
- RAG 检索默认使用 lexical retrieval；如配置本地 embedding provider，可选启用 embedding retrieval。embedding 不可用时会自动回退到 lexical retrieval。
- “历史记录”会展示本地 Review History / Audit Log metadata。它只保存文件名、hash、模式、issue 计数、LLM fallback、retrieval 状态和关键事件摘要，不保存完整正文、完整 extracted text、完整 prompt 或完整 LLM response。
- 本地 privacy policy 会在 history/audit 落库前清洗 metadata，并在 HTML / Excel / Word / ZIP 导出中加入 privacy summary。默认报告仍保留 synthetic issue 展示，不把 demo 当作生产脱敏系统。

示例文件在：

```text
sample_data/
```

## 3. 两种模式区别

- 单文书字段抽取模式：只提取文书中的主体、案号、金额、日期、证据编号等字段，提示人工去外部来源复核。
- 完整复核模式：在字段抽取基础上，与基础信息表和证据目录进行比对，生成复核发现。

## 4. 如何导出复核包

运行复核后，在页面底部下载：

- Excel 复核清单
- HTML 报告
- Word 复核摘要
- 完整复核包 ZIP

如需长期留存，建议下载“完整复核包 ZIP”。

案件工作区中还可以下载“案件级复核包”，其中包含案件复核汇总 Excel、案件复核报告 HTML，以及各单份文书复核包。

## 4.0 Synthetic Demo / Evaluation Cases

项目内置 5 个 synthetic demo/evaluation cases，用于面试演示和自动化回归测试。全部文件为本地合成数据，不需要 API key，不需要 embedding 模型，也不代表真实法律审查能力。

```bash
python scripts/run_demo_cases.py
python scripts/run_demo_cases.py --case client_profile_mismatch
python scripts/run_demo_cases.py --json
python -m pytest tests/test_demo_cases.py -q
```

这些 case 覆盖 clean pass、缺字段/格式问题、RAG client profile mismatch、缺标准条款、LLM mock fallback 与 export privacy summary。

## 4.1 v0.2.0 案件工作区

案件工作区用于把同一案件或项目下的多份文书、复核记录和人工复核记录归集在一起。

- 创建案件：进入“案件工作区”，填写案件名称、内部案件编号、客户名称、对方主体、案件类型和备注。
- 归入案件：在侧边栏选择案件后，单次复核和批量复核都会关联到当前案件。
- 查看历史：进入“历史记录”，可查看 review_id、文书文件名、复核模式、findings 数量和人工复核记录数量。
- 继续复核：在历史记录中选择 review_id，可继续填写人工复核记录并重新导出报告。
- 批量复核：进入“批量复核”，一次上传多份 DOCX/PDF；单个文件失败不影响其他文件。
- 字段差异：案件工作区会展示同一案件下不同文书的基础字段差异提示。

案件内字段差异提示仅表示不同文书之间字段不一致，需人工判断是否属于正常版本差异。

## 4.2 Word 复核提示版

上传 DOCX 文书并完成复核后，下载区会显示“下载 Word 复核提示版”。系统会生成一个副本：

```text
<原文件名>_复核提示版.docx
```

注意：

- 该功能只支持 DOCX，不支持 PDF 原文提示版。
- 系统不会覆盖原始 Word 文件，也不会自动修改原文正文。
- 提示版会在相关段落附近插入“【复核提示】”，并在文末附“复核提示汇总”。
- 提示内容仅用于人工复核，不构成法律意见。
- 提示版 Word 包含原文内容，请按案件材料保密要求妥善保存。
- 历史记录不保存原文书正文，因此历史详情不能重新生成提示版。

## 5. 如何关闭

关闭 `start.bat` 的黑色窗口即可停止服务。

也可以双击 `stop.bat` 尝试停止本项目启动的 Streamlit 服务。

## 5.1 桌面版启动

v0.5.0 提供 Tauri 桌面壳。桌面版会启动本地 Python / Streamlit 服务，并提供状态、日志和 data / exports / logs 目录入口。

开发模式：

```text
cd desktop
npm install
npm run dev
```

也可直接运行：

```text
py -3.12 scripts/desktop_service.py status
py -3.12 scripts/desktop_service.py start
py -3.12 scripts/desktop_service.py stop
```

桌面版不改变复核规则，不保存完整上传文书正文，不接入外部 API。详细说明见 `docs/桌面版说明.md`。

v0.6.0-rc1 提供 Windows installer / exe 打包候选路线。若安装器内置 Python 3.12，用户无需单独安装 Python；若安装器未内置 Python，仍需安装 Python 3.10-3.12，推荐 Python 3.12。

| 版本 | 启动方式 | 适合对象 |
| --- | --- | --- |
| Portable Streamlit 版 | 双击 `start.bat` | 稳定演示、低依赖交付 |
| Tauri 桌面壳版 | 打开桌面壳，再启动本地服务 | 更接近桌面应用体验 |
| Tauri Installer 版 | 安装后从开始菜单或桌面入口启动 | 更接近普通桌面软件 |
| 开发者模式 | `streamlit run app/main.py` / `npm run dev` | 开发调试 |

v0.5.0 桌面壳仍依赖本地 Python 服务，不是完全独立 exe。核心复核功能仍由 Python / Streamlit 提供。

## 6. 常见问题

### 双击后窗口闪退怎么办？

请右键 `start.bat`，选择“在终端中打开”或“以管理员身份运行”，查看错误提示。也可以打开：

```text
logs/startup.log
```

常见原因是未安装 Python 3.10-3.12、当前 `python` 指向 Python 3.13、已有 `.venv` 来自 Python 3.13，或依赖安装失败。

如果提示 `.venv` 版本不适用，请关闭窗口，删除工具目录下的 `.venv` 文件夹后重新双击 `start.bat`。

为避免 Windows CMD 编码差异影响启动，`start.bat` 的控制台命令提示以英文为主；启动前检查和详细错误会写入 `logs/startup.log`。

### 8501 端口被占用怎么办？

程序会自动尝试 8502-8510。请以启动窗口显示的浏览器地址为准。

### 报告导出在哪里？

浏览器下载会保存到系统默认下载目录。应用本地目录中的 `exports/` 可用于手动归档导出文件。

### 依赖安装失败怎么办？

请联系交付人员提供包含 `wheelhouse/` 的离线包，或确认现场电脑可以访问 Python pip 源。错误详情见 `logs/startup.log`。

离线 `wheelhouse/` 必须与现场 Python 版本匹配，例如 Python 3.11 使用 cp311 兼容依赖，Python 3.12 使用 cp312 兼容依赖。

启动前检查会识别 wheelhouse 标签。如果 wheelhouse 是 cp312 但当前 Python 是 3.11，脚本会提示版本不匹配并停止，请安装 Python 3.12 或重新生成匹配的 wheelhouse。

### PDF 上传后提取不到字段怎么办？

可能是扫描版 PDF。可以勾选“启用 OCR 识别扫描版 PDF”后重试，或先转换为可复制文字的 PDF。

### 如何安装 OCR 可选依赖？

在工具目录中运行：

```text
pip install -r requirements-ocr.txt
```

OCR 依赖较大，首次安装可能较慢。基础交付包默认不强制安装 OCR。

### OCR 是否会上传文件？

不会。OCR 全程本地运行，不接入云 OCR，不上传 PDF 或图片。

### OCR 识别错了怎么办？

OCR 结果只是辅助抽取。请在人工复核工作区填写人工确认值，并以原始材料或外部核验结果为准。

### 如何调整复核规则？

进入侧边栏“规则配置”。可以启用/禁用风险类型、调整风险等级、编辑占位符模式、查看文书类型模板和字段词典，并导入/导出规则配置。

配置错误时系统会回退默认配置。建议动作必须包含“建议人工复核”，不能写成绝对化错误判断或法律结论。配置中心用于调整辅助复核规则，不代表系统能够自动完成法律判断。详细说明见 `docs/规则配置说明.md`。

### 如何清空本地复核记录？

关闭服务后删除：

```text
data/review_runs.sqlite
```

Review History / Audit Log 也保存在这个本地 SQLite 文件中。它用于 synthetic demo 的可解释性展示，不是生产合规审计系统。

落库前会移除 `document_text`、`extracted_text`、`prompt`、`raw_response`、`llm_response` 等高风险 metadata 字段，并对 email、手机号、长 ID 类值做基础 mask。这只是本地 demo 隐私边界，不是生产 DLP / 合规系统。

### 是否会上传文件到互联网？

不会。默认本地运行，不接入外部 API，不上传文书到第三方服务。

### 是否能完成最终判断？

不能。本工具只做辅助复核和工作底稿整理，不构成法律意见，最终判断由律师或相关人员完成。

本项目使用 synthetic 示例文书和 synthetic KB，不应加入真实客户资料，也不应作为生产法律系统对外承诺准确性。

### 是否必须安装 embedding 模型？

不必须。默认检索后端是 lexical，不需要下载模型。可选 embedding retrieval 仅用于作品集增强：

```text
RAG_RETRIEVAL_BACKEND=embedding
RAG_EMBEDDING_PROVIDER=local
RAG_EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
```

如果未安装 `sentence-transformers`、模型加载失败或 embedding 计算失败，系统会自动回退到 lexical retrieval。

## 发布验证 Python 要求

v0.5.0 发布验证请使用 Python 3.12。若系统默认 `python` 是 Python 3.13，请不要直接运行 `python -m pytest`。

推荐命令：

```bash
python -m pytest tests/test_extractors.py tests/test_validators.py tests/test_reports.py tests/test_manual_review.py tests/test_single_document_mode.py tests/test_llm_rag_pipeline.py tests/test_case_workspace.py tests/test_rule_config_center.py tests/test_docx_package_export.py tests/test_docx_annotation.py tests/test_single_review_workflow.py tests/test_embedding_retrieval.py tests/test_review_history.py tests/test_audit_log.py tests/test_redaction_policy.py tests/test_privacy_storage.py tests/test_privacy_exports.py tests/test_demo_cases.py -q
py -3.12 scripts/acceptance_check.py
py -3.12 scripts/build_desktop_release.py
```

统一验证命令：

```bash
py -3.12 scripts/verify_release.py
```

验证脚本会优先选择 `py -3.12`，其次 `py -3.11`、`py -3.10`，最后才检查 `python`；Python 3.13 会被拒绝。
