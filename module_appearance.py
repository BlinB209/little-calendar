"""Per-module colors and composited opacity, shared by all module types.

Workspace owns persistence and supplies get_module_style, preview_module_style,
and set_module_style. Preview changes never write to the database.
"""
import re
import sys
from qt_compat import (Qt, QColor, QWidget, QDialog, QVBoxLayout, QHBoxLayout,
                       QFormLayout, QLabel, QPushButton, QLineEdit, QSpinBox,
                       QColorDialog, QDialogButtonBox)

if sys.platform == 'linux':
    from PyQt6.QtWidgets import QGraphicsOpacityEffect, QSlider
else:
    from PySide6.QtWidgets import QGraphicsOpacityEffect, QSlider


DEFAULT_STYLE = dict(background='', foreground='', opacity=100)


def valid_color(value):
    """Only literal RGB colors may be inserted into module stylesheets."""
    return isinstance(value, str) and bool(re.fullmatch(r'#[0-9a-fA-F]{6}', value))


def normalize_style(value, legacy=''):
    """Read old module-color keys, and tolerate malformed stored settings.

    An explicit empty background in the new record means 'follow the theme';
    it must not resurrect an older custom color when the user resets a module.
    """
    source = value if isinstance(value, dict) else {}
    result = dict(DEFAULT_STYLE)
    background = source.get('background', legacy)
    if valid_color(background):
        result['background'] = background.lower()
    if valid_color(source.get('foreground')):
        result['foreground'] = source['foreground'].lower()
    opacity = source.get('opacity', 100)
    try:
        opacity = int(opacity) if not isinstance(opacity, bool) else 100
    except (TypeError, ValueError, OverflowError):
        opacity = 100
    result['opacity'] = max(15, min(100, opacity))
    return result


def contrasting_text(background):
    """Choose the higher-contrast text color using relative luminance."""
    color = QColor(background)
    channels = [color.redF(), color.greenF(), color.blueF()]
    linear = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in channels]
    luminance = sum(c * weight for c, weight in zip(linear, (.2126, .7152, .0722)))
    return '#111827' if luminance > .179 else '#f8fafc'


def resolved_colors(style, theme):
    style = normalize_style(style)
    background = style['background'] or theme['surface']
    foreground = style['foreground'] or (contrasting_text(background) if style['background'] else theme['text'])
    return background, foreground


def apply_panel_style(panel, style, theme):
    """Style only this panel and composite all its children over lower panels.

    QGraphicsOpacityEffect makes text, inputs and painted plugin widgets fade
    together. Setting an alpha background alone would leave their opaque
    child widgets covering the desktop.
    """
    style = normalize_style(style)
    background, foreground = resolved_colors(style, theme)
    rules = [f'''QFrame[freePanel="true"] {{
        background:{background}; border:1px solid {theme['border']}; border-radius:9px;
    }}''']
    # A stylesheet on a panel is scoped to that widget subtree, so sibling
    # modules and the settings dialog keep their own colors.
    if style['background'] or style['foreground']:
        rules.append(f'''QWidget {{color:{foreground};}}
            QLabel,QCheckBox,QRadioButton {{color:{foreground};background:transparent;}}
            QFrame#editorPanel {{background:{background};}}
            QLineEdit,QTextEdit,QPlainTextEdit,QListWidget,QSpinBox,QDoubleSpinBox,
            QComboBox,QPushButton,QToolButton,QAbstractItemView {{
                background:{background};color:{foreground};
                selection-background-color:{theme['accent']};selection-color:#ffffff;
            }}
            QCalendarWidget QWidget {{background:{background};color:{foreground};}}
            QPushButton:hover,QToolButton:hover {{background:{theme['hover']};color:{theme['text']};}}
            QPushButton:checked {{background:{theme['selected']};color:{theme['text']};}}
        ''')
    panel.setStyleSheet('\n'.join(rules))
    effect = panel.graphicsEffect()
    if style['opacity'] < 100:
        if not isinstance(effect, QGraphicsOpacityEffect):
            effect = QGraphicsOpacityEffect(panel)
            panel.setGraphicsEffect(effect)
        effect.setOpacity(style['opacity'] / 100)
        effect.setEnabled(True)
    elif isinstance(effect, QGraphicsOpacityEffect):
        # Disabling instead of deleting avoids repeated effects allocation
        # while dragging the slider through 100%.
        effect.setOpacity(1.0)
        effect.setEnabled(False)
    panel.update()
    return style


class ModuleAppearanceDialog(QDialog):
    """Live, cancelable edit of a single module's colors and opacity."""
    def __init__(self, workspace, key):
        super().__init__(workspace)
        self.workspace, self.key = workspace, key
        self.original = normalize_style(workspace.get_module_style(key))
        self.values = dict(self.original)
        self.inputs, self.swatches, self.default_labels = {}, {}, {}
        self._committed = False
        self.setWindowTitle('模块颜色与透明度 · ' + workspace.docks[key].windowTitle())
        self.setMinimumWidth(480)
        self.resize(560, 360)
        box = QVBoxLayout(self)
        introduction = QLabel('为这个模块单独设置外观。更改会实时显示在工作区，取消即可还原。')
        introduction.setWordWrap(True)
        box.addWidget(introduction)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        for name, label, default in (('background', '模块底色', '跟随主题'),
                                     ('foreground', '文字颜色', '自动配色')):
            row = QWidget()
            layout = QHBoxLayout(row)
            layout.setContentsMargins(0, 0, 0, 0)
            picker = QPushButton('选择颜色…')
            picker.setObjectName('moduleColorPicker_' + name)
            picker.setToolTip('打开色板自由选择颜色')
            edit = QLineEdit(self.values[name])
            edit.setObjectName('moduleColor_' + name)
            edit.setPlaceholderText(default + '（留空）')
            edit.setMaxLength(7)
            edit.setToolTip('输入 #RRGGBB，例如 #3768ab；留空使用默认颜色')
            clear = QPushButton(default)
            clear.setObjectName('moduleColorReset_' + name)
            clear.setToolTip('清除此项自定义颜色')
            self.inputs[name] = edit
            self.swatches[name] = picker
            self.default_labels[name] = default
            picker.clicked.connect(lambda checked=False, field=name: self.choose_color(field))
            clear.clicked.connect(edit.clear)
            edit.textChanged.connect(self.change_colors)
            layout.addWidget(picker)
            layout.addWidget(edit, 1)
            layout.addWidget(clear)
            form.addRow(label, row)
        opacity_row = QWidget()
        opacity_layout = QHBoxLayout(opacity_row)
        opacity_layout.setContentsMargins(0, 0, 0, 0)
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setObjectName('moduleOpacitySlider')
        self.opacity_slider.setRange(15, 100)
        self.opacity_slider.setValue(self.values['opacity'])
        self.opacity = QSpinBox()
        self.opacity.setObjectName('moduleOpacity')
        self.opacity.setRange(15, 100)
        self.opacity.setSuffix(' %')
        self.opacity.setValue(self.values['opacity'])
        self.opacity_slider.valueChanged.connect(self.opacity.setValue)
        self.opacity.valueChanged.connect(self.opacity_slider.setValue)
        self.opacity.valueChanged.connect(self.change_opacity)
        opacity_layout.addWidget(self.opacity_slider, 1)
        opacity_layout.addWidget(self.opacity)
        form.addRow('模块不透明度', opacity_row)
        box.addLayout(form)
        hint = QLabel('100% 完全不透明，数值越低越透明（最低 15%）。\n背景、文字和控件一起变化，可透见桌面背景和下层模块。')
        hint.setWordWrap(True)
        box.addWidget(hint)
        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.setStyleSheet('color:#c03737;')
        box.addWidget(self.error)
        box.addStretch()
        bottom = QHBoxLayout()
        reset = QPushButton('恢复主题默认')
        reset.setObjectName('moduleAppearanceReset')
        reset.setToolTip('清除本模块自定义颜色并恢复 100% 不透明度；保存后生效')
        reset.clicked.connect(self.reset_style)
        bottom.addWidget(reset)
        bottom.addStretch()
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText('保存')
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('取消')
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        bottom.addWidget(self.buttons)
        box.addLayout(bottom)
        self.update_swatches()

    def update_swatches(self):
        theme = self.workspace.owner.theme_colors
        background, foreground = resolved_colors(self.values, theme)
        for name, color in (('background', background), ('foreground', foreground)):
            self.swatches[name].setStyleSheet(
                f'background:{color};color:{contrasting_text(color)};border:1px solid {theme["border"]};padding:7px;')

    def choose_color(self, name):
        resolved = resolved_colors(self.values, self.workspace.owner.theme_colors)
        current = self.values[name] or resolved[0 if name == 'background' else 1]
        color = QColorDialog.getColor(QColor(current), self, '选择模块底色' if name == 'background' else '选择文字颜色')
        if color.isValid():
            self.inputs[name].setText(color.name())

    def change_colors(self, *_):
        valid = all(not edit.text().strip() or valid_color(edit.text().strip()) for edit in self.inputs.values())
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setEnabled(valid)
        self.error.setText('颜色请填写 #RRGGBB，例如 #3768ab；留空可恢复默认。' if not valid else '')
        if valid:
            for name, edit in self.inputs.items():
                self.values[name] = edit.text().strip().lower()
            self.preview()

    def change_opacity(self, value):
        self.values['opacity'] = value
        self.preview()

    def preview(self):
        self.workspace.preview_module_style(self.key, dict(self.values))
        self.update_swatches()

    def reset_style(self):
        self.values = dict(DEFAULT_STYLE)
        for edit in self.inputs.values():
            edit.blockSignals(True)
            edit.clear()
            edit.blockSignals(False)
        self.opacity.blockSignals(True)
        self.opacity.setValue(100)
        self.opacity.blockSignals(False)
        self.opacity_slider.blockSignals(True)
        self.opacity_slider.setValue(100)
        self.opacity_slider.blockSignals(False)
        self.error.clear()
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setEnabled(True)
        self.preview()

    def accept(self):
        if not self.buttons.button(QDialogButtonBox.StandardButton.Save).isEnabled():
            return
        if self.workspace.set_module_style(self.key, dict(self.values)) is False:
            # Workspace reports storage errors itself; keep the draft open so
            # the user can retry or cancel without mistaking it for a save.
            return
        self._committed = True
        super().accept()

    def done(self, result):
        if not self._committed:
            self.workspace.preview_module_style(self.key, dict(self.original))
        super().done(result)
