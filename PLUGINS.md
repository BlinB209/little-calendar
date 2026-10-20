# 自编辑 Python 插件接口（API 1）

小日历支持本地导入自己或他人编写的 Python 插件。插件可以创建 Qt 界面、处理交互并保存自己的数据。内置配件、JSON 配件模板和 Python 插件共用桌面的移动、缩放与外观设置。

## 导入、编辑与调用

1. 打开「配件商店 → 第三方插件」，导入 ZIP 或插件目录内的 `manifest.json`。导入只复制和检查文件，不执行代码，默认停用。
2. 查看标题、版本、描述和源码，确认允许运行后启用；添加到桌面可建立多个独立实例。
3. 「打开源码目录」打开已经导入的副本。编辑后选择重新加载；文件有变化时需要重新确认。原始 ZIP/文件夹与库中副本相互独立。
4. 停用会释放当前运行实例并保留其数据。重新启用或重新加载使用原实例 id，读取原数据。
5. 若插件影响启动，以 `小日历-v0.5.0.exe --safe-mode`（源码使用 `python app.py --safe-mode`）启动，关闭第三方插件后再正常启动。具体 EXE 文件名以下载版本为准。

**Python 插件不是沙箱。** 启用后代码具有当前用户权限，可访问本机文件、网络和进程。确认摘要只用于发现代码变化，不能判断代码是否安全。只启用你信任的插件。加载异常会显示在配件区域；恶意代码、阻塞循环、底层崩溃或直接终止进程无法由界面彻底隔离。

## 文件存储

库目录位于日历数据库旁边的 `plugins/`：

```text
plugins/
  packages/<plugin-id>/    # 已导入的源码、manifest 与资源
  data/<plugin-id>/<instance-id>/  # 每个桌面实例的文件数据
```

通常 Windows 为 `%LOCALAPPDATA%/LittleCalendar/plugins/`，Ubuntu 为 `$XDG_DATA_HOME/LittleCalendar/plugins/`（默认 `~/.local/share/LittleCalendar/plugins/`）。插件库中可直接打开实际目录。`context.set_value()` 保存的 JSON 值仍在日历 SQLite 数据库中，按插件和实例隔离。

建议修改之前备份库和数据库。不要把运行时数据写入 `packages/`，否则摘要变化会要求再次确认。

## 最小插件

```text
my-plugin/
  manifest.json
  main.py
  helpers.py  # 可选
```

`manifest.json`：

```json
{
  "schema": 1,
  "api_version": 1,
  "id": "my-plugin",
  "title": "我的插件",
  "version": "1.0.0",
  "kind": "python",
  "entry": "main.py",
  "description": "一个独立保存内容的便签",
  "author": "你的名字"
}
```

`id` 为 2–64 位小写字母、数字、下划线或连字符，以字母开头。`kind` 可省略，默认 `python`。API 版本必须为 1。ZIP 根目录或唯一顶层文件夹内必须有 `manifest.json`。不接受同 id 覆盖导入；更新请编辑已导入的副本。插件不能与内置/JSON 配件同 id。

`main.py`：

```python
from calendar_plugin_api import QtWidgets

def create_widget(context):
    widget = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(widget)
    text = QtWidgets.QPlainTextEdit()
    text.setPlainText(context.get_value('text', ''))
    text.textChanged.connect(context.guard(
        lambda: context.set_value('text', text.toPlainText())
    ))
    layout.addWidget(text)
    return widget
```

入口必须提供 `create_widget(context)`，返回 `QWidget`（不要创建 `QApplication`、新主窗口或启动自己的事件循环）。从 `calendar_plugin_api` 导入 `QtWidgets`、`QtCore`、`QtGui`；Windows 使用 PySide6，Ubuntu 使用 PyQt6。避免直接依赖某一 Qt 绑定，以便跨平台运行。

同插件文件通过相对导入使用，例如 `from .helpers import label`。资源可用 `Path(__file__).parent / 'image.png'`。运行代码和相对导入来自同一次已确认的文件快照；重新加载会建立新命名空间，不复用旧 `.pyc`。

## context 接口

| 接口 | 含义 |
| --- | --- |
| `plugin_id`, `instance_id` | 插件与桌面实例标识 |
| `get_value(key, default=None)` | 读取当前实例 JSON 数据 |
| `set_value(key, value)` | 同步保存 JSON 数据，单项最多 1 MiB |
| `data_dir` | 当前实例专用 `pathlib.Path`，用于较大的文件 |
| `today` | 读取本机今天日期，`datetime.date` |
| `selected_date` | 主日历当前所选日期，`datetime.date` |
| `theme_colors` | 当前主题颜色字典的副本，读取时获取最新值 |
| `guard(callback)` | 包装按钮、定时器等回调，记录异常并避免普通 Python 异常退出应用 |
| `on_cleanup(callback)` | 卸载/重新加载时调用一次，用来停止定时器、关闭文件等 |
| `report_error(error)` | 将异常记入插件上下文与应用日志 |

新实例不会读到另一个实例的值；同实例重启后保留数据。`theme_colors`、日期不是推送事件，动态显示可使用带父对象的 `QTimer` 轮询。绑定信号和定时器回调时使用 `context.guard()`；未包装的回调不属于宿主能完整捕获的范围。

返回的 widget 可额外定义 `cleanup()`，用于释放自有资源。宿主随后执行 `context.on_cleanup()` 注册的函数，再关闭控件。不要留下后台线程、无父对象的定时器或全局事件过滤器；如确有需要，必须在清理函数中释放。

## 依赖和边界

- 内置支持上面的三个 Qt 模块。Windows EXE 显式包含常用标准库基线：`argparse`、`asyncio`、`base64`、`calendar`、`collections`、`concurrent.futures`、`contextlib`、`csv`、`dataclasses`、`datetime`、`decimal`、`difflib`、`email`、`fractions`、`functools`、`hashlib`、`html`、`http.client`、`inspect`、`io`、`itertools`、`json`、`logging`、`math`、`mimetypes`、`os`、`pathlib`、`platform`、`pprint`、`queue`、`random`、`re`、`shutil`、`socket`、`sqlite3`、`ssl`、`statistics`、`string`、`struct`、`subprocess`、`tempfile`、`threading`、`time`、`traceback`、`types`、`typing`、`unicodedata`、`urllib.parse`、`urllib.request`、`uuid`、`xml.etree.ElementTree`、`zipfile`、`zoneinfo`。不保证这些包的所有可选子模块，也不保证平台服务、系统时区数据库等外部资源存在；完整构建清单见 `build_windows.py` 的 `PLUGIN_STDLIB`。
- Ubuntu 使用系统 Python 及其已安装标准库，第三方插件请使用 Windows 与 Ubuntu 均有的接口。不要在单文件 EXE 内假定 `sys.executable` 是可执行 Python 脚本的解释器。
- 不自动运行 pip、安装第三方依赖、下载代码或执行安装脚本。依赖第三方 Python 包的插件须由作者和用户自行准备兼容运行环境，直接替换 EXE 内部依赖不受支持。
- 每包最多 256 个文件、单文件最多 4 MiB、总计 20 MiB；拒绝绝对路径、`..`、链接和不兼容 API 的插件。
- 内容摘要包括 manifest、源码和资源，编辑任何这些文件都会撤销对应代码的有效批准。缓存 `.pyc` / `__pycache__` 不参与目录摘要。
- 插件管理只发生在本机，本版本没有在线插件市场或自动更新。

项目的 `examples/python-note/` 提供包含相对导入、数据保存和定时器清理的可运行示例；插件库也可导出最小模板 ZIP。
