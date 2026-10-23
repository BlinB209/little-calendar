"""Review dialog: one painted chart plus the numbers behind it."""
from datetime import date

from qt_compat import (Qt, QColor, QFont, QPainter, QRectF, QDialog, QVBoxLayout,
                       QHBoxLayout, QLabel, QPushButton, QWidget)
import review

CELL_GAP = 6
ROWS, COLUMNS = 2, 6


def _blend(first, second, amount):
    a, b = QColor(first), QColor(second)
    amount = max(0.0, min(1.0, amount))
    return QColor(*(round(x * (1 - amount) + y * amount) for x, y in zip(a.getRgb()[:3], b.getRgb()[:3])))


class ReviewChart(QWidget):
    """Twelve month cells (oldest first) above three slot bars."""

    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        self.data = None
        self.setMinimumHeight(330)

    def refresh(self):
        self.data = review.collect(self.owner.day_entries, date.today())
        self.update()
        return self.data

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()

    def paintEvent(self, _event):
        data = self.data or self.refresh()
        theme = self.owner.theme_colors
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width, height = self.width(), self.height()
        painter.fillRect(QRectF(0, 0, width, height), QColor(theme['background']))
        base = QFont(self.owner.custom.get('font_family') or self.font().family())
        base.setPixelSize(max(11, round((self.owner.custom.get('font_size') or 14) * 0.85)))
        painter.setFont(base)
        painter.setPen(QColor(theme['muted']))
        painter.drawText(QRectF(0, 0, width, 22), Qt.AlignmentFlag.AlignLeft, '最近 12 个月完成情况')

        grid_top, grid_height = 26, height - 26 - 110
        cell_width = (width - (COLUMNS - 1) * CELL_GAP) / COLUMNS
        cell_height = (grid_height - (ROWS - 1) * CELL_GAP) / ROWS
        months = data['heatmap']
        for index, month in enumerate(months):
            row, column = divmod(index, COLUMNS)
            rect = QRectF(column * (cell_width + CELL_GAP), grid_top + row * (cell_height + CELL_GAP),
                          cell_width, cell_height)
            fill = _blend(theme['alternate'], theme['accent'], month['ratio'] if month['entries'] else 0.0)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(fill)
            painter.drawRoundedRect(rect, 7, 7)
            painter.setPen(QColor(theme['text'] if month['ratio'] < 0.55 else '#ffffff'))
            label = f"{month['year']}-{month['month']:02d}" if month['month'] == 1 else f"{month['month']:02d} 月"
            painter.drawText(rect.adjusted(8, 5, -8, -5), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, label)
            detail = f"{month['done']}/{month['entries']}" if month['entries'] else '无事项'
            painter.drawText(rect.adjusted(8, 5, -8, -5), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom, detail)

        bar_top = grid_top + grid_height + 18
        painter.setPen(QColor(theme['muted']))
        painter.drawText(QRectF(0, bar_top - 2, width, 20), Qt.AlignmentFlag.AlignLeft, '今年早 / 午 / 晚')
        counts = data['periods']
        label_width, bar_left = 34, 38
        bar_area = max(40, width - bar_left - 46)
        for index, name in enumerate(review.PERIODS):
            row = counts[name]
            y = bar_top + 24 + index * 26
            painter.setPen(QColor(theme['text']))
            painter.drawText(QRectF(0, y, label_width, 20), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(theme['alternate']))
            painter.drawRoundedRect(QRectF(bar_left, y + 4, bar_area, 12), 6, 6)
            if row['entries']:
                painter.setBrush(QColor(theme['accent']))
                painter.drawRoundedRect(QRectF(bar_left, y + 4, max(6, bar_area * row['done'] / row['entries']), 12), 6, 6)
            painter.setPen(QColor(theme['muted']))
            painter.drawText(QRectF(bar_left + bar_area + 8, y, 70, 20), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                             f"{row['done']}/{row['entries']}")
        painter.end()


class ReviewDialog(QDialog):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.setWindowTitle('回顾')
        self.resize(660, 470)
        box = QVBoxLayout(self)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        box.addWidget(self.summary)
        self.chart = ReviewChart(owner)
        box.addWidget(self.chart, 1)
        bottom = QHBoxLayout()
        bottom.addStretch()
        close = QPushButton('关闭')
        close.clicked.connect(self.reject)
        bottom.addWidget(close)
        box.addLayout(bottom)
        self.refresh()

    def summary_text(self):
        data = self.data
        month, year, streaks = data['month'], data['year'], data['streaks']
        lines = [f"本月：完成 {month['done']} / {month['entries']} 条（{review.percent(month['ratio'])}），"
                 f"有事项 {month['with_entries']} 天",
                 f"今年：完成 {year['done']} / {year['entries']} 条（{review.percent(year['ratio'])}），"
                 f"有事项 {year['with_entries']} 天",
                 f"连续完成：当前 {streaks['current']} 天 · 最长 {streaks['longest']} 天"]
        return '\n'.join(lines)

    def refresh(self):
        self.data = self.chart.refresh()
        self.summary.setText(self.summary_text())
        return self.data
