"""Module appearance survives real Workspace dialogs, themes and app restarts."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import sys
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import patch

from app import QApplication, CalendarApp, Store, configure_style
from module_appearance import DEFAULT_STYLE, ModuleAppearanceDialog
from qt_compat import QColor, QDialogButtonBox, QLineEdit, Qt
if sys.platform == 'linux':
    from PyQt6.QtGui import QPalette
    from PyQt6.QtTest import QTest
else:
    from PySide6.QtGui import QPalette
    from PySide6.QtTest import QTest


def assert_opacity(panel, expected):
    effect = panel.graphicsEffect()
    if expected == 100:
        assert effect is None or not effect.isEnabled() or effect.opacity() == 1
    else:
        assert effect is not None and effect.isEnabled()
        assert abs(effect.opacity() - expected / 100) < .001


app = QApplication([])
configure_style(app)
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
    db_path = Path(temporary) / 'appearance.sqlite3'
    store = Store(db_path)
    legacy_key = 'legacy-note'
    store.put('workspace:modules', [dict(id=legacy_key, plugin='notes', kind='note', title='旧版便签', visible=True)])
    store.put('module:' + legacy_key, dict(text='旧版内容必须保留'))
    legacy_colors = {'main-calendar': '#213d5f', 'daily-editor': '#ffeebb', legacy_key: '#604080'}
    for key, color in legacy_colors.items():
        store.put('module-color:' + key, color)
    day_key = 'day:' + date.today().isoformat()
    rows = [dict(period='早', text='保存已有事项', done=False)]
    store.put(day_key, rows)
    window = CalendarApp(store)
    window.count.setCurrentIndex(0)
    window.show()
    QTest.qWait(30)
    workspace = window.body
    assert workspace.docks[legacy_key].widget().text.toPlainText() == '旧版内容必须保留'
    for key, color in legacy_colors.items():
        assert workspace.get_module_style(key) == dict(background=color, foreground='', opacity=100)
        assert store.get('module-style:' + key, None) is None

    # A second instance of the same note module inherits the theme instead of
    # the first instance's legacy or new custom settings.
    second_note = workspace.add_module('notes')
    second_note.text.setPlainText('另一份独立便签')
    second_key = second_note.record['id']
    assert workspace.get_module_style(second_key) == DEFAULT_STYLE
    styles = {
        'main-calendar': dict(background='#082e50', foreground='#f0b3d4', opacity=72),
        'daily-editor': dict(background='#cdf1dc', foreground='#123456', opacity=82),
        legacy_key: dict(background='#e0d7fb', foreground='#351d57', opacity=50),
    }
    for key, style in styles.items():
        assert workspace.set_module_style(key, style)
        assert workspace.get_module_style(key) == style
        assert store.get('module-style:' + key, None) == style
        assert_opacity(workspace.docks[key], style['opacity'])
    assert window.calendar_surface == styles['main-calendar']['background']
    assert window.calendar_foreground == styles['main-calendar']['foreground']
    assert workspace.get_module_style(second_key) == DEFAULT_STYLE
    note = workspace.docks[legacy_key].widget()
    assert note.text.palette().color(QPalette.ColorRole.Base).name() == styles[legacy_key]['background']
    assert note.text.palette().color(QPalette.ColorRole.Text).name() == styles[legacy_key]['foreground']
    editor_fields = workspace.docks['daily-editor'].widget().findChildren(QLineEdit)
    assert editor_fields
    assert all(field.palette().color(QPalette.ColorRole.Text).name() == '#123456' for field in editor_fields)

    # The calendar's dates and headings use QPainter, so confirm custom text
    # actually reaches the drawing rather than only updating a style field.
    workspace.preview_module_style('main-calendar', dict(styles['main-calendar'], opacity=100))
    app.processEvents()
    board = window.boards[0]
    calendar_image = board.grab().toImage()
    text_rgb = QColor(styles['main-calendar']['foreground']).rgb()
    header_height = min(calendar_image.height(), max(1, int(board.header_height())))
    assert any(calendar_image.pixel(x, y) == text_rgb
               for y in range(header_height) for x in range(calendar_image.width())), 'Custom calendar text was not painted'
    workspace.preview_module_style('main-calendar', styles['main-calendar'])

    # A canceled live preview must restore both rendering and the in-memory
    # style cache, with no database edit even after a global theme refresh.
    dialog = ModuleAppearanceDialog(workspace, legacy_key)
    dialog.show()
    dialog.inputs['background'].setText('#123456')
    dialog.opacity.setValue(24)
    assert workspace.get_module_style(legacy_key)['opacity'] == 24
    assert store.get('module-style:' + legacy_key, None) == styles[legacy_key]
    window.change_theme(True)
    assert_opacity(workspace.docks[legacy_key], 24)
    dialog.reject()
    assert workspace.get_module_style(legacy_key) == styles[legacy_key]
    assert_opacity(workspace.docks[legacy_key], 50)
    assert second_note.text.palette().color(QPalette.ColorRole.Base).name() == window.theme_colors['surface']

    # Failed storage must leave the dialog open; cancel still restores the
    # original saved style so a failed save cannot masquerade as a success.
    dialog = ModuleAppearanceDialog(workspace, legacy_key)
    dialog.show()
    dialog.opacity.setValue(36)
    with patch.object(window, 'persist', return_value=False):
        dialog.accept()
    assert dialog.isVisible()
    assert store.get('module-style:' + legacy_key, None) == styles[legacy_key]
    dialog.reject()
    assert workspace.get_module_style(legacy_key) == styles[legacy_key]

    # Saving a reset overrides an old module-color key permanently; it must
    # not return when the new application lazily reconstructs its style cache.
    dialog = ModuleAppearanceDialog(workspace, legacy_key)
    dialog.reset_style()
    dialog.accept()
    assert workspace.get_module_style(legacy_key) == DEFAULT_STYLE
    assert store.get('module-color:' + legacy_key, '') == legacy_colors[legacy_key]
    workspace.save_workspace()
    window.close()
    store.db.close()

    restored = CalendarApp(Store(db_path))
    restored.show()
    QTest.qWait(30)
    for key in ('main-calendar', 'daily-editor'):
        assert restored.body.get_module_style(key) == styles[key]
        assert_opacity(restored.body.docks[key], styles[key]['opacity'])
    assert restored.calendar_surface == '#082e50'
    assert restored.calendar_foreground == '#f0b3d4'
    assert restored.body.get_module_style(legacy_key) == DEFAULT_STYLE
    assert restored.body.get_module_style(second_key) == DEFAULT_STYLE
    assert restored.body.docks[legacy_key].widget().text.toPlainText() == '旧版内容必须保留'
    assert restored.body.docks[second_key].widget().text.toPlainText() == '另一份独立便签'
    assert restored.store.get(day_key, None) == rows
    restored.close()
    restored.store.db.close()

print('PASS: core and accessory colors, painted calendar text, per-instance isolation, legacy migration, cancel, failed save and restart persistence')
