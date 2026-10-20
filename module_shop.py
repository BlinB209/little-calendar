"""Friendly, offline accessory catalog and desktop manager."""
import json
import sys
from pathlib import Path

from qt_compat import *
if sys.platform == 'linux':
    from PyQt6.QtWidgets import QGridLayout, QSizePolicy
else:
    from PySide6.QtWidgets import QGridLayout, QSizePolicy


KINDS = {
    'note': ('文字记录', '便签', '点击正文即可输入，内容自动保存。适合随手记、提醒和灵感。'),
    'checklist': ('任务管理', '清单', '输入事项后按回车添加，勾选完成；双击文字可修改。'),
    'calendar': ('日期与时间', '月历', '用顶部箭头独立翻月，点击日期会切换主日历和每日事项。'),
    'clock': ('日期与时间', '时钟', '跟随本机时间自动更新，调整配件大小时数字随之缩放。'),
    'habit': ('任务管理', '打卡', '每天勾选“今天已完成”，累计次数自动保存。'),
}


def label(text, *, muted=False, size=None):
    result = QLabel(text)
    result.setWordWrap(True)
    result.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    if muted:
        result.setProperty('muted', True)
    if size:
        font = result.font()
        font.setPixelSize(size)
        font.setBold(size >= 18)
        result.setFont(font)
    return result


class AccessoryPreview(QWidget):
    """Small code-drawn examples, with the same theme as the calendar."""
    def __init__(self, kind, colors):
        super().__init__()
        self.kind, self.colors = kind, colors
        self.setFixedHeight(76)
        self.setAccessibleName('配件示意图')

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = self.colors
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(c['alternate']))
        p.drawRoundedRect(QRectF(0, 0, self.width(), self.height()), 9, 9)
        p.setPen(QColor(c['muted']))
        font = QFont(self.font())
        font.setPixelSize(11)
        p.setFont(font)
        p.drawText(QRectF(self.width()-48, 5, 40, 18), Qt.AlignmentFlag.AlignRight, '示意')
        p.setPen(QColor(c['text']))
        font.setPixelSize(13)
        p.setFont(font)
        if self.kind == 'note':
            p.drawText(QRectF(16, 12, self.width()-70, 26), '今天的灵感')
            p.setPen(QColor(c['muted']))
            p.drawText(QRectF(16, 39, self.width()-30, 25), '周末去公园，带上一本书…')
        elif self.kind == 'checklist':
            p.setPen(QColor(c['accent']))
            p.drawRect(QRectF(16, 21, 12, 12))
            p.drawLine(18, 27, 21, 30)
            p.drawLine(21, 30, 26, 24)
            p.drawText(QRectF(39, 12, self.width()-93, 26), '整理本周计划')
            p.setPen(QColor(c['text']))
            p.drawRect(QRectF(16, 47, 12, 12))
            p.drawText(QRectF(39, 39, self.width()-53, 25), '阅读二十分钟')
        elif self.kind == 'calendar':
            width = min((self.width()-36)/7, 38)
            for i in range(7):
                r = QRectF(12+i*width, 28, width-3, 32)
                if i == 3:
                    p.fillRect(r, QColor(c['selected']))
                p.setPen(QColor(c['accent'] if i == 3 else c['text']))
                p.drawText(r, Qt.AlignmentFlag.AlignCenter, str(12+i))
        elif self.kind == 'clock':
            font.setPixelSize(28)
            p.setFont(font)
            p.drawText(QRectF(16, 15, self.width()-65, 44), '10:24:36')
        else:
            p.setPen(QColor(c['accent']))
            p.drawRect(QRectF(16, 21, 12, 12))
            p.drawLine(18, 27, 21, 30)
            p.drawLine(21, 30, 26, 24)
            p.drawText(QRectF(39, 12, self.width()-93, 26), '今天已完成')
            p.setPen(QColor(c['muted']))
            p.drawText(QRectF(16, 39, self.width()-30, 25), '每天一点进步 · 累计完成 12 天')
        p.end()


class ModuleShop(QDialog):
    def __init__(self, workspace):
        super().__init__(workspace)
        self.workspace = workspace
        self.colors = workspace.owner.theme_colors
        self.cards = []
        self._columns = 0
        self.setWindowTitle('配件商店 · 本地离线')
        self.resize(980, 740)
        self.setMinimumSize(660, 510)
        c = self.colors
        self.setStyleSheet(f'''
            QWidget#shopCard {{background:{c['surface']};border:1px solid {c['border']};border-radius:12px;}}
            QWidget#shopContent {{background:{c['background']};}}
            QLabel#shopStatus {{background:{c['selected']};color:{c['text']};padding:9px;border-radius:7px;}}
            QPushButton[primary="true"] {{background:{c['accent']};color:#ffffff;border-color:{c['accent']};font-weight:600;}}
            QPushButton[primary="true"]:hover {{background:{QColor(c['accent']).lighter(112).name()};}}
            QTabWidget::pane {{border:1px solid {c['border']};border-radius:8px;}}
            QTabBar::tab {{background:{c['alternate']};color:{c['secondary']};padding:10px 16px;}}
            QTabBar::tab:selected {{background:{c['surface']};color:{c['accent']};}}
        ''')
        box = QVBoxLayout(self)
        box.setContentsMargins(20, 18, 20, 16)
        box.setSpacing(12)
        box.addWidget(label('把日历布置成你的桌面', size=23))
        box.addWidget(label('添加便签、清单和时钟；同一种配件可以添加多份，各自保存内容。商店离线可用。', muted=True))
        self.tabs = QTabWidget()
        box.addWidget(self.tabs, 1)
        self._build_catalog()
        self._build_desktop()
        self._build_help()
        self.tabs.currentChanged.connect(self._tab_changed)
        self.status = label('选一个配件，点击“添加到桌面”即可开始。')
        self.status.setObjectName('shopStatus')
        self.status.setAccessibleName('操作反馈')
        box.addWidget(self.status)
        footer = QHBoxLayout()
        self.import_button = self._button('导入配件文件…', self.choose_import)
        self.import_button.setToolTip('读取本地 JSON 配件模板；导入成功后可添加到桌面。')
        footer.addWidget(self.import_button)
        self.example_button = self._button('保存示例文件…', self.choose_export)
        self.example_button.setToolTip('保存一个可以修改名称后导入的便签示例。')
        footer.addWidget(self.example_button)
        footer.addStretch()
        self.close_button = self._button('返回桌面', self.accept, primary=True)
        footer.addWidget(self.close_button)
        box.addLayout(footer)
        self.refresh_catalog()
        self.refresh_modules()

    def _button(self, text, callback, primary=False):
        button = QPushButton(text)
        button.setAutoDefault(False)
        button.setProperty('primary', primary)
        button.clicked.connect(callback)
        return button

    def _build_catalog(self):
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(14, 14, 14, 14)
        filter_row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText('搜索配件名称或用途…')
        self.search.setAccessibleName('搜索配件')
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refresh_catalog)
        filter_row.addWidget(self.search, 1)
        self.category = QComboBox()
        self.category.setAccessibleName('配件分类')
        self.category.addItems(['全部分类', '文字记录', '任务管理', '日期与时间'])
        self.category.currentIndexChanged.connect(self.refresh_catalog)
        filter_row.addWidget(self.category)
        self.filter = QComboBox()
        self.filter.setAccessibleName('配件可用状态')
        self.filter.addItems(['全部状态', '可使用', '已停用'])
        self.filter.currentIndexChanged.connect(self.refresh_catalog)
        filter_row.addWidget(self.filter)
        box.addLayout(filter_row)
        self.result_label = label('', muted=True)
        box.addWidget(self.result_label)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.catalog_content = QWidget()
        self.catalog_content.setObjectName('shopContent')
        self.grid = QGridLayout(self.catalog_content)
        self.grid.setContentsMargins(0, 0, 4, 0)
        self.grid.setSpacing(12)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.catalog_content)
        box.addWidget(self.scroll, 1)
        self.tabs.addTab(page, '发现配件')

    def _build_desktop(self):
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(14, 14, 14, 14)
        box.addWidget(label('拖动配件标题移动位置，拖右下角调整大小；重叠时点击配件即可置于前方。', muted=True))
        box.addWidget(label('“隐藏”仅收起显示，内容始终保留；“定位”会返回桌面并滚动到该配件。', muted=True))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName('shopContent')
        self.module_list = QVBoxLayout(content)
        self.module_list.setContentsMargins(0, 0, 4, 0)
        self.module_list.setSpacing(10)
        self.module_list.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(content)
        box.addWidget(scroll, 1)
        self.reset_button = self._button('恢复默认排列（保留全部内容）', self.reset_layout)
        self.reset_button.setToolTip('重新排列日历和配件，并显示所有可用配件。不会清空便签或日历内容。')
        box.addWidget(self.reset_button)
        self.tabs.addTab(page, '我的桌面')

    def _build_help(self):
        page = QScrollArea()
        page.setWidgetResizable(True)
        content = QWidget()
        content.setObjectName('shopContent')
        box = QVBoxLayout(content)
        box.setContentsMargins(22, 20, 22, 20)
        sections = [
            ('01  添加与摆放', '在“发现配件”点击“添加到桌面”。返回桌面后，拖动配件顶部标题移动；拖右下角缩放。配件可以自由重叠，点击会置前。若不能移动，请取消顶部“锁定位置”。'),
            ('02  主日历与配件有什么区别？', '主日历用于在日期格子里手写、盖章和查看每日事项；配件是额外的便签、清单、时钟等。独立月历用于翻月选日，不提供手写。便签接受键盘文字输入。'),
            ('03  隐藏、停用与恢复', '隐藏：只收起某一份配件，在“我的桌面”中重新显示即可。停用：隐藏此种配件的全部实例，保留内容。点击“恢复使用”恢复原有状态；点击“添加到桌面”则会同时再创建一份。'),
            ('04  自定义配件文件', '点击“保存示例文件”得到一个便签模板。用文本编辑器修改 title（显示名称）和 description（用途说明），保存为 JSON 后导入。id 必须唯一，使用小写字母、数字、横线或下划线。'),
            ('05  目前支持的本地类型', 'note：便签；checklist：待办清单；calendar：独立月历；clock：数字时钟；habit：习惯打卡。配件文件只描述这些已有功能，不包含新程序，也不执行脚本。当前商店不连接在线插件源。'),
        ]
        for title, text in sections:
            box.addWidget(label(title, size=18))
            box.addWidget(label(text))
            box.addSpacing(12)
        box.addStretch()
        page.setWidget(content)
        self.tabs.addTab(page, '使用帮助')

    def _tab_changed(self, index):
        if index == 1:
            self.refresh_modules()

    def _clear(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def refresh_catalog(self, *_):
        if not hasattr(self, 'grid'):
            return
        self._clear(self.grid)
        self.cards = []
        needle = self.search.text().strip().casefold()
        category = self.category.currentText()
        state = self.filter.currentIndex()
        matches = []
        for plugin in self.workspace.catalog:
            available = plugin['id'] in self.workspace.installed
            kind_category = KINDS.get(plugin['kind'], ('其他', '', ''))[0]
            searchable = ' '.join([plugin['title'], plugin.get('description', ''), kind_category]).casefold()
            if needle and needle not in searchable:
                continue
            if category != '全部分类' and category != kind_category:
                continue
            if (state == 1 and not available) or (state == 2 and available):
                continue
            matches.append(plugin)
        self.result_label.setText(f'找到 {len(matches)} 种配件 · 已有内容会自动保存')
        self.visible_plugin_ids = [plugin['id'] for plugin in matches]
        if not matches:
            empty = label('没有找到匹配的配件\n试试其他关键词，或把分类和状态改为“全部”。', muted=True)
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setMinimumHeight(160)
            self.cards.append(empty)
        for plugin in matches:
            self.cards.append(self._card(plugin))
        self._reflow(force=True)

    def _card(self, plugin):
        key = plugin['id']
        available = key in self.workspace.installed
        records = [r for r in self.workspace.records if r['plugin'] == key]
        visible = sum(not self.workspace.docks[r['id']].isHidden() for r in records if r['id'] in self.workspace.docks)
        kind_category, kind_name, usage = KINDS[plugin['kind']]
        card = QWidget()
        card.setObjectName('shopCard')
        # The scroll area must scroll whole cards instead of compressing each
        # card into the viewport when the dialog is short.
        card.setMinimumHeight(316)
        box = QVBoxLayout(card)
        box.setContentsMargins(15, 13, 15, 13)
        box.setSpacing(8)
        box.addWidget(label(plugin['title'], size=19))
        box.addWidget(label(f'{kind_category} · {kind_name} · {"可使用" if available else "已停用"}', muted=True))
        box.addWidget(AccessoryPreview(plugin['kind'], self.colors))
        description = label(plugin.get('description') or f'一个可独立使用的{kind_name}配件。')
        box.addWidget(description)
        box.addWidget(label(usage, muted=True))
        box.addStretch()
        box.addWidget(label(f'已添加 {len(records)} 份 · 当前显示 {visible} 份', muted=True))
        actions = QHBoxLayout()
        add = self._button('添加到桌面', lambda _checked=False, k=key: self.add_plugin(k), primary=True)
        add.setObjectName('add:'+key)
        add.setToolTip('新建一份独立配件；现有内容保留。已停用时会自动恢复使用。')
        actions.addWidget(add, 1)
        secondary = self._button('停用…' if available else '恢复使用',
            lambda _checked=False, k=key, active=available: self.disable_plugin(k) if active else self.restore_plugin(k))
        secondary.setObjectName('disable:'+key if available else 'restore:'+key)
        secondary.setToolTip('隐藏该类全部配件，保留内容，可随时恢复。' if available else '恢复原有配件，不创建新的一份。')
        actions.addWidget(secondary)
        box.addLayout(actions)
        return card

    def _reflow(self, force=False):
        if not hasattr(self, 'scroll'):
            return
        columns = 2 if self.scroll.viewport().width() >= 720 else 1
        if not force and columns == self._columns:
            return
        self._columns = columns
        for card in self.cards:
            self.grid.removeWidget(card)
        for index, card in enumerate(self.cards):
            self.grid.addWidget(card, index // columns, index % columns)
        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 1 if columns == 2 else 0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'scroll'):
            QTimer.singleShot(0, self._reflow)

    def refresh_modules(self):
        if not hasattr(self, 'module_list'):
            return
        self._clear(self.module_list)
        records = {r['id']: r for r in self.workspace.records}
        for key, panel in self.workspace.docks.items():
            record = records.get(key)
            available = record is None or record['plugin'] in self.workspace.installed
            visible = not panel.isHidden()
            card = QWidget()
            card.setObjectName('shopCard')
            box = QVBoxLayout(card)
            box.setContentsMargins(13, 11, 13, 11)
            box.addWidget(label(panel.windowTitle(), size=18))
            if key == 'main-calendar':
                detail = '核心日历 · 手写、日期印章和每日事项概览'
            elif key == 'daily-editor':
                detail = '每日事项 · 编辑选中日期的早、午、晚六项安排'
            else:
                detail = f"{KINDS[record['kind']][1]} · 内容独立保存"
            box.addWidget(label(detail + (' · 显示中' if visible else ' · 已隐藏') if available else detail + ' · 已停用，内容保留', muted=True))
            actions = QHBoxLayout()
            toggle = QCheckBox('在桌面显示')
            toggle.setChecked(visible)
            toggle.setEnabled(available)
            toggle.setObjectName('visible:'+key)
            toggle.toggled.connect(lambda checked, k=key: self.set_visible(k, checked))
            actions.addWidget(toggle)
            actions.addStretch()
            if available:
                actions.addWidget(self._button('定位', lambda _checked=False, k=key: self.locate(k)))
            else:
                actions.addWidget(self._button('恢复并显示', lambda _checked=False, k=key: self.restore_module(k)))
            actions.addWidget(self._button('重命名…', lambda _checked=False, k=key: self.prompt_rename(k)))
            box.addLayout(actions)
            self.module_list.addWidget(card)
        if not self.workspace.docks:
            self.module_list.addWidget(label('桌面上还没有配件。到“发现配件”添加一个吧。', muted=True))

    def _refresh(self, message):
        self.refresh_catalog()
        self.refresh_modules()
        self.status.setText(message)

    def add_plugin(self, key):
        plugin = next(p for p in self.workspace.catalog if p['id'] == key)
        self.workspace.install_plugin(key)
        self.workspace.add_module(key)
        self._refresh(f'已添加“{plugin["title"]}”。可继续添加，或点击“返回桌面”拖动标题摆放位置。')

    def disable_plugin(self, key, *, confirm=True):
        plugin = next(p for p in self.workspace.catalog if p['id'] == key)
        if confirm:
            reply = QMessageBox.question(self, '停用此类配件？',
                f'将隐藏所有“{plugin["title"]}”配件。\n内容和位置都会保留，点击“恢复使用”即可找回。',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel)
            if reply != QMessageBox.StandardButton.Yes:
                return
        self.workspace.disable_plugin(key)
        self._refresh(f'已停用“{plugin["title"]}”，原有内容保留。点击“恢复使用”可找回。')

    def restore_plugin(self, key):
        self.workspace.install_plugin(key)
        self._refresh('已恢复使用，原有配件和内容保留。若某份配件先前已隐藏，可到“我的桌面”显示。')

    def set_visible(self, key, visible):
        self.workspace.set_module_visible(key, visible)
        self._refresh('配件已显示。点击“定位”即可在桌面中找到它。' if visible else '配件已隐藏，内容保留；勾选“在桌面显示”即可恢复。')

    def restore_module(self, key):
        record = next(r for r in self.workspace.records if r['id'] == key)
        self.workspace.install_plugin(record['plugin'])
        self.workspace.set_module_visible(key, True)
        self._refresh('已恢复并显示配件，原有内容保留。')

    def locate(self, key):
        self.workspace.activate_module(key)
        self.accept()

    def rename_module(self, key, title):
        title = title.strip()[:40]
        if not title:
            return False
        self.workspace.rename_module(key, title)
        self._refresh(f'已重命名为“{title}”。')
        return True

    def prompt_rename(self, key):
        dialog = QDialog(self)
        dialog.setWindowTitle('重命名桌面配件')
        dialog.setMinimumWidth(350)
        box = QVBoxLayout(dialog)
        box.addWidget(label('给这份配件取一个便于辨认的名字。'))
        edit = QLineEdit(self.workspace.docks[key].windowTitle())
        edit.setMaxLength(40)
        edit.selectAll()
        box.addWidget(edit)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText('保存名称')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('取消')
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        edit.textChanged.connect(lambda value: buttons.button(QDialogButtonBox.StandardButton.Save).setEnabled(bool(value.strip())))
        box.addWidget(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.rename_module(key, edit.text())

    def reset_layout(self):
        self.workspace.reset_layout()
        self._refresh('已恢复默认排列，全部内容保留。返回桌面后可重新拖动摆放。')

    def import_path(self, path):
        plugin = self.workspace.import_plugin(path)
        self.search.clear()
        self.category.setCurrentIndex(0)
        self.filter.setCurrentIndex(0)
        self.tabs.setCurrentIndex(0)
        self._refresh(f'已导入“{plugin["title"]}”。在卡片上点击“添加到桌面”即可使用。')
        return plugin

    def choose_import(self):
        path, _ = QFileDialog.getOpenFileName(self, '选择本地配件文件', '', '配件文件 (*.json)')
        if not path:
            return
        try:
            self.import_path(path)
        except (ValueError, OSError, UnicodeError) as error:
            QMessageBox.warning(self, '未能导入配件', f'{error}\n\n可以先点击“保存示例文件”，参考示例的填写方式。')

    def export_example(self, path):
        example = dict(schema=1, id='my-reading-note', title='阅读便签', kind='note', description='记下读到的好句子，以及下次想读的书。')
        Path(path).write_text(json.dumps(example, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        self.status.setText('已保存便签示例。可直接导入；修改名称或用途后导入时，请使用新的 id。')

    def choose_export(self):
        path, _ = QFileDialog.getSaveFileName(self, '保存可导入的便签示例', '我的阅读便签.json', '配件文件 (*.json)')
        if not path:
            return
        if not path.lower().endswith('.json'):
            path += '.json'
        try:
            self.export_example(path)
        except (OSError, UnicodeError) as error:
            QMessageBox.warning(self, '未能保存示例', str(error))
