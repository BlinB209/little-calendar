"""Automatic backup scheduling: change detection, rotation, isolation, payload."""
import tempfile
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

from app import Store
import autobackup
from autobackup import keep_count, rotate, run, should_run, signature

settings = dict(backup_auto=True, backup_keep=3, backup_folder='')
now = datetime(2026, 10, 23, 12, 0)

with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
    # Resolve the temporary directory: Windows CI hands out an 8.3 short name
    # (RUNNER~1), while the app stores canonical long paths.
    root = Path(folder).resolve()
    store = Store(root / 'calendar.sqlite3')
    store.put('day:2026-10-23', [dict(done=False, period='早', text='交作业')])
    first_signature = signature(store)
    assert first_signature and autobackup.should_run(settings, {}, now, first_signature) is True
    assert should_run(dict(settings, backup_auto=False), {}, now, first_signature) is False
    assert should_run(settings, {}, now, '') is False

    report = run(store, settings, now=now)
    assert report['created'] and report['error'] is None and report['skipped'] is False, report
    created = Path(report['created'])
    assert created.is_file() and created.parent == root / 'backups'
    assert autobackup.load_state(store)['last'] == now.isoformat(timespec='seconds')
    assert autobackup.load_state(store)['signature'] == first_signature
    # A second run inside 24h is skipped even though nothing else was needed.
    assert run(store, settings, now=now + timedelta(hours=1))['created'] is None
    # Unchanged data after the interval is still skipped.
    assert run(store, settings, now=now + timedelta(days=1))['created'] is None
    # Changed data after the interval produces a second archive.
    store.put('day:2026-10-24', [dict(done=False, period='晚', text='散步')])
    changed = signature(store)
    assert changed != first_signature
    second = run(store, settings, now=now + timedelta(days=1, minutes=1))
    assert second['created'] and Path(second['created']).is_file(), second

    # The archive must stay a normal full backup: no nested backups or recoveries.
    with zipfile.ZipFile(second['created']) as archive:
        names = archive.namelist()
    assert 'calendar.sqlite3' in names and 'backup.json' in names
    assert not [name for name in names if name.startswith('backups/')], names
    assert not [name for name in names if name.startswith('recovery-')], names

    # Rotation keeps the newest N archives only.
    rotation_dir = root / 'rotation'
    rotation_dir.mkdir()
    for stamp in ('20260101-000000', '20260102-000000', '20260103-000000', '20260104-000000'):
        (rotation_dir / f'auto-{stamp}.zip').write_bytes(b'x')
    (rotation_dir / 'recovery-keep.zip').write_bytes(b'x')
    removed = rotate(rotation_dir, 2)
    assert removed == ['auto-20260101-000000.zip', 'auto-20260102-000000.zip'], removed
    assert len(sorted(rotation_dir.glob('auto-*.zip'))) == 2
    assert (rotation_dir / 'recovery-keep.zip').is_file(), 'rotation must never touch other files'
    assert rotate(rotation_dir, 0) == ['auto-20260103-000000.zip', 'auto-20260104-000000.zip']
    assert keep_count(dict(backup_keep=0)) == 1 and keep_count(dict(backup_keep=99)) == 30
    assert keep_count(dict(backup_keep='bad')) == autobackup.DEFAULT_KEEP

    # A custom folder is honored once data changed again after the interval.
    custom = root / 'elsewhere' / 'nested'
    store.put('day:2026-10-26', [dict(done=False, period='午', text='自定义目录')])
    custom_report = run(store, dict(settings, backup_folder=str(custom)),
                        now=now + timedelta(days=2, minutes=2))
    assert custom_report['created'] and Path(custom_report['created']).parent == custom, custom_report
    state_before = autobackup.load_state(store)
    blocker = root / 'not-a-folder'
    blocker.write_text('x', encoding='utf-8')
    store.put('day:2026-10-25', [dict(done=False, period='早', text='再次变化')])
    failed = run(store, dict(settings, backup_folder=str(blocker)), now=now + timedelta(days=3, minutes=5))
    assert failed['created'] is None and failed['error'], failed
    assert autobackup.load_state(store) == state_before, 'a failure must not advance the schedule'

    store.db.close()

print('PASS: auto-backup change detection, 24h gate, rotation bounds, payload isolation, custom folder and failure isolation')
