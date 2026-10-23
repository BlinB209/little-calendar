"""Dialog for attaching HH:MM reminder times to the selected day's entries."""
from qt_compat import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
                       QLineEdit, QPushButton)
import entry_times


class EntryTimesDialog(QDialog):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.day = owner.selected
        self.setWindowTitle('定时提醒')
        self.resize(480, 400)
        box = QVBoxLayout(self)
        intro = QLabel(f'为 {self.day.isoformat()} 的事项设置提醒时间。留空表示不提醒；'
                       '到点用托盘气泡提示，错过时间会在下次打开后补提醒。')
        intro.setWordWrap(True)
        box.addWidget(intro)
        self.form = QFormLayout()
        box.addLayout(self.form)
        self.editors = []
        rows = owner.day_entries.get(self.day.isoformat(), [])
        for row in rows[:6] if isinstance(rows, list) else []:
            if not isinstance(row, dict) or not str(row.get('text', '')).strip():
                continue
            edit = QLineEdit(entry_times.parse(row.get('time')) or '')
            edit.setPlaceholderText('HH:MM')
            edit.setMaxLength(5)
            edit.setFixedWidth(90)
            label = QLabel(f"{row.get('period', '')} · {str(row.get('text', '')).strip()}")
            label.setWordWrap(True)
            self.form.addRow(label, edit)
            self.editors.append((row, edit))
        if not self.editors:
            box.addWidget(QLabel('这一天还没有事项。先在编辑面板写下内容，再来设置提醒时间。'))
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        self.hint.setProperty('muted', True)
        box.addWidget(self.hint)
        bottom = QHBoxLayout()
        bottom.addStretch()
        save = QPushButton('保存')
        save.setProperty('primary', True)
        save.setEnabled(bool(self.editors))
        save.clicked.connect(self.save)
        bottom.addWidget(save)
        cancel = QPushButton('取消')
        cancel.clicked.connect(self.reject)
        bottom.addWidget(cancel)
        box.addLayout(bottom)

    def values(self):
        entries, invalid = [], []
        for row, edit in self.editors:
            entry = dict(done=bool(row.get('done')), period=str(row.get('period', '')),
                         text=str(row.get('text', '')).strip())
            raw = edit.text().strip()
            if raw:
                parsed = entry_times.parse(raw)
                if parsed is None:
                    invalid.append(entry['text'])
                else:
                    entry['time'] = parsed
            entries.append(entry)
        return entries, invalid

    def save(self):
        if not self.editors:
            return
        entries, invalid = self.values()
        if invalid:
            self.hint.setText('时间格式不对：' + '、'.join(invalid[:3]) + '。请用 HH:MM，例如 15:30。')
            return
        entry_times.apply_times(self.owner.store, self.day, entries)
        self.owner.reload_entries()
        self.accept()
