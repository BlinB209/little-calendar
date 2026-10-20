"""Regression checks for v0.4 workspace, marking tools and persistence."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import tempfile
from pathlib import Path
from datetime import date
from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest
from app import QApplication, CalendarApp, Store, configure_style
from markings import stroke_hit

app = QApplication([])
configure_style(app)
assert stroke_hit({'points':[[.5,.1],[.5,.9]],'width':4},(900,500),1000,1000,10,previous=(100,500))
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
    path = Path(folder)/'preview.sqlite3'
    window = CalendarApp(Store(path))
    window.count.setCurrentIndex(0)
    window.show()
    app.processEvents()
    board = window.boards[0]
    position = QPoint(int(board.width()/14),int(board.header_height()+30))
    window.tool.setCurrentIndex(window.tool.findData('stamp'))
    window.custom['stamp'] = 'text'
    window.custom['stamp_text'] = '重要'
    QTest.mouseClick(board,Qt.MouseButton.LeftButton,pos=position)
    assert len(board.stamps) == 1 and board.stamps[0]['text'] == '重要'
    window.undo()
    assert not board.stamps
    window.redo()
    assert len(board.stamps) == 1
    before = board.snapshot()
    window.custom['show_stamps'] = False
    board.grab()
    assert board.snapshot() == before
    window.custom['show_stamps'] = True
    window.tool.setCurrentIndex(window.tool.findData('eraser'))
    QTest.mouseClick(board,Qt.MouseButton.LeftButton,pos=position)
    assert not board.stamps
    window.undo()
    assert len(board.stamps) == 1
    window.auto_cross.setChecked(True)
    window.custom['rule'] = 'weekend'
    assert window.is_past_day(date(2026,10,24))
    assert not window.is_past_day(date(2026,10,23))
    window.custom['rule'] = 'completed'
    assert not window.is_past_day(date(2026,10,23))
    window.day_entries['2026-10-23'] = [{'done':True,'period':'早','text':'测试'}]
    assert window.is_past_day(date(2026,10,23))
    note = window.body.add_module('notes')
    note.text.setPlainText('重启后保留的便签')
    note_id = note.record['id']
    window.body.disable_plugin('notes')
    assert window.body.docks[note_id].isHidden()
    window.body.set_module_visible(note_id,True)
    assert window.body.docks[note_id].isHidden()
    window.body.install_plugin('notes')
    assert not window.body.docks[note_id].isHidden()
    for plugin in ('tasks','month','clock','habit'):
        window.body.add_module(plugin)
    plugin_path = Path(folder)/'note.json'
    plugin_path.write_text('{"schema":1,"id":"custom-note","title":"Custom note","kind":"note"}',encoding='utf-8')
    window.body.import_plugin(plugin_path)
    window.body.add_module('custom-note')
    window.custom.update(background_mode='gradient',background_color='#eff5ff',gradient_color='#d5e6ed',font_size=15)
    window.apply_customization()
    window.persist('customization:v1',window.custom)
    window.body.set_module_visible('daily-editor',False)
    assert window.body.docks['daily-editor'].isHidden()
    window.body.set_module_visible('daily-editor',True)
    window.body.set_locked(True)
    assert window.body.locked
    window.body.set_locked(False)
    app.processEvents()
    window.grab().save(str(Path(folder)/'workspace.png'))
    window.close()
    window.store.db.close()
    restored = CalendarApp(Store(path))
    restored.show()
    app.processEvents()
    assert restored.body.docks[note_id].widget().text.toPlainText() == '重启后保留的便签'
    assert 'custom-note' in restored.body.installed
    assert restored.custom['font_size'] == 15
    assert len(restored.boards[0].stamps) == 1
    restored.close()
    restored.store.db.close()
print('PASS: stamps, eraser, undo/redo, layers, auto rules, module install/disable/restart, plugin import and customization')
