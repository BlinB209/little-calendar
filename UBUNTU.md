# 小日历 Ubuntu 安装说明

目标系统：Ubuntu 22.04 / 24.04 LTS 桌面版。使用系统 Python 3 和 PyQt6，包架构为 all，可用于提供这些依赖的 amd64 / arm64 系统。

## 安装

将 `little-calendar_0.5.0_all.deb` 复制到 Ubuntu，在该文件所在目录打开终端：

```sh
sudo apt update
sudo apt install ./little-calendar_0.5.0_all.deb
```

首次安装需要联网，apt 会安装 Python、Qt 和 Noto 中文字体。若找不到 python3-pyqt6，请先启用 Ubuntu universe 软件源：

```sh
sudo add-apt-repository universe
sudo apt update
sudo apt install ./little-calendar_0.5.0_all.deb
```

安装后在应用菜单搜索“小日历”或“Little Calendar”，也可在终端运行 `little-calendar`。

## 数据与卸载

事项、笔迹、配件和设置保存在 `~/.local/share/LittleCalendar/calendar.sqlite3`；背景图片副本在同目录的 `backgrounds/` 中。如果设置了 XDG_DATA_HOME，则保存在该目录下的 LittleCalendar 文件夹。

关闭两端应用后，可将 Windows 的 `%LOCALAPPDATA%/LittleCalendar/` 目录复制到上述位置迁移数据；覆盖前备份已有文件。背景路径属于本机，跨平台后需要重新选择已复制的图片。

```sh
sudo apt remove little-calendar
```

卸载不会删除个人日历数据。

第三方 Python 插件的源码在 `plugins/packages/`，实例文件在 `plugins/data/`，均位于数据库旁边；从“配件商店 → 第三方插件”导入、启停或打开目录。开发接口见 [PLUGINS.md](PLUGINS.md)。如果插件影响启动，运行 `little-calendar --safe-mode` 后停用它。

## 验证状态

已校验 Debian 包结构、依赖声明、文件内容和启动脚本权限；Windows 原有功能检查通过。当前构建机器为 Windows，没有 Ubuntu 环境，尚未完成 Ubuntu 上的实际安装和桌面运行测试。

安装后可执行无界面启动检查：

```sh
little-calendar --smoke-test
echo $?
```

预期退出码为 0。该检查使用临时数据库、图片和插件目录，不写入个人事项，同时检查图片解码、商店、模块外观及示例 Python 插件的导入、加载、数据隔离和停用恢复。
