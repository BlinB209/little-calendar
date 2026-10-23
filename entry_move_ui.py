"""Dialog for moving or copying one day's entries to another date."""
from datetime import timedelta

from qt_compat import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
                       QLineEdit, QPushButton)
import entry_move


class MoveDialog(QDialog):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.day = owner.selected
        self.report = None
        self.setWindowTitle('移动或复制事项')
        self.resize(500, 340)
        box = QVBoxLayout(self)
        intro = QLabel(f'把 {self.day.isoformat()} 的事项移动到或复制到另一个日期。'
                       '目标日期已有相同事项会跳过；超过六条时整次操作不会写入。')
        intro.setWordWrap(True)
        box.addWidget(intro)
        rows = entry_move.rows_of(owner.day_entries, self.day)
        row = QHBoxLayout()
        row.addWidget(QLabel('事项'))
        self.source = QComboBox()
        self.source.addItem('全部事项', -1)
        for index, entry in enumerate(rows):
            self.source.addItem(f"{index + 1}. {entry['period']} · {entry['text']}", index)
        row.addWidget(self.source, 1)
        box.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel('方式'))
        self.mode = QComboBox()
        self.mode.addItem('移动', 'move')
        self.mode.addItem('复制', 'copy')
        row.addWidget(self.mode)
        row.addWidget(QLabel('目标日期'))
        self.target = QLineEdit((self.day + timedelta(days=1)).isoformat())
        self.target.setPlaceholderText('YYYY-MM-DD')
        self.target.setMaxLength(10)
        row.addWidget(self.target, 1)
        box.addLayout(row)
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        self.hint.setProperty('muted', True)
        box.addWidget(self.hint)
        bottom = QHBoxLayout()
        bottom.addStretch()
        run = QPushButton('确定')
        run.setProperty('primary', True)
        run.setEnabled(bool(rows))
        run.clicked.connect(self.save)
        bottom.addWidget(run)
        cancel = QPushButton('取消')
        cancel.clicked.connect(self.reject)
        bottom.addWidget(cancel)
        box.addLayout(bottom)

    def values(self):
        index = self.source.currentData()
        mode = self.mode.currentData()
        target = entry_move.parse_day(self.target.text())
        return (-1 if index is None else index), mode, target

    def save(self):
        index, mode, target = self.values()
        if target is None:
            self.hint.setText('目标日期请用 YYYY-MM-DD 格式，例如 2026-11-05。')
            return
        self.report = entry_move.transfer(self.owner.store, self.owner.day_entries, self.day, target,
                                          index=None if index == -1 else index, mode=mode)
        if self.report['error']:
            self.hint.setText(self.report['error'])
            return
        self.owner.reload_entries()
        self.accept()
