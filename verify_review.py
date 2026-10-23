"""Review statistics: totals, streaks, the heatmap window and malformed input."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import tempfile
from datetime import date
from pathlib import Path

import review
from app import QApplication, CalendarApp, Store, configure_style

today = date(2026, 10, 23)
days = {
    '2026-10-21': [dict(done=True, period='早', text='a')],
    '2026-10-22': [dict(done=True, period='早', text='b'), dict(done=True, period='晚', text='c')],
    '2026-10-23': [dict(done=True, period='午', text='d')],
    '2026-10-05': [dict(done=False, period='早', text='e')],
    '2026-10-02': [dict(done=True, period='早', text='f'), dict(done=False, period='晚', text='g')],
    '2026-09-30': [dict(done=True, period='午', text='h')],
    '2026-10-10': [dict(done=True, period='早', text='i')],
    '2026-10-11': [dict(done=True, period='早', text='j')],
    '2026-10-12': [dict(done=True, period='早', text='k')],
    '2025-12-01': [dict(done=True, period='早', text='l')],
    'not-a-date': [dict(done=True, period='早', text='bad-key')],
    '2026-10-15': 'not a list',
    '2026-10-16': [dict(done=True, period='早', text=''), 'junk', dict(done=True, period='早')],
}

month = review.month_summary(days, today)
assert month == dict(days=23, with_entries=8, entries=10, done=8, open=2, ratio=0.8), month
year = review.year_summary(days, today)
assert year['days'] == 296 and year['with_entries'] == 9 and year['entries'] == 11 and year['done'] == 9, year
assert review.percent(year['ratio']) == '82%'
assert review.percent(month['ratio']) == '80%'

streaks = review.streaks(days, today)
assert streaks == dict(current=3, longest=3), streaks
assert review.day_complete(days, date(2026, 10, 22)) is True
assert review.day_complete(days, date(2026, 10, 2)) is False
assert review.day_complete(days, date(2026, 10, 1)) is False, 'no entries is not complete'

heatmap = review.monthly_heatmap(days, today)
assert len(heatmap) == 12
assert (heatmap[0]['year'], heatmap[0]['month']) == (2025, 11)
assert (heatmap[-1]['year'], heatmap[-1]['month']) == (2026, 10)
assert heatmap[-1]['entries'] == 10 and heatmap[-1]['done'] == 8, 'current month counts elapsed days'
assert heatmap[0]['entries'] == 0 and heatmap[0]['ratio'] == 0.0
september = next(item for item in heatmap if item['month'] == 9 and item['year'] == 2026)
assert september['entries'] == 1 and september['done'] == 1

periods = review.period_counts(days, today)
assert periods['早'] == dict(entries=7, done=6), periods['早']
assert periods['午'] == dict(entries=2, done=2)
assert periods['晚'] == dict(entries=2, done=1)

assert review.entries_on({'2026-10-23': [dict(done=False, period='早', text=' '), 'x', None]}, today) == []
assert review.collect({}, today)['month'] == dict(days=23, with_entries=0, entries=0, done=0, open=0, ratio=0.0)
assert review.streaks({}, today) == dict(current=0, longest=0)

app = QApplication([])
configure_style(app)
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
    window = CalendarApp(Store(Path(folder) / 'calendar.sqlite3'))
    window.show()
    app.processEvents()
    window.store.put('day:' + date.today().isoformat(),
                     [dict(done=True, period='早', text='完成的事'), dict(done=False, period='晚', text='未完成的事')])
    window.reload_entries()
    from review_ui import ReviewDialog
    dialog = ReviewDialog(window)
    dialog.show()
    app.processEvents()
    assert dialog.data['month']['entries'] == 2 and dialog.data['month']['done'] == 1
    assert '本月' in dialog.summary.text() and '连续完成' in dialog.summary.text()
    assert not dialog.grab().isNull()
    queries = []
    window.store.db.set_trace_callback(queries.append)
    dialog.refresh()
    app.processEvents()
    window.store.db.set_trace_callback(None)
    assert not queries, 'review must read the in-memory day map only'
    dialog.close()
    window.close()
    window.store.db.close()

print('PASS: review month/year totals, strict streaks, 12-month heatmap window, slot counts, malformed input and zero-SQL rendering')
