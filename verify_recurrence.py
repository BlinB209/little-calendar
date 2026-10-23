"""Recurring batch insertion: rule dates, bounds, merge-only apply and the dialog."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import tempfile
from datetime import date
from pathlib import Path

import recurrence
import templates
from app import QApplication, CalendarApp, Store, configure_style

assert recurrence.dates('daily', date(2026, 10, 23), 3) == [
    date(2026, 10, 23), date(2026, 10, 24), date(2026, 10, 25)]
assert recurrence.dates('weekly', date(2026, 10, 23), 3) == [
    date(2026, 10, 23), date(2026, 10, 30), date(2026, 11, 6)]
assert recurrence.dates('monthly', date(2026, 1, 31), 4) == [
    date(2026, 1, 31), date(2026, 3, 31), date(2026, 5, 31), date(2026, 7, 31)], 'short months are skipped'
assert recurrence.dates('monthly', date(2028, 1, 29), 3) == [
    date(2028, 1, 29), date(2028, 2, 29), date(2028, 3, 29)], 'leap day works'
assert recurrence.dates('daily', date(2026, 10, 23), 0) == [date(2026, 10, 23)]
assert len(recurrence.dates('daily', date(2026, 10, 23), 999)) == recurrence.MAX_TIMES
assert recurrence.dates('daily', date(2026, 10, 1), 5, min_date=date(2026, 10, 3)) == [
    date(2026, 10, 3), date(2026, 10, 4), date(2026, 10, 5)]
assert recurrence.dates('daily', date(2026, 10, 30), 5, max_date=date(2026, 10, 31)) == [
    date(2026, 10, 30), date(2026, 10, 31)]
try:
    recurrence.dates('yearly', date(2026, 10, 23), 3)
except ValueError:
    pass
else:
    raise AssertionError('unknown rule accepted')

app = QApplication([])
configure_style(app)
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
    store = Store(Path(folder) / 'calendar.sqlite3')
    template = dict(text='晨跑', period='早')
    days = [date(2026, 11, 2), date(2026, 11, 3), date(2026, 11, 4)]
    store.put('day:2026-11-03', [dict(done=False, period='早', text='晨跑')])
    store.put('day:2026-11-04', [dict(done=False, period='早', text=f'满{index}') for index in range(6)])
    report = recurrence.apply(store, store.load_days(), days, template)
    assert report['added'] == ['2026-11-02'], report
    assert [item['day'] for item in report['skipped']] == ['2026-11-03', '2026-11-04']
    assert [item['reason'] for item in report['skipped']] == ['这一天已有相同事项', '这一天已满 6 条']
    assert store.get('day:2026-11-02', []) == [dict(done=False, period='早', text='晨跑')]
    assert '已写入 1 天' in recurrence.summary(report) and '跳过 2 天' in recurrence.summary(report)
    # Re-applying only reports duplicates: the operation is idempotent.
    again = recurrence.apply(store, store.load_days(), days, template)
    assert again['added'] == [] and len(again['skipped']) == 3
    assert recurrence.summary(dict(added=[], skipped=[])) == '没有可写入的日期。'

    window = CalendarApp(Store(Path(folder) / 'ui.sqlite3'))
    window.show()
    app.processEvents()
    window.select(date(2027, 3, 1))
    templates.add(window.store, '晨跑', '早')
    from recurrence_ui import RepeatDialog
    dialog = RepeatDialog(window, dict(text='晨跑', period='早'))
    dialog.show()
    app.processEvents()
    dialog.kind.setCurrentIndex(dialog.kind.findData('weekly'))
    dialog.times.setValue(3)
    assert dialog.target_dates() == [date(2027, 3, 1), date(2027, 3, 8), date(2027, 3, 15)]
    assert '写入 3 天' in dialog.preview.text()
    dialog.save()
    assert dialog.result() == dialog.DialogCode.Accepted
    assert dialog.report['added'] == ['2027-03-01', '2027-03-08', '2027-03-15']
    for iso in dialog.report['added']:
        assert window.store.get('day:' + iso, []) == [dict(done=False, period='早', text='晨跑')]
    assert window.day_entries['2027-03-01'][0]['text'] == '晨跑', 'the open window reloads after insertion'
    dialog.close()

    # Monthly preview and the empty-range guard.
    dialog = RepeatDialog(window, dict(text='交房租', period='午'))
    dialog.kind.setCurrentIndex(dialog.kind.findData('monthly'))
    dialog.times.setValue(2)
    assert len(dialog.target_dates()) == 2
    dialog.close()
    window.close()
    window.store.db.close()

print('PASS: daily/weekly/monthly rule dates, short-month and leap handling, bounds, idempotent apply, refusals and the repeat dialog')
