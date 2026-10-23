"""Portable exchange formats: ICS/CSV export and a merge-only CSV import.

The export is intentionally lossy in a documented way: every entry becomes one
all-day VEVENT, the morning/noon/evening slot stays in the summary prefix, and
the completion flag travels in a private X- property. Import accepts only the
CSV shape this module writes (or the same columns by name), never deletes an
existing entry, and reports every skipped row instead of failing silently.
"""
import csv
import hashlib
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from version import VERSION

PERIODS = ('早', '午', '晚')
MAX_TEXT = 120
MAX_PER_DAY = 6
CSV_HEADER = ('date', 'period', 'text', 'done')
HEADER_ALIASES = {
    'date': ('date', '日期'),
    'period': ('period', '时段', '时间'),
    'text': ('text', '事项', '内容'),
    'done': ('done', '完成', '已完成'),
}
TRUE_WORDS = {'1', 'true', 'yes', 'y', '是', '已完成', '完成'}
FALSE_WORDS = {'', '0', 'false', 'no', 'n', '否', '未完成'}


def _rows(store):
    """Every stored entry as (day, period, text, done), stable-sorted."""
    days = store.load_days()
    result = []
    for iso in sorted(days):
        try:
            day = date.fromisoformat(iso)
        except (TypeError, ValueError):
            continue
        rows = days[iso]
        if not isinstance(rows, list):
            continue
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            text = str(row.get('text', '')).strip()
            period = str(row.get('period', '')).strip()
            if not text or period not in PERIODS:
                continue
            result.append((day, period, text, bool(row.get('done', False)), index))
    result.sort(key=lambda item: (item[0], PERIODS.index(item[1]), item[4]))
    return result


def _ics_escape(text):
    text = str(text).replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,')
    return text.replace('\r\n', '\\n').replace('\n', '\\n').replace('\r', '\\n')


def _fold(line):
    """Split one content line into RFC 5545 physical lines of at most 75 octets.

    Continuation lines begin with one space, so they carry 74 octets of text;
    folding happens per character, never inside a multi-byte UTF-8 sequence.
    """
    encoded = line.encode('utf-8')
    if len(encoded) <= 75:
        return [line]
    lines, current, size, limit = [], '', 0, 75
    for character in line:
        width = len(character.encode('utf-8'))
        if size + width > limit:
            lines.append(current)
            current, size, limit = ' ' + character, 1 + width, 74
            continue
        current += character
        size += width
    if current:
        lines.append(current)
    return lines


def _uid(day, period, text):
    digest = hashlib.sha256(f'{day.isoformat()}|{period}|{text}'.encode('utf-8')).hexdigest()
    return digest[:24] + '@little-calendar'


def export_ics(store, destination):
    """Write one all-day VEVENT per entry; raises ValueError for a non-.ics path."""
    destination = Path(destination)
    if destination.suffix.lower() != '.ics':
        raise ValueError('日历文件名必须以 .ics 结尾')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    lines = ['BEGIN:VCALENDAR', 'VERSION:2.0',
             f'PRODID:-//Little Calendar//Little Calendar {VERSION}//CN',
             'CALSCALE:GREGORIAN']
    for day, period, text, done, _index in _rows(store):
        lines += [
            'BEGIN:VEVENT',
            'UID:' + _uid(day, period, text),
            'DTSTAMP:' + stamp,
            'DTSTART;VALUE=DATE:' + day.strftime('%Y%m%d'),
            'DTEND;VALUE=DATE:' + (day + timedelta(days=1)).strftime('%Y%m%d'),
            'SUMMARY:' + _ics_escape(f'{period} · {text}'),
            'CATEGORIES:小日历',
            'X-LITTLE-CALENDAR-DONE:' + ('TRUE' if done else 'FALSE'),
            'END:VEVENT',
        ]
    lines.append('END:VCALENDAR')
    folded = []
    for line in lines:
        folded.extend(_fold(line))
    destination.write_bytes(('\r\n'.join(folded) + '\r\n').encode('utf-8'))
    return destination


def export_csv(store, destination):
    """Write a UTF-8 (BOM) CSV so spreadsheet tools open Chinese text correctly."""
    destination = Path(destination)
    if destination.suffix.lower() != '.csv':
        raise ValueError('表格文件名必须以 .csv 结尾')
    with destination.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(CSV_HEADER)
        for day, period, text, done, _index in _rows(store):
            writer.writerow([day.isoformat(), period, text, '1' if done else '0'])
    return destination


def _columns(header):
    """Map each logical column to its index, or None when a header is unusable."""
    if not header:
        return None
    cells = [str(cell).strip().casefold() for cell in header]
    mapping = {}
    for key, aliases in HEADER_ALIASES.items():
        for index, cell in enumerate(cells):
            if cell in aliases:
                mapping[key] = index
                break
        else:
            mapping[key] = None
    if mapping['date'] is None or mapping['text'] is None:
        return None
    return mapping


def _done(value):
    word = str(value or '').strip().casefold()
    if word in TRUE_WORDS:
        return True
    if word in FALSE_WORDS:
        return False
    raise ValueError(f'无法识别的完成状态：{value}')


def import_csv(store, path, min_year=None, max_year=None, apply=True):
    """Merge entries from a CSV file; never deletes and never overwrites content.

    ``apply=False`` runs the same validation and returns the same report without
    writing anything, which is how the dialog previews an import first.
    Returns a report: ``added`` (list of [day, period, text]), ``skipped``
    (list of dicts with line/reason) and ``changed_days``.
    """
    path = Path(path)
    if not path.is_file():
        raise ValueError('找不到要导入的文件')
    try:
        stream = path.open('r', encoding='utf-8-sig', newline='')
    except OSError as error:
        raise ValueError(f'无法读取文件：{error}') from error
    added, skipped, changed = [], [], set()
    existing = store.load_days()
    counts = {iso: len(rows) for iso, rows in existing.items() if isinstance(rows, list)}
    seen = set()
    with stream:
        reader = csv.reader(stream)
        first = next(reader, None)
        if first is None:
            raise ValueError('文件是空的')
        mapping = _columns(first)
        if mapping is None:
            # No usable header: treat every row positionally, first row included.
            mapping = {'date': 0, 'period': 1, 'text': 2, 'done': 3}
            rows, first_line = [first] + list(reader), 1
        else:
            rows, first_line = reader, 2
        for line, row in enumerate(rows, start=first_line):
            if not any(str(cell).strip() for cell in row):
                continue
            def cell(key):
                index = mapping.get(key)
                return str(row[index]).strip() if index is not None and index < len(row) else ''
            try:
                day = date.fromisoformat(cell('date'))
            except (TypeError, ValueError):
                skipped.append(dict(line=line, reason='日期不是 YYYY-MM-DD 格式', date=cell('date')))
                continue
            if ((min_year is not None and day.year < min_year) or
                    (max_year is not None and day.year > max_year)):
                skipped.append(dict(line=line, reason=f'日期超出支持范围（{min_year}–{max_year}）', date=cell('date')))
                continue
            period = cell('period')
            if not period:
                period = '午'
            if period not in PERIODS:
                skipped.append(dict(line=line, reason='时段只能是早、午、晚', date=cell('date')))
                continue
            text = cell('text')
            if not text:
                skipped.append(dict(line=line, reason='事项内容为空', date=cell('date')))
                continue
            if len(text) > MAX_TEXT:
                skipped.append(dict(line=line, reason=f'事项超过 {MAX_TEXT} 字', date=cell('date')))
                continue
            try:
                done = _done(cell('done'))
            except ValueError as error:
                skipped.append(dict(line=line, reason=str(error), date=cell('date')))
                continue
            iso = day.isoformat()
            key = (iso, period, text)
            if key in seen:
                skipped.append(dict(line=line, reason='文件内重复', date=iso))
                continue
            seen.add(key)
            current = existing.get(iso, [])
            if not isinstance(current, list):
                current = []
            if any(str(item.get('text', '')).strip() == text and str(item.get('period', '')).strip() == period
                   for item in current if isinstance(item, dict)):
                skipped.append(dict(line=line, reason='这一天已有相同事项', date=iso))
                continue
            if counts.get(iso, 0) >= MAX_PER_DAY:
                skipped.append(dict(line=line, reason=f'该日已满 {MAX_PER_DAY} 条', date=iso))
                continue
            current = current + [dict(done=done, period=period, text=text)]
            existing[iso] = current
            counts[iso] = len(current)
            added.append([iso, period, text])
            changed.add(iso)
    for iso in sorted(changed):
        if apply:
            store.put('day:' + iso, existing[iso])
    return dict(added=added, skipped=skipped, changed_days=sorted(changed))
