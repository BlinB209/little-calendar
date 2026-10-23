"""Daily automatic backups: change detection, bounded rotation, failure isolation.

Reuses backup.export_backup, so the archive layout, validation and the
"backups/ is outside the payload" guarantee stay identical to a manual backup.
A failure only returns an error string: automatic housekeeping must never stop
the calendar or overwrite anything.
"""
from datetime import datetime, timedelta
from pathlib import Path
import hashlib
import os

from backup import data_root, export_backup

STATE_KEY = 'backup:auto:v1'
PREFIX = 'auto-'
INTERVAL = timedelta(hours=24)
DEFAULT_KEEP = 7
# Bookkeeping keys change on every run; hashing them would defeat change detection.
BOOKKEEPING = (STATE_KEY, 'reminder:v1')
TREE_LIMIT = 2000


def database_path(store):
    path = next((row[2] for row in store.db.execute('PRAGMA database_list') if row[1] == 'main'), '')
    return Path(path) if path else None


def _tree_stamp(folder):
    """Bounded (count, newest mtime) stamp for plugin data and background files."""
    count, newest = 0, 0
    try:
        for root, _dirs, files in os.walk(folder):
            for name in files:
                count += 1
                if count >= TREE_LIMIT:
                    return count, newest
                try:
                    newest = max(newest, os.stat(os.path.join(root, name)).st_mtime_ns)
                except OSError:
                    continue
    except OSError:
        pass
    return count, newest


def signature(store):
    """Content signature of everything a backup carries except our own bookkeeping."""
    digest = hashlib.sha256()
    for key, value in store.db.execute('SELECT key, value FROM entries ORDER BY key'):
        if key in BOOKKEEPING:
            continue
        digest.update(key.encode('utf-8'))
        digest.update(b'\0')
        digest.update(str(value).encode('utf-8'))
        digest.update(b'\0')
    path = database_path(store)
    if path is None:
        return ''
    root = path.parent
    for folder in ('backgrounds', 'plugins/data'):
        count, newest = _tree_stamp(root / folder)
        digest.update(f'{folder}:{count}:{newest};'.encode('utf-8'))
    return digest.hexdigest()


def folder_for(store, settings):
    chosen = str(settings.get('backup_folder') or '').strip()
    return Path(chosen) if chosen else data_root(store) / 'backups'


def keep_count(settings):
    try:
        value = int(settings.get('backup_keep', DEFAULT_KEEP))
    except (TypeError, ValueError):
        return DEFAULT_KEEP
    return max(1, min(30, value))


def load_state(store):
    value = store.get(STATE_KEY, {})
    if not isinstance(value, dict):
        return {}
    state = {}
    if isinstance(value.get('last'), str):
        try:
            datetime.fromisoformat(value['last'])
        except ValueError:
            pass
        else:
            state['last'] = value['last']
    if isinstance(value.get('signature'), str):
        state['signature'] = value['signature']
    return state


def save_state(store, state):
    store.put(STATE_KEY, dict(state or {}))


def should_run(settings, state, now, current_signature):
    if not settings.get('backup_auto'):
        return False
    if not current_signature:
        return False
    last = state.get('last')
    if isinstance(last, str):
        try:
            last_at = datetime.fromisoformat(last)
        except ValueError:
            last_at = None
        if last_at is not None and now - last_at < INTERVAL:
            return False
    return state.get('signature') != current_signature


def rotate(folder, keep):
    """Delete the oldest auto backups so at most ``keep`` remain; ignore OSError."""
    try:
        files = sorted(Path(folder).glob(PREFIX + '*.zip'))
    except OSError:
        return []
    removed = []
    for path in files[:-keep] if keep > 0 else files:
        try:
            path.unlink()
            removed.append(path.name)
        except OSError:
            continue
    return removed


def run(store, settings, now=None):
    """Create at most one backup per day when data changed; return a small report."""
    now = now or datetime.now()
    state = load_state(store)
    current = signature(store)
    report = dict(created=None, removed=[], skipped=True, error=None)
    if not should_run(settings, state, now, current):
        return report
    folder = folder_for(store, settings)
    target = folder / f'{PREFIX}{now:%Y%m%d-%H%M%S}.zip'
    try:
        folder.mkdir(parents=True, exist_ok=True)
        export_backup(store, target)
    except Exception as error:  # housekeeping must never break the calendar
        report['error'] = str(error)
        return report
    report.update(created=str(target), removed=rotate(folder, keep_count(settings)), skipped=False)
    save_state(store, dict(last=now.isoformat(timespec='seconds'), signature=current))
    return report
