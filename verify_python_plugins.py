"""Runtime checks use only synthetic plugins under a temporary directory."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import json
from pathlib import Path
import sqlite3
import stat
import sys
import tempfile
import zipfile

from calendar_plugin_api import QtWidgets
from plugin_runtime import PluginApprovalRequired, PluginError, PluginLibrary


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(str(path))
        self.db.execute('CREATE TABLE IF NOT EXISTS entries (key TEXT PRIMARY KEY,value TEXT)')

    def get(self, key, default):
        row = self.db.execute('SELECT value FROM entries WHERE key=?', (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def put(self, key, value):
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO entries VALUES (?,?)', (key, json.dumps(value)))


def rejected(callback, exception=PluginError):
    try:
        callback()
    except exception:
        return
    raise AssertionError('Expected rejection')


application = QtWidgets.QApplication([])
with tempfile.TemporaryDirectory() as temporary:
    folder = Path(temporary)
    store = Store(folder / 'test.sqlite3')
    library = PluginLibrary(store)
    assert library.root == folder / 'plugins'
    marker = folder / 'executed.txt'
    source = folder / 'source'
    source.mkdir()
    manifest = dict(schema=1, api_version=1, id='test-note', title='Test note', version='1.0.0',
                    kind='python', entry='main.py', description='Synthetic test only')
    (source / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    (source / 'helpers.py').write_text('LABEL = "first"\n', encoding='utf-8')
    (source / 'main.py').write_text(f'''from pathlib import Path
from .helpers import LABEL
from calendar_plugin_api import QtWidgets
Path({str(marker)!r}).write_text("executed")

def create_widget(context):
    widget = QtWidgets.QLabel(LABEL)
    widget.context = context
    context.set_value("runs", context.get_value("runs", 0) + 1)
    context.on_cleanup(lambda: (context.data_dir / "closed").write_text("closed"))
    return widget
''', encoding='utf-8')
    metadata = library.import_package(source / 'manifest.json')
    assert not metadata['approved'] and not marker.exists()
    assert library.catalog()[0]['id'] == 'test-note' and not marker.exists()
    rejected(lambda: library.create_widget('test-note', 'one'), PluginApprovalRequired)
    assert not marker.exists()
    rejected(lambda: library.import_package(source / 'manifest.json'))
    assert not marker.exists()
    library.approve('test-note', metadata['digest'])
    first = library.create_widget('test-note', 'one')
    second = library.create_widget('test-note', 'two')
    assert marker.exists() and first.widget.text() == 'first'
    assert first.context.get_value('runs') == second.context.get_value('runs') == 1
    first.context.set_value('private', {'a': [1]})
    assert second.context.get_value('private') is None
    assert first.context.data_dir != second.context.data_dir
    assert first.context.today.year >= 2020
    assert first.context.selected_date == first.context.today
    prefix = first._prefix
    first.cleanup()
    first.cleanup()
    assert (library.data_path('test-note', 'one') / 'closed').is_file()
    assert not any(name == prefix or name.startswith(prefix + '.') for name in sys.modules)
    second.cleanup()
    # Change a same-sized file without timestamp tricks: no cached Python loader is used.
    helper = library.source_path('test-note') / 'helpers.py'
    original_stat = helper.stat()
    helper.write_text('LABEL = "other"\n', encoding='utf-8')
    os.utime(helper, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
    assert not library.is_approved('test-note')
    rejected(lambda: library.create_widget('test-note', 'one'), PluginApprovalRequired)
    rejected(lambda: library.approve('test-note', metadata['digest']), PluginApprovalRequired)
    current = library.metadata('test-note')
    library.approve('test-note', current['digest'])
    reloaded = library.create_widget('test-note', 'one')
    assert reloaded.widget.text() == 'other'
    assert reloaded.context.get_value('runs') == 2
    assert reloaded.context.get_value('private') == {'a': [1]}
    reloaded.context.guard(lambda: (_ for _ in ()).throw(SystemExit(2)))()
    assert 'SystemExit' in reloaded.context.errors[-1]
    reloaded.cleanup()
    library.revoke('test-note')
    assert not library.is_approved('test-note')

    # Exported bundled example works without relying on external source paths.
    example = library.export_example(folder / 'example.zip')
    example_metadata = library.import_package(example)
    assert not example_metadata['approved']
    library.approve('python-note', example_metadata['digest'])
    demo = library.create_widget('python-note', 'sample')
    assert isinstance(demo.widget, QtWidgets.QWidget)
    demo.cleanup()

    for index, path in enumerate(['../escape.py', '/escape.py', 'C:/escape.py', 'folder\\escape.py']):
        bad = folder / f'bad-{index}.zip'
        with zipfile.ZipFile(bad, 'w') as archive:
            archive.writestr('manifest.json', json.dumps(manifest))
            archive.writestr(path, 'pass')
        rejected(lambda bad=bad: library.import_package(bad))
    assert not (folder / 'escape.py').exists()

    linked = folder / 'linked.zip'
    with zipfile.ZipFile(linked, 'w') as archive:
        item = zipfile.ZipInfo('main.py')
        item.create_system = 3
        item.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(item, '../../escape.py')
    rejected(lambda: library.import_package(linked))

    invalid_api = dict(manifest, id='future-api', api_version=99)
    (source / 'manifest.json').write_text(json.dumps(invalid_api), encoding='utf-8')
    rejected(lambda: library.import_package(source / 'manifest.json'))
    assert not library.source_path('future-api').exists()
    (source / 'manifest.json').write_text(json.dumps(dict(manifest, id='notes')), encoding='utf-8')
    rejected(lambda: library.import_package(source / 'manifest.json', reserved_ids={'notes'}))
    assert not library.source_path('notes').exists()

    # Exceptions, including SystemExit, become errors instead of exiting the host.
    (source / 'manifest.json').write_text(json.dumps(dict(manifest, id='bad-entry')), encoding='utf-8')
    (source / 'main.py').write_text('def create_widget(context):\n    raise SystemExit(7)\n', encoding='utf-8')
    bad_metadata = library.import_package(source / 'manifest.json')
    library.approve('bad-entry', bad_metadata['digest'])
    prefixes = {name for name in sys.modules if name.startswith('_little_calendar_plugin_')}
    rejected(lambda: library.create_widget('bad-entry', 'broken'))
    assert prefixes == {name for name in sys.modules if name.startswith('_little_calendar_plugin_')}
    # Restart preserves approvals/data, and in-memory databases never use the real library.
    restarted = PluginLibrary(store)
    assert restarted.is_approved('python-note')
    assert not restarted.is_approved('test-note')
    memory_store = Store(':memory:')
    memory_library = PluginLibrary(memory_store)
    assert memory_library.root != library.root and memory_library.catalog() == []
    memory_store.db.close()
    memory_library._temporary.cleanup()
    store.db.close()
print('PASS: Python plugin import without execution, approval snapshots, isolated data, relative imports/reload, cleanup, ZIP validation, exceptions and example')
