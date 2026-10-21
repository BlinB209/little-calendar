"""Editable starter: use relative imports for files inside this plugin."""
from calendar_plugin_api import QtCore, QtWidgets
from .helpers import date_label


def create_widget(context):
    widget = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(widget)
    label = QtWidgets.QLabel(date_label(context))
    label.setWordWrap(True)
    note = QtWidgets.QPlainTextEdit()
    note.setPlaceholderText('输入自动保存。修改此插件的 main.py 可以增加自己的功能。')
    note.setPlainText(context.get_value('text', ''))
    note.textChanged.connect(context.guard(lambda: context.set_value('text', note.toPlainText())))
    button = QtWidgets.QPushButton('插入所选日期')
    button.clicked.connect(context.guard(lambda checked=False: note.appendPlainText(context.selected_date.isoformat())))
    layout.addWidget(label)
    layout.addWidget(note)
    layout.addWidget(button)
    # Parenting the timer to the widget and registering cleanup avoids orphan timers.
    timer = QtCore.QTimer(widget)
    timer.timeout.connect(context.guard(lambda: label.setText(date_label(context))))
    timer.start(1000)
    context.on_cleanup(timer.stop)
    return widget
