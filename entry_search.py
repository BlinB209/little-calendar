"""Cross-date entry search over the in-memory day map; results never touch SQLite."""
from datetime import date

from qt_compat import (Qt, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QCheckBox,
                       QComboBox, QPushButton, QListWidget, QListWidgetItem)

PERIODS = ('早', '午', '晚')
MAX_RESULTS = 300


def search_entries(day_entries, needle='', only_open=False, period=None):
    """Return matches for one query, newest day first and 早/午/晚 in order.

    A query with no text still applies the filters, so "只看未完成" alone lists
    every open entry. Results are capped so a long history stays responsive.
    """
    word = str(needle or '').strip().casefold()
    if not word and not only_open and not period:
        return []
    matches = []
    for iso, rows in day_entries.items():
        try:
            date.fromisoformat(iso)
        except (TypeError, ValueError):
            continue
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            text = str(row.get('text', '')).strip()
            if not text or row.get('period') not in PERIODS:
                continue
            done = bool(row.get('done', False))
            if word and word not in text.casefold():
                continue
            if only_open and done:
                continue
            if period and row['period'] != period:
                continue
            matches.append(dict(day=iso, period=row['period'], text=text, done=done))
    matches.sort(key=lambda item: PERIODS.index(item['period']))
    matches.sort(key=lambda item: item['day'], reverse=True)
    return matches[:MAX_RESULTS]


def result_label(item):
    return f"{item['day']}  {item['period']} · {item['text']}{'  ✓' if item['done'] else ''}"


class SearchDialog(QDialog):
    """Search every stored entry and jump the calendar to the chosen day."""

    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.matches = []
        self.setWindowTitle('搜索事项')
        self.resize(620, 460)
        box = QVBoxLayout(self)
        box.addWidget(QLabel('在全部日期的事项中搜索；双击结果或点击“跳到该日期”。'))
        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText('输入关键词，例如“读书”“体检”…')
        self.input.setClearButtonEnabled(True)
        self.input.textChanged.connect(self.refresh)
        row.addWidget(self.input, 1)
        self.period = QComboBox()
        self.period.addItem('全部时段', '')
        for name in PERIODS:
            self.period.addItem(name, name)
        self.period.currentIndexChanged.connect(self.refresh)
        row.addWidget(self.period)
        self.open_only = QCheckBox('只看未完成')
        self.open_only.toggled.connect(self.refresh)
        row.addWidget(self.open_only)
        box.addLayout(row)
        self.list = QListWidget()
        self.list.setWordWrap(True)
        self.list.itemActivated.connect(lambda _item: self.locate())
        box.addWidget(self.list, 1)
        self.count = QLabel('还没有关键词；输入后立即搜索。')
        self.count.setProperty('muted', True)
        box.addWidget(self.count)
        bottom = QHBoxLayout()
        go = QPushButton('跳到该日期')
        go.clicked.connect(self.locate)
        bottom.addWidget(go)
        bottom.addStretch()
        close = QPushButton('关闭')
        close.clicked.connect(self.reject)
        bottom.addWidget(close)
        box.addLayout(bottom)
        self.refresh()

    def query(self):
        return dict(needle=self.input.text(), only_open=self.open_only.isChecked(),
                    period=self.period.currentData() or None)

    def refresh(self, *_args):
        self.matches = search_entries(self.owner.day_entries, **self.query())
        self.list.clear()
        for item in self.matches:
            entry = QListWidgetItem(result_label(item))
            entry.setData(Qt.ItemDataRole.UserRole, item)
            self.list.addItem(entry)
        if not self.matches:
            empty = '没有匹配的事项' if self.input.text().strip() or self.open_only.isChecked() or self.period.currentData() else '还没有关键词；输入后立即搜索。'
            self.count.setText(empty)
        elif len(self.matches) >= MAX_RESULTS:
            self.count.setText(f'找到 {len(self.matches)} 条（只显示前 {MAX_RESULTS} 条，请补充关键词）')
        else:
            self.count.setText(f'找到 {len(self.matches)} 条')

    def locate(self):
        entry = self.list.currentItem()
        if entry is None or not self.matches:
            return
        item = entry.data(Qt.ItemDataRole.UserRole)
        day = date.fromisoformat(item['day'])
        self.owner.year, self.owner.month = day.year, day.month
        self.owner.sync_navigation()
        self.owner.select(day)
        dock = self.owner.body.docks.get('main-calendar')
        if dock is not None:
            self.owner.body.activate_module('main-calendar', scroll=False)
        self.owner.raise_()
        self.accept()
