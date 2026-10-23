# 小日历 Ubuntu 安装说明

目标系统：Ubuntu 24.04 LTS 桌面版。使用系统 Python 3 和 PyQt6，包架构为 all，可用于提供这些依赖的 amd64 / arm64 系统。Ubuntu 22.04 的默认软件源缺少 python3-pyqt6，因此本 DEB 不再宣称支持 22.04；请升级到 24.04 后安装。

## 安装

将 `little-calendar_0.8.0_all.deb` 复制到 Ubuntu，在该文件所在目录打开终端：

```sh
sudo apt update
sudo apt install ./little-calendar_0.8.0_all.deb
```

首次安装需要联网，apt 会安装 Python、Qt 和 Noto 中文字体。若找不到 python3-pyqt6，请先启用 Ubuntu universe 软件源：

```sh
sudo add-apt-repository universe
sudo apt update
sudo apt install ./little-calendar_0.8.0_all.deb
```

安装后在应用菜单搜索“小日历”或“Little Calendar”，也可在终端运行 `little-calendar`。

## 数据与卸载

事项、笔迹、配件和设置保存在 `~/.local/share/LittleCalendar/calendar.sqlite3`；背景图片副本在同目录的 `backgrounds/` 中。如果设置了 XDG_DATA_HOME，则保存在该目录下的 LittleCalendar 文件夹。

推荐通过“备份与恢复”在 Windows 导出 ZIP、在 Ubuntu 恢复，背景路径会重新定位，Python 插件恢复后停用。若只想搬事项，也可用“导入导出”导出 .ics 或 .csv，在另一端从 .csv 合并导入（只新增、不删除，每日最多六条）。也可关闭两端应用后手工复制整个数据目录；手工复制时覆盖前备份已有文件，背景图片可能需要重新选择。

```sh
sudo apt remove little-calendar
```

卸载不会删除个人日历数据。

第三方 Python 插件的源码在 `plugins/packages/`，实例文件在 `plugins/data/`，均位于数据库旁边；从“配件商店 → 第三方插件”导入、启停或打开目录。开发接口见 [PLUGINS.md](PLUGINS.md)。如果插件影响启动，运行 `little-calendar --safe-mode` 后停用它。

## 验证状态

本机构建会校验 Debian 包结构、目录条目、依赖声明、文件内容和启动脚本权限。当前本机为 Windows，没有 Ubuntu 桌面环境；人工桌面运行测试尚待完成。远端安装检查见下面的 Actions 流程。

**托盘与提醒**：GNOME 默认不显示传统托盘图标，需要安装 AppIndicator 类扩展才会出现。没有托盘时提醒改在窗口底部提示，“关闭窗口时”的“最小化到托盘”也会自动退回退出程序，不会出现窗口消失却仍在后台运行的情况。

仓库新增 Ubuntu 24.04 Actions 检查：安装系统 Qt 依赖、运行跨平台测试、构建并 apt 安装 DEB，执行无界面启动检查。具体是否通过以对应提交的 Actions 结果为准；无界面检查不等于人工桌面体验验证。

安装后可执行无界面启动检查：

```sh
little-calendar --smoke-test
echo $?
```

预期退出码为 0。该检查使用临时数据库、图片和插件目录，不写入个人事项，同时检查图片解码、商店、模块外观及示例 Python 插件的导入、加载、数据隔离和停用恢复。
