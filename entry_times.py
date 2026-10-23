"""Optional per-entry reminder times: strict HH:MM parsing and due matching.

The time is an extra, optional field on a day entry (``time``). Entries without
it keep behaving exactly as before, so old data needs no migration. "Due" means
"at or before now and not yet fired today", which also covers reminders missed
while the application was closed.
"""
import re
from datetime import date

TIME_RE = re.compile(r'^([01]?\d|2[0-3])\s*[:：]\s*([0-5]\d)$')


def parse(value):
    """Return canonical 'HH:MM' or None; anything else is not a reminder."""
    if not isinstance(value, str):
        return None
    match = TIME_RE.match(value.strip())
    if not match:
        return None
    return f'{int(match.group(1)):02d}:{match.group(2)}'


def row_key(day, time_value, period, text):
    return f'{day.isoformat()}|{time_value}|{period}|{text}'


def scheduled(day_entries, day):
    """Entries of one day that carry a valid time, ordered by that time."""
    rows = day_entries.get(day.isoformat(), []) if isinstance(day_entries, dict) else []
    result = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        text = str(row.get('text', '')).strip()
        time_value = parse(row.get('time'))
        if not text or not time_value:
            continue
        result.append(dict(key=row_key(day, time_value, str(row.get('period', '')), text),
                           time=time_value, period=str(row.get('period', '')), text=text))
    result.sort(key=lambda item: item['time'])
    return result


def pending(day_entries, day, now, fired=(), limit=8):
    """Entries whose time has arrived and that were not fired yet today."""
    done = set(item for item in fired if isinstance(item, str)) if fired else set()
    minute = now.strftime('%H:%M')
    result = [item for item in scheduled(day_entries, day)
              if item['time'] <= minute and item['key'] not in done]
    return result[:limit]


def message(items):
    """One combined notification for everything due in this check."""
    if not items:
        return '', ''
    first = items[0]
    if len(items) == 1:
        return f"{first['time']} {first['text']}", f"{first['period']} · {first['text']}"
    shown = '；'.join(f"{item['time']} {item['text']}" for item in items[:3])
    more = f' 等 {len(items)} 项' if len(items) > 3 else ''
    return f'有 {len(items)} 个定时提醒', shown + more


def prune(fired, day, limit=200):
    """Keep only today's keys so the state file cannot grow without bound."""
    prefix = day.isoformat() + '|'
    kept = [item for item in fired if isinstance(item, str) and item.startswith(prefix)]
    return kept[-limit:]


def apply_times(store, day, entries):
    """Write validated times back onto a day's entries, preserving their order."""
    rows = []
    for entry in entries:
        text = str(entry.get('text', '')).strip()
        if not text:
            continue
        row = dict(done=bool(entry.get('done')), period=str(entry.get('period', '')),
                   text=text)
        time_value = parse(entry.get('time'))
        if time_value:
            row['time'] = time_value
        rows.append(row)
    store.put('day:' + day.isoformat(), rows)
    return rows


__all__ = ['parse', 'row_key', 'scheduled', 'pending', 'message', 'prune', 'apply_times', 'date']
