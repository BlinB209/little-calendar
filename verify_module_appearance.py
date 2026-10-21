"""Verify scoped colors, real opacity composition, dialog transactions and reset."""
import copy
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import sys
from types import SimpleNamespace
from unittest.mock import patch

from module_appearance import (DEFAULT_STYLE, normalize_style, apply_panel_style,
                               ModuleAppearanceDialog, resolved_colors)
from theme import LIGHT, DARK, stylesheet
from qt_compat import QWidget, QVBoxLayout, QLabel, QPlainTextEdit, QPushButton, QColor, QDialogButtonBox, Qt
if sys.platform == 'linux':
    from PyQt6.QtWidgets import QApplication, QFrame
    from PyQt6.QtGui import QPalette
    from PyQt6.QtTest import QTest
else:
    from PySide6.QtWidgets import QApplication, QFrame
    from PySide6.QtGui import QPalette
    from PySide6.QtTest import QTest


assert normalize_style(None, '#AABBCC') == dict(background='#aabbcc', foreground='', opacity=100, background_opacity=100)
assert normalize_style(dict(DEFAULT_STYLE), '#aabbcc')['background'] == ''
assert normalize_style({'background': 'red;border:none', 'foreground': '#12345z', 'opacity': None}) == DEFAULT_STYLE
assert normalize_style({'opacity': -1})['opacity'] == 15
assert normalize_style({'opacity': 999})['opacity'] == 100
assert normalize_style({'opacity': float('nan')})['opacity'] == 100
assert resolved_colors(DEFAULT_STYLE, DARK) == (DARK['surface'], DARK['text'])


class FakeWorkspace(QWidget):
    def __init__(self):
        super().__init__()
        self.owner = SimpleNamespace(theme_colors=dict(LIGHT))
        self.docks, self.saved, self.writes = {}, {}, []
        self.setObjectName('testDesktop')
        self.setStyleSheet('QWidget#testDesktop {background:#224466;}')
        self.resize(850, 400)
        for index, key in enumerate(('first', 'second')):
            panel = QFrame(self)
            panel.setProperty('freePanel', True)
            panel.setWindowTitle('我的便签')
            panel.setGeometry(20 + index * 410, 20, 380, 300)
            layout = QVBoxLayout(panel)
            label = QLabel('可自选的文字')
            note = QPlainTextEdit()
            note.setPlainText('保留的内容')
            layout.addWidget(label)
            layout.addWidget(note)
            panel.label, panel.note = label, note
            self.docks[key] = panel
            self.saved[key] = dict(DEFAULT_STYLE)
            apply_panel_style(panel, DEFAULT_STYLE, self.owner.theme_colors)

    def get_module_style(self, key):
        return copy.deepcopy(self.saved[key])

    def preview_module_style(self, key, value):
        apply_panel_style(self.docks[key], value, self.owner.theme_colors)

    def set_module_style(self, key, value):
        self.saved[key] = copy.deepcopy(value)
        self.writes.append((key, copy.deepcopy(value)))
        self.preview_module_style(key, value)


app = QApplication([])
app.setStyleSheet(stylesheet())
workspace = FakeWorkspace()
workspace.show()
QTest.qWait(30)
first, second = workspace.docks['first'], workspace.docks['second']
sibling_before = second.grab().toImage()

# Style only one panel, including input background and text. Its sibling keeps
# its original rendered appearance, even when both share the global theme.
style = dict(background='#da4638', foreground='#fff2d4', opacity=100)
apply_panel_style(first, style, LIGHT)
app.processEvents()
assert first.note.palette().color(QPalette.ColorRole.Base).name() == '#da4638'
assert first.note.palette().color(QPalette.ColorRole.Text).name() == '#fff2d4'
assert first.label.palette().color(QPalette.ColorRole.WindowText).name() == '#fff2d4'
assert second.grab().toImage() == sibling_before

# The whole rendered panel, including opaque input widgets, blends with the
# blue desktop. This catches implementations that only fade the outer frame.
point = first.note.mapTo(workspace, first.note.rect().bottomRight())
point.setX(point.x() - 30)
point.setY(point.y() - 30)
opaque = workspace.grab().toImage().pixelColor(point)
apply_panel_style(first, dict(style, opacity=50), LIGHT)
app.processEvents()
translucent = workspace.grab().toImage().pixelColor(point)
desktop = QColor('#224466')
for actual, top, under in zip(translucent.getRgb()[:3], opaque.getRgb()[:3], desktop.getRgb()[:3]):
    assert abs(actual - round((top + under) / 2)) <= 3, (opaque.name(), translucent.name())
assert first.graphicsEffect().opacity() == .5

# Background-only transparency must reveal the desktop beneath input widgets,
# while the text color and whole-panel opacity remain unchanged.
apply_panel_style(first, dict(style, background_opacity=0), LIGHT)
app.processEvents()
clear = workspace.grab().toImage().pixelColor(point)
assert clear.name() == desktop.name(), (clear.name(),desktop.name())
assert not first.graphicsEffect().isEnabled()
assert first.note.palette().color(QPalette.ColorRole.Text).name() == '#fff2d4'
apply_panel_style(first, dict(style, background_opacity=50), LIGHT)
app.processEvents()
half = workspace.grab().toImage().pixelColor(point)
for actual,top,under in zip(half.getRgb()[:3],QColor(style['background']).getRgb()[:3],desktop.getRgb()[:3]):
    assert abs(actual-round((top+under)/2))<=3,half.name()

# Live edits have no persistent side effects; cancel restores all original
# colors and full opacity, leaving text entered in the module untouched.
workspace.preview_module_style('first', DEFAULT_STYLE)
dialog = ModuleAppearanceDialog(workspace, 'first')
dialog.show()
with patch('module_appearance.QColorDialog.getColor', return_value=QColor('#6587ab')):
    QTest.mouseClick(dialog.findChild(QPushButton, 'moduleColorPicker_background'), Qt.MouseButton.LeftButton)
dialog.inputs['foreground'].setText('#f0f0f0')
dialog.opacity.setValue(45)
app.processEvents()
assert not workspace.writes
assert workspace.saved['first'] == DEFAULT_STYLE
assert first.graphicsEffect().opacity() == .45
assert first.note.palette().color(QPalette.ColorRole.Base).name() == '#6587ab'
dialog.reject()
app.processEvents()
assert not workspace.writes
assert not first.graphicsEffect().isEnabled()
assert first.note.palette().color(QPalette.ColorRole.Base).name() == LIGHT['surface']
assert first.note.toPlainText() == '保留的内容'

# Bad hex prevents saving, and a valid edit commits exactly once.
dialog = ModuleAppearanceDialog(workspace, 'first')
dialog.show()
dialog.inputs['background'].setText('#zzzzzz')
dialog.accept()
assert not workspace.writes and dialog.isVisible()
dialog.inputs['background'].setText('#325678')
dialog.opacity_slider.setValue(65)
QTest.mouseClick(dialog.buttons.button(QDialogButtonBox.StandardButton.Save), Qt.MouseButton.LeftButton)
assert workspace.saved['first'] == dict(background='#325678', foreground='', opacity=65, background_opacity=100)
assert len(workspace.writes) == 1

# Reset is itself a draft; canceling reset restores the saved custom settings.
dialog = ModuleAppearanceDialog(workspace, 'first')
dialog.show()
QTest.mouseClick(dialog.findChild(QPushButton, 'moduleAppearanceReset'), Qt.MouseButton.LeftButton)
assert dialog.values == DEFAULT_STYLE
assert workspace.saved['first']['opacity'] == 65
dialog.close()
app.processEvents()
assert first.graphicsEffect().opacity() == .65
assert workspace.saved['first']['background'] == '#325678'

# Saving a reset follows the next theme change instead of retaining old RGBs.
dialog = ModuleAppearanceDialog(workspace, 'first')
dialog.reset_style()
dialog.accept()
assert workspace.saved['first'] == DEFAULT_STYLE
app.setStyleSheet(stylesheet(True))
workspace.owner.theme_colors = dict(DARK)
workspace.preview_module_style('first', workspace.saved['first'])
app.processEvents()
assert first.note.palette().color(QPalette.ColorRole.Base).name() == DARK['surface']
assert first.note.palette().color(QPalette.ColorRole.Text).name() == DARK['text']
workspace.close()
print('PASS: module color scoping, composited opacity, live preview, cancel, validation, save, reset and theme inheritance')
