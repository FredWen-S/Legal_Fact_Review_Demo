# v0.6.0-rc1 Release Checklist

## Installer Test Python

- [ ] `scripts/build_windows_installer.py` is launched with a supported Python 3.10-3.12 interpreter that has test dependencies installed.
- [ ] If the current interpreter lacks `pytest`, run `<python> -m pip install -r requirements.txt` or only use `--skip-tests` after manual verification.
- [ ] `--skip-tests` warning has been acknowledged: 已跳过自动测试，请确保已手动运行 pytest/acceptance_check/verify_release。
- [ ] Python 3.13 is still rejected and is not used for tests, runtime selection, or release validation.

## 工作区

- [ ] 执行 `git restore -- app/sample_data/test_cases`。
- [ ] `git status` 中 `app/sample_data/test_cases/` 无 modified。

## 构建环境

- [ ] Windows 构建机。
- [ ] Node.js 20/22 LTS 可用：`node --version`。
- [ ] Node 25 可尝试，但不作为正式推荐构建环境。
- [ ] npm 可用：`npm --version`。
- [ ] Rust cargo 可用：`cargo --version`。
- [ ] Tauri CLI 可用：`npm run tauri -- --version`。
- [ ] Python 3.10-3.12 可用，推荐 Python 3.12。
- [ ] Python 3.13 未被加入支持范围。

## 自动化验证

- [ ] `python -m pytest tests -q --ignore=tmp` 通过。
- [ ] `python scripts/acceptance_check.py` 通过。
- [ ] `python scripts/verify_release.py` 通过。
- [ ] `cargo check --manifest-path desktop/src-tauri/Cargo.toml` 通过。
- [ ] `python scripts/check_installer_env.py` 通过。
- [ ] `python scripts/build_windows_installer.py --no-embedded-python` 通过。
- [ ] 如提供 Python embed zip，`python scripts/build_windows_installer.py --python-zip <zip>` 通过。

## Installer 包

- [ ] `dist/LegalFactReview_v0.6.0-rc1_windows_installer/` 已生成。
- [ ] no-python installer 已生成：`LegalFactReview_v0.6.0-rc1_windows_installer_no_python.exe`。
- [ ] 如构建 embedded Python，已生成：`LegalFactReview_v0.6.0-rc1_windows_installer_embedded_python.exe`。
- [ ] `LegalFactReview_v0.6.0-rc1_windows_installer.sha256.txt` 已生成。
- [ ] resources 包含 `LegalFactReview/`。
- [ ] no-python installer 文档明确要求用户安装 Python 3.10-3.12。
- [ ] embedded-python installer 优先使用 `resources/python/python.exe`。

## 资源审计

- [ ] resources 不包含 `.git`。
- [ ] resources 不包含 `.venv`。
- [ ] resources 不包含 `node_modules`。
- [ ] resources 不包含 `src-tauri/target`。
- [ ] resources 不包含 `tmp`。
- [ ] resources 不包含 `dist`。
- [ ] resources 不包含 `review_runs.sqlite`。
- [ ] resources 不包含用户导出报告。

## 人工验收

- [ ] 干净 Windows 机器安装 no-python installer。
- [ ] no-python installer 机器已安装 Python 3.12。
- [ ] 启动桌面应用。
- [ ] 点击刷新状态。
- [ ] 点击启动服务。
- [ ] 打开复核界面。
- [ ] Case 02 单文书模式通过。
- [ ] Case 01 完整复核模式通过。
- [ ] Word 提示版导出通过。
- [ ] ZIP 导出通过。
- [ ] 停止服务。
- [ ] 卸载应用。
- [ ] logs 中文无乱码。
- [ ] 不误杀其他 Python 进程。

## 边界

- [ ] 不新增复核规则。
- [ ] 不改核心复核逻辑。
- [ ] 不新增业务页面。
- [ ] 不改数据库 schema。
- [ ] 不接入外部 API。
- [ ] 不上传文件。
- [ ] 不保存完整原文书正文。
- [ ] 不自动修改原文书。
- [ ] 不输出法律结论。
- [ ] 明确不构成法律意见，不替代律师判断。
