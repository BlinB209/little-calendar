"""Application lifecycle regression with synthetic plugins and temporary data only."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import json
from pathlib import Path
import sys
import tempfile

from app import QApplication, CalendarApp, Store, configure_style
from calendar_plugin_api import QtCore, QtWidgets


app = QApplication([])
configure_style(app)


def close(window):
    store = window.store
    window.close()
    window.deleteLater()
    QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
    app.processEvents()
    store.db.close()


def open_window(path, safe=False):
    arguments = list(sys.argv)
    try:
        if safe:
            sys.argv.append('--safe-mode')
        window = CalendarApp(Store(path))
        window.show()
        app.processEvents()
        return window
    finally:
        sys.argv[:] = arguments


with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
    folder = Path(temporary)
    db_path = folder / 'calendar.sqlite3'
    source = folder / 'source'
    source.mkdir()
    runs = folder / 'runs.txt'
    cleanups = folder / 'cleanups.txt'
    manifest = dict(schema=1, api_version=1, id='lifecycle-note', title='Lifecycle test',
                    version='1.0.0', kind='python', entry='main.py')
    manifest_text = json.dumps(manifest)
    (source / 'manifest.json').write_text(manifest_text, encoding='utf-8')
    (source / 'main.py').write_text(f'''from pathlib import Path
from calendar_plugin_api import QtWidgets, QtCore
with Path({str(runs)!r}).open('a') as handle:
    handle.write('run\\n')

def create_widget(context):
    widget = QtWidgets.QPlainTextEdit()
    widget.setPlainText(context.get_value('text', ''))
    widget.textChanged.connect(context.guard(lambda: context.set_value('text', widget.toPlainText())))
    timer = QtCore.QTimer(widget)
    timer.start(1000)
    context.on_cleanup(timer.stop)
    def stopped():
        with Path({str(cleanups)!r}).open('a') as handle:
            handle.write(context.instance_id + '\\n')
    context.on_cleanup(stopped)
    return widget
''', encoding='utf-8')
    window = open_window(db_path)
    metadata = window.body.import_python_plugin(source / 'manifest.json')
    assert not runs.exists()
    window.body.enable_python_plugin(metadata['id'], metadata['digest'])
    wrapper = window.body.add_module(metadata['id'])
    instance_id = wrapper.record['id']
    wrapper.instance.widget.setPlainText('same instance survives code trouble')
    panel = window.body.docks[instance_id]
    panel.setGeometry(145, 205, 400, 270)
    window.body.save_workspace()
    plugin_folder = window.body.plugin_library.source_path(metadata['id'])
    close(window)
    assert cleanups.read_text().splitlines() == [instance_id]

    # Safe mode leaves approvals/enabled state intact but runs no third-party code.
    before_runs = runs.read_text()
    window = open_window(db_path, safe=True)
    assert window.body.safe_mode
    assert window.body.docks[instance_id].widget().instance is None
    assert runs.read_text() == before_runs
    note = window.body.add_module('notes')
    note.text.setPlainText('core app still works in safe mode')
    close(window)
    assert runs.read_text() == before_runs

    window = open_window(db_path)
    wrapper = window.body.docks[instance_id].widget()
    assert wrapper.instance.widget.toPlainText() == 'same instance survives code trouble'
    window.body.disable_plugin(metadata['id'])
    assert wrapper.instance is None
    close(window)
    disabled_runs = runs.read_text()
    window = open_window(db_path)
    assert window.body.docks[instance_id].widget().instance is None
    assert runs.read_text() == disabled_runs
    window.body.enable_python_plugin(metadata['id'], metadata['digest'])
    assert window.body.docks[instance_id].widget().instance.widget.toPlainText() == 'same instance survives code trouble'
    close(window)

    # Modified code is held until its new digest is approved; existing data stays.
    main = plugin_folder / 'main.py'
    main.write_text(main.read_text(encoding='utf-8') + '\n# edited\n', encoding='utf-8')
    before_runs = runs.read_text()
    window = open_window(db_path)
    assert window.body.docks[instance_id].widget().instance is None
    assert runs.read_text() == before_runs
    metadata = window.body.plugin_library.metadata('lifecycle-note')
    window.body.enable_python_plugin('lifecycle-note', metadata['digest'])
    assert window.body.docks[instance_id].widget().instance.widget.toPlainText() == 'same instance survives code trouble'
    close(window)

    # A broken manifest must keep the original record, content and geometry.
    (plugin_folder / 'manifest.json').write_text('{ broken json', encoding='utf-8')
    before_runs = runs.read_text()
    window = open_window(db_path)
    assert instance_id in window.body.docks
    assert window.body.docks[instance_id].widget().instance is None
    assert runs.read_text() == before_runs
    assert any(record['id'] == instance_id for record in window.body.records)
    close(window)
    (plugin_folder / 'manifest.json').write_text(manifest_text, encoding='utf-8')

    # Missing package directories are recoverable, not permission to discard records.
    moved = folder / 'temporarily-moved-plugin'
    plugin_folder.rename(moved)
    window = open_window(db_path)
    try:
        assert any(record['id'] == instance_id for record in window.body.records), 'Missing plugin package discarded its saved instance record'
        assert instance_id in window.body.docks, 'Missing plugin should have a recoverable placeholder'
        assert window.body.docks[instance_id].widget().instance is None
        window.body.add_module('notes').text.setPlainText('core app survives missing plugin')
        window.body.save_workspace()
        assert any(record['id'] == instance_id for record in window.store.get('workspace:modules', []))
    finally:
        close(window)
        moved.rename(plugin_folder)
    window = open_window(db_path)
    wrapper = window.body.docks[instance_id].widget()
    assert wrapper.instance is not None
    assert wrapper.instance.widget.toPlainText() == 'same instance survives code trouble'
    rect = window.body.docks[instance_id].geometry()
    assert (rect.x(), rect.y(), rect.width(), rect.height()) == (145, 205, 400, 270)
    close(window)

print('PASS: Python instance lifecycle, safe-mode, disable/re-enable, changed/corrupt/missing code recovery, cleanup, data and layout persistence')
