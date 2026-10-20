"""Stable, small API shared by personal Python calendar plugins (API version 1)."""
import copy
import functools
import json
import logging
import sys
import weakref
from datetime import date
from pathlib import Path

if sys.platform == 'linux':
    from PyQt6 import QtCore, QtGui, QtWidgets
else:
    from PySide6 import QtCore, QtGui, QtWidgets

API_VERSION = 1


class PluginContext:
    """Per-widget data and live calendar information; this is not a sandbox."""
    def __init__(self, store, plugin_id, instance_id, data_dir, owner=None):
        self.plugin_id, self.instance_id = plugin_id, instance_id
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._store = store
        self._owner = weakref.ref(owner) if owner is not None else lambda: None
        self._prefix = f'python-plugin:{plugin_id}:{instance_id}:'
        self._cleanups = []
        self._closed = False
        self.errors = []

    @property
    def today(self):
        return date.today()

    @property
    def selected_date(self):
        return getattr(self._owner(), 'selected', self.today)

    @property
    def theme_colors(self):
        return dict(getattr(self._owner(), 'theme_colors', {}))

    def _key(self, key):
        if not isinstance(key, str) or not 1 <= len(key) <= 128:
            raise ValueError('插件数据键必须为 1–128 个字符')
        return self._prefix + key

    def get_value(self, key, default=None):
        return copy.deepcopy(self._store.get(self._key(key), default))

    def set_value(self, key, value):
        if self._closed:
            raise RuntimeError('插件实例已经关闭')
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False)
        if len(encoded.encode('utf-8')) > 1024 * 1024:
            raise ValueError('单项插件数据不能超过 1 MiB；较大文件请放在 data_dir')
        self._store.put(self._key(key), json.loads(encoded))

    def report_error(self, error):
        message = f'{type(error).__name__}: {error}'
        self.errors.append(message)
        logging.getLogger('calendar.plugins').error('%s: %s', self.plugin_id, message)

    def guard(self, callback):
        """Wrap Qt slots/timer callbacks to report errors without exiting the app."""
        @functools.wraps(callback)
        def protected(*args, **kwargs):
            if self._closed:
                return None
            try:
                return callback(*args, **kwargs)
            except BaseException as error:
                self.report_error(error)
                return None
        return protected

    def on_cleanup(self, callback):
        """Register resource cleanup, e.g. timer.stop, called once on unload."""
        if self._closed:
            raise RuntimeError('插件实例已经关闭')
        if not callable(callback):
            raise TypeError('清理函数必须可调用')
        self._cleanups.append(callback)

    def _cleanup(self):
        if self._closed:
            return
        self._closed = True
        for callback in reversed(self._cleanups):
            try:
                callback()
            except BaseException as error:
                self.report_error(error)
        self._cleanups.clear()
