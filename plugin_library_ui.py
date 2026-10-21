"""Offline library for user-authored Python accessories; importing never runs code."""
import sys
from pathlib import Path

from qt_compat import *
if sys.platform == 'linux':
    from PyQt6.QtCore import QUrl
    from PyQt6.QtGui import QDesktopServices
    from PyQt6.QtWidgets import QSizePolicy, QSplitter
else:
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices
    from PySide6.QtWidgets import QSizePolicy, QSplitter


def text_label(text='', *, muted=False):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(True)
    widget.setProperty('muted', muted)
    # A long Windows source path must wrap instead of forcing the details wider
    # than a narrow scroll viewport.
    widget.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    widget.setMinimumWidth(0)
    return widget


class PythonPluginLibraryPage(QScrollArea):
    def __init__(self, shop):
        super().__init__(shop)
        self.shop = shop
        self.workspace = shop.workspace
        self.library = self.workspace.plugin_library
        self.entries = []
        self.safe_mode = bool(getattr(self.workspace, 'safe_mode', False))
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName('shopContent')
        box = QVBoxLayout(content)
        self.setWidget(content)
        box.setContentsMargins(14, 14, 14, 14)
        box.addWidget(text_label('把自己或他人编写的 Python 插件存入本机模组库，再选择启用并添加到桌面。导入只复制文件，不运行代码。'))
        if self.safe_mode:
            safe_notice = text_label('当前处于安全模式：第三方插件不会运行。仍可导入、查看和编辑源码；正常启动日历后才能启用或重新加载。')
            safe_notice.setObjectName('pythonSafeModeNotice')
            box.addWidget(safe_notice)
        notice = text_label('运行权限：Python 插件与日历在同一进程运行，可以访问本机文件和网络。请只启用你信任的插件；源码修改后需要重新确认。', muted=True)
        notice.setObjectName('pythonPluginNotice')
        box.addWidget(notice)
        import_row = QHBoxLayout()
        self.import_button = self.button('导入插件包…', self.choose_import, 'python:import')
        self.import_button.setToolTip('选择 ZIP 插件包，或插件目录中的 manifest.json。导入后需另行启用。')
        import_row.addWidget(self.import_button)
        self.example_button = self.button('保存可编辑示例…', self.choose_example, 'python:example')
        self.example_button.setToolTip('保存含清单、Python 源码和说明的 ZIP 示例，解压后即可用编辑器修改。')
        import_row.addWidget(self.example_button)
        import_row.addStretch()
        import_row.addWidget(self.button('打开模组库', self.open_library, 'python:library'))
        box.addLayout(import_row)
        self.search = QLineEdit()
        self.search.setPlaceholderText('搜索第三方插件名称、ID 或说明…')
        self.search.setAccessibleName('搜索第三方插件')
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refresh)
        box.addWidget(self.search)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setMinimumHeight(250)
        self.list = QListWidget()
        self.list.setAccessibleName('第三方插件列表')
        self.list.setMinimumWidth(155)
        self.list.setWordWrap(True)
        self.list.currentItemChanged.connect(self.show_selection)
        self.splitter.addWidget(self.list)
        detail_scroll = QScrollArea()
        self.detail_scroll = detail_scroll
        detail_scroll.setWidgetResizable(True)
        detail_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        details = QWidget()
        details.setObjectName('shopContent')
        self.detail_box = QVBoxLayout(details)
        self.detail_box.setContentsMargins(15, 12, 15, 12)
        self.title = text_label('尚未导入第三方插件')
        title_font = self.title.font()
        title_font.setPixelSize(20)
        title_font.setBold(True)
        self.title.setFont(title_font)
        self.detail_box.addWidget(self.title)
        self.meta = text_label('', muted=True)
        self.detail_box.addWidget(self.meta)
        self.description = text_label('点击“保存可编辑示例”开始编写自己的小插件，或导入他人提供的 ZIP 插件包。')
        self.detail_box.addWidget(self.description)
        self.state = text_label('')
        self.state.setObjectName('pythonPluginState')
        self.detail_box.addWidget(self.state)
        self.error = text_label('')
        self.error.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.detail_box.addWidget(self.error)
        actions = QHBoxLayout()
        self.enable_button = self.button('启用插件', self.enable_selected, 'python:enable')
        self.enable_button.setToolTip('已信任的插件可再次启用；首次运行或源码修改时需要确认。')
        actions.addWidget(self.enable_button)
        self.add_button = self.button('添加到桌面', self.add_selected, 'python:add')
        self.add_button.setProperty('primary', True)
        self.add_button.setToolTip('创建一份独立配件。未启用时先确认启用；已有内容保留。')
        actions.addWidget(self.add_button)
        self.detail_box.addLayout(actions)
        manage = QHBoxLayout()
        self.reload_button = self.button('重新加载修改', self.reload_selected, 'python:reload')
        self.reload_button.setToolTip('从模组库中的源码重新创建已启用的配件；保留插件存储的数据。')
        manage.addWidget(self.reload_button)
        self.source_button = self.button('打开源码目录', self.open_source, 'python:source')
        manage.addWidget(self.source_button)
        self.detail_box.addLayout(manage)
        self.detail_box.addWidget(text_label('源码位置（可复制）', muted=True))
        self.path = QPlainTextEdit()
        self.path.setReadOnly(True)
        self.path.setFixedHeight(66)
        self.path.setTabChangesFocus(True)
        self.path.setAccessibleName('插件源码目录')
        self.detail_box.addWidget(self.path)
        self.detail_box.addWidget(text_label('自编辑步骤：打开源码目录 → 修改文件并保存 → 点击“重新加载修改”。停用会关闭该插件的全部配件，已保存的数据保留。', muted=True))
        self.detail_box.addStretch()
        detail_scroll.setWidget(details)
        self.splitter.addWidget(detail_scroll)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 2)
        self.splitter.setSizes([230, 550])
        box.addWidget(self.splitter, 1)
        self.count = text_label('', muted=True)
        box.addWidget(self.count)
        self.refresh()

    def button(self, text, callback, name):
        button = QPushButton(text)
        button.setAutoDefault(False)
        button.setObjectName(name)
        button.clicked.connect(callback)
        return button

    def selected_id(self):
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def refresh(self, *_args, select_id=None):
        selected = select_id or self.selected_id()
        self.workspace.refresh_python_catalog()
        self.entries = [entry for entry in self.workspace.catalog if entry.get('kind') == 'python']
        needle = self.search.text().strip().casefold()
        self.list.blockSignals(True)
        self.list.clear()
        chosen = None
        for entry in self.entries:
            if needle and needle not in ' '.join(str(entry.get(key, '')) for key in ('title', 'id', 'description')).casefold():
                continue
            key = entry['id']
            failure = entry.get('error') or getattr(self.workspace, 'plugin_errors', {}).get(key)
            state = '需要检查' if failure else ('待确认源码' if not entry.get('approved') else ('已启用' if key in self.workspace.installed else '已停用'))
            item = QListWidgetItem(f'{entry.get("title", key)}\nv{entry.get("version", "?")} · {state}')
            item.setData(Qt.ItemDataRole.UserRole, key)
            self.list.addItem(item)
            if key == selected:
                chosen = item
        if chosen:
            self.list.setCurrentItem(chosen)
        elif self.list.count():
            self.list.setCurrentRow(0)
        self.list.blockSignals(False)
        self.count.setText(f'模组库共 {len(self.entries)} 个插件 · 当前找到 {self.list.count()} 个')
        self.show_selection()

    def show_selection(self, *_args):
        key = self.selected_id()
        entry = next((row for row in self.entries if row['id'] == key), None)
        for button in (self.enable_button, self.add_button, self.reload_button, self.source_button):
            button.setEnabled(bool(entry))
        if entry is None:
            self.title.setText('没有匹配的插件' if self.entries else '尚未导入第三方插件')
            self.meta.clear()
            self.description.setText('点击“保存可编辑示例”开始编写自己的小插件，或导入他人提供的 ZIP 插件包。')
            self.state.clear()
            self.error.clear()
            self.path.clear()
            return
        enabled = key in self.workspace.installed
        self.title.setText(entry.get('title', key))
        self.meta.setText(f'ID：{key}\n版本：{entry.get("version", "?")} · 插件 API：{entry.get("api_version", "?")}')
        self.description.setText(entry.get('description') or '作者未提供用途说明。')
        self.state.setText(('已启用，可以添加到桌面。' if enabled else '已停用，文件及已保存数据保留。') if entry.get('approved') else '已存入模组库，尚未确认运行当前源码。')
        failure = entry.get('error') or getattr(self.workspace, 'plugin_errors', {}).get(key, '')
        instances = [panel.widget().instance for panel in self.workspace.docks.values()
                     if getattr(panel.widget(),'record',{}).get('plugin')==key and hasattr(panel.widget(),'instance')]
        callback_errors = [error for instance in instances if instance for error in instance.context.errors]
        if callback_errors:
            failure = '\n'.join(callback_errors[-10:])
        if enabled and entry.get('approved') and not failure:
            running = sum(instance is not None for instance in instances)
            self.state.setText(f'正常运行：{running} 个实例。' if running else '已启用，尚未创建运行实例；点击“添加到桌面”。')
        elif enabled and not entry.get('approved') and not failure:
            self.state.setText('源码已修改或尚未确认，当前源码需要重新确认。正在运行的旧实例将在重新加载后更新。')
        if self.safe_mode:
            self.state.setText('安全模式：当前未运行插件。可停用原有启用状态，或正常启动日历后继续使用。')
        elif entry.get('error'):
            self.state.setText('插件文件需要修复。打开源码目录检查清单和入口文件，修复后再重新加载。')
        elif failure:
            self.state.setText('插件有实例运行出错。可修改源码并重新加载，或先停用插件。')
        self.error.setText('插件问题：\n' + str(failure)[:2500] if failure else '')
        self.error.setVisible(bool(failure))
        self.enable_button.setText('停用插件' if enabled else '启用插件')
        self.add_button.setEnabled(not self.safe_mode and not bool(entry.get('error')))
        self.enable_button.setEnabled(enabled or (not self.safe_mode and not bool(entry.get('error'))))
        self.reload_button.setEnabled(enabled and not self.safe_mode)
        self.path.setPlainText(str(self.library.source_path(key)))

    def confirm_source(self, key):
        entry = self.library.metadata(key)
        if entry.get('error'):
            raise ValueError(entry['error'])
        if not entry.get('approved'):
            reply = QMessageBox.question(self, '启用此 Python 插件？',
                f'即将运行“{entry.get("title", key)}”的当前源码。\n\n'
                '该插件在日历主进程中运行，能够访问本机文件和网络，并可能影响日历稳定性。'
                '\n请确认你信任插件作者及当前源码。导入本身不会运行代码。\n\n'
                f'源码目录：{self.library.source_path(key)}',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel)
            if reply != QMessageBox.StandardButton.Yes:
                return None
        return entry['digest']

    def enable_plugin(self, key):
        digest = self.confirm_source(key)
        if digest is None:
            return False
        self.workspace.enable_python_plugin(key, digest)
        self.changed('已启用插件。点击“添加到桌面”可创建新配件；已有配件和数据保留。', key)
        return True

    def changed(self, message, key=None):
        self.refresh(select_id=key)
        self.shop._refresh(message)

    def perform(self, action):
        try:
            action()
        except Exception as error:
            self.refresh()
            QMessageBox.warning(self, '插件操作未完成', str(error))

    def enable_selected(self):
        key = self.selected_id()
        if not key:
            return
        def apply():
            if key in self.workspace.installed:
                self.workspace.disable_plugin(key)
                self.changed('已停用插件并关闭相关配件，文件与已保存数据保留。', key)
            else:
                self.enable_plugin(key)
        self.perform(apply)

    def add_selected(self):
        key = self.selected_id()
        if not key:
            return
        def apply():
            if key not in self.workspace.installed or not self.library.is_approved(key):
                if not self.enable_plugin(key):
                    return
            self.workspace.add_module(key)
            self.changed('已添加到桌面。返回桌面后拖动标题摆放；颜色和透明度可在“我的桌面 → 外观”修改。', key)
        self.perform(apply)

    def reload_selected(self):
        key = self.selected_id()
        if not key:
            return
        def apply():
            digest = self.confirm_source(key)
            if digest is None:
                return
            self.workspace.reload_python_plugin(key, digest)
            self.changed('已从模组库源码重新加载插件。', key)
        self.perform(apply)

    def import_path(self, path):
        entry = self.workspace.import_python_plugin(path)
        self.search.clear()
        self.changed(f'已导入“{entry.get("title", entry["id"])}”，尚未运行。确认信任后点击“启用插件”。', entry['id'])
        return entry

    def choose_import(self):
        path, _ = QFileDialog.getOpenFileName(self, '选择 ZIP 插件包或源码目录中的清单', '', 'Python 插件包 (*.zip);;插件清单 (manifest.json)')
        if path:
            self.perform(lambda: self.import_path(path))

    def choose_example(self):
        path, _ = QFileDialog.getSaveFileName(self, '保存可编辑的 Python 插件示例', '我的Python插件.zip', 'ZIP 插件包 (*.zip)')
        if not path:
            return
        if not path.lower().endswith('.zip'):
            path += '.zip'
        def save():
            self.library.export_example(path)
            self.shop.status.setText('已保存可编辑示例。解压后编辑 Python 文件；再导入 ZIP 或源码目录中的清单文件。')
        self.perform(save)

    def open_folder(self, path):
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path)))):
            QMessageBox.information(self, '文件夹位置', str(path))

    def open_library(self):
        self.open_folder(self.library.root)

    def open_source(self):
        key = self.selected_id()
        if key:
            self.open_folder(self.library.source_path(key))
