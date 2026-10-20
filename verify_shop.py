"""Exercise the actual shop controls against a temporary calendar database."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import json
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QCoreApplication, QEvent
from PySide6.QtWidgets import QPushButton, QCheckBox, QMessageBox
from PySide6.QtTest import QTest
from app import QApplication, CalendarApp, Store, configure_style
from module_shop import ModuleShop


app = QApplication([])
configure_style(app)
screenshots = Path('build')
screenshots.mkdir(exist_ok=True)


def settle():
    app.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


def click_named(shop, name):
    settle()
    button = shop.findChild(QPushButton, name)
    assert button is not None, name
    button.click()
    settle()


with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
    db_path = Path(folder)/'shop.sqlite3'
    window = CalendarApp(Store(db_path))
    window.show()
    shop = ModuleShop(window.body)
    shop.show()
    settle()
    assert len(shop.visible_plugin_ids) == 5
    assert shop._columns == 2
    assert shop.grab().save(str(screenshots/'shop-light.png'))
    shop.search.setText('便签')
    assert shop.visible_plugin_ids == ['notes']
    shop.search.setText('没有这种配件')
    assert not shop.visible_plugin_ids
    assert any('没有找到匹配' in child.text() for child in shop.cards)
    shop.search.clear()
    shop.category.setCurrentText('日期与时间')
    assert set(shop.visible_plugin_ids) == {'clock', 'month'}
    shop.category.setCurrentIndex(0)

    click_named(shop, 'add:notes')
    assert shop.isVisible(), 'Adding an accessory must leave the shop usable'
    first = window.body.records[-1]['id']
    window.body.docks[first].widget().text.setPlainText('保存我的想法')
    click_named(shop, 'add:notes')
    second = window.body.records[-1]['id']
    assert first != second
    assert len(window.body.records) == 2
    assert not window.body.docks[first].isHidden()

    def accept_disable():
        for widget in app.topLevelWidgets():
            if isinstance(widget, QMessageBox):
                widget.button(QMessageBox.StandardButton.Yes).click()

    QTimer.singleShot(30, accept_disable)
    click_named(shop, 'disable:notes')
    assert 'notes' not in window.body.installed
    assert window.body.docks[first].isHidden() and window.body.docks[second].isHidden()
    shop.filter.setCurrentIndex(2)
    assert shop.visible_plugin_ids == ['notes']
    click_named(shop, 'restore:notes')
    assert len(window.body.records) == 2, 'Restore must not create duplicates'
    assert not window.body.docks[first].isHidden()
    assert window.body.docks[first].widget().text.toPlainText() == '保存我的想法'
    shop.filter.setCurrentIndex(0)

    shop.tabs.setCurrentIndex(1)
    settle()
    toggle = shop.findChild(QCheckBox, 'visible:'+first)
    toggle.setChecked(False)
    settle()
    assert window.body.docks[first].isHidden()
    shop.set_visible(first, True)
    assert not window.body.docks[first].isHidden()
    assert shop.rename_module(first, '旅行灵感')
    assert shop.rename_module('main-calendar', '我的日历')
    assert not shop.rename_module(first, '  ')
    assert window.body.docks[first].windowTitle() == '旅行灵感'
    assert shop.grab().save(str(screenshots/'shop-desktop.png'))

    example_path = Path(folder)/'阅读便签.json'
    shop.export_example(example_path)
    assert json.loads(example_path.read_text(encoding='utf-8'))['kind'] == 'note'
    plugin = shop.import_path(example_path)
    assert plugin['id'] in shop.visible_plugin_ids
    click_named(shop, 'add:'+plugin['id'])
    try:
        shop.import_path(example_path)
    except ValueError:
        pass
    else:
        raise AssertionError('Duplicate import should be rejected without modifying data')
    assert len(window.body.records) == 3

    shop.resize(660, 510)
    settle()
    assert shop._columns == 1
    assert shop.scroll.horizontalScrollBar().maximum() == 0
    assert shop.cards[0].height() >= 316
    assert shop.findChild(QPushButton, 'add:notes').height() >= 28
    assert shop.grab().save(str(screenshots/'shop-small.png'))
    shop.locate(first)
    assert not shop.isVisible()
    assert window.body.order[-1] == first
    assert not window.body.docks[first].isHidden()

    window.change_theme(True)
    dark = ModuleShop(window.body)
    dark.show()
    settle()
    assert dark.colors['background'] == window.theme_colors['background']
    assert dark.grab().save(str(screenshots/'shop-dark.png'))
    dark.close()
    window.close()
    window.store.db.close()

    restored = CalendarApp(Store(db_path))
    restored.show()
    settle()
    assert restored.body.docks[first].windowTitle() == '旅行灵感'
    assert restored.body.docks['main-calendar'].windowTitle() == '我的日历'
    assert restored.body.docks[first].widget().text.toPlainText() == '保存我的想法'
    assert len(restored.body.records) == 3
    restored.close()
    restored.store.db.close()

print('PASS: shop search/category/state filters, add/disable/restore controls, hide/locate/rename, example import, restart persistence and light/dark/small layouts')
