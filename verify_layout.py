"""Exercise real pointer gestures and restore exact free-placement geometry."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import tempfile
from pathlib import Path
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from app import QApplication, CalendarApp, Store, configure_style

app = QApplication([])
configure_style(app)
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
    path = Path(folder)/'layout.sqlite3'
    window = CalendarApp(Store(path))
    window.count.setCurrentIndex(0)
    window.show()
    QTest.qWait(30)
    note = window.body.add_module('notes')
    note.text.setPlainText('自由位置与大小测试')
    key = note.record['id']
    panel = window.body.docks[key]
    window.body.rename_module(key,'我的随手记')
    before = panel.pos()
    QTest.mousePress(panel.title,Qt.MouseButton.LeftButton,pos=QPoint(30,10))
    QTest.mouseMove(panel.title,QPoint(140,80))
    QTest.mouseRelease(panel.title,Qt.MouseButton.LeftButton,pos=QPoint(140,80))
    assert panel.pos() != before,(panel.pos(),before)
    old_size = panel.size()
    QTest.mousePress(panel.corner,Qt.MouseButton.LeftButton,pos=QPoint(10,10))
    QTest.mouseMove(panel.corner,QPoint(90,70))
    QTest.mouseRelease(panel.corner,Qt.MouseButton.LeftButton,pos=QPoint(10,10))
    assert panel.width() > old_size.width() and panel.height() > old_size.height()
    window.layout_lock.setChecked(True)
    locked = panel.geometry()
    QTest.mousePress(panel.title,Qt.MouseButton.LeftButton,pos=QPoint(30,10))
    QTest.mouseMove(panel.title,QPoint(160,90))
    QTest.mouseRelease(panel.title,Qt.MouseButton.LeftButton,pos=QPoint(160,90))
    assert panel.geometry() == locked
    assert panel.corner.isHidden()
    window.layout_lock.setChecked(False)
    window.body.auto_layout = False
    panel.setGeometry(777,555,435,360)
    window.body.rename_module('main-calendar','我的日历')
    window.body.set_module_visible('daily-editor',False)
    window.body.save_workspace()
    QTest.qWait(30)
    expected = panel.geometry()
    window.close()
    window.store.db.close()
    restored = CalendarApp(Store(path))
    restored.show()
    QTest.qWait(30)
    panel = restored.body.docks[key]
    assert panel.geometry() == expected,(panel.geometry(),expected)
    assert panel.windowTitle() == '我的随手记'
    assert restored.body.docks['main-calendar'].windowTitle() == '我的日历'
    assert restored.body.docks['daily-editor'].isHidden()
    assert panel.widget().text.toPlainText() == '自由位置与大小测试'
    restored.body.activate_module(key)
    assert restored.body.desktop.horizontalScrollBar().value() > 0 or panel.x() < restored.body.desktop.viewport().width()
    restored.body.set_module_visible(key,False)
    restored.body.activate_module(key)
    assert not panel.isHidden()
    restored.body.arrange('tile')
    visible = [p for p in restored.body.docks.values() if not p.isHidden()]
    assert all(not a.geometry().intersects(b.geometry()) for i,a in enumerate(visible) for b in visible[i+1:])
    restored.close()
    restored.store.db.close()
print('PASS: pointer drag/resize, locking, free positions, rename, hidden state, content and restart persistence')
