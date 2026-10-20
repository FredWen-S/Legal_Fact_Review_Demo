# v0.5.0 Release Checklist

## 自动化验收

- [ ] `pytest tests -q` 通过。
- [ ] `scripts/acceptance_check.py` 通过。
- [ ] `scripts/verify_release.py` 通过。
- [ ] `cargo check --manifest-path desktop/src-tauri/Cargo.toml` 通过。
- [ ] `scripts/build_desktop_release.py` 通过。
- [ ] release zip 内容审计通过。
- [ ] SHA256 生成。
- [ ] `dist/LegalFactReview_v0.5.0_desktop.zip` 已生成。
- [ ] `dist/LegalFactReview_v0.5.0_desktop.sha256.txt` 已生成。
- [ ] 如保留 portable，`dist/LegalFactReview_v0.5.0_windows_portable.zip` 已生成。
- [ ] 如保留 portable，`dist/LegalFactReview_v0.5.0_windows_portable.sha256.txt` 已生成。

## 包内容审计

- [ ] 桌面 release 包包含 `desktop/`。
- [ ] 桌面 release 包包含 `app/`。
- [ ] 桌面 release 包包含 `scripts/`。
- [ ] 桌面 release 包包含 `requirements.txt`。
- [ ] 桌面 release 包包含 `README.md`。
- [ ] 桌面 release 包包含 `README_快速启动.md`。
- [ ] 桌面 release 包包含 `docs/`。
- [ ] 桌面 release 包包含 `.streamlit/config.toml`。
- [ ] release 包不包含 `.git`。
- [ ] release 包不包含 `.venv`。
- [ ] release 包不包含 `__pycache__`。
- [ ] release 包不包含 `.pytest_cache`。
- [ ] release 包不包含 `node_modules`。
- [ ] release 包不包含 `desktop/src-tauri/target`。
- [ ] release 包不包含 `data/review_runs.sqlite`。
- [ ] release 包不包含用户导出报告。
- [ ] release 包不包含 `tmp`。
- [ ] release 包不包含 `dist` 内旧包。

## Python 与临时目录

- [ ] 推荐 Python 3.12。
- [ ] 支持 Python 3.10-3.12。
- [ ] 不支持 Python 3.13。
- [ ] 只有 Python 3.13 时显示“未找到受支持的 Python 版本。请安装 Python 3.10-3.12，推荐 Python 3.12。”。
- [ ] `pytest` 默认只收集 `tests/`。
- [ ] `pytest` 不扫描 `tmp/`、`dist/`、`.venv/`、`desktop/src-tauri/target/`、`node_modules/`。
- [ ] `scripts/verify_release.py` 使用系统临时目录，不使用项目根目录固定 `tmp/pytest-verify`。
- [ ] `scripts/acceptance_check.py` 不修改 `app/sample_data/test_cases/`。
- [ ] 发布前 `git status` 中 `app/sample_data/test_cases/` 无 modified。

## 人工验收

- [ ] 干净 Windows 解压。
- [ ] 安装 Python 3.12。
- [ ] 在桌面 release 的 `desktop/` 目录运行 `npm install`。
- [ ] 运行 `npm run dev`。
- [ ] 点击“刷新状态”有反馈。
- [ ] 点击“启动服务”有 loading 和成功/失败反馈。
- [ ] 点击“打开复核界面”可打开当前服务地址。
- [ ] 服务未启动时点击“打开复核界面”提示“请先启动服务”。
- [ ] 点击“查看日志”有反馈，空日志显示“暂无日志”。
- [ ] 点击“打开 data 目录”有反馈。
- [ ] 点击“打开 exports 目录”有反馈。
- [ ] 点击“打开 logs 目录”有反馈。
- [ ] 点击“停止服务”有反馈。
- [ ] Case 02 单文书模式通过。
- [ ] Case 01 完整复核模式通过。
- [ ] Case 08 案件批量模式通过。
- [ ] Word 提示版导出通过。
- [ ] 案件级 ZIP 导出通过。
- [ ] 中文日志无乱码。
- [ ] 停止服务不误杀其他 Python 进程。

## 边界确认

- [ ] 不新增复核规则。
- [ ] 不改核心复核逻辑。
- [ ] 不新增 UI 业务页面。
- [ ] 不接入外部 API。
- [ ] 不上传文件。
- [ ] 不自动连接企查查、法院系统或内部数据库。
- [ ] 不保存完整原文书正文。
- [ ] 不自动修改原文书。
- [ ] 不输出法律结论。
- [ ] 明确工具不构成法律意见。
- [ ] 明确工具不替代律师判断。
