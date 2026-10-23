import sys
import os
import json
import sqlite3
import copy
import math
from datetime import date, datetime, timedelta
from pathlib import Path
from theme import colors, stylesheet
from version import VERSION
from workspace import Workspace
from preferences import preferences, Background, PreferencesDialog, load_background, paint_background
from markings import stroke_hit
from qt_compat import QColorDialog, QSpinBox, QPlainTextEdit, QTextEdit, QDialog, QMenu

if sys.platform == 'linux':
    # Ubuntu supplies Qt through apt, so installation needs no pip or venv.
    from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF, QPoint
    from PyQt6.QtGui import QColor, QPainter, QPen, QFont, QFontDatabase, QPalette, QShortcut, QKeySequence
    from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
        QHBoxLayout, QLabel, QPushButton, QComboBox, QScrollArea, QFrame,
        QLineEdit, QCheckBox, QMessageBox, QSplitter, QSizePolicy)
else:
    from PySide6.QtCore import Qt, QTimer, QRectF, QPointF, QPoint
    from PySide6.QtGui import QColor, QPainter, QPen, QFont, QFontDatabase, QPalette, QShortcut, QKeySequence
    from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
        QHBoxLayout, QLabel, QPushButton, QComboBox, QScrollArea, QFrame,
        QLineEdit, QCheckBox, QMessageBox, QSplitter, QSizePolicy)

MIN_YEAR, MAX_YEAR = date.today().year - 10, date.today().year + 10
COLORS = ['#000000', '#5369dc', '#df6583', '#e7ac38', '#39a78d', '#8b65c1']
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

    def load_days(self):
        return {key[4:]: json.loads(value) for key, value in
                self.db.execute("SELECT key,value FROM entries WHERE key LIKE 'day:%'")}


class AdaptivePanel(QFrame):
    """Scale text with the panel, within usable bounds on small screens."""
    def __init__(self, base_width, base_height):
        super().__init__()
        self.base_width, self.base_height = base_width, base_height

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.refresh_font()

    def refresh_font(self):
        prefs = QApplication.instance().property('calendarCustom') or {}
        scale = max(.75, min(1.8, self.width()/self.base_width, self.height()/self.base_height))
        if not prefs.get('font_auto',True):
            scale = 1
        font = QFont(prefs.get('font_family') or FONT_FAMILY)
        font.setPixelSize(round(prefs.get('font_size',14)*scale))
        self.setFont(font)
        # Style sheets can stop font propagation to descendants, so apply it
        # explicitly to controls as well as to the panel itself.
        for child in self.findChildren(QWidget):
            child.setFont(font)
            if child.property('largeText'):
                large = QFont(font)
                large.setPixelSize(round(prefs.get('font_size',14)*1.57*scale))
                child.setFont(large)


class MonthBoard(QWidget):
    def __init__(self, owner, year, month):
        super().__init__()
        self.owner, self.year, self.month = owner, year, month
        self.key = 'ink:%04d-%02d' % (year, month)
        self.strokes = owner.store.get(self.key, [])
        self.stamp_key = self.key.replace('ink:', 'stamps:')
        self.stamps = owner.store.get(self.stamp_key, [])
        self.history = []
        self.redo_stack = []
        self.current = None
        self.erasing = False
        self.erase_previous = None
        first = date(year, month, 1)
        start = first - timedelta(days=first.weekday())
        self.days = [start + timedelta(days=i) for i in range(42)]
        self.setMinimumSize(420, 460)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def scale_factor(self):
        return max(.6, min(2.5, self.width()/700, self.height()/650))

    def header_height(self):
        return 85*self.scale_factor()

    def draw_font(self, size, bold=False):
        font = QFont(self.owner.custom.get('font_family') or FONT_FAMILY)
        factor = self.owner.custom['font_size']/14
        if not self.owner.custom.get('font_auto',True):
            factor /= self.scale_factor()
        font.setPixelSize(max(1, round(size*4/3*factor)))
        font.setBold(bold)
        return font

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        theme = getattr(self.owner,'calendar_colors',self.owner.theme_colors)
        mark_style = self.owner.cross_style.currentData()
        prefs = self.owner.custom
        # Show one continuous wallpaper through the desktop and date cells.
        root = self.owner.centralWidget()
        origin = self.mapTo(root,QPoint(0,0))
        p.save()
        p.translate(-origin.x(),-origin.y())
        background_opacity = getattr(self.owner,'calendar_background_opacity',100)
        if background_opacity == 100:
            paint_background(p,QRectF(root.rect()),prefs,theme,self.owner.background_pixmap)
        p.restore()
        scale = self.scale_factor()
        p.scale(scale, scale)
        width, height = self.width()/scale, self.height()/scale
        header_color = QColor(theme['surface'])
        header_color.setAlpha(round(240*background_opacity/100))
        p.fillRect(QRectF(0,0,width,85),header_color)
        p.setFont(self.draw_font(15,True))
        p.setPen(QColor(theme['text']))
        p.drawText(QRectF(20, 8, width-40, 40), Qt.AlignmentFlag.AlignVCenter, f'{self.year} 年  {self.month:02d} 月')
        w, h = width/7, (height-85)/6
        today = date.today()
        p.setFont(self.draw_font(9))
        for col, name in enumerate(['一', '二', '三', '四', '五', '六', '日']):
            p.setPen(QColor(theme['muted']))
            p.drawText(QRectF(col*w, 50, w, 30), Qt.AlignmentFlag.AlignCenter, '周'+name)
        for i, day in enumerate(self.days):
            x, y = (i % 7)*w, 85+(i//7)*h
            rect = QRectF(x+2, y+2, w-4, h-4)
            active = day.month == self.month
            crossed = self.owner.is_past_day(day, today)
            faded = crossed and mark_style == 'fade'
            cell_color = QColor(theme['faded'] if faded else (self.owner.calendar_surface or theme['surface']) if active else theme['alternate'])
            cell_color.setAlpha(round(255*prefs.get('cell_opacity',92)*background_opacity/10000))
            p.fillRect(rect,cell_color)
            if day == self.owner.selected:
                p.fillRect(rect, QColor(theme['selected']))
            p.setPen(QPen(QColor(theme['grid']), 1))
            p.drawRoundedRect(rect, 6, 6)
            if crossed:
                mark_color = QColor(prefs.get('mark_color') or theme['mark'])
                mark_color.setAlpha(round(255*prefs['mark_opacity']/100))
                p.setPen(QPen(mark_color, prefs['mark_width']))
                if mark_style in ('diagonal', 'cross'):
                    p.drawLine(QPointF(x+8, y+h-10), QPointF(x+w-8, y+10))
                if mark_style == 'cross':
                    p.drawLine(QPointF(x+8, y+10), QPointF(x+w-8, y+h-10))
                if mark_style == 'horizontal':
                    p.drawLine(QPointF(x+8, y+h/2), QPointF(x+w-8, y+h/2))
            p.setOpacity(.48 if faded else 1.0)
            if day == today:
                p.setBrush(QColor(theme['accent']))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(QRectF(x+9, y+7, 26, 26))
                p.setBrush(Qt.BrushStyle.NoBrush)
            date_font = self.draw_font(10,True)
            date_font.setStrikeOut(crossed and not faded)
            p.setFont(date_font)
            p.setPen(QColor('#ffffff' if day == today else theme['text'] if active else theme['dim']))
            p.drawText(QRectF(x+9, y+7, 26, 26), Qt.AlignmentFlag.AlignCenter, str(day.day))
            rows = self.owner.day_entries.get(day.isoformat(), [])
            line_height = min(18, max(10, (h-37)/6))
            p.setFont(self.draw_font(8))
            for j, row in enumerate(rows):
                p.setPen(QColor(theme['dim'] if row['done'] else theme[{'早':'morning','午':'noon','晚':'evening'}[row['period']]]))
                text = ('✓ ' if row['done'] else '') + row['period']+' · '+row['text']
                text = p.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight, int(w-16))
                p.drawText(QRectF(x+8, y+36+j*line_height, w-16, line_height), Qt.AlignmentFlag.AlignVCenter, text)
            p.setOpacity(1.0)
        p.setClipRect(QRectF(0, 85, width, height-85))
        if prefs['show_stamps']:
            for stamp in self.stamps:
                day = date.fromisoformat(stamp['day'])
                if day not in self.days:
                    continue
                index = self.days.index(day)
                x,y = index%7*w,85+(index//7)*h
                target = QRectF(x+8,y+8,w-16,h-16)
                color = QColor(stamp['color'])
                color.setAlpha(round(255*stamp.get('opacity',80)/100))
                p.setPen(QPen(color,stamp.get('width',3)))
                kind = stamp['kind']
                if kind == 'circle':
                    p.drawEllipse(target)
                elif kind == 'box':
                    p.drawRoundedRect(target,8,8)
                elif kind == 'cross':
                    p.drawLine(target.topLeft(),target.bottomRight())
                    p.drawLine(target.bottomLeft(),target.topRight())
                elif kind == 'underline':
                    p.drawLine(target.bottomLeft(),target.bottomRight())
                elif kind == 'fill':
                    color.setAlpha(min(100,color.alpha()))
                    p.fillRect(target,color)
                elif kind == 'text':
                    p.setFont(self.draw_font(12,True))
                    text = p.fontMetrics().elidedText(stamp.get('text',''),Qt.TextElideMode.ElideRight,int(target.width()))
                    p.drawText(target,Qt.AlignmentFlag.AlignCenter,text)
        for stroke in (self.strokes + ([self.current] if self.current else [])) if prefs['show_ink'] else []:
            color = QColor(stroke['color'])
            color.setAlpha(round(255*stroke['opacity']/100) if 'opacity' in stroke else (110 if stroke.get('highlight') else 230))
            pen = QPen(color, stroke['width'] * width/700, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            points = [QPointF(a*width, 85+b*(height-85)) for a,b in stroke['points']]
            # Preserve actual black ink, adding only a light outline at night.
            pens = [pen]
            if self.owner.night_mode.isChecked() and stroke['color'] == '#000000':
                halo = QPen(pen)
                halo.setColor(QColor('#a6b4ca'))
                halo.setWidthF(pen.widthF()+2)
                pens.insert(0, halo)
            for active_pen in pens:
                p.setPen(active_pen)
                if len(points) == 1:
                    p.drawPoint(points[0])
                for a,b in zip(points, points[1:]):
                    p.drawLine(a,b)

    def norm(self, pos):
        header = self.header_height()
        return [max(0, min(1, pos.x()/self.width())), max(0,min(1,(pos.y()-header)/(self.height()-header)))]

    def day_at(self,pos):
        header = self.header_height()
        if pos.y() < header or not self.rect().contains(pos.toPoint()):
            return None
        index = min(41,int((pos.y()-header)/((self.height()-header)/6))*7+int(pos.x()/(self.width()/7)))
        return self.days[index]

    def snapshot(self):
        return copy.deepcopy(dict(strokes=self.strokes,stamps=self.stamps))

    def begin_edit(self):
        self.history.append(self.snapshot())
        self.history = self.history[-100:]
        self.redo_stack.clear()

    def restore_snapshot(self, value):
        self.strokes, self.stamps = copy.deepcopy(value['strokes']), copy.deepcopy(value['stamps'])
        self.save()

    def erase_at(self,pos):
        header = self.header_height()
        point = (pos.x(),pos.y()-header)
        if self.owner.custom['show_ink']:
            self.strokes = [stroke for stroke in self.strokes if not stroke_hit(stroke,point,self.width(),self.height()-header,self.owner.custom['eraser_size'],previous=self.erase_previous)]
        if self.owner.custom['show_stamps']:
            start = self.erase_previous or point
            steps = max(1, math.ceil(math.dist(start,point)/5))
            days = set()
            for step in range(steps+1):
                t = step/steps
                day = self.day_at(QPointF(start[0]+(point[0]-start[0])*t,header+start[1]+(point[1]-start[1])*t))
                if day:
                    days.add(day.isoformat())
            self.stamps = [stamp for stamp in self.stamps if stamp['day'] not in days]
        self.erase_previous = point
        self.update()

    def mousePressEvent(self, event):
        header = self.header_height()
        if event.button() != Qt.MouseButton.LeftButton or event.position().y() < header:
            return
        self.owner.active_board = self
        self.setFocus()
        if self.owner.draw_mode:
            self.begin_edit()
            prefs = self.owner.custom
            tool = self.owner.tool.currentData()
            if tool == 'eraser':
                self.erasing = True
                self.erase_previous = None
                self.erase_at(event.position())
            elif tool == 'stamp':
                day = self.day_at(event.position())
                if day:
                    self.stamps.append(dict(day=day.isoformat(),kind=prefs['stamp'],color=self.owner.color,width=prefs['pen_width'],opacity=prefs['pen_opacity'],text=prefs['stamp_text']))
                    self.save()
            else:
                self.current = dict(color=self.owner.color, width=max(12,prefs['pen_width']) if self.owner.highlight.isChecked() else prefs['pen_width'], opacity=min(45,prefs['pen_opacity']) if self.owner.highlight.isChecked() else prefs['pen_opacity'], highlight=self.owner.highlight.isChecked(), points=[self.norm(event.position())])
        else:
            index = min(41, int((event.position().y()-header)/((self.height()-header)/6))*7 + int(event.position().x()/(self.width()/7)))
            day = self.days[index]
            if MIN_YEAR <= day.year <= MAX_YEAR:
                self.owner.select(day)
        self.update()

    def mouseMoveEvent(self, event):
        if self.erasing:
            self.erase_at(event.position())
        if self.current:
            self.current['points'].append(self.norm(event.position()))
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self.erasing:
            self.erase_at(event.position())
            self.erasing = False
            self.erase_previous = None
            self.save()
        if self.current:
            self.current['points'].append(self.norm(event.position()))
            self.strokes.append(self.current)
            self.current = None
            self.redo_stack.clear()
            self.save()

    def save(self):
        self.owner.persist(self.key, self.strokes)
        self.owner.persist(self.stamp_key, self.stamps)
        self.update()


class CalendarApp(QMainWindow):
    def __init__(self, store=None):
        super().__init__()
        self.store = store or Store()
        self.tray = None
        self._quitting = False
        self._reminder_slot = None
        self.custom = preferences(self.store)
        self.background_pixmap = load_background(self.custom)
        self.calendar_surface = self.store.get('module-color:main-calendar','')
        self.dark = bool(self.store.get('night_mode', False))
        self.theme_colors = colors(self.dark,self.custom['overrides'])
        self.day_entries = self.store.load_days()
        today = date.today()
        self.selected = min(max(today, date(MIN_YEAR,1,1)), date(MAX_YEAR,12,31))
        self.year, self.month = self.selected.year, self.selected.month
        self.draw_mode, self.color, self.active_board = False, COLORS[0], None
        self.loading = False
        self.setWindowTitle(f'小日历 · v{VERSION} 自由桌面' + (' · 安全模式' if '--safe-mode' in sys.argv else ''))
        self.setMinimumSize(760, 600)
        self.resize(1320, 880)
        root = Background(self)
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(24,18,24,18)
        header = QHBoxLayout()
        title = QLabel('小日历 · 安全模式' if '--safe-mode' in sys.argv else '小日历')
        if '--safe-mode' in sys.argv:
            title.setToolTip('第三方 Python 插件未运行，正常启动应用可恢复。')
        title.setObjectName('mainTitle')
        header.addWidget(title)
        self.button('配件商店',lambda: self.body.shop(),header).setToolTip('浏览配件、添加到桌面，管理已添加的配件')
        self.button('背景与外观',self.open_preferences,header).setToolTip('选择本地图片，调整字体、颜色和标记样式')
        self.button('操作说明',self.show_help,header)
        self.button('备份与恢复',self.open_backup,header)
        self.button('导入导出',self.open_exchange,header).setToolTip('把事项导出为 .ics 日历或 .csv 表格，也可从 .csv 合并导入')
        arrange = self.button('整理布局',lambda:None,header)
        arrange_menu = QMenu(arrange)
        for label,kind in [('日历与事项左右排列','default'),('全部配件平铺','tile'),('全部配件层叠','cascade')]:
            arrange_menu.addAction(label,lambda checked=False,k=kind:self.body.arrange(k))
        arrange_menu.addSeparator()
        arrange_menu.addAction('撤销布局调整',lambda:self.body.undo_layout())
        arrange_menu.addAction('重做布局调整',lambda:self.body.redo_layout())
        arrange_menu.addAction('找回屏幕外模块',lambda:self.body.recover_panels())
        snap = arrange_menu.addAction('拖动时吸附对齐')
        snap.setCheckable(True)
        snap.setChecked(bool(self.store.get('workspace:snap',True)))
        snap.toggled.connect(lambda value:self.body.set_snap(value))
        arrange.setMenu(arrange_menu)
        self.layout_lock = QCheckBox('锁定位置')
        self.layout_lock.setToolTip('锁定后配件不能拖动或缩放，仍可编辑内容')
        self.layout_lock.setChecked(bool(self.store.get('workspace:locked',False)))
        self.layout_lock.toggled.connect(lambda locked:self.body.set_locked(locked))
        self.layout_lock.toggled.connect(lambda locked:arrange.setEnabled(not locked))
        arrange.setEnabled(not self.layout_lock.isChecked())
        header.addWidget(self.layout_lock)
        header.addStretch()
        self.clock = QLabel()
        self.clock.setObjectName('localClock')
        self.night_mode = QCheckBox('夜间主题')
        self.night_mode.setChecked(self.dark)
        self.night_mode.toggled.connect(self.change_theme)
        header.addWidget(self.night_mode)
        layout.addLayout(header)
        self.sections = QSplitter(Qt.Orientation.Vertical)
        self.sections.setChildrenCollapsible(False)
        self.sections.setHandleWidth(8)
        layout.addWidget(self.sections, 1)
        nav_panel = AdaptivePanel(1100, 52)
        bar = QHBoxLayout(nav_panel)
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
        self.auto_cross = QCheckBox('自动标记')
        self.auto_cross.setToolTip('按自定义中的条件标记日期：已过日期、周末或事项全部完成')
        self.auto_cross.setChecked(bool(self.store.get('auto_cross_past', False)))
        self.auto_cross.toggled.connect(self.save_auto_cross)
        bar.addWidget(self.auto_cross)
        self.cross_style = QComboBox()
        for label, value in [('斜线', 'diagonal'), ('叉号', 'cross'), ('横线', 'horizontal'), ('淡化', 'fade')]:
            self.cross_style.addItem(label, value)
        self.cross_style.setCurrentIndex(max(0, self.cross_style.findData(self.store.get('past_mark_style', 'diagonal'))))
        self.cross_style.setToolTip('自动标记的显示样式；条件、颜色和粗细可在“自定义”中设置')
        self.cross_style.setEnabled(self.auto_cross.isChecked())
        self.cross_style.currentIndexChanged.connect(self.save_cross_style)
        bar.addWidget(self.cross_style)
        self.button('搜索事项',self.open_search,bar).setToolTip('在全部日期中搜索事项并跳转（Ctrl+F）')
        self.button('回顾',self.open_review,bar).setToolTip('本月与今年的完成情况、连续天数与最近 12 个月热力图')
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
        self.sections.addWidget(self.toolbar_scroll(nav_panel))
        ink_panel = AdaptivePanel(1100, 52)
        ink = QHBoxLayout(ink_panel)
        self.pen_button = self.button('开始标记', self.toggle_draw, ink)
        self.pen_button.setToolTip('进入标记模式；再次点击返回日期选择和事项编辑')
        self.tool = QComboBox()
        for label,value in [('画笔','pen'),('橡皮擦','eraser'),('日期印章','stamp')]:
            self.tool.addItem(label,value)
        self.tool.currentIndexChanged.connect(lambda _: self.enable_tool())
        self.tool.setToolTip('画笔：按住拖动；橡皮擦：删除经过的整笔笔迹；日期印章：点击日期盖章')
        ink.addWidget(self.tool)
        self.color_buttons = {}
        for color in COLORS:
            b = self.button('●', lambda checked=False, c=color: self.set_color(c), ink)
            b.setProperty('largeText', True)
            b.setCheckable(True)
            b.setToolTip('黑色画笔' if color == '#000000' else color)
            b.setStyleSheet(f'color:{color};min-width:26px;padding:2px;')
            self.color_buttons[color] = b
        self.highlight = QCheckBox('荧光笔')
        self.button('自选色',self.choose_color,ink).setToolTip('为画笔和印章选择任意颜色')
        self.saved_colors = QComboBox()
        self.saved_colors.setMinimumWidth(80)
        self.saved_colors.activated.connect(lambda _:self.set_color(self.saved_colors.currentData()))
        ink.addWidget(self.saved_colors)
        self.button('收藏色',self.favorite_color,ink).setToolTip('把当前颜色加入左侧颜色列表，方便再次使用')
        ink.addWidget(self.highlight)
        self.button('撤销标记', self.undo, ink)
        self.button('重做', self.redo, ink)
        self.button('清空本月笔迹', self.clear_ink, ink).setToolTip('仅清除当前月份的自由笔迹；日期印章可用橡皮擦删除')
        ink.addStretch()
        self.ink_label = QLabel('选日期模式：点击日期编辑事项。配件标题可拖动，右下角可缩放。')
        self.ink_label.setObjectName('modeHint')
        self.ink_label.setWordWrap(True)
        layout.addWidget(self.ink_label)
        self.sections.addWidget(self.toolbar_scroll(ink_panel))
        self.body = Workspace(self)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setMinimumWidth(280)
        self.body.addWidget(self.scroll)
        panel = AdaptivePanel(320, 650)
        self.editor_panel = panel
        panel.setMinimumWidth(240)
        panel.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        panel.setObjectName('editorPanel')
        editor = QVBoxLayout(panel)
        editor.setContentsMargins(18,20,18,20)
        self.day_label = QLabel()
        self.day_label.setStyleSheet('font-weight:600;')
        self.day_label.setProperty('largeText', True)
        editor.addWidget(self.day_label)
        day_row = QHBoxLayout()
        day_row.addWidget(QLabel('当天事项 · 最多六条'))
        day_row.addStretch()
        self.template_button = QPushButton('模板…')
        self.template_button.setToolTip('把常用事项存成模板，一键插入这一天')
        self.template_button.clicked.connect(self.open_templates)
        day_row.addWidget(self.template_button)
        self.times_button = QPushButton('定时…')
        self.times_button.setToolTip('给当天的事项设置提醒时间（HH:MM）')
        self.times_button.clicked.connect(self.open_entry_times)
        day_row.addWidget(self.times_button)
        editor.addLayout(day_row)
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
            field.setMinimumWidth(40)
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
        tip.setProperty('muted', True)
        editor.addWidget(tip)
        editor.addStretch()
        self.range_label = QLabel(f'本地离线存储  ·  {MIN_YEAR} — {MAX_YEAR}')
        editor.addWidget(self.range_label)
        editor_scroll = QScrollArea()
        editor_scroll.setWidgetResizable(True)
        editor_scroll.setMinimumWidth(250)
        editor_scroll.setWidget(panel)
        self.body.addWidget(editor_scroll)
        self.sections.addWidget(self.body)
        self.sections.setSizes([76,76,700])
        self.body.setSizes([960,320])
        self.status = QLabel('已就绪 · 数据自动保存到本机')
        self.status.setObjectName('saveStatus')
        self.status.setProperty('muted', True)
        status_row = QHBoxLayout()
        status_row.addWidget(self.status,1)
        status_row.addWidget(self.clock)
        layout.addLayout(status_row)
        self.rebuild()
        self.select(self.selected)
        self.last_today = today
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(1000)
        self.tick()
        self.set_color(self.color)
        self.restore_layout()
        self.undo_shortcut = QShortcut(QKeySequence('Ctrl+Z'), self)
        self.redo_shortcut = QShortcut(QKeySequence('Ctrl+Y'), self)
        self.undo_shortcut.activated.connect(lambda: self.shortcut_edit(False))
        self.redo_shortcut.activated.connect(lambda: self.shortcut_edit(True))
        self.layout_undo_shortcut = QShortcut(QKeySequence('Ctrl+Alt+Z'),self)
        self.layout_redo_shortcut = QShortcut(QKeySequence('Ctrl+Alt+Y'),self)
        self.layout_undo_shortcut.activated.connect(self.body.undo_layout)
        self.layout_redo_shortcut.activated.connect(self.body.redo_layout)
        self.search_shortcut = QShortcut(QKeySequence('Ctrl+F'), self)
        self.search_shortcut.activated.connect(self.open_search)
        self.change_theme(self.dark, save=False)
        self.body.restore_workspace()
        self.apply_customization()
        self.refresh_color_list()
        self.apply_tray_settings()
        self.schedule_auto_backup()

    def apply_tray_settings(self):
        """Create/show or hide the tray icon; a missing tray simply degrades."""
        from status_tray import StatusTray, available as tray_available
        want = bool(self.custom.get('reminder_enabled') or self.custom.get('close_action') == 'tray')
        if want and self.tray is None and tray_available():
            try:
                self.tray = StatusTray(self, dict(show=self.show_window, today=self.go_today,
                                                  search=self.open_search, backup=self.open_backup,
                                                  pause=self.pause_reminder, snooze=self.snooze_reminders,
                                                  message_clicked=self.show_reminder_target,
                                                  quit=self.quit_app))
            except Exception:
                self.tray = None
        if self.tray is not None:
            try:
                self.tray.setVisible(bool(want) and tray_available())
            except Exception:
                pass

    def show_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def quit_app(self):
        self._quitting = True
        self.close()

    def pause_reminder(self):
        from reminders import pause_today
        pause_today(self.store, date.today())
        self.status.setText('今天不再提醒，明天按设置继续。')

    def snooze_reminders(self, minutes=10):
        from reminders import snooze
        state = snooze(self.store, minutes)
        self.status.setText(f"已推迟提醒到 {state['snooze'][11:16]}。")

    def show_reminder_target(self):
        self.show_window()
        self.go_today()

    def _notify(self, title, body):
        """Tray balloon when possible, otherwise the status bar; True when shown."""
        shown = False
        if self.tray is not None:
            try:
                shown = bool(self.tray.isVisible() and self.tray.notify(title, body))
            except Exception:
                shown = False
        if not shown:
            self.status.setText('提醒：' + title + (f' · {body}' if body else ''))
        return shown

    def check_reminder(self, now=None):
        """Per-entry times first, then the daily summary; once per minute slot."""
        from reminders import add_fired, due, load_state, mark_fired, snoozed, summary
        import entry_times
        now = now or datetime.now()
        slot = now.strftime('%Y%m%d%H%M')
        if slot == self._reminder_slot:
            return False
        self._reminder_slot = slot
        state = load_state(self.store)
        if snoozed(state, now):
            return False
        fired = False
        pending = entry_times.pending(self.day_entries, now.date(), now, state.get('fired', []))
        if pending:
            title, body = entry_times.message(pending)
            self._notify(title, body)
            add_fired(self.store, [item['key'] for item in pending], now.date())
            fired = True
        count, text = summary(self.day_entries, now.date())
        if due(self.custom, load_state(self.store), now, count > 0):
            title = f'今天还有 {count} 件未完成' if count else '今天没有未完成的事项'
            self._notify(title, text)
            mark_fired(self.store, now.date())
            fired = True
        return fired

    def schedule_auto_backup(self):
        QTimer.singleShot(30000, self.run_auto_backup)

    def run_auto_backup(self):
        try:
            from autobackup import run as run_backup
            report = run_backup(self.store, self.custom)
        except Exception as error:
            self.status.setText('自动备份未完成：' + str(error))
            return None
        if report.get('created'):
            self.status.setText('已自动备份：' + Path(report['created']).name)
        elif report.get('error'):
            self.status.setText('自动备份未完成：' + report['error'])
        return report

    def enable_tool(self):
        if not self.draw_mode:
            self.toggle_draw()
        self.update_mode_hint()

    def update_mode_hint(self):
        if not self.draw_mode:
            text = '选日期模式：点击日期编辑事项。配件标题可拖动，右下角可缩放。'
        else:
            text = {'pen':'画笔：按住鼠标拖动绘画；颜色在工具栏选择。',
                    'eraser':'橡皮擦：拖动删除经过的整笔笔迹或日期印章，Ctrl+Z 可撤销。',
                    'stamp':'日期印章：点击日期盖章；形状与文字在“背景与外观 → 标记与图层”设置。'}[self.tool.currentData()]
            text += ' 点击“返回选日期”可继续编辑事项。'
        self.ink_label.setText(text)

    def show_help(self):
        dialog = QDialog(self)
        dialog.setWindowTitle('小日历 · 操作说明')
        dialog.resize(640,510)
        box = QVBoxLayout(dialog)
        text = QTextEdit()
        text.setReadOnly(True)
        text.setHtml('''<h2>按你喜欢的方式安排桌面</h2>
<p><b>移动和缩放</b>：按住配件标题拖动到任意位置；拖右下角斜线调整大小。配件可以重叠，点击标题放到最前。勾选“锁定位置”可防止误动。</p>
<p><b>找回配件</b>：打开“配件商店 → 我的桌面”，显示或定位已有配件。标题上的 × 只隐藏配件，内容保留。使用“整理布局”可重新平铺。</p>
<p><b>布局保护</b>：“整理布局”可撤销/重做移动、缩放与整理，也可找回屏幕外模块。拖动时默认吸附对齐，可在同一菜单关闭。快捷键 Ctrl+Alt+Z / Ctrl+Alt+Y 专用于布局，Ctrl+Z / Ctrl+Y 仍用于笔迹或文本。</p>
<p><b>背景图片</b>：进入“背景与外观”，选择本地图片，查看预览后保存。图片不明显时，降低“日期格底色不透明度”。</p>
<p><b>模块外观</b>：在配件标题的“设置 → 颜色与透明度”独立选择底色、文字颜色及整体不透明度。100% 为完全不透明，数值越低越透明；取消可恢复原样。</p>
<p><b>背景透明、文字清晰</b>：降低“仅底色不透明度”，保持“模块不透明度”为 100%，即可让背景透明而保留文字。第三方插件自绘内容由插件控制。</p>
<p><b>备份与恢复</b>：顶部“备份与恢复”可导出整套 ZIP 备份，包含背景与插件数据。恢复会先备份原数据，再替换当前内容；恢复后的 Python 插件需要重新确认启用。</p>
<p><b>导入导出</b>：顶部“导入导出”把事项导出为 .ics 日历文件或 .csv 表格。从 .csv 导入只新增、不删除，按日期+时段+文字去重，每日最多六条，逐行报告跳过原因，并自动备份原数据。</p>
<p><b>定时提醒</b>：编辑面板“定时…”给当天事项设置 HH:MM 提醒时间，留空表示不提醒。到点用托盘气泡提示，点击气泡打开窗口并跳到今天；同一分钟的多条合并成一条，错过时间会在下次打开后补提醒；托盘菜单可“稍后提醒（10 分钟）”。</p>
<p><b>提醒与托盘</b>：设置窗口的“提醒”页签，选择提醒时间与是否只在工作日提醒；到点用托盘气泡提示当天未完成的事项，没有未完成就不打扰。托盘菜单可显示窗口、搜索、备份、暂停今天的提醒或退出；“关闭窗口时”可选退出或最小化到托盘，系统没有托盘时自动退回退出。</p>
<p><b>自动备份</b>：设置窗口的“备份”页签，每天在数据有变化时生成一份完整 ZIP，保留最近几份，默认写入数据目录的 backups 文件夹；失败只在窗口底部提示。</p>
<p><b>回顾</b>：导航栏“回顾”查看本月与今年的完成条数、完成率、有事项天数，以及当前与历史最长连续完成天数；下方是最近 12 个月热力图和今年早/午/晚的完成分布。连续天数只算“当天有事项且全部完成”。</p>
<p><b>事项模板</b>：编辑面板“模板…”把常用事项存起来（最多 30 条），选中日期后一键插入；同一天已有相同事项或已满六条会拒绝，不会覆盖已有内容。</p>
<p><b>搜索事项</b>：导航栏“搜索事项”（Ctrl+F）跨全部日期查找，可按早/午/晚和“只看未完成”过滤，双击结果跳到该日期。</p>
<p><b>第三方插件</b>：进入“配件商店 → 第三方插件”，导入 ZIP 或 manifest.json，确认信任后启用，再添加到桌面。“保存可编辑示例”提供 Python 模板；打开源码目录修改后可重新加载。插件拥有本机用户权限。</p>
<p><b>每日事项</b>：在选日期模式点击日期，填写最多六条事项，早/午/晚可自由选择，文字自动保存。左侧勾选表示完成。</p>
<p><b>绘画与印章</b>：点击“开始标记”，选择画笔、橡皮擦或日期印章。橡皮擦删除经过的整笔笔迹以及日期上的印章。印章形状、文字与粗细在“背景与外观 → 标记与图层”设置。</p>
<p><b>自动标记</b>：勾选“自动标记”，旁边选择斜线、叉号、横线或淡化。条件可在标记设置里选择已过日期、周末或事项全部完成。</p>
<p><b>快捷键</b>：Ctrl+Z 撤销、Ctrl+Y 重做、T 回到今天、Ctrl+F 搜索事项、Ctrl+Alt+Z / Ctrl+Alt+Y 撤销/重做布局调整。文本输入时保留正常输入和文本撤销。</p>''')
        box.addWidget(text)
        done = QPushButton('知道了，开始使用')
        done.clicked.connect(dialog.accept)
        box.addWidget(done)
        dialog.exec()

    def choose_color(self):
        color = QColorDialog.getColor(QColor(self.color),self,'选择画笔 / 印章颜色')
        if color.isValid():
            self.set_color(color.name())
            self.custom['recent_colors'] = ([color.name()] + [v for v in self.custom['recent_colors'] if v != color.name()])[:12]
            self.persist('customization:v1',self.custom)
            self.refresh_color_list()

    def favorite_color(self):
        if self.color not in self.custom['favorite_colors']:
            self.custom['favorite_colors'].append(self.color)
            self.persist('customization:v1',self.custom)
            self.refresh_color_list()

    def refresh_color_list(self):
        self.saved_colors.clear()
        for prefix,key in [('★','favorite_colors'),('最近','recent_colors')]:
            for color in self.custom[key]:
                self.saved_colors.addItem(prefix+' '+color,color)

    def open_preferences(self):
        dialog = PreferencesDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.custom = dialog.values
            self.persist('customization:v1',self.custom)
            self.background_pixmap = load_background(self.custom)
            self.change_theme(self.dark,save=False)
            self.centralWidget().update()
            self.apply_tray_settings()

    def apply_customization(self):
        QApplication.instance().setProperty('calendarCustom',self.custom)
        font = QFont(self.custom.get('font_family') or FONT_FAMILY)
        font.setPixelSize(self.custom['font_size'])
        if QApplication.instance().font() != font:
            QApplication.instance().setFont(font)
        for panel in self.findChildren(AdaptivePanel):
            panel.refresh_font()
        self.body.refresh_fonts()
        self.body.apply_colors()
        for board in self.boards:
            board.update()

    def change_theme(self, dark, save=True):
        self.dark = dark
        self.theme_colors = colors(dark,self.custom['overrides'])
        configure_style(QApplication.instance(), dark,self.custom['overrides'])
        self.apply_customization()
        # A black swatch stays identifiable against the dark toolbar.
        self.color_buttons['#000000'].setStyleSheet('color:#000000;background:#dce3ee;min-width:26px;padding:2px;')
        self.set_color(self.color)
        for board in self.boards:
            board.update()
        if save:
            self.persist('night_mode', dark)

    def save_cross_style(self, *_):
        self.persist('past_mark_style', self.cross_style.currentData())
        for board in self.boards:
            board.update()

    def shortcut_edit(self, redo):
        field = QApplication.focusWidget()
        if isinstance(field, (QLineEdit,QPlainTextEdit,QTextEdit)):
            field.redo() if redo else field.undo()
        else:
            self.redo() if redo else self.undo()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_T and event.modifiers() == Qt.KeyboardModifier.NoModifier and not isinstance(QApplication.focusWidget(), (QLineEdit,QPlainTextEdit,QTextEdit)):
            self.go_today()
            event.accept()
        else:
            super().keyPressEvent(event)

    def toolbar_scroll(self, panel):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(76)
        scroll.setWidget(panel)
        return scroll

    def is_past_day(self, day, today=None):
        if not self.auto_cross.isChecked() or not self.custom['show_auto']:
            return False
        rule = self.custom['rule']
        if rule == 'weekend':
            return day.weekday() >= 5
        if rule == 'completed':
            rows = self.day_entries.get(day.isoformat(),[])
            return bool(rows) and all(row['done'] for row in rows)
        return day < (today or date.today())

    def save_auto_cross(self, enabled):
        self.persist('auto_cross_past', enabled)
        self.cross_style.setEnabled(enabled)
        for board in self.boards:
            board.update()

    def restore_layout(self):
        saved = self.store.get('layout:v2', {})
        if not saved:
            return
        self.resize(*saved.get('window', [1320,880]))
        self.orientation.setCurrentIndex(saved.get('orientation', 0))
        self.count.setCurrentIndex(saved.get('count', 1))
        self.body.setSizes(saved.get('body', [960,320]))
        self.sections.setSizes(saved.get('sections', [64,64,700]))
        self.month_splitter.setSizes(saved.get('months', [650]*len(self.boards)))

    def open_backup(self):
        from backup_ui import BackupDialog
        BackupDialog(self).exec()

    def open_exchange(self):
        from exchange_ui import ExchangeDialog
        ExchangeDialog(self).exec()

    def open_search(self):
        from entry_search import SearchDialog
        SearchDialog(self).exec()

    def open_review(self):
        from review_ui import ReviewDialog
        ReviewDialog(self).exec()

    def open_templates(self):
        from templates_ui import TemplatesDialog
        TemplatesDialog(self).exec()

    def open_entry_times(self):
        from entry_times_ui import EntryTimesDialog
        EntryTimesDialog(self).exec()

    def reload_entries(self):
        """Re-read entry data after an import; ink, workspace and plugins are untouched."""
        self.day_entries = self.store.load_days()
        self.select(self.selected)
        for board in self.boards:
            board.update()

    def save_session(self):
        self.body.save_workspace()
        self.persist('layout:v2', dict(window=[self.width(),self.height()],
            body=self.body.sizes(), sections=self.sections.sizes(),
            orientation=self.orientation.currentIndex(), count=self.count.currentIndex(),
            months=self.month_splitter.sizes()))

    def closeEvent(self, event):
        tray_ready = self.tray is not None and self.tray.isVisible()
        if (not getattr(self,'_quitting',False) and tray_ready
                and self.custom.get('close_action') == 'tray'):
            # Keep reminders alive in the tray; the quit action still exits fully.
            if not getattr(self,'_skip_save',False):
                self.save_session()
            self.hide()
            event.ignore()
            return
        if not getattr(self,'_skip_save',False):
            self.save_session()
        self.body.shutdown_plugins()
        super().closeEvent(event)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        for board in getattr(self,'boards',[]):
            board.update()
        if hasattr(self,'body'):
            self.body.canvas.update()

    def button(self, text, callback, layout):
        b = QPushButton(text)
        b.clicked.connect(callback)
        layout.addWidget(b)
        return b

    def persist(self, key, value):
        try:
            self.store.put(key, value)
            self.status.setText('已保存到本机 · 配件与标记自动保存')
            self.status.setToolTip(str(Path(self.store.db.execute('PRAGMA database_list').fetchone()[2])))
            return True
        except (OSError, sqlite3.Error) as exc:
            self.status.setText('保存失败，请保留窗口并检查磁盘空间：' + str(exc))
            return False

    def tick(self):
        global MIN_YEAR, MAX_YEAR
        from datetime import datetime
        self.clock.setText(datetime.now().strftime('本地时间  %Y-%m-%d  %H:%M:%S'))
        if date.today() != self.last_today:
            self.last_today = date.today()
            if MAX_YEAR != self.last_today.year + 10:
                MIN_YEAR, MAX_YEAR = self.last_today.year - 10, self.last_today.year + 10
                self.year = max(MIN_YEAR, min(MAX_YEAR, self.year))
                self.year_box.blockSignals(True)
                self.year_box.clear()
                self.year_box.addItems([str(y) for y in range(MIN_YEAR, MAX_YEAR+1)])
                self.year_box.blockSignals(False)
                self.range_label.setText(f'本地离线存储  ·  {MIN_YEAR} — {MAX_YEAR}')
                self.sync_navigation()
            for b in self.boards:
                b.update()
        self.check_reminder()

    def rebuild(self, *_):
        previous_sizes = self.month_splitter.sizes() if hasattr(self, 'month_splitter') else []
        container = QSplitter(Qt.Orientation.Horizontal if self.orientation.currentIndex() else Qt.Orientation.Vertical)
        container.setChildrenCollapsible(False)
        container.setHandleWidth(10)
        self.month_splitter = container
        self.boards = []
        for offset in range(self.count.currentIndex()+1):
            serial = self.year*12+self.month-1+offset
            year, month = serial//12, serial%12+1
            if year > MAX_YEAR:
                break
            board = MonthBoard(self,year,month)
            board.setCursor(Qt.CursorShape.CrossCursor if self.draw_mode else Qt.CursorShape.ArrowCursor)
            container.addWidget(board)
            self.boards.append(board)
        self.active_board = self.boards[0]
        self.scroll.setWidget(container)
        container.setSizes(previous_sizes if len(previous_sizes) == len(self.boards) else [650]*len(self.boards))
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
        saved = self.day_entries.get(day.isoformat(), [])
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
        if self.persist('day:'+self.selected.isoformat(),rows):
            self.day_entries[self.selected.isoformat()] = rows
        for b in self.boards:
            b.update()

    def toggle_draw(self):
        self.draw_mode = not self.draw_mode
        self.pen_button.setText('返回选日期' if self.draw_mode else '开始标记')
        self.update_mode_hint()
        for b in self.boards:
            b.setCursor(Qt.CursorShape.CrossCursor if self.draw_mode else Qt.CursorShape.ArrowCursor)

    def set_color(self,color):
        if not color:
            return
        self.color = color
        self.pen_button.setStyleSheet('font-weight:bold;')
        for value, button in self.color_buttons.items():
            button.setChecked(value == color)

    def undo(self):
        b = self.active_board
        if b.history:
            b.redo_stack.append(b.snapshot())
            b.restore_snapshot(b.history.pop())

    def redo(self):
        b = self.active_board
        if b.redo_stack:
            b.history.append(b.snapshot())
            b.restore_snapshot(b.redo_stack.pop())

    def clear_ink(self):
        b = self.active_board
        if b.strokes and QMessageBox.question(self,'清空笔迹',f'清空 {b.year} 年 {b.month} 月的全部笔迹？事项不会被删除。') == QMessageBox.StandardButton.Yes:
            b.begin_edit()
            b.strokes = []
            b.save()


def configure_style(app, dark=False, overrides=None):
    theme = colors(dark,overrides)
    if not app.property('calendarStyleInitialized'):
        app.setStyle('Fusion')
        if sys.platform == 'win32':
            fonts = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts'
            for name in ('msyh.ttc', 'msyhbd.ttc', 'segoeui.ttf'):
                if (fonts / name).exists():
                    QFontDatabase.addApplicationFont(str(fonts / name))
        app.setFont(QFont(FONT_FAMILY, 10))
        app.setProperty('calendarStyleInitialized', True)
    palette = QPalette()
    for role, color in {
        QPalette.ColorRole.Window: theme['background'],
        QPalette.ColorRole.WindowText: theme['text'],
        QPalette.ColorRole.Base: theme['surface'],
        QPalette.ColorRole.AlternateBase: theme['alternate'],
        QPalette.ColorRole.Text: theme['text'],
        QPalette.ColorRole.Button: theme['surface'],
        QPalette.ColorRole.ButtonText: theme['text'],
        QPalette.ColorRole.ToolTipBase: theme['surface'],
        QPalette.ColorRole.ToolTipText: theme['text'],
        QPalette.ColorRole.Highlight: theme['accent'],
        QPalette.ColorRole.HighlightedText: '#ffffff',
        QPalette.ColorRole.PlaceholderText: theme['muted'],
    }.items():
        palette.setColor(role, QColor(color))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText, QPalette.ColorRole.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(theme['dim']))
    app.setPalette(palette)
    app.setStyleSheet(stylesheet(dark,overrides))


def main():
    smoke = '--smoke-test' in sys.argv
    if smoke:
        os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    app = QApplication(sys.argv)
    configure_style(app)
    temporary = None
    if smoke:
        import tempfile
        temporary = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    window = CalendarApp(Store(Path(temporary.name)/'smoke.sqlite3') if smoke else None)
    window.show()
    if smoke:
        # Check the packaged image decoder, store and settings UI too. These
        # paths used to be missed by a main-window-only startup check.
        from qt_compat import QPixmap
        from preferences import cache_background_image
        from module_shop import ModuleShop
        sample = QPixmap(80,60)
        sample.fill(QColor('#90b4d4'))
        path = Path(temporary.name)/'本地背景.png'
        assert sample.save(str(path),'PNG')
        window.custom['background_image'] = cache_background_image(window.store,path)
        window.custom['background_mode'] = 'image'
        window.background_pixmap = load_background(window.custom)
        assert not window.background_pixmap.isNull()
        note = window.body.add_module('notes')
        note.text.setPlainText('打包检查')
        from module_appearance import ModuleAppearanceDialog
        library = window.body.plugin_library
        example = library.export_example(Path(temporary.name)/'示例插件.zip')
        plugin = window.body.import_python_plugin(example)
        assert not library.is_approved(plugin['id'])
        if not window.body.safe_mode:
            window.body.enable_python_plugin(plugin['id'],plugin['digest'])
            first = window.body.add_module(plugin['id'])
            second = window.body.add_module(plugin['id'])
            assert first.instance is not None and second.instance is not None, window.body.plugin_errors
            editor = first.instance.widget.findChild(QPlainTextEdit)
            editor.setPlainText('冻结程序动态插件检查')
            assert first.instance.context.get_value('text') == '冻结程序动态插件检查'
            assert second.instance.context.get_value('text','') == ''
            window.body.reload_python_plugin(plugin['id'])
            assert first.instance.widget.findChild(QPlainTextEdit).toPlainText() == '冻结程序动态插件检查'
            window.body.disable_plugin(plugin['id'])
            assert first.instance is None and second.instance is None
            window.body.enable_python_plugin(plugin['id'],plugin['digest'])
            assert first.instance is not None
        assert window.body.set_module_style('main-calendar',dict(background='#172033',foreground='',opacity=80))
        appearance = ModuleAppearanceDialog(window.body,'main-calendar')
        appearance.show()
        shop, settings = ModuleShop(window.body), PreferencesDialog(window)
        shop.show()
        settings.show()
        app.processEvents()
        assert not shop.grab().isNull() and not settings.grab().isNull() and not appearance.grab().isNull()
        appearance.reject()
        from backup import export_backup, PreparedRestore
        from backup_ui import BackupDialog
        backup_dialog = BackupDialog(window)
        backup_dialog.show()
        app.processEvents()
        assert not backup_dialog.grab().isNull()
        window.save_session()
        backup_path = export_backup(window.store,Path(temporary.name)/'smoke-backup.zip')
        restored_backup = PreparedRestore(backup_path)
        assert 'workspace:modules' in restored_backup.entries
        restored_backup.close()
        backup_dialog.close()
        from exchange_ui import ExchangeDialog
        from exchange import export_ics, export_csv, import_csv
        exchange_dialog = ExchangeDialog(window)
        exchange_dialog.show()
        window.rows[0][2].setText('导入导出检查')
        app.processEvents()
        assert not exchange_dialog.grab().isNull()
        ics_path = export_ics(window.store,Path(temporary.name)/'导出.ics')
        csv_path = export_csv(window.store,Path(temporary.name)/'导出.csv')
        assert ics_path.stat().st_size > 0 and b'BEGIN:VCALENDAR' in ics_path.read_bytes()
        assert csv_path.stat().st_size > 0 and '导入导出检查' in csv_path.read_text(encoding='utf-8-sig')
        assert import_csv(window.store,csv_path,min_year=MIN_YEAR,max_year=MAX_YEAR)['added'] == []
        upcoming = (window.selected+timedelta(days=1)).isoformat()
        extra = Path(temporary.name)/'导入.csv'
        extra.write_text('date,period,text,done\n'+upcoming+',早,来自表格,0\n',encoding='utf-8')
        written = import_csv(window.store,extra,min_year=MIN_YEAR,max_year=MAX_YEAR)
        assert len(written['added']) == 1 and written['skipped'] == []
        window.reload_entries()
        assert window.day_entries[upcoming][0]['text'] == '来自表格'
        exchange_dialog.close()
        from preferences import PreferencesDialog as _PreferencesDialog
        prefs = _PreferencesDialog(window)
        prefs.reminder_hour.setValue(6)
        assert prefs.values['reminder_minutes'] == 6*60 + prefs.reminder_minute.value()
        prefs.close()
        window.custom.update(reminder_enabled=True, reminder_minutes=0, reminder_skip_empty=False)
        assert window.check_reminder(datetime.combine(date.today(), datetime(2000, 1, 1).time())) is True
        assert '提醒' in window.status.text()
        window.custom.update(reminder_enabled=False)
        window.custom['close_action'] = 'tray'
        window.apply_tray_settings()
        window.custom['close_action'] = 'quit'
        assert window.run_auto_backup()['skipped'] is True
        window.custom.update(backup_auto=True, backup_keep=2)
        assert window.run_auto_backup()['created']
        from review_ui import ReviewDialog as _ReviewDialog
        review_dialog = _ReviewDialog(window)
        review_dialog.show()
        app.processEvents()
        assert not review_dialog.grab().isNull() and review_dialog.data['month']['entries'] >= 0
        review_dialog.close()
        from templates_ui import TemplatesDialog as _TemplatesDialog
        template_dialog = _TemplatesDialog(window)
        template_dialog.show()
        template_dialog.input.setText('打包检查模板')
        template_dialog.period.setCurrentIndex(0)
        template_dialog.add_current()
        template_dialog.insert_selected()
        assert any(row.get('text') == '打包检查模板'
                   for row in window.day_entries.get(window.selected.isoformat(), []))
        assert not template_dialog.grab().isNull()
        template_dialog.close()
        from entry_times_ui import EntryTimesDialog as _EntryTimesDialog
        window.select(date.today())
        times_dialog = _EntryTimesDialog(window)
        if times_dialog.editors:
            times_dialog.editors[0][1].setText('23:59')
            times_dialog.save()
            assert window.store.get('day:' + date.today().isoformat(), [])[0].get('time') == '23:59'
        times_dialog.close()
        from recurrence_ui import RepeatDialog as _RepeatDialog
        repeat_source = _TemplatesDialog(window)
        repeat_source.input.setText('重复检查')
        repeat_source.period.setCurrentIndex(0)
        repeat_source.add_current()
        repeat_source.list.setCurrentRow(max(0, repeat_source.list.count() - 1))
        repeat_dialog = _RepeatDialog(window, repeat_source.selected())
        repeat_dialog.times.setValue(2)
        repeat_dialog.save()
        assert repeat_dialog.report and len(repeat_dialog.report['added']) == 2, repeat_dialog.report
        repeat_dialog.close()
        repeat_source.close()
        shop.close()
        settings.close()
        QTimer.singleShot(500, app.quit)
    result = app.exec()
    if smoke:
        window.close()
        window.store.db.close()
        temporary.cleanup()
    sys.exit(result)


if __name__ == '__main__':
    main()
