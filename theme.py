"""Shared colors for native controls and the custom-painted calendar."""
from string import Template

LIGHT = dict(background='#f3f5fa', surface='#ffffff', alternate='#f7f8fb',
    text='#25334b', secondary='#536078', muted='#68758a', dim='#9aa4b5',
    border='#cbd3e0', grid='#e9edf3', selected='#eef1ff', accent='#5369dc',
    hover='#edf0ff', handle='#d5dced', mark='#aebbd1', faded='#edf0f5',
    morning='#a97719', noon='#278674', evening='#7960b3')
DARK = dict(background='#141b27', surface='#1e293b', alternate='#192233',
    text='#e5edf8', secondary='#c0ccdf', muted='#9eafc8', dim='#75869f',
    border='#45546c', grid='#334158', selected='#303f65', accent='#6178e8',
    hover='#2c3c57', handle='#3e4d67', mark='#667a9a', faded='#182131',
    morning='#ebc674', noon='#7bd2bb', evening='#bea5f0')


def colors(dark=False, overrides=None):
    result = dict(DARK if dark else LIGHT)
    import re
    for key,value in (overrides or {}).items():
        if key in result and isinstance(value,str) and re.fullmatch(r'#[0-9a-fA-F]{6}',value):
            result[key] = value
    return result


def stylesheet(dark=False, overrides=None):
    return Template('''
        QWidget {color:$text;}
        QMainWindow,QDialog,QMessageBox {background:$background;}
        QFrame#editorPanel {background:$surface;border-radius:12px;}
        QLabel#mainTitle {font-size:20px;font-weight:600;color:$text;}
        QLabel#mainTitle,QLabel#modeHint,QLabel#localClock,QLabel#saveStatus {
            background:$background;border-radius:4px;padding:4px;
        }
        QLabel[muted="true"] {color:$muted;}
        QPushButton,QComboBox,QLineEdit,QPlainTextEdit,QTextEdit,QListWidget,QSpinBox {
            color:$text;background:$surface;border:1px solid $border;
            border-radius:6px;padding:7px;
            selection-background-color:$accent;selection-color:#ffffff;
        }
        QPushButton:hover {background:$hover;}
        QPushButton:disabled,QComboBox:disabled {color:$dim;background:$alternate;}
        QComboBox QAbstractItemView {
            color:$text;background:$surface;
            selection-color:#ffffff;selection-background-color:$accent;
        }
        QScrollArea {border:none;background:$background;}
        QSplitter::handle {background:$handle;border-radius:3px;}
        QSplitter::handle:hover {background:$accent;}
        QPushButton:checked {background:$selected;border:2px solid $accent;}
        QLabel {color:$secondary;}
        QCheckBox {color:$text;spacing:4px;background:$background;border-radius:3px;padding:2px;}
        QDockWidget {color:$text;}
        QDockWidget::title {background:$alternate;padding:6px;}
        QMainWindow::separator {background:$handle;width:8px;height:8px;}
        QToolTip {color:$text;background:$surface;border:1px solid $border;}
    ''').substitute(colors(dark, overrides))
