"""Entry search: ordering, filters, caps, zero-SQL refresh and jump-to-date."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import tempfile
from datetime import date
from pathlib import Path

from app import QApplication, CalendarApp, Store, configure_style
from entry_search import MAX_RESULTS, SearchDialog, result_label, search_entries
from qt_compat import Qt

app = QApplication([])
configure_style(app)

# Pure search semantics on a synthetic map: ordering, filters, case folding.
days = {
    '2027-01-02': [dict(done=False, period='晚', text='晚间读书'), dict(done=True, period='早', text='晨跑')],
    '2027-01-01': [dict(done=False, period='午', text='读书会'), dict(done=False, period='早', text='REPORT')],
    '2026-12-31': [dict(done=True, period='午', text='年终总结')],
}
assert [item['text'] for item in search_entries(days, '读书')] == ['晚间读书', '读书会']
assert [item['text'] for item in search_entries(days, 'report')] == ['REPORT']
assert [(item['day'], item['period']) for item in search_entries(days, '读书')] == [
    ('2027-01-02', '晚'), ('2027-01-01', '午')]
assert search_entries(days, '') == []
assert [item['text'] for item in search_entries(days, '', only_open=True)] == [
    '晚间读书', 'REPORT', '读书会']
assert [item['text'] for item in search_entries(days, '', period='午')] == ['读书会', '年终总结']
assert [item['text'] for item in search_entries(days, '', period='午', only_open=True)] == ['读书会']
assert search_entries(days, '不存在的词') == []
assert result_label(dict(day='2027-01-01', period='早', text='晨跑', done=True)).endswith('✓')
assert '✓' not in result_label(dict(day='2027-01-01', period='早', text='晨跑', done=False))

# A single day keeps 早/午/晚 order even when the map stores them shuffled.
shuffled = {'2027-03-01': [dict(done=False, period='晚', text='三'), dict(done=False, period='早', text='一'),
                           dict(done=False, period='午', text='二')]}
assert [item['text'] for item in search_entries(shuffled, '', only_open=True)] == ['一', '二', '三']
assert [item['day'] for item in search_entries({'bad-key': [], '2027-03-02': [
    dict(done=False, period='早', text='x')]}, 'x')] == ['2027-03-02']

# Results are capped and keep the newest days.
many = {f'2027-{month:02d}-{day:02d}': [dict(done=False, period='早', text='批量')]
        for month in range(1, 13) for day in range(1, 29)}
assert len(many) > MAX_RESULTS
capped = search_entries(many, '批量')
assert len(capped) == MAX_RESULTS and capped[0]['day'] == '2027-12-28'

with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
    window = CalendarApp(Store(Path(folder) / 'calendar.sqlite3'))
    window.show()
    app.processEvents()
    window.store.put('day:2027-05-01', [dict(done=False, period='早', text='体检预约'),
                                        dict(done=True, period='晚', text='整理照片')])
    window.store.put('day:2027-05-02', [dict(done=False, period='午', text='体检复查')])
    window.reload_entries()

    dialog = SearchDialog(window)
    dialog.show()
    app.processEvents()
    assert dialog.list.count() == 0 and '关键词' in dialog.count.text()
    dialog.input.setText('体检')
    app.processEvents()
    assert dialog.list.count() == 2 and '找到 2 条' in dialog.count.text()
    assert dialog.list.item(0).text().startswith('2027-05-02')
    dialog.open_only.setChecked(True)
    app.processEvents()
    assert dialog.list.count() == 2
    dialog.open_only.setChecked(False)
    dialog.period.setCurrentIndex(dialog.period.findData('晚'))
    app.processEvents()
    assert dialog.list.count() == 0, '整理照片 is done and does not contain 体检'
    dialog.period.setCurrentIndex(0)
    dialog.input.clear()
    dialog.open_only.setChecked(True)
    app.processEvents()
    assert dialog.list.count() == 2

    # Searching must not query SQLite: entries stay in memory.
    queries = []
    window.store.db.set_trace_callback(queries.append)
    dialog.refresh()
    app.processEvents()
    window.store.db.set_trace_callback(None)
    assert not queries, queries

    # Picking a result navigates the calendar to that date and closes the dialog.
    dialog.list.setCurrentRow(0)
    assert dialog.list.currentItem().data(Qt.ItemDataRole.UserRole)['day'] == '2027-05-02'
    dialog.locate()
    assert dialog.result() == dialog.DialogCode.Accepted
    assert window.selected == date(2027, 5, 2)
    assert (window.year, window.month) == (2027, 5)
    assert window.boards[0].month == 5
    assert window.rows[0][2].text() == '体检复查'

    window.close()
    window.store.db.close()

print('PASS: search ordering/filters/case folding, cap, zero-SQL refresh and jump-to-date')
