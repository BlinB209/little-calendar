"""Daily reminder scheduling and message text; no Qt, so every rule is testable.

Settings live in ``customization:v1`` (``reminder_*`` keys, normalized by
preferences.py). Only the fired/paused marks live in ``reminder:v1``: losing
that state must never lose user data, so a bad value just means "not fired".
"""
from datetime import date, datetime

STATE_KEY = 'reminder:v1'


def minutes(settings):
    value = settings.get('reminder_minutes', 20 * 60)
    try:
        return max(0, min(1439, int(value)))
    except (TypeError, ValueError):
        return 20 * 60


def label(value):
    return '%02d:%02d' % (value // 60, value % 60)


def is_workday(day):
    return day.weekday() < 5


def open_entries(day_entries, today):
    rows = day_entries.get(today.isoformat(), [])
    result = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        text = str(row.get('text', '')).strip()
        if text and not row.get('done'):
            result.append(dict(period=str(row.get('period', '')), text=text))
    return result


def summary(day_entries, today, limit=4):
    """Return (open count, '早 · 读书；晚 · 散步 等 6 件') for the notification body."""
    rows = open_entries(day_entries, today)
    shown = [f"{row['period']} · {row['text']}" for row in rows[:limit]]
    text = '；'.join(shown)
    if len(rows) > limit:
        text += f' 等 {len(rows)} 件'
    return len(rows), text


def due(settings, state, now, has_open):
    """One reminder per local day, at or after the chosen minute."""
    if not settings.get('reminder_enabled'):
        return False
    day = now.date().isoformat()
    if not isinstance(state, dict):
        state = {}
    if state.get('last') == day or state.get('paused') == day:
        return False
    if settings.get('reminder_weekdays_only') and not is_workday(now.date()):
        return False
    if not has_open and settings.get('reminder_skip_empty', True):
        return False
    return now.hour * 60 + now.minute >= minutes(settings)


def message(day_entries, today):
    count, text = summary(day_entries, today)
    if count:
        title = f'今天还有 {count} 件未完成'
        return title, text
    return '今天没有未完成的事项', ''


def load_state(store):
    value = store.get(STATE_KEY, {})
    if not isinstance(value, dict):
        return {}
    state = {}
    for key in ('last', 'paused'):
        item = value.get(key)
        if isinstance(item, str):
            try:
                date.fromisoformat(item)
            except ValueError:
                continue
            state[key] = item
    return state


def save_state(store, state):
    store.put(STATE_KEY, dict(state or {}))


def mark_fired(store, day=None):
    state = load_state(store)
    state['last'] = (day or date.today()).isoformat()
    state.pop('paused', None)
    save_state(store, state)


def pause_today(store, day=None):
    state = load_state(store)
    state['paused'] = (day or date.today()).isoformat()
    save_state(store, state)


def reset_due(store):
    """Forget today's marks so the next check may fire again (settings change)."""
    state = load_state(store)
    state.pop('last', None)
    state.pop('paused', None)
    save_state(store, state)
