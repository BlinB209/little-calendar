"""Reminder rules, message text, persisted marks and the throttled app check."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import tempfile
from datetime import date, datetime, time
from pathlib import Path

from app import QApplication, CalendarApp, Store, configure_style
from preferences import normalize_preferences
import reminders
from reminders import due, label, load_state, mark_fired, message, pause_today, reset_due, summary

settings = dict(reminder_enabled=True, reminder_minutes=20*60,
                reminder_weekdays_only=False, reminder_skip_empty=True)
state = {}
friday = datetime(2026, 10, 23, 19, 59)   # 2026-10-23 is a Friday
assert due(settings, state, friday, True) is False, 'before the chosen minute'
assert due(settings, state, datetime(2026, 10, 23, 20, 0), True) is True
assert due(settings, state, datetime(2026, 10, 23, 23, 30), True) is True
assert due(dict(settings, reminder_enabled=False), state, datetime(2026, 10, 23, 20, 0), True) is False
assert due(settings, dict(last='2026-10-23'), datetime(2026, 10, 23, 21, 0), True) is False
assert due(settings, dict(paused='2026-10-23'), datetime(2026, 10, 23, 21, 0), True) is False
assert due(settings, dict(last='2026-10-22'), datetime(2026, 10, 23, 21, 0), True) is True
assert due(settings, state, datetime(2026, 10, 23, 21, 0), False) is False, 'nothing open is not a reminder'
assert due(dict(settings, reminder_skip_empty=False), state, datetime(2026, 10, 23, 21, 0), False) is True
assert due(dict(settings, reminder_weekdays_only=True), state, datetime(2026, 10, 24, 21, 0), True) is False, 'Saturday'
assert due(dict(settings, reminder_weekdays_only=True), state, datetime(2026, 10, 26, 21, 0), True) is True, 'Monday'
assert due(dict(settings, reminder_minutes='bad'), state, datetime(2026, 10, 23, 20, 0), True) is True, 'bad value falls back to 20:00'
assert due(settings, {'last': 'not-a-date'}, datetime(2026, 10, 23, 20, 0), True) is True
assert label(0) == '00:00' and label(20*60 + 5) == '20:05' and label(1439) == '23:59'

entries = {'2026-10-23': [dict(done=False, period='早', text='交作业'),
                          dict(done=True, period='午', text='已完成'),
                          dict(done=False, period='晚', text='散步')]}
count, text = summary(entries, date(2026, 10, 23))
assert count == 2 and text == '早 · 交作业；晚 · 散步', (count, text)
assert summary(entries, date(2026, 10, 22)) == (0, '')
many = {'2026-10-23': [dict(done=False, period='早', text=f'事项{index}') for index in range(7)]}
assert summary(many, date(2026, 10, 23)) == (7, '早 · 事项0；早 · 事项1；早 · 事项2；早 · 事项3 等 7 件')
assert message(entries, date(2026, 10, 23))[0] == '今天还有 2 件未完成'
assert message({}, date(2026, 10, 23))[0] == '今天没有未完成的事项'

# New preference keys survive normalization and clamp hostile values.
normalized = normalize_preferences(dict(reminder_enabled=True, reminder_minutes=5000,
                                        backup_keep=0, close_action='tray', backup_folder='x'*9000,
                                        reminder_weekdays_only=True))
assert normalized['reminder_enabled'] is True and normalized['reminder_minutes'] == 1439
assert normalized['backup_keep'] == 1 and normalized['close_action'] == 'tray'
assert len(normalized['backup_folder']) == 4096 and normalized['reminder_weekdays_only'] is True
fallback = normalize_preferences(dict(close_action='explode', reminder_enabled='yes'))
assert fallback['close_action'] == 'quit' and fallback['reminder_enabled'] is False

app = QApplication([])
configure_style(app)
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
    store = Store(Path(folder) / 'calendar.sqlite3')
    window = CalendarApp(store)
    window.show()
    app.processEvents()
    today = date.today()
    window.day_entries[today.isoformat()] = [dict(done=False, period='早', text='交作业')]
    window.custom.update(reminder_enabled=True, reminder_minutes=0, reminder_skip_empty=True,
                         reminder_weekdays_only=False, close_action='quit')
    now = datetime.combine(today, time(9, 0))
    assert window.check_reminder(now) is True
    assert '提醒' in window.status.text() and '交作业' in window.status.text()
    assert load_state(store)['last'] == today.isoformat()
    assert window.check_reminder(now) is False, 'the same minute must not fire twice'
    assert window.check_reminder(datetime.combine(today, time(9, 30))) is False, 'once per day'
    # A throttle hit costs no SQLite query at all.
    queries = []
    window._reminder_slot = now.strftime('%Y%m%d%H%M')
    store.db.set_trace_callback(queries.append)
    assert window.check_reminder(now) is False
    store.db.set_trace_callback(None)
    assert not queries, queries
    # Pause today, then tomorrow's mark clears itself.
    pause_today(store, today)
    window._reminder_slot = None
    assert window.check_reminder(datetime.combine(today, time(10, 0))) is False
    assert load_state(store)['paused'] == today.isoformat()
    mark_fired(store, today)
    state = load_state(store)
    assert state['last'] == today.isoformat() and 'paused' not in state
    reset_due(store)
    assert load_state(store) == {}
    # Corrupt state is ignored instead of crashing.
    store.put(reminders.STATE_KEY, dict(last=123, paused='not-a-date'))
    assert load_state(store) == {}
    # Preferences wiring: the time spins compose the stored minute value.
    from preferences import PreferencesDialog
    dialog = PreferencesDialog(window)
    dialog.reminder_hour.setValue(7)
    dialog.reminder_minute.setValue(30)
    assert dialog.values['reminder_minutes'] == 7*60 + 30
    dialog.backup_folder.setText('/tmp/backup-target')
    assert dialog.values['backup_folder'] == '/tmp/backup-target'
    dialog.reject()
    window.close()
    store.db.close()

print('PASS: reminder due rules, workday/empty/pause gates, text, preference clamping, once-per-day marks and a zero-SQL throttle')
