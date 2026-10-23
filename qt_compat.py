import sys

if sys.platform == 'linux':
    from PyQt6.QtCore import Qt, QTimer, QByteArray, QDate, QRectF, QPointF
    from PyQt6.QtGui import QColor, QFont, QPainter, QPixmap, QLinearGradient, QImageReader
    from PyQt6.QtWidgets import (QWidget, QMainWindow, QDockWidget, QDialog,
        QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QPushButton, QComboBox,
        QCheckBox, QLineEdit, QTextEdit, QPlainTextEdit, QListWidget,
        QListWidgetItem, QSpinBox, QColorDialog, QFileDialog, QMessageBox,
        QDialogButtonBox, QTabWidget, QFontComboBox, QCalendarWidget, QMenu,
        QScrollArea, QSystemTrayIcon, QStyle)
else:
    from PySide6.QtCore import Qt, QTimer, QByteArray, QDate, QRectF, QPointF
    from PySide6.QtGui import QColor, QFont, QPainter, QPixmap, QLinearGradient, QImageReader
    from PySide6.QtWidgets import (QWidget, QMainWindow, QDockWidget, QDialog,
        QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QPushButton, QComboBox,
        QCheckBox, QLineEdit, QTextEdit, QPlainTextEdit, QListWidget,
        QListWidgetItem, QSpinBox, QColorDialog, QFileDialog, QMessageBox,
        QDialogButtonBox, QTabWidget, QFontComboBox, QCalendarWidget, QMenu,
        QScrollArea, QSystemTrayIcon, QStyle)
