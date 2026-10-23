"""Entry move/copy: capacity, duplicates, source cleanup, dialog and persistence."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import tempfile
from datetime import date, timedelta
from pathlib import Path

import entry_move
from app import QApplication, CalendarApp, Store, configure_style

source = date(2026, 12, 1)
target = date(2026, 12, 2)
rows = [dict(done=False, period='早', text='体检', time='09:30'),
        dict(done=True, period='午', text='交作业')]
assert entry_move.parse_day('2026-12-02') == target
assert entry_move.parse_day(' 2026-12-02 ') == target
assert entry_move.parse_day('2026-13-01') is None
assert entry_move.parse_day('明天') is None
assert entry_move.rows_of({'2026-12-01': rows}, source)[0] == dict(done=False, period='早', text='体检', time='09:30')

app = QApplication([])
configure_style(app)
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
    store = Store(Path(folder) / 'calendar.sqlite3')
    store.put('day:2026-12-01', rows)
    store.put('day:2026-12-02', [dict(done=False, period='晚', text='看电影')])

    # Copy keeps the source and appends to the target.
    report = entry_move.transfer(store, store.load_days(), source, target, index=0, mode='copy')
    assert report == dict(moved=['体检'], skipped=[], error=None), report
    assert store.get('day:2026-12-01', []) == rows
    assert [row['text'] for row in store.get('day:2026-12-02', [])] == ['看电影', '体检']
    assert store.get('day:2026-12-02', [])[1]['time'] == '09:30', 'time survives the transfer'

    # Move removes it from the source.
    report = entry_move.transfer(store, store.load_days(), source, target, index=1, mode='move')
    assert report['moved'] == ['交作业']
    assert [row['text'] for row in store.get('day:2026-12-01', [])] == ['体检']

    # Duplicates on the target are skipped, never duplicated.
    report = entry_move.transfer(store, store.load_days(), source, target, index=0, mode='copy')
    assert report['moved'] == [] and report['skipped'][0]['reason'] == '目标日期已有相同事项'

    # Same day, missing entries and capacity refusals write nothing.
    assert entry_move.transfer(store, store.load_days(), source, source)['error'] == '目标日期与来源是同一天'
    assert entry_move.transfer(store, store.load_days(), source, target, index=9)['error'] == '要移动的事项不存在'
    full_day = date(2026, 12, 3)
    store.put('day:2026-12-03', [dict(done=False, period='早', text=f'满{index}') for index in range(6)])
    before = store.get('day:2026-12-03', [])
    report = entry_move.transfer(store, store.load_days(), source, full_day, mode='copy')
    assert report['error'] == '目标日期最多 6 条，请先腾出位置' and report['moved'] == []
    assert store.get('day:2026-12-03', []) == before

    # Moving everything empties the source day.
    store.put('day:2026-12-04', [dict(done=False, period='早', text='一条')])
    report = entry_move.transfer(store, store.load_days(), date(2026, 12, 4), date(2026, 12, 5), mode='move')
    assert report['moved'] == ['一条'] and store.get('day:2026-12-04', []) == []
    assert '已处理 1 条' in entry_move.summary(report)

    # Dialog: default target is the next day; saving moves and reloads the window.
    window = CalendarApp(Store(Path(folder) / 'ui.sqlite3'))
    window.show()
    app.processEvents()
    window.select(date.today())
    window.rows[0][2].setText('对话框移动')
    window.store.put('day:' + date.today().isoformat(), [dict(done=False, period='早', text='对话框移动')])
    window.reload_entries()
    from entry_move_ui import MoveDialog
    dialog = MoveDialog(window)
    dialog.show()
    app.processEvents()
    assert dialog.target.text() == (date.today() + timedelta(days=1)).isoformat()
    dialog.mode.setCurrentIndex(dialog.mode.findData('move'))
    dialog.save()
    assert dialog.result() == dialog.DialogCode.Accepted
    tomorrow = date.today() + timedelta(days=1)
    assert window.store.get('day:' + tomorrow.isoformat(), []) == [dict(done=False, period='早', text='对话框移动')]
    assert window.store.get('day:' + date.today().isoformat(), []) == []
    assert window.day_entries.get(date.today().isoformat(), []) == [], 'the open window reloads'
    # A bad date is refused with a hint and no write.
    dialog2 = MoveDialog(window)
    dialog2.target.setText('明天')
    dialog2.save()
    assert 'YYYY-MM-DD' in dialog2.hint.text() and dialog2.result() != dialog2.DialogCode.Accepted
    dialog2.close()
    dialog.close()
    window.close()
    window.store.db.close()

print('PASS: move/copy semantics, time preservation, duplicate/capacity/same-day refusals, source cleanup and the dialog path')
