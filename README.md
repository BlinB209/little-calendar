# 小日历 · 基础预览版

Windows：打开 `dist/小日历.exe` 即可运行，不需要安装 Python。

- 读取本地时间，支持 2020 至 2030 年，月视图补齐相邻月份日期。
- 可同时显示 1 至 3 个月，并切换横向或纵向排列；窗口可调整大小。
- 点击日期，在右侧编辑最多六条事项，自由选择早、午、晚；文字自动保存。
- 开启画笔后，在日历上拖动画线。支持五种颜色、荧光笔、撤销、重做。
- 笔迹跟随月份保存，调整窗口后按比例缩放。撤销针对最后点击或绘画的月份。
- 数据保存在 `%LOCALAPPDATA%/LittleCalendar/calendar.sqlite3`。关闭应用后复制该文件即可备份。

当前为预览版本：尚未提供橡皮擦、自定义颜色和导入导出。

Ubuntu 安装包：`dist/little-calendar_0.1.1_all.deb`，详细安装与验证状态见 `UBUNTU.md`。

## 源码运行

Windows：Python 3.10 或以上，安装 requirements.txt 后执行 `python app.py`。

Ubuntu：使用系统包 `python3-pyqt6` 和 `fonts-noto-cjk`，执行 `python3 app.py`。

Windows 打包：安装依赖到 `.venv` 后执行 `powershell -ExecutionPolicy Bypass -File build_windows.ps1`。

Ubuntu 打包：`python build_ubuntu.py`。此包不含本机二进制，依赖由 apt 安装；实际 Ubuntu 桌面运行尚待验证。
