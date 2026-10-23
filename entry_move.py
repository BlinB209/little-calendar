"""Move or copy day entries between dates; merge-only and capacity checked."""
from datetime import date

import templates

MAX_PER_DAY = templates.MAX_PER_DAY


def rows_of(day_entries, day):
    rows = day_entries.get(day.isoformat(), []) if isinstance(day_entries, dict) else []
    result = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        text = str(row.get('text', '')).strip()
        if not text:
            continue
        entry = dict(done=bool(row.get('done')), period=str(row.get('period', '')), text=text)
        time_value = str(row.get('time', '')).strip()
        if time_value:
            entry['time'] = time_value
        result.append(entry)
    return result


def transfer(store, day_entries, source, target, index=None, mode='move'):
    """Move/copy one entry (index) or all of them; returns moved/skipped/error."""
    if mode not in ('move', 'copy'):
        raise ValueError('不支持的操作')
    if source == target:
        return dict(moved=[], skipped=[], error='目标日期与来源是同一天')
    rows = rows_of(day_entries, source)
    if not rows:
        return dict(moved=[], skipped=[], error='这一天没有事项')
    indices = list(range(len(rows))) if index is None else [index]
    if any(not isinstance(item, int) or isinstance(item, bool) or not 0 <= item < len(rows) for item in indices):
        return dict(moved=[], skipped=[], error='要移动的事项不存在')
    target_rows = rows_of(day_entries, target)
    additions, kept, skipped = [], [], []
    for item in indices:
        row = rows[item]
        if any(other['text'] == row['text'] and other['period'] == row['period']
               for other in target_rows) or any(other['text'] == row['text'] and other['period'] == row['period']
                                                for other in additions):
            skipped.append(dict(text=row['text'], reason='目标日期已有相同事项'))
            continue
        additions.append(row)
        kept.append(item)
    if len(target_rows) + len(additions) > MAX_PER_DAY:
        return dict(moved=[], skipped=skipped, error=f'目标日期最多 {MAX_PER_DAY} 条，请先腾出位置')
    if not additions:
        return dict(moved=[], skipped=skipped, error=None)
    store.put('day:' + target.isoformat(), target_rows + additions)
    if mode == 'move':
        keep = set(kept)
        store.put('day:' + source.isoformat(), [row for position, row in enumerate(rows) if position not in keep])
    return dict(moved=[row['text'] for row in additions], skipped=skipped, error=None)


def parse_day(value, fallback=None):
    try:
        return date.fromisoformat(str(value).strip())
    except (TypeError, ValueError):
        return fallback


def summary(report):
    if report.get('error'):
        return report['error']
    moved, skipped = len(report['moved']), len(report['skipped'])
    if not moved and not skipped:
        return '没有可移动的事项。'
    text = f'已处理 {moved} 条。'
    if skipped:
        text += f" 跳过 {skipped} 条：{skipped_text(report['skipped'])}。"
    return text


def skipped_text(skipped):
    return '、'.join(item['text'] for item in skipped[:3]) + (' 等' if len(skipped) > 3 else '')
