"""Tray availability, menu wiring and the close-to-tray fallback contract."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import tempfile
from pathlib import Path

from app import QApplication, CalendarApp, Store, configure_style
from status_tray import StatusTray, available

app = QApplication([])
configure_style(app)

with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
    store = Store(Path(folder) / 'calendar.sqlite3')
    window = CalendarApp(store)
    window.show()
    app.processEvents()

    # Defaults ask for neither a reminder nor a tray: nothing is created.
    assert window.custom['close_action'] == 'quit'
    window.apply_tray_settings()
    if not available():
        assert window.tray is None

    # Requesting close-to-tray must either work or fall back to a real close.
    window.custom['close_action'] = 'tray'
    window.apply_tray_settings()
    tray_ready = bool(available() and window.tray is not None and window.tray.isVisible())
    if tray_ready:
        menu = window.tray.contextMenu()
        labels = [action.text() for action in menu.actions() if action.text()]
        assert '显示窗口' in labels and '暂停今天的提醒' in labels and '退出小日历' in labels, labels
        window.hide()
        window.show()
        app.processEvents()
    window.close()
    app.processEvents()
    if tray_ready:
        assert not window.isVisible(), 'close-to-tray should hide, not quit'
        assert not window._quitting
        window.quit_app()
        app.processEvents()
        assert window._quitting and not window.isVisible()
    else:
        assert not window.isVisible(), 'without a tray the window must close instead'
    store.db.close()

# A tray object can be built from callbacks and its notify path is guarded.
if available():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
        store = Store(Path(folder) / 'calendar.sqlite3')
        window = CalendarApp(store)
        calls = []
        tray = StatusTray(window, dict(show=lambda: calls.append('show'),
                                       quit=lambda: calls.append('quit')))
        tray._run('show')
        tray._run('quit')
        tray._run('missing')
        assert calls == ['show', 'quit']
        tray.setVisible(True)
        assert tray.notify('标题', '正文') in (True, False)
        tray.setVisible(False)
        assert tray.notify('标题', '正文') is False, 'hidden tray must not report a shown message'
        window.close()
        store.db.close()

print('PASS: tray availability guard, menu wiring, close-to-tray hide/quit and degraded close')
