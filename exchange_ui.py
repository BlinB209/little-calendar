"""Import/export dialog for the portable formats; an import is previewed first."""
from datetime import datetime
import uuid
from pathlib import Path

from qt_compat import (QDialog, QVBoxLayout, QLabel, QPushButton, QFileDialog,
                       QMessageBox, QPlainTextEdit)
from backup import data_root, export_backup
from exchange import export_ics, export_csv, import_csv


class ExchangeDialog(QDialog):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.setWindowTitle('导入导出')
        self.resize(560, 420)
        box = QVBoxLayout(self)
        intro = QLabel('把事项导出成通用格式，或从表格把事项合并进来。\n'
                       '导出的日历文件（.ics）可以在手机和常见日历中查看；表格（.csv）可用 Excel 打开。\n'
                       '导入只新增，不删除也不覆盖已有事项；导入前会自动保存一份原数据备份。')
        intro.setWordWrap(True)
        box.addWidget(intro)
        for title, callback in [('导出日历文件（.ics）…', self.export_calendar),
                                ('导出事项表格（.csv）…', self.export_table),
                                ('从表格导入（.csv）…', self.import_table)]:
            button = QPushButton(title)
            button.clicked.connect(callback)
            box.addWidget(button)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setPlaceholderText('从表格导入时，这里会先显示将要新增和跳过的条目。')
        self.preview.setVisible(False)
        box.addWidget(self.preview, 1)
        self.status = QLabel('数据目录：' + str(data_root(owner.store)))
        self.status.setWordWrap(True)
        box.addWidget(self.status)
        done = QPushButton('关闭')
        done.clicked.connect(self.reject)
        box.addWidget(done)

    def _name(self, suffix):
        return '小日历-事项-' + datetime.now().strftime('%Y%m%d-%H%M') + suffix

    def _summary(self, report):
        lines = [f'将新增 {len(report["added"])} 条事项，涉及 {len(report["changed_days"])} 天。']
        if report['skipped']:
            lines.append(f'跳过 {len(report["skipped"])} 条：')
            for item in report['skipped'][:12]:
                detail = f'  第 {item["line"]} 行：{item["reason"]}'
                if item.get('date'):
                    detail += f'（{item["date"]}）'
                lines.append(detail)
            if len(report['skipped']) > 12:
                lines.append(f'  ……还有 {len(report["skipped"]) - 12} 条')
        return '\n'.join(lines)

    def export_calendar(self):
        path, _ = QFileDialog.getSaveFileName(self, '导出日历文件', self._name('.ics'), '日历文件 (*.ics)')
        if path:
            self._export(path, export_ics, '日历文件已导出：')

    def export_table(self):
        path, _ = QFileDialog.getSaveFileName(self, '导出事项表格', self._name('.csv'), '表格文件 (*.csv)')
        if path:
            self._export(path, export_csv, '表格已导出：')

    def _export(self, path, writer, message):
        try:
            self.owner.save_session()
            target = writer(self.owner.store, path)
        except Exception as error:
            QMessageBox.warning(self, '导出未完成', str(error))
            return
        self.status.setText(message + str(target))

    def import_table(self):
        path, _ = QFileDialog.getOpenFileName(self, '选择事项表格', '', '表格文件 (*.csv)')
        if path:
            self.import_path(path)

    def import_path(self, path):
        import app as application
        try:
            report = import_csv(self.owner.store, path, min_year=application.MIN_YEAR,
                                max_year=application.MAX_YEAR, apply=False)
        except Exception as error:
            QMessageBox.warning(self, '无法读取表格', str(error))
            return
        self.preview.setPlainText(self._summary(report))
        self.preview.setVisible(True)
        if not report['added']:
            self.status.setText('这个文件没有可以新增的事项；已有内容没有改动。')
            return
        reply = QMessageBox.question(
            self, '导入这些事项？',
            self._summary(report) + '\n\n导入只新增，不删除也不修改已有事项。是否继续？',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel)
        if reply != QMessageBox.StandardButton.Yes:
            self.status.setText('已取消导入，没有改动任何内容。')
            return
        backup = data_root(self.owner.store) / ('recovery-' + datetime.now().strftime('%Y%m%d-%H%M%S')
                                                + '-' + uuid.uuid4().hex[:6] + '.zip')
        try:
            export_backup(self.owner.store, backup)
            written = import_csv(self.owner.store, path, min_year=application.MIN_YEAR,
                                 max_year=application.MAX_YEAR)
        except Exception as error:
            QMessageBox.warning(self, '导入未完成', str(error))
            return
        self.owner.reload_entries()
        self.status.setText(f'已导入 {len(written["added"])} 条事项；原数据备份：{backup.name}')
        self.owner.status.setText(f'已导入 {len(written["added"])} 条事项，可继续编辑')
