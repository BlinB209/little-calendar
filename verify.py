import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import tempfile
from pathlib import Path
from datetime import date
from datetime import timedelta
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest
from app import CalendarApp, Store, configure_style, MIN_YEAR, MAX_YEAR

app = QApplication([])
configure_style(app)
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
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
    window.year,window.month = MAX_YEAR,12
    window.sync_navigation()
    assert len(window.boards) == 1 and not window.next.isEnabled()
    window.navigate(1)
    assert (window.year,window.month) == (MAX_YEAR,12)
    assert MIN_YEAR == date.today().year-10 and MAX_YEAR == date.today().year+10
    window.year,window.month = 2028,2
    window.sync_navigation()
    assert date(2028,2,29) in window.boards[0].days
    assert window.boards[0].days[0].weekday() == 0
    window.toggle_draw()
    window.set_color('#000000')
    board = window.boards[0]
    QTest.mousePress(board, Qt.MouseButton.LeftButton, pos=QPoint(40,120))
    QTest.mouseMove(board, QPoint(140,180))
    QTest.mouseRelease(board, Qt.MouseButton.LeftButton, pos=QPoint(140,180))
    assert len(board.strokes) == 1
    assert board.strokes[0]['color'] == '#000000'
    queries = []
    window.store.db.set_trace_callback(queries.append)
    for _ in range(4):
        board.grab()
    window.store.db.set_trace_callback(None)
    assert not queries, queries
    window.undo()
    assert not board.strokes
    window.redo()
    assert len(board.strokes) == 1
    window.activateWindow()
    board.setFocus()
    app.processEvents()
    QTest.keyClick(board, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert not board.strokes
    QTest.keyClick(board, Qt.Key.Key_Y, Qt.KeyboardModifier.ControlModifier)
    assert len(board.strokes) == 1
    field = window.rows[5][2]
    field.setFocus()
    old_selected = window.selected
    QTest.keyClicks(field, 't')
    assert field.text().endswith('t') and window.selected == old_selected
    QTest.keyClick(field, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert field.text() == '事项 6' and len(board.strokes) == 1
    board.setFocus()
    QTest.keyClick(board, Qt.Key.Key_T)
    assert window.selected == date.today()
    window.year,window.month = 2028,2
    window.sync_navigation()
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
    # Resize the actual window and panels; both custom-painted and widget text
    # must respond, and date hit testing must use the scaled header.
    window.resize(1000,720)
    window.body.setSizes([700,250])
    app.processEvents()
    small_scale = window.boards[0].scale_factor()
    small_font = window.rows[0][2].font().pixelSize()
    window.resize(1800,1100)
    window.body.setSizes([1200,540])
    app.processEvents()
    assert window.boards[0].scale_factor() > small_scale
    assert window.rows[0][2].font().pixelSize() > small_font
    board = window.boards[0]
    position = QPoint(int(board.width()/14), int(board.header_height()+(board.height()-board.header_height())/12))
    QTest.mouseClick(board, Qt.MouseButton.LeftButton, pos=position)
    assert window.selected == board.days[0]
    window.count.setCurrentIndex(1)
    window.orientation.setCurrentIndex(1)
    app.processEvents()
    window.month_splitter.setSizes([450,750])
    app.processEvents()
    assert window.boards[1].width() > window.boards[0].width()
    window.count.setCurrentIndex(0)
    window.orientation.setCurrentIndex(0)
    window.resize(1320,880)
    window.body.setSizes([960,320])
    window.select(date(2026,10,14))
    app.processEvents()
    today = date.today()
    assert not window.auto_cross.isChecked()
    before_days = window.store.get('day:2028-02-29', [])
    before_ink = window.store.get('ink:2028-02', [])
    before_image = window.boards[0].grab().toImage()
    window.auto_cross.setChecked(True)
    assert window.is_past_day(today-timedelta(days=1))
    assert not window.is_past_day(today)
    assert not window.is_past_day(today+timedelta(days=1))
    assert window.is_past_day(date(2028,2,29), date(2028,3,1))
    assert window.is_past_day(date(2029,12,31), date(2030,1,1))
    assert window.boards[0].grab().toImage() != before_image
    window.auto_cross.setChecked(False)
    assert window.boards[0].grab().toImage() == before_image
    assert window.store.get('day:2028-02-29', []) == before_days
    assert window.store.get('ink:2028-02', []) == before_ink
    window.auto_cross.setChecked(True)
    window.grab().save('preview.png')
    # Each style must visibly differ, without altering any user data.
    styles = []
    for index in range(window.cross_style.count()):
        window.cross_style.setCurrentIndex(index)
        app.processEvents()
        rendered = window.boards[0].grab().toImage()
        assert all(rendered != previous for previous in styles)
        styles.append(rendered)
    window.cross_style.setCurrentIndex(1)
    light_image = window.boards[0].grab().toImage()
    window.night_mode.setChecked(True)
    app.processEvents()
    dark_image = window.boards[0].grab().toImage()
    assert dark_image != light_image
    assert dark_image.pixelColor(4,4).lightness() < 80
    assert window.rows[0][2].palette().text().color().lightness() > 180
    window.grab().save('preview-night.png')
    window.night_mode.setChecked(False)
    app.processEvents()
    returned_image = window.boards[0].grab().toImage()
    # Qt can renegotiate dock/toolbar heights during repolishing; compare
    # restored colors independently of those few pixels of layout movement.
    assert returned_image.pixelColor(4,4) == light_image.pixelColor(4,4)
    assert window.rows[0][2].palette().text().color().name() == window.theme_colors['text']
    window.night_mode.setChecked(True)
    assert window.store.get('day:2028-02-29', []) == before_days
    assert window.store.get('ink:2028-02', []) == before_ink
    window.close()
    window.store.db.close()
    reopened = Store(path)
    assert len(reopened.get('day:2028-02-29', [])) == 6
    assert len(reopened.get('ink:2028-02', [])) == 1
    assert reopened.get('ink:2028-02', [])[0]['color'] == '#000000'
    restored = CalendarApp(reopened)
    restored.show()
    app.processEvents()
    assert restored.size() == window.size()
    assert restored.count.currentIndex() == 0
    assert restored.auto_cross.isChecked()
    assert restored.night_mode.isChecked()
    assert restored.cross_style.currentData() == 'cross'
    restored.close()
    reopened.db.close()
print('PASS: rolling years, zero-SQL redraws, shortcuts, black pen, responsive fonts, splitters, four past-day styles, night theme and persistence')
