import sys
import os
import json
import sqlite3
from datetime import date, timedelta
from pathlib import Path

if sys.platform == 'linux':
    # Ubuntu supplies Qt through apt, so installation needs no pip or venv.
    from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF
    from PyQt6.QtGui import QColor, QPainter, QPen, QFont, QFontDatabase, QPalette
    from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
        QHBoxLayout, QLabel, QPushButton, QComboBox, QScrollArea, QFrame,
        QLineEdit, QCheckBox, QMessageBox)
else:
    from PySide6.QtCore import Qt, QTimer, QRectF, QPointF
    from PySide6.QtGui import QColor, QPainter, QPen, QFont, QFontDatabase, QPalette
    from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
        QHBoxLayout, QLabel, QPushButton, QComboBox, QScrollArea, QFrame,
        QLineEdit, QCheckBox, QMessageBox)

MIN_YEAR, MAX_YEAR = 2020, 2030
COLORS = ['#5369dc', '#df6583', '#e7ac38', '#39a78d', '#8b65c1']
FONT_FAMILY = 'Noto Sans CJK SC' if sys.platform == 'linux' else 'Microsoft YaHei'


class Store:
    def __init__(self, path=None):
        data_root = os.environ.get('LOCALAPPDATA') if sys.platform == 'win32' else os.environ.get('XDG_DATA_HOME')
        folder = Path(data_root or str(Path.home() / '.local/share')) / 'LittleCalendar'
        if path is None:
            folder.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path or folder / 'calendar.sqlite3'))
        self.db.execute('CREATE TABLE IF NOT EXISTS entries (key TEXT PRIMARY KEY, value TEXT NOT NULL)')

    def get(self, key, default):
        row = self.db.execute('SELECT value FROM entries WHERE key=?', (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def put(self, key, value):
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO entries VALUES (?, ?)', (key, json.dumps(value, ensure_ascii=False)))


class MonthBoard(QWidget):
    def __init__(self, owner, year, month):
        super().__init__()
        self.owner, self.year, self.month = owner, year, month
        self.key = 'ink:%04d-%02d' % (year, month)
        self.strokes = owner.store.get(self.key, [])
        self.redo_stack = []
        self.current = None
        first = date(year, month, 1)
        start = first - timedelta(days=first.weekday())
        self.days = [start + timedelta(days=i) for i in range(42)]
        self.setMinimumSize(630, 650)
        self.setMouseTracking(True)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor('#ffffff'))
        p.setFont(QFont(FONT_FAMILY, 15, QFont.Weight.Bold))
        p.setPen(QColor('#25334b'))
        p.drawText(QRectF(20, 8, self.width()-40, 40), Qt.AlignmentFlag.AlignVCenter, f'{self.year} 年  {self.month:02d} 月')
        w, h = self.width()/7, (self.height()-85)/6
        p.setFont(QFont(FONT_FAMILY, 9))
        for col, name in enumerate(['一', '二', '三', '四', '五', '六', '日']):
            p.setPen(QColor('#8992a6'))
            p.drawText(QRectF(col*w, 50, w, 30), Qt.AlignmentFlag.AlignCenter, '周'+name)
        for i, day in enumerate(self.days):
            x, y = (i % 7)*w, 85+(i//7)*h
            rect = QRectF(x+2, y+2, w-4, h-4)
            active = day.month == self.month
            p.fillRect(rect, QColor('#ffffff' if active else '#f7f8fb'))
            if day == self.owner.selected:
                p.fillRect(rect, QColor('#eef1ff'))
            p.setPen(QPen(QColor('#e9edf3'), 1))
            p.drawRoundedRect(rect, 6, 6)
            if day == date.today():
                p.setBrush(QColor('#5369dc'))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(QRectF(x+9, y+7, 26, 26))
                p.setBrush(Qt.BrushStyle.NoBrush)
            p.setFont(QFont(FONT_FAMILY, 10, QFont.Weight.Bold))
            p.setPen(QColor('#ffffff' if day == date.today() else '#35435c' if active else '#aab1be'))
            p.drawText(QRectF(x+9, y+7, 26, 26), Qt.AlignmentFlag.AlignCenter, str(day.day))
            rows = self.owner.store.get('day:'+day.isoformat(), [])
            line_height = min(18, max(10, (h-37)/6))
            p.setFont(QFont(FONT_FAMILY, 8))
            for j, row in enumerate(rows):
                p.setPen(QColor('#a5acb9' if row['done'] else {'早':'#ba8a2e','午':'#3b9c8b','晚':'#8270bf'}[row['period']]))
                text = ('✓ ' if row['done'] else '') + row['period']+' · '+row['text']
                text = p.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight, int(w-16))
                p.drawText(QRectF(x+8, y+36+j*line_height, w-16, line_height), Qt.AlignmentFlag.AlignVCenter, text)
        p.setClipRect(QRectF(0, 85, self.width(), self.height()-85))
        for stroke in self.strokes + ([self.current] if self.current else []):
            color = QColor(stroke['color'])
            color.setAlpha(110 if stroke.get('highlight') else 230)
            pen = QPen(color, stroke['width'] * self.width()/700, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            points = [QPointF(a*self.width(), 85+b*(self.height()-85)) for a,b in stroke['points']]
            if len(points) == 1:
                p.drawPoint(points[0])
            for a,b in zip(points, points[1:]):
                p.drawLine(a,b)

    def norm(self, pos):
        return [max(0, min(1, pos.x()/self.width())), max(0,min(1,(pos.y()-85)/(self.height()-85)))]

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or event.position().y() < 85:
            return
        self.owner.active_board = self
        if self.owner.draw_mode:
            self.current = dict(color=self.owner.color, width=16 if self.owner.highlight.isChecked() else 4, highlight=self.owner.highlight.isChecked(), points=[self.norm(event.position())])
        else:
            index = min(41, int((event.position().y()-85)/((self.height()-85)/6))*7 + int(event.position().x()/(self.width()/7)))
            day = self.days[index]
            if MIN_YEAR <= day.year <= MAX_YEAR:
                self.owner.select(day)
        self.update()

    def mouseMoveEvent(self, event):
        if self.current:
            self.current['points'].append(self.norm(event.position()))
            self.update()

    def mouseReleaseEvent(self, event):
        if self.current:
            self.strokes.append(self.current)
            self.current = None
            self.redo_stack.clear()
            self.save()

    def save(self):
        self.owner.persist(self.key, self.strokes)
        self.update()


class CalendarApp(QMainWindow):
    def __init__(self, store=None):
        super().__init__()
        self.store = store or Store()
        today = date.today()
        self.selected = min(max(today, date(MIN_YEAR,1,1)), date(MAX_YEAR,12,31))
        self.year, self.month = self.selected.year, self.selected.month
        self.draw_mode, self.color, self.active_board = False, COLORS[0], None
        self.loading = False
        self.setWindowTitle('小日历 · 个人日历预览版')
        self.resize(1320, 880)
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(24,18,24,18)
        header = QHBoxLayout()
        title = QLabel('小日历  /  把日子慢慢写下来')
        title.setStyleSheet('font-size:20px;font-weight:600;color:#25334b')
        header.addWidget(title)
        header.addStretch()
        self.clock = QLabel()
        header.addWidget(self.clock)
        layout.addLayout(header)
        bar = QHBoxLayout()
        self.prev = self.button('← 上个月', lambda: self.navigate(-1), bar)
        self.button('今天', self.go_today, bar)
        self.next = self.button('下个月 →', lambda: self.navigate(1), bar)
        self.year_box = QComboBox()
        self.year_box.addItems([str(y) for y in range(MIN_YEAR, MAX_YEAR+1)])
        self.year_box.setCurrentText(str(self.year))
        bar.addWidget(self.year_box)
        self.month_box = QComboBox()
        self.month_box.addItems([f'{m} 月' for m in range(1,13)])
        self.month_box.setCurrentIndex(self.month-1)
        bar.addWidget(self.month_box)
        self.year_box.currentIndexChanged.connect(self.jump)
        self.month_box.currentIndexChanged.connect(self.jump)
        bar.addStretch()
        self.orientation = QComboBox()
        self.orientation.addItems(['纵向排列', '横向排列'])
        self.orientation.currentIndexChanged.connect(self.rebuild)
        bar.addWidget(self.orientation)
        self.count = QComboBox()
        self.count.addItems(['显示 1 个月', '显示 2 个月', '显示 3 个月'])
        self.count.setCurrentIndex(1)
        self.count.currentIndexChanged.connect(self.rebuild)
        bar.addWidget(self.count)
        layout.addLayout(bar)
        ink = QHBoxLayout()
        self.pen_button = self.button('✎ 开启画笔', self.toggle_draw, ink)
        for color in COLORS:
            b = self.button('●', lambda checked=False, c=color: self.set_color(c), ink)
            b.setStyleSheet(f'color:{color};font-size:24px;min-width:30px;padding:2px;')
        self.highlight = QCheckBox('荧光笔')
        ink.addWidget(self.highlight)
        self.button('撤销笔迹', self.undo, ink)
        self.button('重做', self.redo, ink)
        self.button('清空本月笔迹', self.clear_ink, ink)
        ink.addStretch()
        self.ink_label = QLabel('点击日期编辑事项；开启画笔后可自由标记')
        ink.addWidget(self.ink_label)
        layout.addLayout(ink)
        body = QHBoxLayout()
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        body.addWidget(self.scroll, 1)
        panel = QFrame()
        panel.setFixedWidth(300)
        panel.setStyleSheet('QFrame {background:white;border-radius:12px;}')
        editor = QVBoxLayout(panel)
        editor.setContentsMargins(18,20,18,20)
        self.day_label = QLabel()
        self.day_label.setStyleSheet('font-size:20px;font-weight:600;')
        editor.addWidget(self.day_label)
        editor.addWidget(QLabel('当天事项 · 最多六条'))
        editor.addSpacing(14)
        self.rows = []
        for i in range(6):
            row = QHBoxLayout()
            done = QCheckBox()
            period = QComboBox()
            period.addItems(['早','午','晚'])
            field = QLineEdit()
            field.setPlaceholderText('添加事项…')
            field.setMaxLength(120)
            row.addWidget(done)
            row.addWidget(period)
            row.addWidget(field,1)
            editor.addLayout(row)
            self.rows.append((done,period,field))
            done.stateChanged.connect(self.save_day)
            period.currentIndexChanged.connect(self.save_day)
            field.textChanged.connect(self.save_day)
        editor.addSpacing(16)
        tip = QLabel('早 · 开始新的一天\n午 · 给重要的事留点时间\n晚 · 记录今天的小小收获\n\n直接输入即可保存，清空文字可删除。\n勾选左侧方框，将事项标记为完成。')
        tip.setWordWrap(True)
        tip.setStyleSheet('color:#8992a6;line-height:1.5;')
        editor.addWidget(tip)
        editor.addStretch()
        editor.addWidget(QLabel('本地离线存储  ·  2020 — 2030'))
        body.addWidget(panel)
        layout.addLayout(body,1)
        self.status = QLabel('已就绪 · 数据自动保存到本机')
        self.status.setStyleSheet('color:#8992a6;')
        layout.addWidget(self.status)
        self.rebuild()
        self.select(self.selected)
        self.last_today = today
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(1000)
        self.tick()

    def button(self, text, callback, layout):
        b = QPushButton(text)
        b.clicked.connect(callback)
        layout.addWidget(b)
        return b

    def persist(self, key, value):
        try:
            self.store.put(key, value)
            self.status.setText('已保存到本机 · ' + str(Path(self.store.db.execute('PRAGMA database_list').fetchone()[2])))
        except (OSError, sqlite3.Error) as exc:
            self.status.setText('保存失败，请保留窗口并检查磁盘空间：' + str(exc))

    def tick(self):
        from datetime import datetime
        self.clock.setText(datetime.now().strftime('本地时间  %Y-%m-%d  %H:%M:%S'))
        if date.today() != self.last_today:
            self.last_today = date.today()
            for b in self.boards:
                b.update()

    def rebuild(self, *_):
        container = QWidget()
        box = QHBoxLayout(container) if self.orientation.currentIndex() else QVBoxLayout(container)
        box.setContentsMargins(0,0,0,0)
        box.setSpacing(16)
        self.boards = []
        for offset in range(self.count.currentIndex()+1):
            serial = self.year*12+self.month-1+offset
            year, month = serial//12, serial%12+1
            if year > MAX_YEAR:
                break
            board = MonthBoard(self,year,month)
            board.setCursor(Qt.CursorShape.CrossCursor if self.draw_mode else Qt.CursorShape.ArrowCursor)
            box.addWidget(board)
            self.boards.append(board)
        self.active_board = self.boards[0]
        self.scroll.setWidget(container)
        self.prev.setEnabled((self.year,self.month) > (MIN_YEAR,1))
        self.next.setEnabled((self.year,self.month) < (MAX_YEAR,12))

    def jump(self, *_):
        self.year = int(self.year_box.currentText())
        self.month = self.month_box.currentIndex()+1
        self.rebuild()

    def navigate(self, delta):
        serial = self.year*12+self.month-1+delta
        if not MIN_YEAR*12 <= serial < (MAX_YEAR+1)*12:
            return
        self.year, self.month = serial//12, serial%12+1
        self.sync_navigation()

    def sync_navigation(self):
        self.year_box.blockSignals(True)
        self.month_box.blockSignals(True)
        self.year_box.setCurrentText(str(self.year))
        self.month_box.setCurrentIndex(self.month-1)
        self.year_box.blockSignals(False)
        self.month_box.blockSignals(False)
        self.rebuild()

    def go_today(self):
        day = min(max(date.today(),date(MIN_YEAR,1,1)),date(MAX_YEAR,12,31))
        self.year,self.month = day.year,day.month
        self.sync_navigation()
        self.select(day)

    def select(self, day):
        self.selected = day
        self.day_label.setText(f'{day.month} 月 {day.day} 日  周'+ '一二三四五六日'[day.weekday()])
        saved = self.store.get('day:'+day.isoformat(), [])
        self.loading = True
        for i,(done,period,field) in enumerate(self.rows):
            row = saved[i] if i<len(saved) else dict(done=False,period=['早','午','晚'][i//2],text='')
            done.setChecked(row['done'])
            period.setCurrentText(row['period'])
            field.setText(row['text'])
        self.loading = False
        for b in self.boards:
            b.update()

    def save_day(self, *_):
        if self.loading:
            return
        rows = [dict(done=d.isChecked(),period=p.currentText(),text=f.text().strip()) for d,p,f in self.rows if f.text().strip()]
        self.persist('day:'+self.selected.isoformat(),rows)
        for b in self.boards:
            b.update()

    def toggle_draw(self):
        self.draw_mode = not self.draw_mode
        self.pen_button.setText('结束绘画' if self.draw_mode else '✎ 开启画笔')
        self.ink_label.setText('绘画中 · 退出绘画后可选择日期' if self.draw_mode else '点击日期编辑事项；开启画笔后可自由标记')
        for b in self.boards:
            b.setCursor(Qt.CursorShape.CrossCursor if self.draw_mode else Qt.CursorShape.ArrowCursor)

    def set_color(self,color):
        self.color = color
        self.pen_button.setStyleSheet(f'color:{color};font-weight:bold;')

    def undo(self):
        b = self.active_board
        if b.strokes:
            b.redo_stack.append(b.strokes.pop())
            b.save()

    def redo(self):
        b = self.active_board
        if b.redo_stack:
            b.strokes.append(b.redo_stack.pop())
            b.save()

    def clear_ink(self):
        b = self.active_board
        if b.strokes and QMessageBox.question(self,'清空笔迹',f'清空 {b.year} 年 {b.month} 月的全部笔迹？事项不会被删除。') == QMessageBox.StandardButton.Yes:
            b.redo_stack.extend(reversed(b.strokes))
            b.strokes = []
            b.save()


def configure_style(app):
    # Use one complete light palette: native dark-mode text on our white
    # backgrounds otherwise makes inputs and selectors unreadable.
    app.setStyle('Fusion')
    palette = QPalette()
    for role, color in {
        QPalette.ColorRole.Window: '#f3f5fa',
        QPalette.ColorRole.WindowText: '#25334b',
        QPalette.ColorRole.Base: '#ffffff',
        QPalette.ColorRole.AlternateBase: '#eef1f7',
        QPalette.ColorRole.Text: '#25334b',
        QPalette.ColorRole.Button: '#ffffff',
        QPalette.ColorRole.ButtonText: '#25334b',
        QPalette.ColorRole.ToolTipBase: '#25334b',
        QPalette.ColorRole.ToolTipText: '#ffffff',
        QPalette.ColorRole.Highlight: '#5369dc',
        QPalette.ColorRole.HighlightedText: '#ffffff',
        QPalette.ColorRole.PlaceholderText: '#68758a',
    }.items():
        palette.setColor(role, QColor(color))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText, QPalette.ColorRole.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor('#748095'))
    app.setPalette(palette)
    if sys.platform == 'win32':
        fonts = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts'
        for name in ('msyh.ttc', 'msyhbd.ttc', 'segoeui.ttf'):
            if (fonts / name).exists():
                QFontDatabase.addApplicationFont(str(fonts / name))
    app.setFont(QFont(FONT_FAMILY, 10))
    app.setStyleSheet('''
        QWidget {color:#25334b;}
        QMainWindow,QDialog,QMessageBox {background:#f3f5fa;}
        QPushButton,QComboBox,QLineEdit {
            color:#25334b;background:#ffffff;border:1px solid #cbd3e0;
            border-radius:6px;padding:7px;
            selection-background-color:#5369dc;selection-color:#ffffff;
        }
        QPushButton:hover {background:#edf0ff;}
        QPushButton:disabled {color:#748095;background:#edf0f5;}
        QComboBox QAbstractItemView {
            color:#25334b;background:#ffffff;
            selection-color:#ffffff;selection-background-color:#5369dc;
        }
        QScrollArea {border:none;}
        QLabel {color:#536078;}
        QCheckBox {color:#25334b;spacing:4px;}
        QToolTip {color:#ffffff;background:#25334b;border:0;}
    ''')


def main():
    smoke = '--smoke-test' in sys.argv
    if smoke:
        os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    app = QApplication(sys.argv)
    configure_style(app)
    window = CalendarApp(Store(':memory:') if smoke else None)
    window.show()
    if smoke:
        QTimer.singleShot(500, app.quit)
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
