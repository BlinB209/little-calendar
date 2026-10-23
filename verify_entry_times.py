"""Per-entry reminder times: parsing, catch-up, de-duplication and the dialog."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import tempfile
from datetime import date, datetime, time, timedelta
from pathlib import Path

import entry_times
import reminders
from app import QApplication, CalendarApp, Store, configure_style

assert entry_times.parse('15:30') == '15:30'
assert entry_times.parse(' 9:05 ') == '09:05'
assert entry_times.parse('09：05') == '09:05'
assert entry_times.parse('23:59') == '23:59'
for bad in ('24:00', '12:60', '1234', 'abc', '', None, '1:2', 930):
    assert entry_times.parse(bad) is None, bad

day = date(2026, 10, 23)
rows = [dict(done=False, period='早', text='体检', time='15:30'),
        dict(done=False, period='午', text='交作业', time='09:00'),
        dict(done=True, period='晚', text='无时间'),
        dict(done=False, period='早', text='坏时间', time='99:99')]
scheduled = entry_times.scheduled({'2026-10-23': rows}, day)
assert [item['time'] for item in scheduled] == ['09:00', '15:30']
assert scheduled[0]['key'] == '2026-10-23|09:00|午|交作业'
assert entry_times.scheduled({}, day) == []

nine = datetime.combine(day, time(9, 0))
assert [item['text'] for item in entry_times.pending({'2026-10-23': rows}, day, nine)] == ['交作业']
assert entry_times.pending({'2026-10-23': rows}, day, datetime.combine(day, time(9, 0)),
                           ['2026-10-23|09:00|午|交作业']) == []
# Catch-up: a late check still fires the item that was due earlier.
assert [item['text'] for item in entry_times.pending({'2026-10-23': rows}, day,
                                                     datetime.combine(day, time(23, 0)))] == ['交作业', '体检']
assert entry_times.pending({'2026-10-23': rows}, day, datetime.combine(day, time(8, 59))) == []
assert entry_times.message([]) == ('', '')
assert entry_times.message([dict(time='09:00', period='午', text='交作业')]) == ('09:00 交作业', '午 · 交作业')
title, body = entry_times.message([dict(time='09:00', period='午', text='交作业'),
                                   dict(time='15:30', period='早', text='体检'),
                                   dict(time='16:00', period='早', text='取快递'),
                                   dict(time='17:00', period='晚', text='散步')])
assert title == '有 4 个定时提醒' and body.startswith('09:00 交作业') and body.endswith('等 4 项'), (title, body)
assert entry_times.prune(['2026-10-23|a', '2026-10-22|b', 5], day) == ['2026-10-23|a']
assert len(entry_times.prune([f'2026-10-23|{index}' for index in range(300)], day)) == 200

app = QApplication([])
configure_style(app)
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
    store = Store(Path(folder) / 'calendar.sqlite3')
    written = entry_times.apply_times(store, day, [
        dict(done=True, period='早', text='体检', time='9:05'),
        dict(done=False, period='午', text='空时间'),
        dict(done=False, period='晚', text='   '),
        dict(done=False, period='晚', text='坏时间', time='25:00')])
    assert written == [dict(done=True, period='早', text='体检', time='09:05'),
                       dict(done=False, period='午', text='空时间'),
                       dict(done=False, period='晚', text='坏时间')], written
    assert store.get('day:2026-10-23', []) == written

    # Fired keys merge, stay bounded and drop yesterday's keys.
    reminders.add_fired(store, ['2026-10-23|x'], day)
    reminders.add_fired(store, ['2026-10-23|x', '2026-10-23|y'], day)
    assert reminders.load_state(store)['fired'] == ['2026-10-23|x', '2026-10-23|y']
    reminders.add_fired(store, ['2026-10-24|z'], date(2026, 10, 24))
    assert reminders.load_state(store)['fired'] == ['2026-10-24|z']

    # Snooze blocks checks until its deadline.
    now = datetime.combine(day, time(9, 0))
    reminders.snooze(store, 10, now)
    assert reminders.snoozed(reminders.load_state(store), now) is True
    assert reminders.snoozed(reminders.load_state(store), now + timedelta(minutes=11)) is False
    reminders.save_state(store, {})

    # Dialog: setting a time persists it, bad input is refused, empty days disable save.
    window = CalendarApp(Store(Path(folder) / 'ui.sqlite3'))
    window.show()
    app.processEvents()
    window.select(day)
    window.store.put('day:2026-10-23', [dict(done=False, period='早', text='体检'),
                                        dict(done=True, period='晚', text='散步')])
    window.reload_entries()
    from entry_times_ui import EntryTimesDialog
    dialog = EntryTimesDialog(window)
    dialog.show()
    app.processEvents()
    assert len(dialog.editors) == 2
    dialog.editors[0][1].setText('15:30')
    dialog.editors[1][1].setText('bad')
    dialog.save()
    assert '时间格式不对' in dialog.hint.text()
    assert 'time' not in window.store.get('day:2026-10-23', [])[0], 'invalid input must not be written'
    dialog.editors[1][1].clear()
    dialog.save()
    assert [row.get('time') for row in window.store.get('day:2026-10-23', [])] == ['15:30', None]
    assert dialog.result() == dialog.DialogCode.Accepted
    assert window.rows[0][2].text() == '体检'
    dialog.close()

    # App check: fires once at/after the time, then never again that day.
    window.select(day)
    window.custom.update(reminder_enabled=False, reminder_skip_empty=True)
    window.day_entries = window.store.load_days()
    window._reminder_slot = None
    at_time = datetime.combine(day, time(15, 30))
    assert window.check_reminder(at_time) is True
    assert '提醒' in window.status.text() and '体检' in window.status.text()
    assert any('15:30' in key for key in reminders.load_state(window.store)['fired'])
    assert window.check_reminder(at_time + timedelta(minutes=15)) is False
    # A different minute slot costs no SQLite query for the per-entry path when snoozed.
    window._reminder_slot = None
    reminders.snooze(window.store, 10, at_time)
    queries = []
    window.store.db.set_trace_callback(queries.append)
    assert window.check_reminder(at_time + timedelta(minutes=1)) is False
    window.store.db.set_trace_callback(None)
    assert len(queries) <= 1, queries
    window.close()
    window.store.db.close()

print('PASS: HH:MM parsing, per-entry due/catch-up, fired de-duplication, snooze gate, dialog validation and one-shot firing')
