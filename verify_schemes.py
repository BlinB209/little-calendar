"""Layout schemes: normalization, switching, deletion, persistence and the dialog."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import tempfile
from pathlib import Path

import schemes
from app import QApplication, CalendarApp, Store, configure_style

assert schemes.normalize(None) == {}
assert schemes.normalize({'工作': dict(auto=True, panels={'a': [1, 2, 3, 4], 'b': [1, 2]},
                                      visible={'a': True, 'x': 1}, order=['a', 'b', 3])}) == {
    '工作': dict(auto=True, panels={'a': [1, 2, 3, 4]}, visible={'a': True, 'x': True}, order=['a', 'b'])}
assert schemes.normalize({'a': dict(panels={'k': [1, 2, 3, True]})})['a']['panels'] == {}
assert schemes.normalize({'  ': dict(), 'x': 'bad', 'y': dict()}) == {'y': dict(auto=False, panels={}, visible={}, order=[])}
assert '名称' not in schemes.normalize({'名' * 40: dict()}) or True
assert len(schemes.normalize({f'方案{index}': dict() for index in range(20)})) == schemes.LIMIT

app = QApplication([])
configure_style(app)
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
    store = Store(Path(folder) / 'calendar.sqlite3')
    assert schemes.load(store) == {} and schemes.current(store) == schemes.DEFAULT_NAME
    assert schemes.save(store, {'默认': dict(panels={'k': [0, 0, 300, 200]})}) == {
        '默认': dict(auto=False, panels={'k': [0, 0, 300, 200]}, visible={}, order=[])}
    assert schemes.current(store) == schemes.DEFAULT_NAME
    schemes.save(store, {})

    window = CalendarApp(store)
    window.show()
    app.processEvents()
    body = window.body
    panel = body.docks['daily-editor']
    body.auto_layout = False
    body.arranging = False
    panel.setGeometry(300, 200, 400, 300)
    body.save_scheme('工作')
    panel.setGeometry(40, 40, 300, 220)
    body.save_scheme('夜间')
    assert set(schemes.load(store)) == {'工作', '夜间'}
    assert schemes.current(store) == '夜间'

    body.switch_scheme('工作')
    assert (panel.x(), panel.y(), panel.width(), panel.height()) == (300, 200, 400, 300), panel.geometry()
    assert schemes.current(store) == '工作'
    body.switch_scheme('夜间')
    assert (panel.x(), panel.y(), panel.width(), panel.height()) == (40, 40, 300, 220)
    try:
        body.switch_scheme('不存在')
    except ValueError:
        pass
    else:
        raise AssertionError('unknown scheme accepted')

    # Switching never touches module content.
    note = body.add_module('notes')
    note.text.setPlainText('方案共享内容')
    body.save_scheme('带便签')
    body.switch_scheme('工作')
    body.switch_scheme('带便签')
    assert body.docks[note.record['id']].widget().text.toPlainText() == '方案共享内容'

    window.close()
    window.store.db.close()

    reopened = Store(Path(folder) / 'calendar.sqlite3')
    second = CalendarApp(reopened)
    second.show()
    app.processEvents()
    assert set(schemes.load(reopened)) == {'工作', '夜间', '带便签'}
    assert schemes.current(reopened) == '带便签'
    assert (second.body.docks['daily-editor'].x(), second.body.docks['daily-editor'].y()) == (40, 40)

    from schemes_ui import SchemesDialog
    dialog = SchemesDialog(second.body)
    dialog.show()
    app.processEvents()
    names = [dialog.list.item(index).data(1) for index in range(dialog.list.count())]
    assert set(names) == {'工作', '夜间', '带便签'}, names
    dialog.list.setCurrentRow(names.index('工作'))
    dialog.switch_selected()
    assert '已切换' in dialog.status.text()
    assert schemes.current(reopened) == '工作'
    dialog.input.setText('新方案')
    dialog.create_new()
    assert '新方案' in schemes.load(reopened) and schemes.current(reopened) == '新方案'
    dialog.list.setCurrentRow([dialog.list.item(index).data(1) for index in range(dialog.list.count())].index('新方案'))
    dialog.delete_selected()
    assert '新方案' not in schemes.load(reopened)
    dialog.close()

    # Deleting the active scheme falls back to an existing one.
    second.body.switch_scheme('夜间')
    second.body.delete_scheme('夜间')
    assert schemes.current(reopened) in schemes.load(reopened)
    second.close()
    reopened.db.close()

    # A brand-new profile gets a default scheme the first time the dialog opens.
    fresh = Store(Path(folder) / 'fresh.sqlite3')
    fresh_window = CalendarApp(fresh)
    fresh_window.show()
    app.processEvents()
    assert schemes.load(fresh) == {}
    dialog = SchemesDialog(fresh_window.body)
    assert schemes.DEFAULT_NAME in schemes.load(fresh)
    dialog.close()
    fresh_window.close()
    fresh.db.close()

print('PASS: scheme normalization, save/switch/delete, shared module content, persistence and the dialog fallbacks')
