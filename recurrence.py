"""One-off batch insertion of a template across repeated dates.

Rules are evaluated only when the user asks; nothing is scheduled or auto-filled
later, so a "repeat" never writes to the calendar behind the user's back.
"""
from datetime import date, timedelta

import templates

MAX_TIMES = 52
KINDS = ('daily', 'weekly', 'monthly')


def _next_month(year, month, day):
    while True:
        month += 1
        if month > 12:
            year, month = year + 1, 1
        if year > 9000:
            return None
        try:
            return date(year, month, day)
        except ValueError:
            continue


def dates(kind, start, times, min_date=None, max_date=None):
    """Target dates for one rule, oldest first, bounded by the app's year range."""
    times = max(1, min(MAX_TIMES, int(times)))
    result = []
    if kind == 'daily':
        cursor = start
        for _index in range(times):
            result.append(cursor)
            cursor += timedelta(days=1)
    elif kind == 'weekly':
        cursor = start
        for _index in range(times):
            result.append(cursor)
            cursor += timedelta(weeks=1)
    elif kind == 'monthly':
        cursor = start
        for _index in range(times):
            result.append(cursor)
            cursor = _next_month(cursor.year, cursor.month, cursor.day)
            if cursor is None:
                break
    else:
        raise ValueError('不支持的重复方式')
    if min_date is not None:
        result = [day for day in result if day >= min_date]
    if max_date is not None:
        result = [day for day in result if day <= max_date]
    return result


def apply(store, day_entries, target_dates, template):
    """Insert a template into each date; duplicates and full days are reported."""
    entries = dict(day_entries) if isinstance(day_entries, dict) else {}
    added, skipped = [], []
    for day in target_dates:
        _rows, error = templates.insert(store, entries, day, template)
        if error:
            skipped.append(dict(day=day.isoformat(), reason=error))
            continue
        added.append(day.isoformat())
        entries[day.isoformat()] = store.get('day:' + day.isoformat(), [])
    return dict(added=added, skipped=skipped)


def summary(report):
    added, skipped = len(report['added']), len(report['skipped'])
    if not added and not skipped:
        return '没有可写入的日期。'
    text = f'已写入 {added} 天。'
    if skipped:
        reasons = {}
        for item in report['skipped']:
            reasons[item['reason']] = reasons.get(item['reason'], 0) + 1
        detail = '、'.join(f'{reason} ×{count}' for reason, count in reasons.items())
        text += f' 跳过 {skipped} 天：{detail}。'
    return text
