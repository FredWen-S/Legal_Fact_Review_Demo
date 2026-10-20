# v0.6.0-rc1 Installer Manual Test

## 准备

1. 使用干净 Windows 机器。
2. Node.js / Rust / cargo 只要求构建机安装，普通用户机器不要求安装。
3. 如果测试 no-python installer，请安装 Python 3.12。
4. 确认没有仅安装 Python 3.13 的误用环境。

## 安装

1. 运行 `LegalFactReview_v0.6.0-rc1_windows_installer_no_python.exe`。
2. 如果测试 embedded-python installer，运行 `LegalFactReview_v0.6.0-rc1_windows_installer_embedded_python.exe`。
3. 按安装器提示完成安装。
4. 从开始菜单或桌面入口启动 LegalFactReview。

## 桌面壳验证

1. 点击“刷新状态”，页面必须有反馈。
2. 点击“启动服务”，页面显示 loading，并最终显示成功或中文错误。
3. 点击“打开复核界面”，应打开当前服务地址。
4. 点击“查看日志”，空日志显示“暂无日志”，有日志时中文不乱码。
5. 点击“打开 data 目录”，目录应打开或显示中文错误。
6. 点击“打开 exports 目录”，目录应打开或显示中文错误。
7. 点击“打开 logs 目录”，目录应打开或显示中文错误。

## 业务 smoke test

1. 上传 Case 02 单文书模式样例。
2. 执行复核，确认不出现外部比对误报。
3. 上传 Case 01 完整复核模式样例。
4. 执行复核，确认有复核发现。
5. 导出 Word 提示版。
6. 导出完整 ZIP 复核包。
7. 确认导出报告不构成法律意见，仍要求人工判断。

## 停止与卸载

1. 回到桌面壳，点击“停止服务”。
2. 确认不会误杀其他 Python 进程。
3. 卸载应用。
4. 检查 `logs/desktop_service.log` 中文无乱码。

## 隐私边界

- 不上传文书。
- 不接入外部 API。
- 不自动连接企查查、法院系统或内部数据库。
- 不保存完整原文书正文。
- 不自动修改原文书。
- 不输出法律结论。
