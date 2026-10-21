"""Real cross-platform window restore, migration, validation and rollback checks."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import hashlib
import json
from pathlib import Path
import tempfile
import zipfile
from unittest.mock import patch
from app import QApplication, CalendarApp, Store, configure_style
from qt_compat import QPixmap, QColor, QMessageBox
from backup import export_backup, PreparedRestore, restore_backup
from backup_ui import BackupDialog

app = QApplication([])
configure_style(app)
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
    base = Path(temporary).resolve()
    source,destination = base/'old-computer',base/'new-computer'
    source.mkdir()
    destination.mkdir()
    first = CalendarApp(Store(source/'calendar.sqlite3'))
    first.show()
    app.processEvents()
    first.rows[0][2].setText('迁移事项')
    day = first.selected.isoformat()
    note = first.body.add_module('notes')
    note.text.setPlainText('迁移便签')
    record = note.record['id']
    first.body.set_module_style(record,dict(background='#172033',opacity=80,background_opacity=35))
    pixmap = QPixmap(24,24)
    pixmap.fill(QColor('#d12345'))
    image = source/'source-image.png'
    assert pixmap.save(str(image))
    from preferences import cache_background_image
    first.custom.update(background_mode='image',background_image=cache_background_image(first.store,image))
    first.store.put('customization:v1',first.custom)
    library = first.body.plugin_library
    example = library.export_example(base/'plugin.zip')
    metadata = first.body.import_python_plugin(example)
    first.body.enable_python_plugin(metadata['id'],metadata['digest'])
    plugin = first.body.add_module(metadata['id'])
    plugin.instance.context.set_value('text','迁移的插件内容')
    plugin_id = plugin.record['id']
    (plugin.instance.context.data_dir/'我的文件.txt').write_text('独立文件',encoding='utf-8')
    first.save_session()
    archive = export_backup(first.store,base/'backup.zip')
    before = archive.read_bytes()
    first.close()
    first.store.db.close()
    image.unlink()

    target = CalendarApp(Store(destination/'calendar.sqlite3'))
    target.rows[0][2].setText('恢复前的事项')
    target.save_session()
    dialog = BackupDialog(target)
    # Cancel never changes the target or runs any plugin.
    with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Cancel):
        dialog.restore_path(archive)
    assert target.store.get('day:'+day,[])[0]['text']=='恢复前的事项'
    assert archive.read_bytes()==before
    errors = []
    with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Yes),patch.object(QMessageBox,'warning',side_effect=lambda *args:errors.append(str(args))):
        dialog.restore_path(archive)
    assert not errors,errors
    restored = target._replacement
    from calendar_plugin_api import QtCore
    settle = QtCore.QEventLoop()
    QtCore.QTimer.singleShot(400,settle.quit)
    settle.exec()
    assert target.body.restoring and not target.body.save_timer.isActive()
    assert restored.store.get('day:'+day,[])[0]['text']=='迁移事项'
    assert restored.body.docks[record].widget().text.toPlainText()=='迁移便签'
    assert restored.body.get_module_style(record)['background_opacity']==35
    assert Path(restored.custom['background_image']).is_relative_to(destination)
    assert not restored.background_pixmap.isNull()
    assert 'python-note' not in restored.body.installed
    assert restored.store.get('python-plugins:approved',None)=={}
    assert restored.body.docks[plugin_id].widget().instance is None
    assert (restored.body.plugin_library.data_path('python-note',plugin_id)/'我的文件.txt').read_text(encoding='utf-8')=='独立文件'
    meta = restored.body.plugin_library.metadata('python-note')
    restored.body.enable_python_plugin('python-note',meta['digest'])
    assert restored.body.docks[plugin_id].widget().instance.context.get_value('text')=='迁移的插件内容'
    recoveries = list(destination.glob('recovery-*.zip'))
    assert len(recoveries)==1
    check = PreparedRestore(recoveries[0])
    assert json.loads(check.entries['day:'+day])[0]['text']=='恢复前的事项'
    check.close()
    restored.close()

    # Verify checksums and traversal before replacing any data.
    for attack in ('../escape.txt','/absolute.txt','plugins/CON','plugins/a/../../oops'):
        bad = base/'bad.zip'
        with zipfile.ZipFile(bad,'w') as z:
            z.writestr(attack,'bad')
        try:
            PreparedRestore(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(attack)
    corrupt = base/'corrupt.zip'
    with zipfile.ZipFile(archive) as src,zipfile.ZipFile(corrupt,'w') as dst:
        for info in src.infolist():
            content = src.read(info)
            dst.writestr(info,content+b'bad' if info.filename=='calendar.sqlite3' else content)
    try:
        PreparedRestore(corrupt)
    except ValueError:
        pass
    else:
        raise AssertionError('Corrupt database accepted')

    # Filesystem failure after one directory replacement must roll back both.
    prepared = PreparedRestore(archive)
    marker = destination/'backgrounds'/'rollback-marker.txt'
    marker.write_text('keep',encoding='utf-8')
    original = Path.rename
    def fail_second(path,new):
        if path.name=='plugins' and path.parent.name.startswith('.restore-'):
            raise OSError('injected rename failure')
        return original(path,new)
    before_rows = list(restored.store.db.execute('SELECT * FROM entries ORDER BY key'))
    with patch.object(Path,'rename',fail_second):
        try:
            restore_backup(restored.store,prepared)
        except OSError:
            pass
        else:
            raise AssertionError('Expected failure')
    assert marker.read_text()=='keep'
    assert list(restored.store.db.execute('SELECT * FROM entries ORDER BY key'))==before_rows
    assert (destination/'plugins'/'packages'/'python-note'/'main.py').is_file()
    prepared.close()
    restored.store.db.close()
print('PASS: backup migration, actual restore/cancel UI, background relocation, plugin trust reset, recovery copy, checksum/traversal rejection and rollback')
