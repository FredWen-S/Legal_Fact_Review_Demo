# v0.5.0-rc1 Release Checklist

## 桌面服务

- [ ] `python scripts/desktop_service.py status` 输出可解析 JSON。
- [ ] 未启动时显示 `stopped`。
- [ ] 缺少 `app/main.py` 时返回中文错误 JSON。
- [ ] 启动时自动选择可用端口。
- [ ] 启动后写入 `logs/service.pid`。
- [ ] 启动后写入 `logs/desktop_service.log`。
- [ ] `stop` 只停止 `logs/service.pid` 指向的本项目 Streamlit 服务。
- [ ] stale pid 会被清理。
- [ ] 不误杀其他 Python 进程。
- [ ] `logs` 在日志为空时也返回稳定 JSON。

## 桌面 UI

- [ ] 服务未启动时显示“服务未启动”并提供启动按钮。
- [ ] 服务启动中显示明确提示并避免重复点击启动。
- [ ] 服务已启动时显示访问地址。
- [ ] “打开复核界面”使用 service status 返回的端口。
- [ ] “停止服务”可用。
- [ ] 启动失败时显示中文错误摘要。
- [ ] 可查看最近日志。
- [ ] data / exports / logs 目录按钮可用，失败时友好提示。

## Release 包

- [ ] `dist/LegalFactReview_v0.5.0-rc1_desktop/` 已生成。
- [ ] `dist/LegalFactReview_v0.5.0-rc1_desktop.zip` 已生成。
- [ ] `dist/LegalFactReview_v0.5.0-rc1_desktop.sha256.txt` 已生成。
- [ ] 包内包含 `desktop/`、`app/`、`scripts/`、`docs/`。
- [ ] 包内包含 `requirements.txt`、`README.md`、`README_快速启动.md`。
- [ ] 如存在 `.streamlit/config.toml`，包内包含该文件。
- [ ] 包内包含 `docs/桌面版说明.md`。
- [ ] 包内不包含 `.git`、`.venv`、`__pycache__`、`.pytest_cache`。
- [ ] 包内不包含 `node_modules`。
- [ ] 包内不包含 `desktop/src-tauri/target`。
- [ ] 包内不包含 `data/review_runs.sqlite`。
- [ ] 包内不包含用户导出报告或临时 acceptance 测试数据。

## 样例数据保护

- [ ] `scripts/generate_test_files.py --output <dir>` 可生成到临时目录。
- [ ] `scripts/acceptance_check.py` 不修改 `app/sample_data/test_cases/`。
- [ ] 发布前 `git status` 中 `app/sample_data/test_cases/` 无非预期 modified。
- [ ] 如有验收脚本遗留二进制噪声，执行 `git restore -- app/sample_data/test_cases`。

## 旧流程回归

- [ ] 完整复核模式通过。
- [ ] 单文书字段抽取模式通过。
- [ ] 案件工作区、批量复核、历史记录通过。
- [ ] Word 复核提示版通过。
- [ ] 规则配置中心通过。
- [ ] Windows portable 构建仍通过。
- [ ] release zip 构建仍通过。

## 干净 Windows 人工验收

- [ ] Python 3.10-3.12 可用，推荐 3.11 或 3.12。
- [ ] portable `start.bat` 可启动。
- [ ] 桌面壳可打开。
- [ ] 桌面壳启动本地服务成功。
- [ ] 桌面壳打开复核界面成功。
- [ ] 桌面壳停止服务成功。
- [ ] data / exports / logs 目录可打开。
- [ ] 日志能辅助定位启动失败原因。
