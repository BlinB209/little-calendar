"""Real plugin-library controls: inert import, consent, lifecycle, editing and errors."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import json
import sys
import tempfile
import zipfile
from pathlib import Path

from PySide6.QtCore import QTimer, QCoreApplication, QEvent
from PySide6.QtWidgets import QMessageBox, QPlainTextEdit, QPushButton
from app import QApplication, CalendarApp, Store, configure_style
from module_shop import ModuleShop


app = QApplication([])
configure_style(app)


def settle():
    app.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
    root = Path(folder)
    window = CalendarApp(Store(root/'calendar.sqlite3'))
    window.show()
    shop = ModuleShop(window.body)
    shop.show()
    page = shop.python_page
    shop.tabs.setCurrentWidget(page)
    settle()
    assert not page.add_button.isEnabled()
    assert not shop.import_button.isVisible(), 'JSON buttons should not confuse Python import'
    assert len(shop.visible_plugin_ids) == 5
    example = root/'editable-example.zip'
    page.library.export_example(example)
    marker = root/'executed.txt'
    with zipfile.ZipFile(example) as archive:
        contents = {name: archive.read(name) for name in archive.namelist()}
    contents['main.py'] = (f'from pathlib import Path\nPath({str(marker)!r}).write_text("ran", encoding="utf-8")\n'.encode('utf-8') + contents['main.py'])
    package = root/'test-plugin.zip'
    with zipfile.ZipFile(package, 'w') as archive:
        for name, data in contents.items():
            archive.writestr(name, data)
    entry = page.import_path(package)
    key = entry['id']
    assert not marker.exists(), 'Import must never run Python'
    assert key not in window.body.installed
    assert page.selected_id() == key
    assert key not in shop.visible_plugin_ids, 'Python entries have their own page'
    page.search.setText('不存在的插件')
    assert page.list.count() == 0 and not page.add_button.isEnabled()
    page.search.clear()
    assert page.selected_id() == key

    decisions = []
    def decide(answer):
        def respond():
            dialogs = [w for w in app.topLevelWidgets() if isinstance(w, QMessageBox) and w.isVisible()]
            assert len(dialogs) == 1, 'Expected one source approval dialog'
            decisions.append(dialogs[0].windowTitle())
            dialogs[0].button(answer).click()
        QTimer.singleShot(30, respond)

    decide(QMessageBox.StandardButton.Cancel)
    page.enable_button.click()
    assert not marker.exists() and key not in window.body.installed
    assert not page.library.is_approved(key)
    decide(QMessageBox.StandardButton.Yes)
    page.enable_button.click()
    assert key in window.body.installed and page.library.is_approved(key)
    assert not marker.exists(), 'Enable with no existing instances does not create an instance'
    page.add_button.click()
    settle()
    assert marker.exists() and len(window.body.records) == 1
    first = window.body.records[-1]['id']
    wrapper = window.body.docks[first].widget()
    note = wrapper.instance.widget.findChild(QPlainTextEdit)
    note.setPlainText('插件数据在停用和重载后保留')
    page.add_button.click()
    settle()
    assert len(window.body.records) == 2
    assert len(decisions) == 2, 'Unchanged trusted source must not ask on every add'
    second = window.body.records[-1]['id']
    other = window.body.docks[second].widget().instance.widget.findChild(QPlainTextEdit)
    assert other.toPlainText() == '', 'Each instance owns independent storage'
    page.enable_button.click()
    settle()
    assert key not in window.body.installed
    assert wrapper.instance is None and window.body.docks[first].isHidden()
    page.enable_button.click()
    settle()
    assert len(decisions) == 2, 'Re-enable unchanged source retains prior approval'
    assert wrapper.instance.widget.findChild(QPlainTextEdit).toPlainText() == '插件数据在停用和重载后保留'

    source = page.library.source_path(key)/'main.py'
    old_widget = wrapper.instance.widget
    source.write_text(source.read_text(encoding='utf-8').replace('widget = QtWidgets.QWidget()', 'widget = QtWidgets.QWidget()\n    widget.setObjectName("reloaded-version")'), encoding='utf-8')
    page.refresh()
    assert not page.library.is_approved(key)
    decide(QMessageBox.StandardButton.Cancel)
    page.reload_button.click()
    assert wrapper.instance.widget is old_widget
    decide(QMessageBox.StandardButton.Yes)
    page.reload_button.click()
    settle()
    assert len(decisions) == 4
    assert wrapper.instance.widget.objectName() == 'reloaded-version'
    assert wrapper.instance.widget.findChild(QPlainTextEdit).toPlainText() == '插件数据在停用和重载后保留'

    output = Path('build')
    output.mkdir(exist_ok=True)
    assert shop.grab().save(str(output/'python-plugin-library.png'))
    shop.resize(660, 510)
    settle()
    assert page.verticalScrollBar().maximum() > 0, 'Short dialogs must scroll instead of crushing the controls'
    page.verticalScrollBar().setValue(page.verticalScrollBar().maximum())
    settle()
    assert page.detail_scroll.widget().width() <= page.detail_scroll.viewport().width(), 'Long source paths must not clip action buttons'
    assert page.add_button.width() >= 80 and page.add_button.height() >= 24
    assert shop.grab().save(str(output/'python-plugin-library-small.png'))
    shop.tabs.setCurrentIndex(1)
    settle()
    assert any(button.text() == '外观…' for button in shop.findChildren(QPushButton))
    assert any('Python 插件' in label.text() for label in shop.findChildren(__import__('qt_compat').QLabel))

    manifest = source.parent/'manifest.json'
    metadata = json.loads(manifest.read_text(encoding='utf-8'))
    metadata['api_version'] = 99
    manifest.write_text(json.dumps(metadata), encoding='utf-8')
    page.refresh()
    assert '不兼容' in page.error.text()
    assert not page.add_button.isEnabled()
    assert page.enable_button.isEnabled(), 'An invalid running plugin can still be disabled'
    page.enable_button.click()
    assert key not in window.body.installed
    manifest.write_bytes(contents['manifest.json'])
    window.body.enable_python_plugin(key, page.library.metadata(key)['digest'])
    active_context = wrapper.instance.context
    shop.close()
    window.close()
    assert active_context._closed, 'Closing the calendar must clean up active plugins'
    window.store.db.close()
    marker.unlink()

    sys.argv.append('--safe-mode')
    try:
        safe_window = CalendarApp(Store(root/'calendar.sqlite3'))
        safe_window.show()
        safe_shop = ModuleShop(safe_window.body)
        safe_shop.show()
        safe_page = safe_shop.python_page
        safe_shop.tabs.setCurrentWidget(safe_page)
        settle()
        assert not marker.exists(), 'Safe-mode restore must not execute approved plugins'
        assert safe_window.body.docks[first].widget().instance is None
        assert '安全模式' in safe_page.state.text()
        assert not safe_page.add_button.isEnabled() and not safe_page.reload_button.isEnabled()
        assert safe_page.enable_button.isEnabled() and safe_page.enable_button.text() == '停用插件'
        safe_shop.close()
        safe_window.close()
        safe_window.store.db.close()
    finally:
        sys.argv.remove('--safe-mode')

    source.write_text(source.read_text(encoding='utf-8')+'\n# changed while the app was closed\n', encoding='utf-8')
    restored = CalendarApp(Store(root/'calendar.sqlite3'))
    restored.show()
    restored_shop = ModuleShop(restored.body)
    restored_shop.show()
    restored_page = restored_shop.python_page
    restored_shop.tabs.setCurrentWidget(restored_page)
    settle()
    assert not marker.exists(), 'Modified source must not execute on restart'
    assert not restored_page.library.is_approved(key)
    assert restored.body.docks[first].widget().instance is None
    assert '尚未确认' in restored_page.state.text()
    decide(QMessageBox.StandardButton.Yes)
    restored_page.reload_button.click()
    settle()
    assert marker.exists()
    assert restored.body.docks[first].widget().instance.widget.findChild(QPlainTextEdit).toPlainText() == '插件数据在停用和重载后保留'
    restored_shop.close()
    restored.close()
    restored.store.db.close()

print('PASS: third-party library inert import, source consent/cancel, independent instances, disable/restore/close cleanup, changed-source reload/restart gate, safe mode, error display and small layout')
