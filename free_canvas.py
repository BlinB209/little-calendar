"""A scrollable desktop with movable, overlapping panels inside the app."""
import sys
from qt_compat import Qt, QTimer, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QMenu, QRectF, QPainter
from preferences import paint_background
if sys.platform == 'linux':
    from PyQt6.QtCore import QEvent, QPoint
    from PyQt6.QtWidgets import QFrame
else:
    from PySide6.QtCore import QEvent, QPoint
    from PySide6.QtWidgets import QFrame


class ResizeCorner(QWidget):
    def __init__(self, panel):
        super().__init__(panel)
        self.panel = panel
        self.origin = None
        self.setFixedSize(22, 22)
        self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        self.setToolTip('按住拖动，调整这个配件的宽度和高度')

    def paintEvent(self, event):
        p = QPainter(self)
        p.setPen(self.panel.workspace.owner.palette().mid().color())
        for step in (5, 10, 15):
            p.drawLine(20-step,20,20,20-step)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and not self.panel.workspace.locked:
            self.panel.workspace.history.begin()
            self.origin = (event.globalPosition().toPoint(),self.panel.size())
            self.panel.workspace.activate_module(self.panel.objectName(), scroll=False)
            event.accept()

    def mouseMoveEvent(self, event):
        if self.origin is not None:
            delta = event.globalPosition().toPoint()-self.origin[0]
            self.panel.workspace.auto_layout = False
            self.panel.resize(self.origin[1].width()+delta.x(),self.origin[1].height()+delta.y())

    def mouseReleaseEvent(self, event):
        self.origin = None
        self.panel.workspace.history.finish()
        self.panel.workspace.schedule_save()


class FreePanel(QFrame):
    def __init__(self, workspace, key, title, content):
        super().__init__(workspace.canvas)
        self.workspace = workspace
        self._content = content
        self._drag = None
        self.setObjectName(key)
        self.setProperty('freePanel',True)
        self.setMinimumSize(240,180)
        self.setWindowTitle(title)
        box = QVBoxLayout(self)
        box.setContentsMargins(7,5,7,7)
        box.setSpacing(4)
        bar = QHBoxLayout()
        self.title = QLabel(title+' · 拖动')
        self.title.setProperty('panelTitle',True)
        self.title.setCursor(Qt.CursorShape.SizeAllCursor)
        self.title.setToolTip('按住标题拖动到任意位置；配件可以重叠')
        self.title.installEventFilter(self)
        bar.addWidget(self.title,1)
        self.menu_button = QPushButton('设置')
        self.menu_button.setFixedSize(48,28)
        self.menu_button.setToolTip('重命名、置顶、调整位置和颜色')
        self.menu_button.clicked.connect(self.open_menu)
        bar.addWidget(self.menu_button)
        self.hide_button = QPushButton('×')
        self.hide_button.setFixedSize(30,28)
        self.hide_button.setToolTip('隐藏配件，内容保留；可从配件商店重新显示')
        self.hide_button.clicked.connect(lambda:workspace.set_module_visible(key,False))
        bar.addWidget(self.hide_button)
        box.addLayout(bar)
        box.addWidget(content,1)
        self.corner = ResizeCorner(self)
        self.corner.raise_()

    def widget(self):
        return self._content

    def setWindowTitle(self,title):
        super().setWindowTitle(title)
        if hasattr(self,'title'):
            self.title.setText(title+(' · 已锁定' if self.workspace.locked else ' · 拖动'))

    def set_locked(self,locked):
        self._drag = None
        self.corner.origin = None
        self.corner.setVisible(not locked)
        self.title.setCursor(Qt.CursorShape.ArrowCursor if locked else Qt.CursorShape.SizeAllCursor)
        self.title.setText(self.windowTitle()+(' · 已锁定' if locked else ' · 拖动'))
        self.title.setToolTip('布局已锁定；取消顶部“锁定位置”可拖动' if locked else '按住标题拖动到任意位置；配件可以重叠')

    def open_menu(self):
        menu = QMenu(self)
        menu.addAction('置于最前',lambda:self.workspace.activate_module(self.objectName(),scroll=False))
        rename = menu.addAction('重命名…',lambda:self.workspace.prompt_rename(self.objectName()))
        fill = menu.addAction('放大到当前视图',lambda:self.workspace.fill_view(self.objectName()))
        fill.setEnabled(not self.workspace.locked)
        menu.addSeparator()
        menu.addAction('颜色与透明度…',lambda:self.workspace.open_module_appearance(self.objectName()))
        menu.addSeparator()
        menu.addAction('隐藏（保留内容）',lambda:self.workspace.set_module_visible(self.objectName(),False))
        menu.exec(self.menu_button.mapToGlobal(self.menu_button.rect().bottomLeft()))

    def eventFilter(self,watched,event):
        if watched is self.title:
            kind = event.type()
            if kind == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                if not self.workspace.locked:
                    self.workspace.history.begin()
                self.workspace.activate_module(self.objectName(),scroll=False)
                if not self.workspace.locked:
                    self._drag = (event.globalPosition().toPoint(),self.pos())
                return True
            if kind == QEvent.Type.MouseMove and self._drag is not None:
                pos = self._drag[1]+event.globalPosition().toPoint()-self._drag[0]
                self.workspace.auto_layout = False
                x,y = self.workspace.snap_position(self,pos.x(),pos.y())
                self.move(x,y)
                return True
            if kind == QEvent.Type.MouseButtonRelease:
                self._drag = None
                self.workspace.history.finish()
                self.workspace.schedule_save()
                return True
        return super().eventFilter(watched,event)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'corner'):
            self.corner.move(self.width()-23,self.height()-23)
            self.corner.raise_()
        self.workspace.geometry_changed()

    def moveEvent(self,event):
        super().moveEvent(event)
        self.workspace.geometry_changed()

    def showEvent(self,event):
        super().showEvent(event)
        self.workspace.geometry_changed()

    def closeEvent(self,event):
        event.ignore()
        self.workspace.set_module_visible(self.objectName(),False)


class Canvas(QWidget):
    def __init__(self,workspace):
        super().__init__()
        self.workspace = workspace

    def paintEvent(self,event):
        owner = self.workspace.owner
        painter = QPainter(self)
        root = owner.centralWidget()
        origin = self.mapTo(root,QPoint(0,0))
        painter.translate(-origin.x(),-origin.y())
        paint_background(painter,QRectF(root.rect()),owner.custom,owner.theme_colors,owner.background_pixmap)
        painter.translate(origin.x(),origin.y())
        painter.setPen(self.palette().highlight().color())
        for axis,value in self.workspace.guides:
            if axis=='x':
                painter.drawLine(value,0,value,self.height())
            else:
                painter.drawLine(0,value,self.width(),value)


class FreeCanvas(QScrollArea):
    def __init__(self,workspace):
        super().__init__()
        self.workspace = workspace
        self.setWidgetResizable(False)
        self.canvas = Canvas(workspace)
        self.setWidget(self.canvas)
        self.horizontalScrollBar().valueChanged.connect(self.refresh_background)
        self.verticalScrollBar().valueChanged.connect(self.refresh_background)

    def refresh_background(self,*_):
        self.canvas.update()
        for board in getattr(self.workspace.owner,'boards',[]):
            board.update()

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self.workspace,'canvas'):
            if self.workspace.auto_layout:
                self.workspace.arrange_default(save=False)
            self.workspace.resize_canvas()
