"""Templates: normalization, storage, merge-only insertion and the dialog path."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import tempfile
from datetime import date
from pathlib import Path

import templates
from app import QApplication, CalendarApp, Store, configure_style

assert templates.normalize(None) == []
assert templates.normalize(['跑步', dict(text='读书', period='早'), dict(text='坏', period='夜'),
                            dict(text=''), 'x' * 200, dict(text='读书', period='早')]) == [
    dict(text='跑步', period='午'), dict(text='读书', period='早'), dict(text='坏', period='午')]
assert len(templates.normalize([dict(text=f'模板{i}', period='午') for i in range(40)])) == templates.LIMIT

app = QApplication([])
configure_style(app)
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
    store = Store(Path(folder) / 'calendar.sqlite3')
    assert templates.load(store) == []
    saved = templates.add(store, '健身 30 分钟', '晚')
    assert saved == [dict(text='健身 30 分钟', period='晚')]
    templates.add(store, '读书', '早')
    assert len(templates.load(store)) == 2
    templates.add(store, '读书', '早')
    assert templates.load(store) == [dict(text='健身 30 分钟', period='晚'), dict(text='读书', period='早')], 'identical templates replace, not duplicate'
    try:
        templates.add(store, '   ', '早')
    except ValueError:
        pass
    else:
        raise AssertionError('empty template accepted')
    assert templates.remove(store, 0) == [dict(text='读书', period='早')]
    try:
        templates.remove(store, 5)
    except ValueError:
        pass
    else:
        raise AssertionError('out-of-range removal accepted')

    # Insertion appends, refuses duplicates and never overwrites the day.
    day = date(2026, 11, 3)
    day_entries = {'2026-11-03': [dict(done=True, period='早', text='原有')]}
    rows, error = templates.insert(store, day_entries, day, dict(text='新增', period='晚'))
    assert error is None and [row['text'] for row in rows] == ['原有', '新增'], (rows, error)
    assert store.get('day:2026-11-03', []) == [
        dict(done=True, period='早', text='原有'), dict(done=False, period='晚', text='新增')]
    rows, error = templates.insert(store, {'2026-11-03': store.get('day:2026-11-03', [])}, day,
                                   dict(text='新增', period='晚'))
    assert rows and error == '这一天已有相同事项'
    full = [dict(done=False, period='早', text=f'满{index}') for index in range(6)]
    rows, error = templates.insert(store, {'2026-11-04': full}, date(2026, 11, 4), dict(text='溢出', period='早'))
    assert error == '这一天已满 6 条' and len(rows) == 6
    assert store.get('day:2026-11-04', None) is None, 'a refused insert must not write'
    assert templates.insert(store, {}, date(2026, 11, 5), dict(text='', period='早'))[1] == '模板内容为空'

    # Dialog: add, insert into the selected date and refresh the open window.
    window = CalendarApp(Store(Path(folder) / 'ui.sqlite3'))
    window.show()
    app.processEvents()
    window.select(date(2027, 2, 8))
    from templates_ui import TemplatesDialog
    dialog = TemplatesDialog(window)
    dialog.show()
    dialog.input.setText('体检预约')
    dialog.period.setCurrentIndex(dialog.period.findData('早'))
    dialog.add_current()
    assert templates.load(window.store)[0] == dict(text='体检预约', period='早')
    dialog.insert_selected()
    assert window.store.get('day:2027-02-08', []) == [dict(done=False, period='早', text='体检预约')]
    assert window.rows[0][2].text() == '体检预约', 'the open editor should show the inserted entry'
    assert '已插入' in dialog.status.text()
    dialog.insert_selected()
    assert '已有相同事项' in dialog.status.text()
    dialog.list.setCurrentRow(0)
    dialog.remove_selected()
    assert templates.load(window.store) == []
    dialog.close()

    # Full day surfaces the limit instead of dropping the row.
    window.select(date(2027, 2, 9))
    templates.add(window.store, '第十条', '早')
    window.store.put('day:2027-02-09', [dict(done=False, period='早', text=f'满{index}') for index in range(6)])
    window.reload_entries()
    dialog = TemplatesDialog(window)
    dialog.insert_selected()
    assert '已满 6 条' in dialog.status.text()
    dialog.close()
    window.close()
    window.store.db.close()

print('PASS: template normalization, add/replace/remove, merge-only insertion, duplicate/full/empty refusals and the dialog path')
