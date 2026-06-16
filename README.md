# 律师文书基础信息复核助手 Demo

Legal Fact Review Demo 是一个本地运行的律师文书事实项复核助手，用于在文书提交或交付前，辅助发现基础信息和关键事实中需要人工复核的问题。

本工具不是自动法律判断工具，不生成法律意见，不能替代律师、律师助理或法务人员的专业判断。

当前开发版本：`v0.5.0-dev`

用户使用说明书：[docs/用户使用说明书.md](docs/用户使用说明书.md)

## 功能边界

- 从 `.docx` / `.pdf` 文书中抽取案号、主体、法定代表人、金额、日期、证据编号、占位符等信息。
- 读取基础信息表 `.xlsx`，将文书值与标准值比对。
- 读取证据目录 `.xlsx`，检查正文引用的证据编号是否存在。
- 检查内部不一致、格式异常、占位符残留、金额不一致、日期顺序可疑等风险。
- 输出页面表格、Excel 复核工作底稿、HTML 报告、Word 复核摘要和 ZIP 复核包。

## 本地启动

```bash
pip install -r requirements.txt
streamlit run app/main.py
```

启动后访问 Streamlit 显示的本地地址，通常是 `http://localhost:8501`。

## Windows 一键启动

面向非技术用户，推荐使用 Windows portable 交付包：

运行要求：Python 3.10-3.12。v0.4.0-rc1 Windows portable 推荐统一使用 Python 3.11 或 3.12；如果交付包包含 `wheelhouse/`，wheelhouse 必须与目标 Python 版本匹配。

```bash
python scripts/build_wheelhouse.py
python scripts/build_portable.py
python scripts/build_release_zip.py
```

生成目录：

```text
dist/LegalFactReview/
dist/LegalFactReview_v0.4.0-rc1_windows_portable.zip
```

使用方式：

1. 将 `dist/LegalFactReview/` 整个文件夹交付给试用用户。
2. 用户解压或复制到本机任意目录。
3. 双击 `start.bat`。
4. 首次启动会自动创建 `.venv` 并安装依赖；如果包内有 `wheelhouse/`，会优先离线安装。
5. 浏览器访问启动窗口显示的地址，默认通常是 `http://localhost:8501`。
6. 上传示例文书体验。
7. 关闭启动窗口即可停止服务。

如果 Python 不存在，或当前 `python` 指向 Python 3.13，启动脚本会提示安装 Python 3.10-3.12，推荐 Python 3.11 或 3.12，不会直接静默退出。

如果交付包内包含 `wheelhouse/`，启动前检查会识别 wheel 文件中的 Python 标签，例如 `cp312`。当 wheelhouse 是 `cp312` 但当前 Python 是 3.11 时，脚本会给出清晰提示并停止，避免盲目离线安装失败。v0.4.0-rc1 推荐使用 Python 3.11 或 3.12，并准备匹配的 wheelhouse。

当前推荐交付方式为 portable 源码包 + `start.bat` 自动创建虚拟环境。由于 Streamlit、pandas、PyMuPDF、python-docx 等依赖较多，暂不强制提供 PyInstaller exe，以降低演示交付风险。

## 桌面版 Tauri 壳

v0.5.0-dev 新增 Tauri 桌面壳骨架，用于让非技术用户通过桌面应用启动本地 Python / Streamlit 服务。桌面壳只负责启动状态、日志入口和目录入口，不重写复核引擎。

开发模式：

```bash
cd desktop
npm install
npm run dev
```

也可以直接使用服务管理脚本：

```bash
python scripts/desktop_service.py status
python scripts/desktop_service.py start
python scripts/desktop_service.py stop
python scripts/desktop_service.py logs
```

桌面版要求 Node.js 18+、Rust stable、Windows WebView2 Runtime，以及 Python 3.10-3.12。详细说明见 [docs/桌面版说明.md](docs/桌面版说明.md)。

桌面版、portable 版、源码 Streamlit 启动和 Docker 启动共用同一套 Python 应用与复核规则。配置中心用于调整辅助复核规则，不代表系统能够自动完成法律判断。

| 版本 | 启动方式 | 适合对象 |
| --- | --- | --- |
| Portable Streamlit 版 | 双击 `start.bat` | 稳定演示、低依赖交付 |
| Tauri 桌面壳版 | 打开桌面壳，再启动本地服务 | 更接近桌面应用体验 |
| 开发者模式 | `streamlit run app/main.py` / `npm run dev` | 开发调试 |

v0.5.0-rc1 桌面壳仍依赖本地 Python 服务，不是完全独立 exe。桌面壳负责启动、停止和打开本地 Streamlit 服务；核心复核功能仍由 Python / Streamlit 提供。

发布前请确认 `app/sample_data/test_cases` 没有因验收脚本产生非预期 modified；如需手动恢复测试数据，可执行：

```bash
git restore -- app/sample_data/test_cases
```

### 离线依赖包

开发者可先构建离线 wheelhouse：

```bash
python scripts/build_wheelhouse.py
```

wheelhouse 必须与目标 Python 版本匹配，例如目标机器使用 Python 3.11 时应准备 cp311 兼容依赖，目标机器使用 Python 3.12 时应准备 cp312 兼容依赖。v0.4.0-rc1 推荐统一确认现场 Python 版本后构建对应 wheelhouse。

该命令会把依赖下载到：

```text
dist/wheelhouse/
```

随后执行：

```bash
python scripts/build_portable.py
```

如果 `dist/wheelhouse/` 存在，构建脚本会将其复制到：

```text
dist/LegalFactReview/wheelhouse/
```

用户双击 `start.bat` 时会优先使用：

```text
pip install --no-index --find-links=wheelhouse -r requirements.txt
```

如果离线安装失败，脚本会在控制台提示是否尝试联网安装，并把失败原因写入 `logs/startup.log`。

OCR 是可选能力，基础包默认不强制包含。需要构建 OCR 离线依赖时，可单独运行：

```bash
python scripts/build_wheelhouse.py --ocr
```

该命令会下载 `requirements-ocr.txt` 中的 OCR 依赖到 `dist/wheelhouse-ocr/`。OCR 依赖通常较大，建议仅在确实需要处理扫描版 PDF 的交付场景中准备。

### Release ZIP

构建可直接分发的 zip：

```bash
python scripts/build_release_zip.py
```

输出示例：

```text
dist/LegalFactReview_v0.4.0-rc1_windows_portable.zip
```

release zip 不包含 `.git`、`.venv`、`__pycache__`、`.pytest_cache`、已有 SQLite 数据库、旧导出文件或临时文件。

### 启动失败排查

- 没有 Python 或版本不匹配：安装 Python 3.10-3.12，推荐 Python 3.11 或 3.12，并勾选 Add Python to PATH。Python 3.13 暂不作为默认交付运行版本。
- 依赖安装失败：优先构建并随包交付 `wheelhouse/`；或确认现场网络可以访问 pip 源。
- 已有 `.venv` 来自 Python 3.13：删除 `.venv` 后重新双击 `start.bat`，脚本会用 Python 3.10-3.12 重新创建虚拟环境。
- 8501 端口被占用：启动脚本会自动尝试 8502-8510，并在控制台显示实际地址。
- 双击后窗口闪退：在终端中运行 `start.bat`，或查看 `logs/startup.log`。
- 日志在哪里：`logs/startup.log`。
- 如何清空本地复核记录：关闭服务后删除 `data/review_runs.sqlite`。
- 是否会上传文件到互联网：不会，默认本地运行，不接入外部 API。

## Docker 启动

```bash
docker compose up --build
```

然后访问 `http://localhost:8501`。

## 目录说明

| 目录 | 用途 |
| --- | --- |
| `app/` | 应用代码 |
| `sample_data/` | portable 包中的示例数据 |
| `app/sample_data/` | 开发环境中的示例数据 |
| `data/` | SQLite 本地复核记录 |
| `exports/` | 导出报告归档目录 |
| `logs/` | 启动和运行日志目录 |
| `scripts/` | 验收、示例数据生成和 Windows 启动脚本 |

## 示例数据

示例文件位于 `app/sample_data/`：

- `sample_document.docx`：虚构律师文书，故意包含公司名称不一致、金额不一致、证据 7 缺失、占位符、案号异常、日期顺序可疑等问题。
- `sample_base_info.xlsx`：基础信息表，包含字段名、标准值、更新时间、备注。
- `sample_evidence_index.xlsx`：证据目录，故意不包含“证据7”。

如果示例文件缺失，可运行：

```bash
python scripts/generate_sample_data.py
```

## 测试文件与演示数据

额外的人工演示和功能测试材料位于：

```text
app/sample_data/test_cases/
```

重新生成全部测试文件：

```bash
python scripts/generate_test_files.py
```

该脚本可重复运行，会清理并重新创建 `app/sample_data/test_cases/`。测试材料全部使用虚构公司、虚构人员、虚构案号和虚构统一社会信用代码。

当前包含的场景：

| Case | 用途 |
| --- | --- |
| `case_01_full_review_basic` | 完整复核基础场景，覆盖基础信息不一致、金额不一致、证据缺失、占位符、案号格式和日期顺序问题 |
| `case_02_single_document_only` | 单文书字段抽取模式，不上传基础信息表和证据目录 |
| `case_03_many_conflicts` | 高冲突文书，包含多版本公司名、金额、合同编号、案号和多个占位符 |
| `case_04_missing_fields` | 关键字段缺失场景，验证 MISSING_FIELD 和报告稳定性 |
| `case_05_evidence_missing` | 证据目录问题，验证缺失证据编号、重复编号和附件编号混用 |
| `case_06_clean_document` | 基本干净文书，用于测试低风险或无明显风险展示 |
| `case_07_pdf_text_extraction` | 可复制文本 PDF 解析测试，不需要 OCR |
| `case_08_case_workspace_batch` | 案件工作区批量复核，包含同一案件三份文书、字段差异和案件级复核包演示 |
| `case_09_custom_rules_profile` | 自定义规则配置和文书类型模板演示，包含律师函、合同审查和配置 YAML |

推荐演示顺序：

1. Case 02：单文书字段抽取模式。
2. Case 01：完整复核基础场景。
3. Case 03：高冲突文书。
4. Case 06：干净文书。

## v0.2.0 案件工作区

v0.2.0-dev 将工具从一次性复核扩展为案件/项目维度的工作区。用户可以在侧边栏选择“临时复核模式”，也可以创建案件工作区，把单次复核或批量复核记录归入同一个案件。

案件工作区包含案件名称、内部案件编号、客户名称、对方主体、案件类型、备注、创建时间和更新时间。系统只保存案件信息、文书元数据、复核结果、待外部复核字段和人工复核记录，不保存完整上传文书正文。

主要能力：

- 创建、选择和删除案件工作区，删除前需要二次确认。
- 在当前案件下运行单次复核，review_run 会关联 `case_id`。
- 批量上传多份 DOCX/PDF，对每份文书分别生成独立 review_id；单个文件失败不影响其他文件。
- 在“历史记录”中查看 review_id、所属案件、文书文件名、复核模式、findings 数量、风险等级数量、外部复核字段数量、人工复核记录数量和创建时间。
- 重新打开历史记录，继续填写人工复核记录，并重新导出单份文书报告。
- 在案件工作区导出案件级复核包，包含案件汇总 Excel、案件 HTML 报告和每份文书的复核包。
- 生成案件内字段差异提示，对同一案件下不同文书的当事人名称、统一社会信用代码、法定代表人、地址、案号、法院名称、合同编号、金额、日期和证据编号做基础字段级对比。

案件内字段差异提示仅表示不同文书之间字段不一致，需人工判断是否属于正常版本差异、材料更新或录入错误，不构成法律结论。

## Word 复核提示版

v0.3.0-dev 新增 DOCX 原文书复核提示版导出。用户上传 `.docx` 文书并完成复核后，可以下载：

```text
<原文件名>_复核提示版.docx
```

说明：

- 仅支持 DOCX 原文书；PDF 仍可导出 Word 复核摘要，但不生成原文提示版。
- 系统不会覆盖原始 Word 文件，也不会自动修改原文正文。
- 提示版会在可定位段落附近插入“【复核提示】”块，并在文末生成“复核提示汇总”。
- 提示内容仅用于人工复核，所有建议仍表达为“建议人工复核”，不构成法律意见。
- 提示版 Word 包含原文内容，用户应按案件材料保密要求妥善保存和流转。
- 历史记录不保存原文书正文，因此历史详情只能重新导出摘要和复核包，不能重新生成原文提示版。

## 规则配置中心

v0.4.0-rc1 新增“规则配置中心”，用于把内置复核规则产品化为可配置规则。入口位于侧边栏“规则配置”。配置中心用于调整辅助复核规则，不代表系统能够自动完成法律判断。

支持能力：

- 查看当前配置概览、配置版本、配置文件路径和 fallback 状态。
- 启用 / 禁用风险类型。
- 调整风险类型 severity 映射。
- 编辑占位符模式。
- 编辑外部复核来源和建议动作。
- 查看并选择文书类型模板。
- 查看字段词典并编辑 alias，alias 会影响字段抽取标签识别。
- 导出当前规则配置为 YAML。
- 导入 YAML / JSON 配置，导入前自动校验。
- 恢复默认规则配置。
- 写入本地配置历史记录。

配置错误时系统会回退默认配置，不会导致复核流程崩溃。所有建议动作必须包含“建议人工复核”，不得包含绝对化错误判断或法律结论。详细说明见 [docs/规则配置说明.md](docs/规则配置说明.md)。

## 演示流程

1. 启动应用并打开 `http://localhost:8501`。
2. 单文书字段抽取模式：只上传文书 `app/sample_data/sample_document.docx`，点击“开始复核”。
3. 完整复核模式：在页面中依次上传：
   - 文书：`app/sample_data/sample_document.docx`
   - 基础信息表：`app/sample_data/sample_base_info.xlsx`
   - 证据目录：`app/sample_data/sample_evidence_index.xlsx`
4. 点击“开始复核”。
5. 查看当前模式、结果概览、复核发现和待外部复核字段清单。
6. 使用风险等级、风险类型和字段搜索过滤复核项。
7. 下载 Excel 复核清单、HTML 报告、Word 复核摘要或 ZIP 复核包。

示例数据通常会触发 5 条以上复核项，包括占位符、案号格式、当事人名称不一致、金额不一致、证据编号缺失、日期顺序可疑等。

## 扫描版 PDF OCR

普通 PDF 通常包含可复制文字，系统可以直接解析。扫描版 PDF 本质上更像图片，普通文本解析可能提取不到字段。

系统会对 PDF 做基础检测：如果 PDF 页数大于 0 但可提取文本很少，会提示该 PDF 可能是扫描件。此时可以在上传区勾选“启用 OCR 识别扫描版 PDF”后重试。

OCR 说明：

- OCR 全程本地运行，不上传 PDF 或图片到外部服务。
- OCR 是可选能力，基础依赖不强制安装。
- 如未安装 OCR 依赖，页面会提示：`当前未安装 OCR 可选依赖。请运行 pip install -r requirements-ocr.txt 后重试。`
- 安装 OCR 依赖：

```bash
pip install -r requirements-ocr.txt
```

- OCR 识别结果会标记来源，例如 `第1页 OCR 文本`，以便和原生 PDF 文本区分。
- OCR 可能识别错误，所有 OCR 结果都必须人工复核。
- OCR 依赖较大，首次安装可能较慢。

## 单文书字段抽取模式

当只上传 DOCX / PDF 文书，未上传基础信息表和证据目录时，系统会自动进入“单文书字段抽取模式”。

该模式适合以下场景：

- 暂时没有结构化基础信息表、案件台账或证据目录。
- 律师助理希望先从文书中整理主体、案号、金额、日期、证据编号等关键事实项。
- 法务需要把文书字段带到企查查、国家企业信用信息公示系统、法院系统、内部客户库或案件台账中人工复核。

该模式只做字段抽取和内部一致性提示，默认本地运行，不访问第三方网站或外部数据库。输出的“待外部复核字段清单”仅表示系统从当前文书中识别到的待核对字段，外部来源仍需人工核对，最终判断由人工完成。

字段清单包含字段类型、提取值、角色/上下文、出现位置、置信度、建议复核来源和建议动作。例如：公司名称建议到企查查、国家企业信用信息公示系统或内部客户库复核；案号建议到法院系统、律所案件台账或内部数据库复核；金额建议与合同、对账单、发票和财务台账复核。

## 两种模式对比

| 模式 | 上传文件 | 系统行为 | 适合场景 |
| --- | --- | --- | --- |
| 单文书字段抽取模式 | 仅文书 | 抽取字段，提示外部人工复核；保留占位符、格式、金额、日期等文书内部检查 | 没有台账或基础信息表时 |
| 完整复核模式 | 文书 + 基础信息表 + 证据目录 | 抽取并比对，生成复核 findings，同时输出待外部复核字段清单 | 有结构化资料时 |

## 人工复核工作流

复核运行完成后，页面会显示“待外部复核字段清单”和“人工复核工作区”。人工复核工作区用于把抽取结果转成可保存的工作底稿。

可记录的信息包括：

- 复核状态：`未复核`、`已确认`、`需修改`、`已忽略`。
- 人工确认值：当状态为“需修改”时，可填写人工核验后的正确值。
- 实际复核来源：可从建议来源中选择，也可选择“其他”。
- 复核备注：记录核验口径、材料名称或需要后续处理的事项。

常见操作流程：

1. 查看“待外部复核字段清单”，确认需要核对的主体、案号、金额、日期、证据编号等字段。
2. 到企查查、国家企业信用信息公示系统、法院系统、律所案件台账、内部客户库、合同台账或案件材料库中人工核验。
3. 在“人工复核工作区”逐条设置复核状态。
4. 如字段需要修改，填写“人工确认值”和备注。
5. 点击“保存人工复核记录”，记录会写入本地 SQLite。
6. 下载 Excel 或 HTML 报告，报告会包含“人工复核记录”。

SQLite 默认保存位置为 `data/review_runs.sqlite`。系统保存复核发现摘要、字段抽取值、脱敏后的敏感值、source_location、人工确认值、复核状态、复核来源、备注和复核时间；不保存完整上传文书内容，也不会连接外部 API 或外部数据库。人工复核工作流只记录用户的人工核验过程，不代表系统已经完成自动外部核验。

## Word 复核包导出

下载区提供“下载 Word 复核摘要”和“下载完整复核包 ZIP”。

Word 复核摘要是面向律师文书工作流的复核工作底稿，包含基本信息、免责声明、复核发现汇总、待外部复核字段清单、人工复核记录、高风险优先处理清单和需修改字段清单。没有人工复核记录时，文档会显示“暂无人工复核记录”，仍可正常生成。

完整复核包 ZIP 包含：

- `复核工作底稿.xlsx`：复核发现、待外部复核字段和人工复核记录。
- `复核报告.html`：适合演示和快速查看的可读报告。
- `文书复核摘要.docx`：适合律师查看、归档和作为工作底稿流转的 Word 摘要。

复核包不包含完整上传文书正文，不会自动修改原文书，也不会连接企查查、法院系统或任何外部数据库。系统只导出抽取字段、出现位置、复核发现、人工复核结果和备注。这样做是为了避免把“辅助复核报告”误用为对原文书的自动修订，最终修改仍应由律师或相关人员完成。

Word 复核摘要可以作为工作底稿归档：建议与原始文书、基础信息表、证据目录和人工核验材料一并保存，便于后续追溯复核过程。

## 当前导出能力

| 导出类型 | 文件格式 | 内容 | 适合场景 |
| --- | --- | --- | --- |
| 复核清单 | Excel | findings、外部复核字段、人工复核记录 | 工作底稿、二次筛选 |
| 复核报告 | HTML | 可读报告 | 演示、快速查看 |
| Word 复核摘要 | DOCX | 面向律师的复核摘要 | 文书工作流、归档 |
| 完整复核包 | ZIP | Excel + HTML + DOCX | 交付和归档 |

## 三种工作流说明

| 工作流 | 上传文件 | 系统行为 | 人工操作 |
| --- | --- | --- | --- |
| 单文书字段抽取 | 仅文书 | 抽取字段并提示外部复核 | 用户去外部来源核验 |
| 完整复核 | 文书 + 基础信息表 + 证据目录 | 自动比对并生成 findings | 用户处理高风险项 |
| 人工复核工作流 | 基于前两者结果 | 保存复核状态、确认值、来源和备注 | 用户形成工作底稿 |

## 支持文件格式

- 文书：`.docx`、`.pdf`
- 基础信息表：`.xlsx`
- 证据目录：`.xlsx`

## 复核规则

当前 MVP 包含以下风险类型：

- `MISSING_FIELD`：关键字段缺失。
- `INTERNAL_CONFLICT`：同一字段在文书内部出现多个不一致值。
- `SOURCE_MISMATCH`：文书值与基础信息表标准值不一致。
- `FORMAT_ERROR`：案号、身份证号、统一社会信用代码、日期、金额等格式异常。
- `POSSIBLY_OUTDATED`：基础信息表更新时间晚于文书中疑似版本日期。
- `PLACEHOLDER_REMAINING`：残留“待补充”“XXXX”“某某”“202X”“【】”等模板痕迹。
- `EVIDENCE_REFERENCE_MISSING`：正文引用的证据编号在证据目录中不存在。
- `AMOUNT_INCONSISTENCY`：文书中的金额值前后不一致。
- `DATE_LOGIC_WARNING`：日期顺序疑似异常。

## 规则配置

规则配置雏形位于 `app/config/review_rules.yml`，当前支持：

- `enabled_risk_types`：启用或关闭某类风险输出。
- `critical_fields`：配置关键字段缺失检查范围。
- `placeholder_patterns`：配置模板占位符匹配模式。
- `severity_overrides`：覆盖部分风险类型的默认风险等级。
- `external_review_sources`：配置字段类型对应的建议复核来源和建议动作，用于“待外部复核字段清单”。

配置文件用于演示规则可配置方向。修改后建议运行测试和验收脚本，避免关闭关键规则导致 sample 演示结果不足。

## 质量验收

运行单元测试：

```bash
python -m pytest -q
```

运行 sample 端到端验收：

```bash
python scripts/acceptance_check.py
```

验收脚本会检查 sample 数据是否能触发预期风险类型、finding 是否都有来源位置、建议动作是否均为人工复核表述、导出报告是否可生成，以及表格中是否存在未脱敏的统一社会信用代码。

构建 Windows portable 包：

```bash
python scripts/build_portable.py
```

portable 包会生成在 `dist/LegalFactReview/`。构建脚本不会打包 `.git`、`.venv`、`__pycache__`、`.pytest_cache`、已有 SQLite 数据库、旧导出文件或临时文件。

## 隐私与安全

- 默认完全本地运行，不上传文书到任何第三方服务。
- 上传文件会写入系统临时文件用于解析，并在单次复核结束后清理。
- 不在日志中输出完整身份证号、手机号、统一社会信用代码等敏感信息。
- UI 和报告仅展示必要复核信息，并对敏感号码做部分脱敏。
- 人工复核记录保存到本地 SQLite，不保存完整文书正文。
- 用户应自行保护 `data/` 和 `exports/` 目录，二者可能包含复核记录、人工备注和导出报告。
- 预留 LLM 抽取接口，但默认关闭；启用外部模型前应由使用者自行评估保密义务、数据出境、客户授权和供应商合规风险。

## 已知边界

- 扫描版 PDF 可通过可选 OCR 处理，但识别准确率受扫描质量影响。
- 多主体基础信息映射仍为规则雏形，复杂案件建议人工重点复核。
- 金额和日期逻辑为启发式检查，只提示可疑项，不作法律判断。
- 未发现明显复核项不代表文书无误。

## 免责声明

本工具仅用于辅助复核基础信息和事实项，输出结果均为“建议人工复核”的线索，不构成法律意见，也不应理解为错误结论。最终判断和修改责任由人工完成。

## 后续可扩展方向

- 增加更多文书类型模板和字段词典。
- 增强 OCR 版面识别和扫描件质量提示。
- 增加规则配置页面，让律所按业务类型维护字段规则。
- 增加本地大模型抽取选项，并提供严格的脱敏和审计机制。
- 增加批量复核、版本对比、审查留痕和权限控制。

## v0.5.0-rc1 发布验证 Python 要求

发布验证必须使用 Python 3.10-3.12，推荐 Python 3.12。不要直接信任系统默认 `python`；如果默认 `python` 指向 Python 3.13，请不要直接运行 `python -m pytest` 或 `python scripts/acceptance_check.py`。

推荐命令：

```bash
py -3.12 -m pytest -q
py -3.12 scripts/acceptance_check.py
py -3.12 scripts/build_desktop_release.py
```

也可以统一运行：

```bash
py -3.12 scripts/verify_release.py
```

`scripts/verify_release.py` 和发布构建脚本会按 `py -3.12`、`py -3.11`、`py -3.10`、最后 `python` 的顺序选择解释器；如果只找到 Python 3.13，会失败并提示安装 Python 3.10-3.12。
