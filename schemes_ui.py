"""Desktop-scheme dialog: list, switch, create from current and delete."""
from qt_compat import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                       QPushButton, QListWidget, QListWidgetItem)
import schemes as scheme_store


class SchemesDialog(QDialog):
    def __init__(self, workspace):
        super().__init__(workspace)
        self.workspace = workspace
        self.setWindowTitle('桌面方案')
        self.resize(480, 400)
        box = QVBoxLayout(self)
        intro = QLabel('桌面方案只保存模块的位置、显示与层序；便签、清单和插件内容共用，切换不会复制或丢失数据。')
        intro.setWordWrap(True)
        box.addWidget(intro)
        self.list = QListWidget()
        box.addWidget(self.list, 1)
        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText('新方案名称，例如“工作”“夜间”')
        self.input.setMaxLength(scheme_store.MAX_NAME)
        self.input.returnPressed.connect(self.create_new)
        row.addWidget(self.input, 1)
        create = QPushButton('新建（复制当前）')
        create.clicked.connect(self.create_new)
        row.addWidget(create)
        box.addLayout(row)
        actions = QHBoxLayout()
        switch = QPushButton('切换到选中方案')
        switch.setProperty('primary', True)
        switch.clicked.connect(self.switch_selected)
        actions.addWidget(switch)
        remove = QPushButton('删除选中方案')
        remove.clicked.connect(self.delete_selected)
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

    def refresh(self):
        if not scheme_store.load(self.workspace.owner.store):
            self.workspace.save_scheme(scheme_store.DEFAULT_NAME)
        self.values = scheme_store.load(self.workspace.owner.store)
        self.current = scheme_store.current(self.workspace.owner.store)
        self.list.clear()
        for name in self.values:
            item = QListWidgetItem(name + ('（当前）' if name == self.current else ''))
            item.setData(1, name)
            self.list.addItem(item)
            if name == self.current:
                self.list.setCurrentItem(item)
        if self.list.currentRow() < 0 and self.list.count():
            self.list.setCurrentRow(0)
        return self.values

    def selected(self):
        item = self.list.currentItem()
        return item.data(1) if item is not None else None

    def switch_selected(self):
        name = self.selected()
        if not name:
            self.status.setText('先选择一个方案。')
            return
        try:
            self.workspace.switch_scheme(name)
        except ValueError as error:
            self.status.setText(str(error))
            return
        self.status.setText(f'已切换到“{name}”。')
        self.refresh()

    def create_new(self):
        name = self.input.text().strip()
        if not name:
            self.status.setText('请输入方案名称。')
            return
        try:
            self.workspace.save_scheme(name)
        except ValueError as error:
            self.status.setText(str(error))
            return
        self.input.clear()
        self.status.setText(f'已保存“{name}”并切换过去。')
        self.refresh()

    def delete_selected(self):
        name = self.selected()
        if not name:
            self.status.setText('先选择一个方案。')
            return
        try:
            self.workspace.delete_scheme(name)
        except ValueError as error:
            self.status.setText(str(error))
            return
        self.status.setText(f'已删除“{name}”。')
        self.refresh()
