"""Dialog for inserting one template on a repeating series of dates."""
from datetime import date

from qt_compat import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
                       QSpinBox, QPushButton)
import recurrence


class RepeatDialog(QDialog):
    def __init__(self, owner, template):
        super().__init__(owner)
        self.owner = owner
        self.template = dict(template)
        self.report = None
        self.setWindowTitle('重复插入')
        self.resize(470, 300)
        box = QVBoxLayout(self)
        title = QLabel(f"模板：{template['period']} · {template['text']}")
        title.setWordWrap(True)
        box.addWidget(title)
        intro = QLabel('从当前选中的日期开始，按规则把这条事项写入若干天。只新增，不覆盖已有内容。')
        intro.setWordWrap(True)
        box.addWidget(intro)
        row = QHBoxLayout()
        row.addWidget(QLabel('重复方式'))
        self.kind = QComboBox()
        for label, value in [('每天', 'daily'), ('每周同一天', 'weekly'), ('每月同一天', 'monthly')]:
            self.kind.addItem(label, value)
        row.addWidget(self.kind)
        row.addWidget(QLabel('次数'))
        self.times = QSpinBox()
        self.times.setRange(1, recurrence.MAX_TIMES)
        self.times.setValue(12)
        row.addWidget(self.times)
        row.addStretch()
        box.addLayout(row)
        self.preview = QLabel()
        self.preview.setWordWrap(True)
        box.addWidget(self.preview)
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        self.hint.setProperty('muted', True)
        box.addWidget(self.hint)
        bottom = QHBoxLayout()
        bottom.addStretch()
        write = QPushButton('写入')
        write.setProperty('primary', True)
        write.clicked.connect(self.save)
        bottom.addWidget(write)
        cancel = QPushButton('取消')
        cancel.clicked.connect(self.reject)
        bottom.addWidget(cancel)
        box.addLayout(bottom)
        self.kind.currentIndexChanged.connect(self.refresh)
        self.times.valueChanged.connect(self.refresh)
        self.refresh()

    def target_dates(self):
        import app as application
        return recurrence.dates(self.kind.currentData(), self.owner.selected, self.times.value(),
                                min_date=date(application.MIN_YEAR, 1, 1),
                                max_date=date(application.MAX_YEAR, 12, 31))

    def refresh(self, *_args):
        days = self.target_dates()
        if not days:
            self.preview.setText('当前支持范围内没有可写入的日期。')
            return
        suffix = f'，最后一次 {days[-1].isoformat()}' if len(days) > 1 else ''
        self.preview.setText(f'将从 {days[0].isoformat()} 起写入 {len(days)} 天{suffix}。')

    def save(self):
        days = self.target_dates()
        if not days:
            self.hint.setText('没有可写入的日期，请调整重复方式或次数。')
            return
        self.report = recurrence.apply(self.owner.store, self.owner.day_entries, days, self.template)
        if hasattr(self.owner, 'reload_entries'):
            self.owner.reload_entries()
        self.accept()
