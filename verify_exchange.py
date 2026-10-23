"""ICS/CSV exchange checks: folding, escaping, ordering, merge-only import, refusals."""
import csv
import tempfile
from datetime import date
from pathlib import Path

from app import Store
from exchange import export_ics, export_csv, import_csv

PERIOD_ORDER = {'早': 0, '午': 1, '晚': 2}
LONG_TEXT = '这是一条很长的中文事项' * 6
SPECIAL_TEXT = '包含,逗号;分号\\反斜杠与"引号"'
SOURCE = {
    '2028-02-29': [dict(done=False, period='早', text='闰日读书'), dict(done=True, period='晚', text=LONG_TEXT)],
    '2027-12-31': [dict(done=True, period='午', text=SPECIAL_TEXT)],
    '2028-01-01': [dict(done=False, period='早', text='新年计划'), dict(done=False, period='午', text='午餐'), dict(done=True, period='晚', text='看烟花')],
}


def unfold(data):
    lines, out = data.decode('utf-8').split('\r\n'), []
    for line in lines:
        if line.startswith(' ') and out:
            out[-1] += line[1:]
        elif line:
            out.append(line)
    return out


def unescape(value):
    out, index = '', 0
    while index < len(value):
        if value[index] == '\\' and index + 1 < len(value):
            out += '\n' if value[index + 1] == 'n' else value[index + 1]
            index += 2
            continue
        out += value[index]
        index += 1
    return out


def parse_ics(data):
    events, current = [], None
    for line in unfold(data):
        if line == 'BEGIN:VEVENT':
            current = {}
        elif line == 'END:VEVENT':
            events.append(current)
            current = None
        elif current is not None and ':' in line:
            name, value = line.split(':', 1)
            current[name.split(';', 1)[0]] = value
    return events


def write_csv(path, rows):
    with path.open('w', encoding='utf-8', newline='') as stream:
        csv.writer(stream).writerows(rows)


with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
    root = Path(folder)
    store = Store(root / 'calendar.sqlite3')
    total = sum(len(rows) for rows in SOURCE.values())
    for iso, rows in SOURCE.items():
        store.put('day:' + iso, rows)

    ics = export_ics(store, root / '全部事项.ics')
    csv_path = export_csv(store, root / '全部事项.csv')

    # --- ICS: CRLF only, 75-octet folding that never splits a character, escapes.
    data = ics.read_bytes()
    assert data.startswith(b'BEGIN:VCALENDAR\r\n'), 'ICS must start with a CRLF-terminated header'
    assert data.endswith(b'\r\n'), 'ICS must end with CRLF'
    assert data.count(b'\n') == data.count(b'\r\n'), 'bare LF found in ICS'
    physical = data.split(b'\r\n')[:-1]
    assert physical, 'empty ICS'
    assert all(len(line) <= 75 for line in physical), 'a physical line exceeds 75 octets'
    assert all(line.decode('utf-8') for line in physical), 'folding split a UTF-8 character'
    assert sum(line == b'BEGIN:VEVENT' for line in physical) == total
    assert sum(line == b'END:VEVENT' for line in physical) == total
    assert data.count(b'\r\n ') > 0, 'long Chinese summary should be folded'
    assert any(b'\\,' in line for line in physical), 'comma must be escaped'
    assert any(b'\\;' in line for line in physical), 'semicolon must be escaped'
    assert any(b'\\\\' in line for line in physical), 'backslash must be escaped'

    events = parse_ics(data)
    assert len(events) == total
    parsed = {}
    for event in events:
        day = date(int(event['DTSTART'][0:4]), int(event['DTSTART'][4:6]), int(event['DTSTART'][6:8]))
        summary = unescape(event['SUMMARY'])
        period, _, text = summary.partition(' · ')
        done = event['X-LITTLE-CALENDAR-DONE'] == 'TRUE'
        parsed[(day.isoformat(), period, text)] = done
        assert event['UID'].endswith('@little-calendar')
    expected = {(iso, row['period'], row['text']): bool(row['done'])
                for iso, rows in SOURCE.items() for row in rows}
    assert parsed == expected, 'ICS round trip mismatch'
    # The all-day event must end on the following calendar day, including leap day.
    leap = next(event for event in events if event['DTSTART'] == '20280229')
    assert leap['DTEND'] == '20280301', leap['DTEND']
    year_end = next(event for event in events if event['DTSTART'] == '20271231')
    assert year_end['DTEND'] == '20280101'

    # Stable UIDs: exporting twice keeps the same identifiers.
    again = parse_ics(export_ics(store, root / 'second.ics').read_bytes())
    assert [event['UID'] for event in again] == [event['UID'] for event in events]
    assert len({event['UID'] for event in events}) == total, 'UID must be unique per entry'

    # --- CSV: BOM for spreadsheets, stable header and ordering.
    raw = csv_path.read_bytes()
    assert raw.startswith(b'\xef\xbb\xbf'), 'CSV should carry a UTF-8 BOM'
    with csv_path.open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.reader(stream))
    assert rows[0] == ['date', 'period', 'text', 'done']
    assert len(rows) == total + 1
    body = rows[1:]
    assert [row[0] for row in body] == sorted(row[0] for row in body), 'dates must be ascending'
    by_day = {}
    for row in body:
        by_day.setdefault(row[0], []).append(PERIOD_ORDER[row[1]])
    assert all(values == sorted(values) for values in by_day.values()), 'periods must follow 早/午/晚'
    assert [row[2] for row in body if row[1] == '晚'] == ['看烟花', LONG_TEXT]
    assert body[0][3] in ('0', '1')

    # --- Import: merge-only, reports every refusal, never touches other keys.
    target = Store(root / 'target.sqlite3')
    target.put('night_mode', True)
    report = import_csv(target, csv_path, min_year=2016, max_year=2036)
    assert len(report['added']) == total, report
    assert report['skipped'] == [], report['skipped']
    assert target.get('night_mode', None) is True
    for iso, rows in SOURCE.items():
        assert target.get('day:' + iso, []) == [dict(done=row['done'], period=row['period'], text=row['text'])
                                                for row in rows], iso
    assert import_csv(target, csv_path, min_year=2016, max_year=2036)['added'] == []
    repeated = import_csv(target, csv_path, min_year=2016, max_year=2036)
    assert all('已有相同事项' in item['reason'] for item in repeated['skipped']), repeated['skipped']

    # A day that is already full refuses new rows instead of dropping data.
    full = '2028-04-01'
    target.put('day:' + full, [dict(done=False, period=period, text=f'已满{i}') for i, period in enumerate(['早', '午', '晚', '早', '午', '晚'])])
    full_csv = root / 'full.csv'
    write_csv(full_csv, [['date', 'period', 'text', 'done'], [full, '早', '再来一条', '0']])
    full_report = import_csv(target, full_csv, min_year=2016, max_year=2036)
    assert full_report['added'] == []
    assert full_report['skipped'][0]['reason'] == '该日已满 6 条', full_report
    assert len(target.get('day:' + full, [])) == 6

    # A preview runs the same validation but writes nothing.
    preview_store = Store(root / 'preview.sqlite3')
    preview = import_csv(preview_store, csv_path, min_year=2016, max_year=2036, apply=False)
    assert len(preview['added']) == total and preview['skipped'] == []
    assert preview_store.load_days() == {}

    # --- Refusals: bad date, bad period, empty/oversized text, out-of-range year.
    bad = root / 'bad.csv'
    write_csv(bad, [
        ['date', 'period', 'text', 'done'],
        ['2028-05-01', '早', '正常事项', '1'],
        ['not-a-date', '早', '坏日期', '0'],
        ['2028-05-02', '夜', '坏时段', '0'],
        ['2028-05-03', '早', '', '0'],
        ['2028-05-04', '早', '长' * 121, '0'],
        ['1990-01-01', '早', '太早', '0'],
        ['2028-05-05', '早', '重复键', '0'],
        ['2028-05-05', '早', '重复键', '0'],
    ])
    fresh = Store(root / 'fresh.sqlite3')
    bad_report = import_csv(fresh, bad, min_year=2016, max_year=2036)
    assert bad_report['added'] == [['2028-05-01', '早', '正常事项'], ['2028-05-05', '早', '重复键']], bad_report
    reasons = [item['reason'] for item in bad_report['skipped']]
    assert reasons == ['日期不是 YYYY-MM-DD 格式', '时段只能是早、午、晚', '事项内容为空',
                       '事项超过 120 字', '日期超出支持范围（2016–2036）', '文件内重复'], reasons
    assert fresh.get('day:not-a-date', None) is None
    assert len(fresh.get('day:2028-05-04', [])) == 0

    # Headerless positional rows and the Chinese header both work; done words are tolerant.
    positional = root / 'positional.csv'
    write_csv(positional, [['2028-06-01', '午', '无表头', '0'], ['2028-06-02', '晚', '无表头2', 'true']])
    chinese = root / 'chinese.csv'
    write_csv(chinese, [['日期', '时段', '事项', '完成'], ['2028-06-03', '早', '中文表头', '是']])
    fresh2 = Store(root / 'fresh2.sqlite3')
    assert import_csv(fresh2, positional)['added'] == [['2028-06-01', '午', '无表头'], ['2028-06-02', '晚', '无表头2']]
    assert fresh2.get('day:2028-06-02', [])[0]['done'] is True
    assert import_csv(fresh2, chinese)['added'] == [['2028-06-03', '早', '中文表头']]
    assert fresh2.get('day:2028-06-03', [])[0]['done'] is True

    # Empty files and wrong extensions fail loudly.
    empty = root / 'empty.csv'
    empty.write_text('', encoding='utf-8')
    for call, argument in ((lambda: import_csv(fresh2, empty), '空文件'),
                           (lambda: import_csv(fresh2, root / 'missing.csv'), '缺失文件'),
                           (lambda: export_ics(store, root / 'wrong.txt'), 'ics 扩展名'),
                           (lambda: export_csv(store, root / 'wrong.csv.txt'), 'csv 扩展名')):
        try:
            call()
        except ValueError:
            pass
        else:
            raise AssertionError(argument)

    # An existing entry keeps its own position and done flag; new rows append.
    mixed = Store(root / 'mixed.sqlite3')
    mixed.put('day:2028-07-01', [dict(done=True, period='早', text='原有'), dict(done=False, period='午', text='原有二')])
    merge_csv = root / 'merge.csv'
    write_csv(merge_csv, [['date', 'period', 'text', 'done'],
                          ['2028-07-01', '早', '原有', '0'],
                          ['2028-07-01', '晚', '新增', '1']])
    mixed_report = import_csv(mixed, merge_csv)
    assert mixed_report['added'] == [['2028-07-01', '晚', '新增']]
    assert mixed.get('day:2028-07-01', []) == [
        dict(done=True, period='早', text='原有'),
        dict(done=False, period='午', text='原有二'),
        dict(done=True, period='晚', text='新增')]
    assert mixed_report['changed_days'] == ['2028-07-01']

    store.db.close()
    target.db.close()
    fresh.db.close()
    fresh2.db.close()
    mixed.db.close()
    preview_store.db.close()

    # --- The dialog path: confirm -> recovery backup -> merge -> window refresh.
    import os
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    from datetime import date
    from unittest.mock import patch
    from app import QApplication, CalendarApp, Store as UiStore, configure_style
    from qt_compat import QMessageBox
    from exchange_ui import ExchangeDialog

    ui_app = QApplication.instance() or QApplication([])
    configure_style(ui_app)
    window = CalendarApp(UiStore(root / 'ui.sqlite3'))
    window.show()
    ui_app.processEvents()
    chosen = date.today().isoformat()
    dialog = ExchangeDialog(window)
    dialog.show()
    ui_csv = root / 'ui.csv'
    write_csv(ui_csv, [['date', 'period', 'text', 'done'], [chosen, '午', '从表格导入', '0']])
    with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes):
        dialog.import_path(ui_csv)
    assert window.store.get('day:' + chosen, []) == [dict(done=False, period='午', text='从表格导入')]
    assert window.rows[0][2].text() == '从表格导入', 'the open window should reload after an import'
    assert window.day_entries[chosen][0]['text'] == '从表格导入'
    assert '已导入 1 条' in dialog.status.text()
    recoveries = sorted(root.glob('recovery-*.zip'))
    assert len(recoveries) == 1, 'a confirmed import must back up the previous data first'
    # Re-importing the same rows only previews: no second backup, no write.
    with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes):
        dialog.import_path(ui_csv)
    assert len(sorted(root.glob('recovery-*.zip'))) == 1
    assert window.store.get('day:' + chosen, []) == [dict(done=False, period='午', text='从表格导入')]
    # Cancelling the confirmation changes nothing.
    cancel_csv = root / 'cancel.csv'
    write_csv(cancel_csv, [['date', 'period', 'text', 'done'], [chosen, '晚', '不应写入', '0']])
    with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Cancel):
        dialog.import_path(cancel_csv)
    assert window.store.get('day:' + chosen, []) == [dict(done=False, period='午', text='从表格导入')]
    dialog.close()
    window.close()
    window.store.db.close()

print('PASS: ICS folding/escaping/CRLF and round trip, CSV BOM/order, merge-only import, day cap, idempotence, every refusal, and the dialog preview/backup/cancel path')
