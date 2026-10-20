"""Exercise background selection through the UI and persistent cached images."""
import copy
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from pathlib import Path
import tempfile
from unittest.mock import patch

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QColor, QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QPushButton, QScrollArea, QDialog
from app import QApplication, CalendarApp, Store, configure_style
from preferences import PreferencesDialog, load_background, preferences


application = QApplication([])
configure_style(application)
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
    folder = Path(temporary)
    source = folder / '我的背景 晴天.png'
    picture = QImage(640, 400, QImage.Format.Format_RGB32)
    picture.fill(QColor('#f4b65b'))
    painter = QPainter(picture)
    painter.fillRect(0, 0, 320, 400, QColor('#73afcb'))
    painter.fillRect(210, 140, 260, 140, QColor('#9dbf75'))
    painter.end()
    assert picture.save(str(source))
    db_path = folder / 'calendar.sqlite3'
    window = CalendarApp(Store(db_path))
    window.show()
    application.processEvents()
    original = copy.deepcopy(window.custom)

    # Click the actual choose button; only the operating system picker is stubbed.
    dialog = PreferencesDialog(window)
    dialog.show()
    application.processEvents()
    choose_button = dialog.findChild(QPushButton, 'chooseBackgroundImage')
    with patch('preferences.QFileDialog.getOpenFileName', return_value=(str(source), '图片')):
        QTest.mouseClick(choose_button, Qt.MouseButton.LeftButton)
    application.processEvents()
    assert dialog.values['background_mode'] == 'image'
    assert dialog.controls['background_mode'].currentData() == 'image'
    assert dialog.values['cell_opacity'] == 65
    assert source.name in dialog.image_label.text()
    cached_path = Path(dialog.values['background_image'])
    assert cached_path.exists() and cached_path != source
    assert not dialog.preview_pixmap.isNull()
    assert window.custom == original, 'Draft selection must not change the calendar'
    dialog.controls['overlay'].setValue(0)
    application.processEvents()
    first_preview = dialog.preview.grab().toImage()
    dialog.controls['overlay'].setValue(90)
    application.processEvents()
    assert first_preview != dialog.preview.grab().toImage()
    dialog.controls['overlay'].setValue(10)
    build = Path(__file__).parent / 'build'
    build.mkdir(exist_ok=True)
    dialog.grab().save(str(build / 'background-preview.png'))
    dialog.resize(490, 480)
    application.processEvents()
    assert any(scroll.verticalScrollBar().maximum() > 0 for scroll in dialog.findChildren(QScrollArea))
    assert dialog.findChild(QPushButton, 'savePreferences').isVisible()
    dialog.grab().save(str(build / 'background-preview-small.png'))

    # Failed and cancelled selections retain the draft that was already valid.
    valid_draft = copy.deepcopy(dialog.values)
    invalid = folder / '损坏图片.png'
    invalid.write_bytes(b'not an image')
    with patch('preferences.QFileDialog.getOpenFileName', return_value=(str(invalid), '图片')), patch('preferences.QMessageBox.warning') as warning:
        QTest.mouseClick(choose_button, Qt.MouseButton.LeftButton)
        assert warning.call_count == 1
    assert dialog.values == valid_draft
    with patch('preferences.QFileDialog.getOpenFileName', return_value=('', '')):
        QTest.mouseClick(choose_button, Qt.MouseButton.LeftButton)
    assert dialog.values == valid_draft
    dialog.reject()
    assert window.custom == original
    assert preferences(window.store) == original

    # Drive CalendarApp's real modal opening and save handler.
    errors = []
    def select_and_save():
        active = next(widget for widget in application.topLevelWidgets()
                      if isinstance(widget, PreferencesDialog) and widget.isVisible())
        try:
            with patch('preferences.QFileDialog.getOpenFileName', return_value=(str(source), '图片')):
                QTest.mouseClick(active.findChild(QPushButton, 'chooseBackgroundImage'), Qt.MouseButton.LeftButton)
            QTest.mouseClick(active.findChild(QPushButton, 'savePreferences'), Qt.MouseButton.LeftButton)
        except BaseException as error:
            errors.append(error)
            active.reject()
    QTimer.singleShot(30, select_and_save)
    window.open_preferences()
    assert not errors, errors
    assert window.custom['background_mode'] == 'image'
    assert not window.background_pixmap.isNull()
    source.unlink()
    assert not load_background(window.custom).isNull(), 'Original removal must not break the cache'
    window.close()
    window.store.db.close()
    restored = CalendarApp(Store(db_path))
    assert restored.custom['background_image_name'] == '我的背景 晴天.png'
    assert not restored.background_pixmap.isNull()

    empty = PreferencesDialog(restored)
    empty.clear_image()
    empty.controls['background_mode'].setCurrentIndex(empty.controls['background_mode'].findData('image'))
    with patch('preferences.QMessageBox.warning') as warning:
        empty.accept()
        assert warning.call_count == 1
        assert empty.result() != QDialog.DialogCode.Accepted
    empty.reject()
    restored.close()
    restored.store.db.close()

print('PASS: actual choose/save button chain, preview updates, cancelled/invalid images, small-window scrolling, cached Chinese image path, source removal and restart')
