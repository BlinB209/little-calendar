"""Review statistics over the in-memory day map; no Qt and no SQL.

A day counts as "complete" only when it has at least one entry and every entry
is checked. Empty or incomplete days break a streak: the number is meant to
describe the calendar, not to flatter it.
"""
from datetime import date, timedelta

PERIODS = ('早', '午', '晚')
HEATMAP_MONTHS = 12


def entries_on(day_entries, day):
    rows = day_entries.get(day.isoformat(), []) if isinstance(day_entries, dict) else []
    result = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        text = str(row.get('text', '')).strip()
        if text:
            result.append(dict(done=bool(row.get('done')), period=str(row.get('period', ''))))
    return result


def day_complete(day_entries, day):
    rows = entries_on(day_entries, day)
    return bool(rows) and all(row['done'] for row in rows)


def _span(day_entries, start, end):
    days = entries = done = with_entries = 0
    cursor = start
    while cursor <= end:
        rows = entries_on(day_entries, cursor)
        days += 1
        if rows:
            with_entries += 1
        entries += len(rows)
        done += sum(1 for row in rows if row['done'])
        cursor += timedelta(days=1)
    return dict(days=days, with_entries=with_entries, entries=entries, done=done,
                open=entries - done, ratio=(done / entries) if entries else 0.0)


def month_summary(day_entries, today):
    return _span(day_entries, today.replace(day=1), today)


def year_summary(day_entries, today):
    return _span(day_entries, date(today.year, 1, 1), today)


def streaks(day_entries, today):
    """Current streak counts back from today (or yesterday), longest scans all data."""
    current, cursor = 0, today
    if not day_complete(day_entries, cursor):
        cursor = today - timedelta(days=1)
    while day_complete(day_entries, cursor):
        current += 1
        cursor -= timedelta(days=1)
    days = []
    for key in day_entries:
        try:
            days.append(date.fromisoformat(key))
        except (TypeError, ValueError):
            continue
    longest = run = 0
    previous = None
    for day in sorted(set(days)):
        if not day_complete(day_entries, day):
            run = 0
            previous = day
            continue
        run = run + 1 if previous == day - timedelta(days=1) else 1
        longest = max(longest, run)
        previous = day
    return dict(current=current, longest=longest)


def _month_end(start):
    return (start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)


def monthly_heatmap(day_entries, today, months=HEATMAP_MONTHS):
    """The last `months` months, oldest first; the current month counts elapsed days only."""
    starts = []
    for back in range(months - 1, -1, -1):
        serial = today.year * 12 + (today.month - 1) - back
        starts.append(date(serial // 12, serial % 12 + 1, 1))
    result = []
    for start in starts:
        end = min(_month_end(start), today)
        span = _span(day_entries, start, end)
        result.append(dict(year=start.year, month=start.month, **span))
    return result


def period_counts(day_entries, today):
    """Year-to-date counts per morning/noon/evening slot, unknown slots ignored."""
    counts = {name: dict(entries=0, done=0) for name in PERIODS}
    cursor = date(today.year, 1, 1)
    while cursor <= today:
        for row in entries_on(day_entries, cursor):
            if row['period'] in counts:
                counts[row['period']]['entries'] += 1
                counts[row['period']]['done'] += 1 if row['done'] else 0
        cursor += timedelta(days=1)
    return counts


def collect(day_entries, today):
    return dict(today=today.isoformat(), month=month_summary(day_entries, today),
                year=year_summary(day_entries, today), streaks=streaks(day_entries, today),
                heatmap=monthly_heatmap(day_entries, today), periods=period_counts(day_entries, today))


def percent(value):
    return f'{round(value * 100)}%'
