"""Templates dialog: save frequently used entries and insert one into a day."""
from qt_compat import (Qt, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                       QComboBox, QPushButton, QListWidget, QListWidgetItem)
import templates


class TemplatesDialog(QDialog):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.setWindowTitle('事项模板')
        self.resize(500, 430)
        box = QVBoxLayout(self)
        intro = QLabel('把常用事项存成模板，之后一键插入当前选中的日期。插入只新增，不改动已有事项。')
        intro.setWordWrap(True)
        box.addWidget(intro)
        self.target = QLabel()
        self.target.setWordWrap(True)
        self.target.setProperty('muted', True)
        box.addWidget(self.target)
        self.list = QListWidget()
        box.addWidget(self.list, 1)
        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText('新模板内容，例如“健身 30 分钟”')
        self.input.setMaxLength(templates.MAX_TEXT)
        self.input.returnPressed.connect(self.add_current)
        row.addWidget(self.input, 1)
        self.period = QComboBox()
        for name in templates.PERIODS:
            self.period.addItem(name, name)
        row.addWidget(self.period)
        add = QPushButton('添加')
        add.clicked.connect(self.add_current)
        row.addWidget(add)
        box.addLayout(row)
        actions = QHBoxLayout()
        insert = QPushButton('插入到选中日期')
        insert.setProperty('primary', True)
        insert.clicked.connect(self.insert_selected)
        actions.addWidget(insert)
        remove = QPushButton('删除选中模板')
        remove.clicked.connect(self.remove_selected)
        actions.addWidget(remove)
        actions.addStretch()
        close = QPushButton('关闭')
        close.clicked.connect(self.reject)
        actions.addWidget(close)
        box.addLayout(actions)
        self.status = QLabel()
        self.status.setWordWrap(True)
        box.addWidget(self.status)
        self.refresh()

    def refresh(self, select=None):
        self.values = templates.load(self.owner.store)
        self.target.setText(f"插入到：{self.owner.selected.isoformat()}（当前选中的日期）")
        self.list.clear()
        for item in self.values:
            entry = QListWidgetItem(f"{item['period']} · {item['text']}")
            entry.setData(Qt.ItemDataRole.UserRole, item)
            self.list.addItem(entry)
            if select is not None and entry.data(Qt.ItemDataRole.UserRole) == select:
                self.list.setCurrentItem(entry)
        if self.values and self.list.currentRow() < 0:
            self.list.setCurrentRow(0)
        return self.values

    def selected(self):
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def add_current(self):
        text = self.input.text().strip()
        period = self.period.currentData()
        try:
            templates.add(self.owner.store, text, period)
        except ValueError as error:
            self.status.setText(str(error))
            return
        self.input.clear()
        self.status.setText('已添加模板。')
        self.refresh(select=dict(text=text, period=period))

    def insert_selected(self):
        template = self.selected()
        if template is None:
            self.status.setText('先选择一个模板。')
            return
        _rows, error = templates.insert(self.owner.store, self.owner.day_entries, self.owner.selected, template)
        if error:
            self.status.setText(error)
            return
        self.owner.reload_entries()
        self.status.setText(f"已插入“{template['text']}”到 {self.owner.selected.isoformat()}。")
        self.refresh(select=template)

    def remove_selected(self):
        row = self.list.currentRow()
        if row < 0:
            self.status.setText('先选择一个模板。')
            return
        try:
            templates.remove(self.owner.store, row)
        except ValueError as error:
            self.status.setText(str(error))
            return
        self.status.setText('已删除模板。')
        self.refresh()
