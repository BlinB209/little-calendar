import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import tempfile
from pathlib import Path
from datetime import date
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest
from app import CalendarApp, Store, configure_style

app = QApplication([])
configure_style(app)
with tempfile.TemporaryDirectory() as folder:
    path = Path(folder) / 'test.sqlite3'
    window = CalendarApp(Store(path))
    window.show()
    app.processEvents()
    window.select(date(2028, 2, 29))
    for i, (done, period, field) in enumerate(window.rows):
        field.setText('事项 %s' % (i+1))
        period.setCurrentIndex(i % 3)
    window.rows[0][0].setChecked(True)
    assert len(window.store.get('day:2028-02-29', [])) == 6
    window.select(date(2028,3,1))
    assert all(not field.text() for _,_,field in window.rows)
    window.select(date(2028,2,29))
    assert window.rows[0][0].isChecked()
    assert window.rows[5][2].text() == '事项 6'
    window.year,window.month = 2030,12
    window.sync_navigation()
    assert len(window.boards) == 1 and not window.next.isEnabled()
    window.navigate(1)
    assert (window.year,window.month) == (2030,12)
    window.year,window.month = 2028,2
    window.sync_navigation()
    assert date(2028,2,29) in window.boards[0].days
    assert window.boards[0].days[0].weekday() == 0
    window.toggle_draw()
    board = window.boards[0]
    QTest.mousePress(board, Qt.MouseButton.LeftButton, pos=QPoint(40,120))
    QTest.mouseMove(board, QPoint(140,180))
    QTest.mouseRelease(board, Qt.MouseButton.LeftButton, pos=QPoint(140,180))
    assert len(board.strokes) == 1
    window.undo()
    assert not board.strokes
    window.redo()
    assert len(board.strokes) == 1
    window.orientation.setCurrentIndex(1)
    app.processEvents()
    assert len(window.boards[0].strokes) == 1
    window.toggle_draw()
    window.year,window.month = 2026,10
    window.sync_navigation()
    window.select(date(2026,10,14))
    window.count.setCurrentIndex(0)
    window.orientation.setCurrentIndex(0)
    app.processEvents()
    window.grab().save('preview.png')
    window.close()
    window.store.db.close()
    reopened = Store(path)
    assert len(reopened.get('day:2028-02-29', [])) == 6
    assert len(reopened.get('ink:2028-02', [])) == 1
    reopened.db.close()
print('PASS: dates, six entries, completion, month limits, drawing, undo/redo, layout and persistence')
