"""Optional system tray. Every entry point is guarded: no tray must degrade,
never crash, and a hidden window must always keep an explicit way out.
"""
from qt_compat import QSystemTrayIcon, QStyle, QMenu


def available():
    try:
        return bool(QSystemTrayIcon.isSystemTrayAvailable())
    except Exception:
        return False


class StatusTray(QSystemTrayIcon):
    """Tray icon plus menu; created only when the platform reports a tray."""

    def __init__(self, owner, callbacks):
        super().__init__(owner)
        self._callbacks = dict(callbacks)
        self.setToolTip('小日历')
        try:
            self.setIcon(owner.style().standardIcon(QStyle.StandardPixmap.SP_DesktopIcon))
        except Exception:
            pass
        menu = QMenu()
        for label, key in [('显示窗口', 'show'), ('今天', 'today'), ('搜索事项…', 'search'),
                           ('备份与恢复…', 'backup')]:
            action = menu.addAction(label)
            action.triggered.connect(lambda checked=False, k=key: self._run(k))
        menu.addSeparator()
        pause = menu.addAction('暂停今天的提醒')
        pause.triggered.connect(lambda checked=False: self._run('pause'))
        menu.addSeparator()
        quit_action = menu.addAction('退出小日历')
        quit_action.triggered.connect(lambda checked=False: self._run('quit'))
        self.setContextMenu(menu)
        self.activated.connect(self._activated)

    def _run(self, key):
        callback = self._callbacks.get(key)
        if callable(callback):
            callback()

    def _activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self._run('show')

    def notify(self, title, body):
        """Show a balloon message; returns False when it cannot be shown."""
        try:
            if not self.isVisible():
                return False
            self.showMessage(title, body, QSystemTrayIcon.MessageIcon.Information, 8000)
            return True
        except Exception:
            return False
