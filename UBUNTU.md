# 小日历 Ubuntu 安装说明

目标系统：Ubuntu 22.04 / 24.04 LTS 桌面版。使用系统 Python 3 和 PyQt6，包架构为 all，可用于提供这些依赖的 amd64 / arm64 系统。

## 安装

将 `little-calendar_0.1.1_all.deb` 复制到 Ubuntu，在该文件所在目录打开终端：

```sh
sudo apt update
sudo apt install ./little-calendar_0.1.1_all.deb
```

首次安装需要联网，apt 会安装 Python、Qt 和 Noto 中文字体。若找不到 python3-pyqt6，请先启用 Ubuntu universe 软件源：

```sh
sudo add-apt-repository universe
sudo apt update
sudo apt install ./little-calendar_0.1.1_all.deb
```

安装后在应用菜单搜索“小日历”或“Little Calendar”，也可在终端运行 `little-calendar`。

## 数据与卸载

事项和笔迹保存在 `~/.local/share/LittleCalendar/calendar.sqlite3`；如果设置了 XDG_DATA_HOME，则保存在该目录下的 LittleCalendar 文件夹。

关闭两端应用后，可将 Windows 的 `%LOCALAPPDATA%/LittleCalendar/calendar.sqlite3` 复制到上述位置迁移数据；覆盖前备份已有文件。

```sh
sudo apt remove little-calendar
```

卸载不会删除个人日历数据。

## 验证状态

已校验 Debian 包结构、依赖声明、文件内容和启动脚本权限；Windows 原有功能检查通过。当前构建机器为 Windows，没有 Ubuntu 环境，尚未完成 Ubuntu 上的实际安装和桌面运行测试。

安装后可执行无界面启动检查：

```sh
little-calendar --smoke-test
echo $?
```

预期退出码为 0。该检查使用内存数据库，不写入个人事项。
