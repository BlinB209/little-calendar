"""Saved entry snippets: normalized storage and merge-only insertion into a day."""
PERIODS = ('早', '午', '晚')
KEY = 'templates:v1'
LIMIT = 30
MAX_TEXT = 120
MAX_PER_DAY = 6


def normalize(values):
    result = []
    for item in values if isinstance(values, list) else []:
        if isinstance(item, dict):
            text, period = str(item.get('text', '')).strip(), str(item.get('period', '')).strip()
        elif isinstance(item, str):
            text, period = item.strip(), ''
        else:
            continue
        if not text or len(text) > MAX_TEXT:
            continue
        entry = dict(text=text, period=period if period in PERIODS else '午')
        if entry not in result:
            result.append(entry)
        if len(result) >= LIMIT:
            break
    return result


def load(store):
    return normalize(store.get(KEY, []))


def save(store, values):
    cleaned = normalize(values)
    store.put(KEY, cleaned)
    return cleaned


def add(store, text, period):
    """Append one template, replacing an identical one instead of duplicating it."""
    entry = dict(text=str(text).strip(), period=period if period in PERIODS else '午')
    if not entry['text'] or len(entry['text']) > MAX_TEXT:
        raise ValueError(f'模板内容需为 1–{MAX_TEXT} 字')
    values = [item for item in load(store) if item != entry]
    values.append(entry)
    return save(store, values)


def remove(store, index):
    values = load(store)
    if not 0 <= index < len(values):
        raise ValueError('模板不存在')
    del values[index]
    return save(store, values)


def insert(store, day_entries, day, template):
    """Append a template to one day; returns (rows, error). Never overwrites."""
    text = str(template.get('text', '')).strip()
    period = template.get('period') if template.get('period') in PERIODS else '午'
    if not text:
        return [], '模板内容为空'
    rows = day_entries.get(day.isoformat(), []) if isinstance(day_entries, dict) else []
    existing = [dict(done=bool(row.get('done')), period=str(row.get('period', '')), text=str(row.get('text', '')).strip())
                for row in rows if isinstance(row, dict) and str(row.get('text', '')).strip()]
    if any(row['text'] == text and row['period'] == period for row in existing):
        return existing, '这一天已有相同事项'
    if len(existing) >= MAX_PER_DAY:
        return existing, f'这一天已满 {MAX_PER_DAY} 条'
    updated = existing + [dict(done=False, period=period, text=text)]
    store.put('day:' + day.isoformat(), updated)
    return updated, None
