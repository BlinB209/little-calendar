from datetime import datetime
from pathlib import Path
from qt_compat import QDialog, QVBoxLayout, QLabel, QPushButton, QFileDialog, QMessageBox
from backup import export_backup, PreparedRestore, restore_backup, data_root


class BackupDialog(QDialog):
    def __init__(self,owner):
        super().__init__(owner)
        self.owner = owner
        self.setWindowTitle('备份与恢复')
        self.resize(560,300)
        box = QVBoxLayout(self)
        label = QLabel('备份包含事项、笔迹、布局、外观、背景图片、插件源码与插件数据。\n恢复会替换当前数据，恢复前会自动生成一份原数据备份。\n恢复后的 Python 插件默认停用，需要重新确认启用。')
        label.setWordWrap(True)
        box.addWidget(label)
        for title,callback in [('导出整套备份…',self.export),('从备份恢复…',self.restore)]:
            button = QPushButton(title)
            button.clicked.connect(callback)
            box.addWidget(button)
        self.status = QLabel('数据目录：'+str(data_root(owner.store)))
        self.status.setWordWrap(True)
        box.addWidget(self.status)
        done = QPushButton('关闭')
        done.clicked.connect(self.reject)
        box.addWidget(done)

    def export(self):
        path,_ = QFileDialog.getSaveFileName(self,'导出整套备份','小日历备份-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.zip','日历备份 (*.zip)')
        if not path:
            return
        if not path.lower().endswith('.zip'):
            path += '.zip'
        try:
            self.owner.save_session()
            export_backup(self.owner.store,path)
            self.status.setText('备份已保存：'+path)
        except Exception as exc:
            QMessageBox.warning(self,'备份未完成',str(exc))

    def restore(self):
        path,_ = QFileDialog.getOpenFileName(self,'选择日历备份','','日历备份 (*.zip)')
        if path:
            self.restore_path(path)

    def restore_path(self,path):
        prepared = None
        try:
            prepared = PreparedRestore(path)
            # Validate through the actual application before touching user data.
            import sys
            from app import CalendarApp, Store, configure_style
            from qt_compat import QTimer
            original_args = list(sys.argv)
            probe = None
            from app import QApplication
            existing_windows = set(QApplication.topLevelWidgets())
            original_font = QApplication.instance().font()
            probe_store = Store(prepared.root/'calendar.sqlite3')
            try:
                sys.argv.append('--safe-mode')
                probe = CalendarApp(probe_store)
            finally:
                sys.argv[:] = original_args
                for candidate in set(QApplication.topLevelWidgets())-existing_windows:
                    for timer in candidate.findChildren(QTimer):
                        timer.stop()
                    if hasattr(candidate,'body'):
                        candidate.body.restoring = True
                        candidate.body.shutdown_plugins()
                    candidate.hide()
                    candidate.deleteLater()
                probe_store.db.close()
                configure_style(QApplication.instance(),self.owner.dark,self.owner.custom['overrides'])
                QApplication.instance().setProperty('calendarCustom',self.owner.custom)
                QApplication.instance().setFont(original_font)
            reply = QMessageBox.question(self,'恢复并替换当前数据？',
                '备份已通过校验。将替换事项、笔迹、模块、背景及设置，并重新打开日历。\n'
                '当前数据会先备份到数据目录的 recovery-*.zip。第三方插件恢复后停用。',
                QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Cancel)
            if reply != QMessageBox.StandardButton.Yes:
                return
            owner = self.owner
            owner.save_session()
            # Quiesce callbacks before replacing files/database and never let the
            # old window write its in-memory state over restored settings.
            owner.body.restoring = True
            for timer in owner.findChildren(QTimer):
                timer.stop()
            owner.body.shutdown_plugins()
            try:
                recovery = restore_backup(owner.store,prepared)
            except Exception:
                owner._replacement = CalendarApp(owner.store)
                owner._replacement.show()
                owner._skip_save = True
                self.reject()
                owner.close()
                raise
            owner._skip_save = True
            owner._replacement = CalendarApp(owner.store)
            owner._replacement.show()
            owner._replacement.status.setText('恢复完成；原数据备份：'+str(recovery))
            self.accept()
            owner.close()
        except Exception as exc:
            QMessageBox.warning(self,'恢复未完成',str(exc))
        finally:
            if prepared:
                prepared.close()
