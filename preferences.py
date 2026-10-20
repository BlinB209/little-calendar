import copy
import hashlib
import math
import os
import re
import tempfile
from pathlib import Path
from qt_compat import *

DEFAULTS = dict(background_mode='solid', background_color='', gradient_color='#b7c8ee',
    background_image='', background_image_name='', image_fit='cover', overlay=18, cell_opacity=92,
    font_family='', font_size=14, font_auto=True, overrides={},
    rule='past', mark_color='', mark_width=2, mark_opacity=65,
    show_ink=True, show_stamps=True, show_auto=True,
    pen_width=4, pen_opacity=90, eraser_size=22, stamp='circle', stamp_text='重要',
    recent_colors=[], favorite_colors=[])


COLOR_KEYS = ('surface', 'text', 'secondary', 'muted', 'dim', 'accent', 'grid',
    'selected', 'morning', 'noon', 'evening', 'alternate', 'border', 'hover',
    'handle', 'mark', 'faded', 'background')
CHOICES = dict(background_mode=('solid', 'gradient', 'image'),
    image_fit=('cover', 'contain', 'center', 'tile'),
    rule=('past', 'weekend', 'completed'),
    stamp=('circle', 'box', 'cross', 'underline', 'fill', 'text'))
RANGES = dict(overlay=(0, 95), cell_opacity=(10, 100), font_size=(10, 32),
    mark_width=(1, 12), mark_opacity=(10, 100), pen_width=(1, 40),
    pen_opacity=(5, 100), eraser_size=(5, 80))


def valid_color(value):
    """Keep persisted colors in the same opaque RGB format as the theme."""
    if isinstance(value, str) and re.fullmatch(r'#[0-9a-fA-F]{6}', value):
        return value.lower()
    return ''


def normalize_preferences(saved):
    """Invalid or older saved values should never prevent the app opening."""
    result = copy.deepcopy(DEFAULTS)
    if not isinstance(saved, dict):
        return result
    for key, choices in CHOICES.items():
        if isinstance(saved.get(key), str) and saved[key] in choices:
            result[key] = saved[key]
    for key, (low, high) in RANGES.items():
        value = saved.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
            result[key] = max(low, min(high, round(value)))
    for key in ('font_auto', 'show_ink', 'show_stamps', 'show_auto'):
        if isinstance(saved.get(key), bool):
            result[key] = saved[key]
    for key in ('background_color', 'gradient_color', 'mark_color'):
        result[key] = valid_color(saved.get(key)) or DEFAULTS[key]
    for key, limit in (('font_family', 200), ('background_image', 4096), ('background_image_name', 255), ('stamp_text', 16)):
        value = saved.get(key)
        if isinstance(value, str) and '\x00' not in value:
            result[key] = value[:limit]
    overrides = saved.get('overrides', {})
    if isinstance(overrides, dict):
        result['overrides'] = {key: valid_color(value) for key, value in overrides.items()
                               if key in COLOR_KEYS and valid_color(value)}
    for key, limit in (('recent_colors', 12), ('favorite_colors', 100)):
        if isinstance(saved.get(key), list):
            result[key] = list(dict.fromkeys(valid_color(v) for v in saved[key] if valid_color(v)))[:limit]
    return result


def preferences(store):
    return normalize_preferences(store.get('customization:v1', {}))


def read_background_image(path):
    if not path:
        raise ValueError('尚未选择图片，请先点击“选择本地图片”')
    path = Path(path)
    if not path.is_file():
        raise ValueError('图片不存在或已被移动，请重新选择图片')
    if path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError('请选择不超过 64 MB 的图片')
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    size = reader.size()
    if not size.isValid() or size.width()*size.height() > 40_000_000 or not reader.canRead():
        raise ValueError('请选择可读取且不超过 4000 万像素的图片')
    # Keep the shared paint cache bounded, even for camera originals.
    if max(size.width(), size.height()) > 4096:
        reader.setScaledSize(size.scaled(4096, 4096, Qt.AspectRatioMode.KeepAspectRatio))
    image = reader.read()
    if image.isNull():
        raise ValueError('图片无法完整解码，请重新选择图片')
    return image


def cache_background_image(store, path):
    source = Path(path)
    image = read_background_image(source)
    digest = hashlib.sha256(b'little-calendar-background-v1')
    with source.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    db_file = store.db.execute('PRAGMA database_list').fetchone()[2]
    if db_file:
        folder = Path(db_file).parent / 'backgrounds'
    else:
        data_root = os.environ.get('LOCALAPPDATA') if os.name == 'nt' else os.environ.get('XDG_DATA_HOME')
        folder = Path(data_root or str(Path.home() / '.local/share')) / 'LittleCalendar' / 'backgrounds'
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / (digest.hexdigest()[:24] + '.png')
    # Save a decoded, orientation-corrected copy independently of the source.
    # Atomic replacement also repairs a previously interrupted cache write.
    with tempfile.NamedTemporaryFile(dir=folder, suffix='.png', delete=False) as stream:
        temporary = Path(stream.name)
    try:
        if not image.save(str(temporary), 'PNG'):
            raise OSError('无法保存背景图片')
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return str(target)


def load_background(prefs):
    if prefs.get('background_image'):
        try:
            return QPixmap.fromImage(read_background_image(prefs['background_image']))
        except (OSError, ValueError):
            pass
    return QPixmap()


def paint_background(painter, rect, prefs, theme, pixmap):
    if rect.isEmpty():
        return
    painter.save()
    painter.setClipRect(rect, Qt.ClipOperation.IntersectClip)
    base = prefs.get('background_color') or theme['background']
    painter.fillRect(rect, QColor(base))
    mode = prefs.get('background_mode', 'solid')
    if mode == 'gradient':
        gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
        gradient.setColorAt(0, QColor(base))
        gradient.setColorAt(1, QColor(prefs['gradient_color']))
        painter.fillRect(rect, gradient)
    elif mode == 'image' and not pixmap.isNull():
        fit = prefs.get('image_fit', 'cover')
        if fit == 'tile':
            painter.drawTiledPixmap(rect, pixmap)
        elif fit == 'center':
            painter.drawPixmap(QPointF(rect.x()+(rect.width()-pixmap.width())/2, rect.y()+(rect.height()-pixmap.height())/2), pixmap)
        else:
            ratio = max(rect.width()/pixmap.width(), rect.height()/pixmap.height()) if fit == 'cover' else min(rect.width()/pixmap.width(), rect.height()/pixmap.height())
            w, h = pixmap.width()*ratio, pixmap.height()*ratio
            painter.drawPixmap(QRectF(rect.x()+(rect.width()-w)/2, rect.y()+(rect.height()-h)/2, w, h), pixmap, QRectF(pixmap.rect()))
        shade = QColor(theme['background'])
        shade.setAlpha(round(255*prefs.get('overlay',18)/100))
        painter.fillRect(rect, shade)
    painter.restore()


class Background(QWidget):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner

    def paintEvent(self, event):
        p = QPainter(self)
        paint_background(p, QRectF(self.rect()), self.owner.custom, self.owner.theme_colors, self.owner.background_pixmap)


class BackgroundPreview(QWidget):
    """Render draft settings without changing the live calendar or its store."""
    def __init__(self, dialog):
        super().__init__(dialog)
        self.dialog = dialog
        self.setMinimumHeight(180)
        self.setObjectName('backgroundPreview')

    def paintEvent(self, event):
        prefs = self.dialog.values
        theme = dict(self.dialog.owner.theme_colors)
        theme.update(prefs['overrides'])
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        paint_background(painter, QRectF(self.rect()), prefs, theme, self.dialog.preview_pixmap)
        font = QFont(prefs['font_family'] or self.dialog.owner.font().family())
        font.setPixelSize(prefs['font_size'])
        painter.setFont(font)
        inset, gap = 14, 7
        width = (self.width() - 2 * inset - 2 * gap) / 3
        height = self.height() - 2 * inset
        for index, (day, title, period) in enumerate((('18', '早 · 读书', 'morning'), ('19', '午 · 散步', 'noon'), ('20', '晚 · 看电影', 'evening'))):
            cell = QRectF(inset + index * (width + gap), inset, width, height)
            fill = QColor(theme['surface'])
            fill.setAlpha(round(255 * prefs['cell_opacity'] / 100))
            painter.setBrush(fill)
            painter.setPen(QColor(theme['grid']))
            painter.drawRoundedRect(cell, 7, 7)
            painter.setPen(QColor(theme['text']))
            painter.drawText(cell.adjusted(10, 12, -6, -8), Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft, day)
            painter.setPen(QColor(theme[period]))
            painter.drawText(cell.adjusted(10, 50, -6, -8), Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft, title)
        painter.end()


class PreferencesDialog(QDialog):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.values = normalize_preferences(owner.custom)
        self.controls = {}
        self.color_controls = []
        self.preview_pixmap = load_background(self.values)
        self.setWindowTitle('自定义外观与标记')
        available = self.screen().availableGeometry()
        self.resize(min(700, available.width() - 40), min(800, available.height() - 60))
        box = QVBoxLayout(self)
        tabs = QTabWidget()
        box.addWidget(tabs)
        appearance = QWidget()
        appearance_box = QVBoxLayout(appearance)
        self.preview = BackgroundPreview(self)
        preview_hint = QLabel('效果预览 · 修改设置后立即更新，点击“保存并应用”才会改变日历')
        preview_hint.setWordWrap(True)
        appearance_box.addWidget(preview_hint)
        appearance_box.addWidget(self.preview)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        appearance_box.addLayout(form)
        self.combo(form,'背景类型','background_mode',[('纯色','solid'),('渐变','gradient'),('本地图片','image')])
        self.color(form, '背景颜色', 'background_color', owner.theme_colors['background'])
        self.color(form, '渐变终点', 'gradient_color', '#b7c8ee')
        self.image_label = QLabel()
        self.image_label.setObjectName('backgroundImageStatus')
        self.image_label.setWordWrap(True)
        image_actions = QWidget()
        image_actions_box = QHBoxLayout(image_actions)
        image_actions_box.setContentsMargins(0, 0, 0, 0)
        choose = QPushButton('选择本地图片…')
        choose.setObjectName('chooseBackgroundImage')
        choose.clicked.connect(self.choose_image)
        self.clear_image_button = QPushButton('移除图片')
        self.clear_image_button.clicked.connect(self.clear_image)
        image_actions_box.addWidget(choose)
        image_actions_box.addWidget(self.clear_image_button)
        form.addRow('背景图片', image_actions)
        form.addRow(self.image_label)
        self.combo(form,'图片显示','image_fit',[('铺满','cover'),('完整显示','contain'),('居中','center'),('平铺','tile')])
        self.spin(form, '图片遮罩（%）', 'overlay', 0, 95)
        self.spin(form, '日期格底色不透明度（%）', 'cell_opacity', 10, 100)
        hint = QLabel('图片会保存到本机日历数据目录，原图移动后仍可使用。\n遮罩越低，图片越清晰；日期格底色越低，透出的背景越多。')
        hint.setWordWrap(True)
        form.addRow(hint)
        family = QFontComboBox()
        self.controls['font_family'] = family
        family.setCurrentFont(QFont(self.values['font_family'] or owner.font().family()))
        family.currentFontChanged.connect(lambda font: self.set_value('font_family', font.family()))
        form.addRow('字体', family)
        self.spin(form, '基础字号（像素）', 'font_size', 10, 32)
        self.check(form, '字号跟随模块大小缩放', 'font_auto')
        self.add_scroll_tab(tabs, appearance, '背景与字体')
        palette = QWidget()
        palette_form = QFormLayout(palette)
        for label,key in [('模块底色','surface'),('文字','text'),('说明文字','secondary'),('辅助文字','muted'),('强调色','accent'),('日期边框','grid'),('选中日期','selected'),('早间事项','morning'),('午间事项','noon'),('晚间事项','evening')]:
            self.color(palette_form,label,key,owner.theme_colors[key], override=True)
        palette_form.addRow(QLabel('自选配色优先于浅色/夜间主题。模块标题右键可单独改底色。'))
        self.add_scroll_tab(tabs, palette, '全局颜色')
        markers = QWidget()
        marker_form = QFormLayout(markers)
        self.combo(marker_form,'自动标记条件','rule',[('今天之前','past'),('周末','weekend'),('当日事项全部完成','completed')])
        self.color(marker_form,'自动标记颜色','mark_color',owner.theme_colors['mark'])
        self.spin(marker_form,'自动标记粗细','mark_width',1,12)
        self.spin(marker_form,'自动标记不透明度 %','mark_opacity',10,100)
        self.spin(marker_form,'画笔粗细','pen_width',1,40)
        self.spin(marker_form,'画笔不透明度 %','pen_opacity',5,100)
        self.spin(marker_form,'橡皮擦半径','eraser_size',5,80)
        self.combo(marker_form,'印章形状','stamp',[('圆圈','circle'),('方框','box'),('叉号','cross'),('下划线','underline'),('色块','fill'),('文字标签','text')])
        text = QLineEdit(self.values['stamp_text'])
        self.controls['stamp_text'] = text
        text.setMaxLength(16)
        text.textChanged.connect(lambda text: self.set_value('stamp_text', text))
        marker_form.addRow('标签文字',text)
        self.check(marker_form,'显示自由笔迹','show_ink')
        self.check(marker_form,'显示日期印章','show_stamps')
        self.check(marker_form,'显示自动标记','show_auto')
        self.add_scroll_tab(tabs, markers, '标记与图层')
        defaults = QPushButton('恢复默认外观和标记设置')
        def reset():
            if QMessageBox.question(self,'恢复默认','恢复默认自定义设置？日历事项、模块内容和已有标记保留。') == QMessageBox.StandardButton.Yes:
                self.values = copy.deepcopy(DEFAULTS)
                self.preview_pixmap = QPixmap()
                self.sync_controls()
        defaults.clicked.connect(reset)
        box.addWidget(defaults)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('保存并应用')
        buttons.button(QDialogButtonBox.StandardButton.Ok).setObjectName('savePreferences')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('取消修改')
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        box.addWidget(buttons)
        self.refresh_preview()

    def add_scroll_tab(self, tabs, content, title):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        tabs.addTab(scroll, title)

    def set_value(self, key, value):
        self.values[key] = value
        self.refresh_preview()

    def refresh_preview(self):
        if not hasattr(self, 'image_label'):
            return
        path = self.values['background_image']
        if path:
            name = self.values.get('background_image_name') or Path(path).name
            status = '已选择：' if not self.preview_pixmap.isNull() else '图片不可用，请重新选择：'
            self.image_label.setText(status + name)
            self.image_label.setToolTip(path)
        else:
            self.image_label.setText('尚未选择图片。点击“选择本地图片”后会自动启用图片背景。')
            self.image_label.setToolTip('')
        self.clear_image_button.setEnabled(bool(path))
        for key in ('image_fit', 'overlay'):
            if key in self.controls:
                self.controls[key].setEnabled(self.values['background_mode'] == 'image')
        self.preview.update()

    def sync_controls(self):
        for key, widget in self.controls.items():
            widget.blockSignals(True)
            if isinstance(widget, QFontComboBox):
                widget.setCurrentFont(QFont(self.values[key] or self.owner.font().family()))
            elif isinstance(widget, QComboBox):
                widget.setCurrentIndex(max(0, widget.findData(self.values[key])))
            elif isinstance(widget, QCheckBox):
                widget.setChecked(self.values[key])
            elif isinstance(widget, QSpinBox):
                widget.setValue(self.values[key])
            else:
                widget.setText(self.values[key])
            widget.blockSignals(False)
        for button, key, fallback, override in self.color_controls:
            values = self.values['overrides'] if override else self.values
            button.setText(values.get(key) or fallback)
        self.refresh_preview()

    def clear_image(self):
        self.values.update(background_image='', background_image_name='', background_mode='solid')
        self.preview_pixmap = QPixmap()
        self.sync_controls()

    def accept(self):
        if self.values['background_mode'] == 'image' and self.preview_pixmap.isNull():
            QMessageBox.warning(self, '请选择背景图片', '尚未选择可用的图片。请点击“选择本地图片”，或将背景类型改为纯色或渐变。')
            return
        super().accept()

    def combo(self, form, title, key, items):
        widget = QComboBox()
        self.controls[key] = widget
        widget.setObjectName(key)
        for text,value in items:
            widget.addItem(text,value)
        widget.setCurrentIndex(max(0,widget.findData(self.values[key])))
        widget.currentIndexChanged.connect(lambda _: self.set_value(key, widget.currentData()))
        form.addRow(title,widget)

    def spin(self, form, title, key, low, high):
        widget = QSpinBox()
        self.controls[key] = widget
        widget.setObjectName(key)
        widget.setRange(low,high)
        widget.setValue(self.values[key])
        widget.valueChanged.connect(lambda value: self.set_value(key, value))
        form.addRow(title,widget)

    def check(self, form, title, key):
        widget = QCheckBox(title)
        self.controls[key] = widget
        widget.setObjectName(key)
        widget.setChecked(self.values[key])
        widget.toggled.connect(lambda value: self.set_value(key, value))
        form.addRow(widget)

    def color(self, form, title, key, fallback, override=False):
        values = self.values['overrides'] if override else self.values
        button = QPushButton(values.get(key) or fallback)
        self.color_controls.append((button, key, fallback, override))
        def choose():
            values = self.values['overrides'] if override else self.values
            color = QColorDialog.getColor(QColor(values.get(key) or fallback),self,title)
            if color.isValid():
                values[key] = color.name()
                button.setText(color.name())
                self.refresh_preview()
        button.clicked.connect(choose)
        form.addRow(title,button)

    def choose_image(self):
        path, _ = QFileDialog.getOpenFileName(self,'选择本地背景图片','','图片 (*.png *.jpg *.jpeg *.webp *.bmp *.gif *.tif *.tiff)')
        if not path:
            return
        try:
            target = cache_background_image(self.owner.store, path)
            self.values['background_image'] = target
            self.values['background_image_name'] = Path(path).name
            self.values['background_mode'] = 'image'
            if self.values['cell_opacity'] == DEFAULTS['cell_opacity']:
                self.values['cell_opacity'] = 65
            self.preview_pixmap = load_background(self.values)
            self.sync_controls()
        except (OSError,ValueError) as exc:
            QMessageBox.warning(self,'无法使用图片',str(exc))
