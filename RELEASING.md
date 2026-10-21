# 构建与发布

版本号只在 `version.py` 中定义，主窗口、Windows / Ubuntu 构建均从这里读取。发布前更新 CHANGELOG.md 首段和用户文档。

1. 在 Windows 执行 `python verify_all.py`，然后 `python build_windows.py`；运行生成的 EXE `--smoke-test` 和 `--smoke-test --safe-mode`。
2. 执行 `python build_ubuntu.py` 生成 DEB。Linux 检查用 `/usr/bin/python3 verify_all.py`，安装 DEB 后运行 `little-calendar --smoke-test`。
3. 推送 main 或创建 PR 会触发 `.github/workflows/build.yml`：Windows 回归、EXE 打包检查，以及 Ubuntu 24.04 apt 安装和无界面检查。两端产物保存在对应 Actions run。
4. 确认检查成功后，对该提交创建与版本匹配的 `vX.Y.Z` 标签并推送。标签构建成功后，流程生成 SHA256SUMS.txt 和发布说明，自动创建带 EXE / DEB 的 Release **草稿**。不自动将未检查版本公开。
5. 核对附件、标签、检查结果和发布说明后，在 GitHub 发布草稿并设为 Latest。下载名称使用英文，便于脚本及浏览器兼容。

Actions 使用 GitHub 自带的短期 `GITHUB_TOKEN`，只有草稿发布任务具有 contents:write。不要提交个人凭据或本机用户数据。若仓库关闭 Actions 或组织限制 token 写入权限，需要仓库管理员启用。

自动检查是无界面测试；Ubuntu 实际桌面的显示缩放、窗口管理器和安装体验仍应人工验证。Windows 本机构建不代表已完成 Ubuntu 桌面实测。

恢复备份会重开日历窗口，备份最多 512 MiB / 5000 个文件。备份不包含之前生成的 recovery ZIP，以免反复嵌套；请自行保留这些文件。当前恢复是整套替换，不合并两个日历，不能恢复任意 SQLite 文件，只接受本程序导出的 ZIP 备份。
