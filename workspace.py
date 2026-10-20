"""Free desktop, built-in accessories and explicitly enabled Python plugins."""
import json
import re
import uuid
import sys
from datetime import datetime, date
from qt_compat import *
from plugin_runtime import PluginLibrary, PluginError, PluginApprovalRequired
from module_appearance import normalize_style, resolved_colors, apply_panel_style, ModuleAppearanceDialog

CATALOG = [
    dict(id='notes', title='便签', kind='note', description='独立保存的自由文字便签，可重复添加。'),
    dict(id='tasks', title='待办清单', kind='checklist', description='与每日事项分开管理的可勾选清单。'),
    dict(id='month', title='独立月历', kind='calendar', description='独立翻月，点击日期联动主日历和每日事项。'),
    dict(id='clock', title='数字时钟', kind='clock', description='本地日期与时间，随模块尺寸调整字体。'),
    dict(id='habit', title='习惯打卡', kind='habit', description='记录每日打卡，每天独立保存。'),
]
KINDS = {'note', 'checklist', 'calendar', 'clock', 'habit'}


def validate_plugin(value):
    if not isinstance(value, dict) or value.get('schema') != 1:
        raise ValueError('插件需要 schema: 1 的 JSON 对象')
    if not re.fullmatch(r'[a-z][a-z0-9_-]{1,63}', str(value.get('id', ''))):
        raise ValueError('插件 id 必须为 2–64 位小写字母、数字、下划线或连字符')
    if value.get('kind') not in KINDS:
        raise ValueError('不支持的模块类型；插件只能使用 note/checklist/calendar/clock/habit')
    if not isinstance(value.get('title'), str) or not 1 <= len(value['title']) <= 40:
        raise ValueError('插件标题长度必须为 1–40 字符')
    if set(value) - {'schema', 'id', 'kind', 'title', 'description'}:
        raise ValueError('插件含有未知字段；不接受脚本、命令、网址或执行入口')
    return dict(id=value['id'], title=value['title'], kind=value['kind'],
                description=str(value.get('description', ''))[:500])


class ModuleWidget(QWidget):
    def __init__(self, owner, record):
        super().__init__()
        self.owner, self.record = owner, record
        self.key = 'module:' + record['id']
        self.kind = record['kind']
        self.setMinimumSize(180, 140)
        layout = QVBoxLayout(self)
        data = owner.store.get(self.key, {})
        if self.kind == 'note':
            self.text = QPlainTextEdit()
            self.text.setPlaceholderText('写下想法，内容自动保存…')
            self.text.setPlainText(data.get('text', ''))
            self.text.textChanged.connect(lambda: self.save(dict(text=self.text.toPlainText())))
            layout.addWidget(self.text)
        elif self.kind == 'checklist':
            self.items = QListWidget()
            for item in data.get('items', []):
                self.add_item(item['text'], item.get('done', False))
            self.items.itemChanged.connect(self.save_items)
            self.input = QLineEdit()
            self.input.setPlaceholderText('输入后按回车新增')
            self.input.returnPressed.connect(self.add_input)
            layout.addWidget(self.input)
            layout.addWidget(self.items)
            remove = QPushButton('删除选中项')
            remove.clicked.connect(self.remove_item)
            layout.addWidget(remove)
        elif self.kind == 'calendar':
            self.calendar = QCalendarWidget()
            self.calendar.setGridVisible(True)
            self.calendar.setFirstDayOfWeek(Qt.DayOfWeek.Monday)
            self.refresh_calendar_range()
            year, month = data.get('year', date.today().year), data.get('month', date.today().month)
            if isinstance(year, int) and isinstance(month, int) and 1 <= month <= 12:
                self.calendar.setCurrentPage(max(date.today().year-10, min(date.today().year+10, year)), month)
            self.calendar.currentPageChanged.connect(lambda year, month: self.save(dict(year=year, month=month)))
            self.calendar.clicked.connect(lambda day: self.select_day(day.toPyDate() if hasattr(day, 'toPyDate') else day.toPython()))
            layout.addWidget(self.calendar)
        elif self.kind == 'clock':
            self.label = QLabel()
            self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(self.label)
            self.timer = QTimer(self)
            self.timer.timeout.connect(self.refresh)
            self.timer.start(1000)
            self.refresh()
        else:
            self.label = QLabel()
            self.check = QCheckBox('今天已完成')
            layout.addWidget(self.label)
            layout.addWidget(self.check)
            layout.addStretch()
            self.habit_data = data.get('days', {})
            self.check.toggled.connect(self.save_habit)
            self.timer = QTimer(self)
            self.timer.timeout.connect(self.refresh)
            self.timer.start(1000)
            self.refresh()

    def save(self, data):
        self.owner.persist(self.key, data)

    def add_item(self, text, done=False):
        item = QListWidgetItem(text[:500])
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEditable)
        item.setCheckState(Qt.CheckState.Checked if done else Qt.CheckState.Unchecked)
        self.items.addItem(item)

    def add_input(self):
        text = self.input.text().strip()
        if text:
            self.add_item(text)
            self.input.clear()
            self.save_items()

    def remove_item(self):
        if self.items.currentRow() >= 0:
            self.items.takeItem(self.items.currentRow())
            self.save_items()

    def save_items(self, *_):
        self.save(dict(items=[dict(text=self.items.item(i).text(), done=self.items.item(i).checkState() == Qt.CheckState.Checked) for i in range(self.items.count())]))

    def select_day(self, day):
        self.owner.year, self.owner.month = day.year, day.month
        self.owner.sync_navigation()
        self.owner.select(day)

    def refresh_calendar_range(self):
        self.calendar.setMinimumDate(QDate(date.today().year-10, 1, 1))
        self.calendar.setMaximumDate(QDate(date.today().year+10, 12, 31))

    def refresh(self):
        if self.kind == 'clock':
            self.label.setText(datetime.now().strftime('%H:%M:%S\n%Y-%m-%d'))
        else:
            self.label.setText(f'{date.today().isoformat()}\n累计完成 {sum(bool(v) for v in self.habit_data.values())} 天')
            self.check.blockSignals(True)
            self.check.setChecked(self.habit_data.get(date.today().isoformat(), False))
            self.check.blockSignals(False)

    def save_habit(self, done):
        self.habit_data[date.today().isoformat()] = done
        self.save(dict(days=self.habit_data))
        self.refresh()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.refresh_font()

    def refresh_font(self):
        prefs = self.owner.custom
        px = prefs.get('font_size', 14)
        if prefs.get('font_auto', True):
            px *= max(.75, min(1.8, min(self.width()/330, self.height()/230)))
        font = QFont(prefs.get('font_family') or self.font().family())
        font.setPixelSize(round(px * (1.6 if self.kind == 'clock' else 1)))
        for child in self.findChildren(QWidget):
            child.setFont(font)

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh_font()
        if hasattr(self, 'timer'):
            self.refresh()
            self.timer.start(1000)
        if self.kind == 'calendar':
            self.refresh_calendar_range()

    def hideEvent(self, event):
        if hasattr(self, 'timer'):
            self.timer.stop()
        super().hideEvent(event)


class PythonModuleWidget(QWidget):
    """Keep a plugin's content and lifecycle separate from the desktop panel."""
    def __init__(self,workspace,record):
        super().__init__()
        self.workspace, self.record = workspace, record
        self.instance = None
        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(0,0,0,0)
        self.setMinimumSize(180,140)
        if workspace.safe_mode:
            self.show_message('安全模式：未运行第三方插件。正常启动应用后可在插件库启用。')
        elif record['plugin'] in workspace.installed:
            self.start()
        else:
            self.show_message('此插件已停用。内容保留，可在第三方插件库恢复。')

    def clear_content(self):
        if self.instance is not None:
            instance, self.instance = self.instance, None
            try:
                instance.cleanup()
            except Exception as exc:
                self.workspace.plugin_errors[self.record['plugin']] = str(exc)
        while self.box.count():
            item = self.box.takeAt(0)
            widget = item.widget()
            if widget is not None:
                for timer in widget.findChildren(QTimer):
                    timer.stop()
                widget.hide()
                widget.deleteLater()

    def show_message(self,message):
        label = QLabel(message)
        label.setWordWrap(True)
        label.setTextFormat(Qt.TextFormat.PlainText)
        self.box.addWidget(label)

    def stop(self):
        self.clear_content()
        self.show_message('此插件已停用。内容保留，可在第三方插件库恢复。')

    def start(self):
        self.clear_content()
        key = self.record['plugin']
        if self.workspace.safe_mode:
            self.show_message('安全模式下不运行第三方插件。')
            return
        try:
            self.instance = self.workspace.plugin_library.create_widget(key,self.record['id'],self.workspace.owner)
            self.box.addWidget(self.instance.widget)
            self.workspace.plugin_errors.pop(key,None)
        except PluginApprovalRequired:
            self.show_message('插件尚未授权，或代码已经改变。请在“第三方插件”中确认后启用。')
        except Exception as exc:
            self.workspace.plugin_errors[key] = str(exc)
            self.show_message('插件启动失败：'+str(exc)+'\n可在插件库停用，或修改代码后重新加载。')


class Workspace(QMainWindow):
    """Free placement workspace; old module content keys remain unchanged."""
    def __init__(self,owner):
        super().__init__()
        from free_canvas import FreeCanvas
        self.owner = owner
        self.safe_mode = '--safe-mode' in sys.argv
        self.plugin_library = PluginLibrary(owner.store)
        self.plugin_errors = {}
        self.style_cache = {}
        self.docks, self.core = {}, []
        self.restoring = True
        self.arranging = False
        self.auto_layout = True
        self.locked = bool(owner.store.get('workspace:locked',False))
        self.catalog = [dict(p) for p in CATALOG]
        for plugin in owner.store.get('plugins:custom',[]):
            try:
                plugin = validate_plugin(dict(plugin,schema=1))
            except (ValueError,TypeError):
                continue
            if not any(p['id'] == plugin['id'] for p in self.catalog):
                self.catalog.append(plugin)
        default_installed = [p['id'] for p in self.catalog]
        self.refresh_python_catalog()
        known = {p['id']:p for p in self.catalog}
        self.installed = list(dict.fromkeys(key for key in owner.store.get('plugins:installed',default_installed) if key in known))
        self.records = []
        seen = {'main-calendar','daily-editor'}
        for record in owner.store.get('workspace:modules',[]):
            if not isinstance(record,dict) or record.get('plugin') not in known:
                continue
            key = record.get('id','')
            if not isinstance(key,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}',key) or key in seen:
                continue
            seen.add(key)
            plugin = known[record['plugin']]
            title = record.get('title')
            self.records.append(dict(record,kind=plugin['kind'],title=title[:40] if isinstance(title,str) and title.strip() else plugin['title']))
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.timeout.connect(self.save_workspace)
        self.canvas_timer = QTimer(self)
        self.canvas_timer.setSingleShot(True)
        self.canvas_timer.timeout.connect(self.resize_canvas)
        self.desktop = FreeCanvas(self)
        self.canvas = self.desktop.canvas
        self.setCentralWidget(self.desktop)
        self.setMinimumSize(350,300)
        self.order = []

    def addWidget(self,widget):
        index = len(self.core)
        key = ['main-calendar','daily-editor'][index]
        titles = self.owner.store.get('workspace:core-titles',{})
        dock = self.create_dock(key,titles.get(key,['日历','每日事项'][index]),widget)
        self.core.append(dock)

    def create_dock(self,key,title,widget):
        from free_canvas import FreePanel
        dock = FreePanel(self,key,title,widget)
        self.docks[key] = dock
        self.order.append(key)
        dock.resize(360,300)
        dock.set_locked(self.locked)
        dock.show()
        return dock

    def schedule_save(self,*_):
        if not self.restoring and not self.arranging:
            self.save_timer.start(300)

    def geometry_changed(self):
        if hasattr(self,'canvas_timer') and not self.arranging:
            self.canvas_timer.start(0)
        self.schedule_save()
        for board in getattr(self.owner,'boards',[]):
            board.update()

    def resize_canvas(self):
        if self.arranging:
            return
        width,height = self.desktop.viewport().width(),self.desktop.viewport().height()
        for panel in self.docks.values():
            if not panel.isHidden():
                width = max(width,panel.x()+panel.width()+12)
                height = max(height,panel.y()+panel.height()+12)
        self.canvas.resize(max(350,width),max(300,height))
        self.canvas.update()

    def view_size(self):
        return max(650,self.desktop.viewport().width()),max(350,self.desktop.viewport().height())

    def arrange_default(self,save=True):
        if self.arranging or len(self.core) < 2:
            return
        self.arranging = True
        width,height = self.view_size()
        gap = 12
        main_width = max(400,round(width*.70)-gap*2)
        side_width = max(260,width-main_width-gap*3)
        self.core[0].setGeometry(gap,gap,main_width,height-gap*2)
        self.core[1].setGeometry(main_width+gap*2,gap,side_width,height-gap*2)
        for i,panel in enumerate(p for p in self.docks.values() if p not in self.core):
            panel.setGeometry(60+(i%5)*40,70+(i%5)*36,360,300)
        self.arranging = False
        self.resize_canvas()
        if save:
            self.auto_layout = True
            self.save_workspace()

    def arrange(self,kind):
        if self.locked:
            return
        if kind == 'default':
            self.arrange_default()
            return
        panels = [p for p in self.docks.values() if not p.isHidden()]
        self.auto_layout = False
        self.arranging = True
        width,height = self.view_size()
        if kind == 'tile':
            columns = max(1,width//400)
            cell_width = max(360,(width-12)//columns-12)
            for i,panel in enumerate(panels):
                panel.setGeometry(12+(i%columns)*(cell_width+12),12+(i//columns)*360,cell_width,348)
        else:
            for i,panel in enumerate(panels):
                panel.setGeometry(12+(i%8)*40,12+(i%8)*36,min(width-40,780),min(height-40,560))
                panel.raise_()
            self.order = [key for key in self.order if self.docks[key].isHidden()]+[p.objectName() for p in panels]
        self.arranging = False
        self.resize_canvas()
        self.save_workspace()

    def setSizes(self,sizes):
        if len(self.core) != 2 or len(sizes) != 2 or sum(sizes) <= 0:
            return
        self.arranging = True
        width,height = self.view_size()
        left = max(300,round((width-36)*sizes[0]/sum(sizes)))
        self.core[0].setGeometry(12,12,left,height-24)
        self.core[1].setGeometry(left+24,12,max(250,width-left-36),height-24)
        self.arranging = False
        self.resize_canvas()

    def sizes(self):
        return [d.width() for d in self.core]

    def set_locked(self,locked):
        self.locked = locked
        for dock in self.docks.values():
            dock.set_locked(locked)
        self.owner.persist('workspace:locked',locked)

    def add_module(self,plugin_id,record=None):
        self.refresh_python_catalog()
        plugin = next((p for p in self.catalog if p['id'] == plugin_id),None)
        if plugin is None or plugin_id not in self.installed:
            raise ValueError('请先启用该配件')
        if plugin['kind'] == 'python' and (self.safe_mode or not self.plugin_library.is_approved(plugin_id)):
            raise ValueError('请在普通启动模式下，从第三方插件库确认并启用当前插件代码。')
        if record is None:
            record = dict(id=uuid.uuid4().hex,plugin=plugin_id,kind=plugin['kind'],title=plugin['title'],visible=True)
            self.records.append(record)
        if record['id'] in self.docks:
            return self.docks[record['id']].widget()
        widget = self.create_module(record)
        self.auto_layout = False
        offset = (len(self.records)-1)%6*32
        self.docks[record['id']].move(self.desktop.horizontalScrollBar().value()+50+offset,self.desktop.verticalScrollBar().value()+50+offset)
        self.activate_module(record['id'])
        self.apply_colors()
        self.save_workspace()
        return widget

    def create_module(self,record):
        widget = PythonModuleWidget(self,record) if record['kind'] == 'python' else ModuleWidget(self.owner,record)
        dock = self.create_dock(record['id'],record['title'],widget)
        dock.setVisible(record.get('visible',True) and record['plugin'] in self.installed)
        return widget

    def set_module_visible(self,key,visible):
        record = next((r for r in self.records if r['id'] == key),None)
        if record is not None:
            if record['plugin'] not in self.installed:
                return
            record['visible'] = bool(visible)
        self.docks[key].setVisible(visible)
        self.resize_canvas()
        self.save_workspace()

    def activate_module(self,key,scroll=True):
        if key not in self.docks:
            return
        record = next((r for r in self.records if r['id'] == key),None)
        if record and record['plugin'] not in self.installed:
            return
        panel = self.docks[key]
        panel.show()
        if record:
            record['visible'] = True
        panel.raise_()
        if key in self.order:
            self.order.remove(key)
        self.order.append(key)
        if scroll:
            self.resize_canvas()
            self.desktop.ensureVisible(panel.x()+80,panel.y()+30,80,30)
        self.schedule_save()

    def rename_module(self,key,title):
        title = title.strip()[:40]
        if not title:
            return
        self.docks[key].setWindowTitle(title)
        for record in self.records:
            if record['id'] == key:
                record['title'] = title
        self.save_workspace()

    def prompt_rename(self,key):
        import sys
        if sys.platform == 'linux':
            from PyQt6.QtWidgets import QInputDialog
        else:
            from PySide6.QtWidgets import QInputDialog
        title,ok = QInputDialog.getText(self,'重命名配件','新名称（最多 40 字）',text=self.docks[key].windowTitle())
        if ok:
            self.rename_module(key,title)

    def fill_view(self,key):
        if self.locked:
            return
        self.auto_layout = False
        width,height = self.view_size()
        self.docks[key].setGeometry(self.desktop.horizontalScrollBar().value()+12,self.desktop.verticalScrollBar().value()+12,width-24,height-24)
        self.activate_module(key)

    def install_plugin(self,key):
        if not any(p['id'] == key for p in self.catalog):
            raise ValueError('找不到该配件')
        if key in self.installed:
            return
        plugin = next(p for p in self.catalog if p['id'] == key)
        if plugin['kind'] == 'python':
            if self.safe_mode or not self.plugin_library.is_approved(key):
                raise ValueError('请先在第三方插件库确认并启用当前代码。')
        self.installed.append(key)
        for record in self.records:
            if record['plugin'] == key:
                widget = self.docks[record['id']].widget()
                if isinstance(widget,PythonModuleWidget):
                    widget.start()
                self.docks[record['id']].setVisible(record.get('visible',True))
        self.owner.persist('plugins:installed',self.installed)
        self.save_workspace()

    def disable_plugin(self,key):
        if key not in self.installed:
            return
        self.installed.remove(key)
        for record in self.records:
            if record['plugin'] == key:
                panel = self.docks[record['id']]
                panel.hide()
                if isinstance(panel.widget(),PythonModuleWidget):
                    panel.widget().stop()
        self.owner.persist('plugins:installed',self.installed)
        self.resize_canvas()
        self.save_workspace()

    def import_plugin(self,path):
        from pathlib import Path
        if Path(path).stat().st_size > 65536:
            raise ValueError('配件文件不能超过 64 KB')
        plugin = validate_plugin(json.loads(Path(path).read_text(encoding='utf-8-sig')))
        if any(p['id'] == plugin['id'] for p in self.catalog):
            raise ValueError('这个配件已经存在')
        self.catalog.append(plugin)
        self.owner.persist('plugins:custom',[p for p in self.catalog if p['kind'] != 'python' and p['id'] not in {v['id'] for v in CATALOG}])
        self.install_plugin(plugin['id'])
        return plugin

    def refresh_python_catalog(self):
        base = [p for p in self.catalog if p.get('kind') != 'python']
        reserved = {p['id'] for p in base}
        self.catalog = base+[p for p in self.plugin_library.catalog() if p['id'] not in reserved]
        # Keep the original instance ids and layout when source files have been
        # moved or temporarily removed. Reimporting can then recover their data.
        known = {p['id'] for p in self.catalog}
        records = self.records if hasattr(self,'records') else self.owner.store.get('workspace:modules',[])
        for record in records:
            if not isinstance(record,dict) or record.get('kind') != 'python':
                continue
            key = record.get('plugin')
            if not isinstance(key,str) or not re.fullmatch(r'[a-z][a-z0-9_-]{1,63}',key) or key in known:
                continue
            self.catalog.append(dict(id=key,title=key,kind='python',description='原有插件的源码暂时缺失，桌面实例及数据已保留。',
                version='',approved=False,digest='',error='找不到插件源码，请重新导入同 ID 的插件以恢复。'))
            known.add(key)

    def import_python_plugin(self,path):
        reserved = {p['id'] for p in self.catalog if p['kind'] != 'python'}
        plugin = self.plugin_library.import_package(path,reserved_ids=reserved)
        self.refresh_python_catalog()
        # Import only copies files. Enable is a separate explicit operation.
        self.owner.persist('plugins:installed',self.installed)
        return plugin

    def enable_python_plugin(self,key,digest=None):
        if self.safe_mode:
            raise ValueError('安全模式下不运行第三方插件；请正常启动应用后再启用。')
        self.plugin_library.approve(key,digest=digest)
        self.refresh_python_catalog()
        if key in self.installed:
            self.reload_python_plugin(key,digest)
        else:
            self.install_plugin(key)

    def reload_python_plugin(self,key,digest=None):
        if self.safe_mode:
            raise ValueError('安全模式下不运行第三方插件。')
        if digest is not None:
            self.plugin_library.approve(key,digest=digest)
        if not self.plugin_library.is_approved(key):
            raise ValueError('源码已改变，请在插件库确认新代码后再加载。')
        self.refresh_python_catalog()
        if key not in self.installed:
            self.install_plugin(key)
            return
        for record in self.records:
            if record['plugin'] == key:
                self.docks[record['id']].widget().start()
        self.apply_colors()
        self.save_workspace()

    def shutdown_plugins(self):
        for panel in self.docks.values():
            if isinstance(panel.widget(),PythonModuleWidget):
                panel.widget().clear_content()

    def restore_workspace(self):
        self.restoring = True
        for record in self.records:
            self.create_module(record)
        saved = self.owner.store.get('workspace:free:v1',{})
        self.auto_layout = not bool(saved) or bool(saved.get('auto',False))
        if saved:
            for key,value in saved.get('panels',{}).items():
                panel = self.docks.get(key)
                if panel is None or not isinstance(value,dict):
                    continue
                rect = value.get('rect',[])
                if len(rect) == 4 and all(isinstance(v,int) for v in rect):
                    panel.setGeometry(max(0,min(rect[0],20000)),max(0,min(rect[1],20000)),max(240,min(rect[2],5000)),max(180,min(rect[3],5000)))
                record = next((r for r in self.records if r['id'] == key),None)
                panel.setVisible(bool(value.get('visible',True)) and (record is None or record['plugin'] in self.installed))
            self.order = [key for key in saved.get('order',[]) if key in self.docks]
            self.order += [key for key in self.docks if key not in self.order]
        else:
            self.arrange_default(save=False)
        for key in self.order:
            self.docks[key].raise_()
        self.restoring = False
        self.set_locked(self.locked)
        self.apply_colors()
        self.resize_canvas()

    def save_workspace(self):
        if self.restoring or self.arranging:
            return
        self.save_timer.stop()
        self.owner.persist('workspace:modules',self.records)
        self.owner.persist('workspace:core-titles',{p.objectName():p.windowTitle() for p in self.core})
        panels = {key:dict(rect=[p.x(),p.y(),p.width(),p.height()],visible=not p.isHidden()) for key,p in self.docks.items()}
        self.owner.persist('workspace:free:v1',dict(panels=panels,order=self.order,auto=self.auto_layout))

    def reset_layout(self):
        for key in self.docks:
            record = next((r for r in self.records if r['id'] == key),None)
            if record is None or record['plugin'] in self.installed:
                self.docks[key].show()
                if record:
                    record['visible'] = True
        self.arrange_default()

    def set_module_color(self,dock,reset=False):
        key = dock.objectName()
        style = self.get_module_style(key)
        if reset:
            style.update(background='',foreground='')
        else:
            color = QColorDialog.getColor(QColor(style['background'] or self.owner.theme_colors['surface']),self,'配件底色')
            if not color.isValid():
                return
            style['background'] = color.name()
        self.set_module_style(key,style)

    def get_module_style(self,key):
        if key not in self.style_cache:
            self.style_cache[key] = normalize_style(self.owner.store.get('module-style:'+key,{}),self.owner.store.get('module-color:'+key,''))
        return dict(self.style_cache[key])

    def preview_module_style(self,key,style):
        self.style_cache[key] = normalize_style(style)
        self.apply_colors()

    def set_module_style(self,key,style):
        style = normalize_style(style)
        if self.owner.persist('module-style:'+key,style):
            self.style_cache[key] = style
            self.apply_colors()
            return True
        return False

    def open_module_appearance(self,key):
        if key in self.docks:
            ModuleAppearanceDialog(self,key).exec()

    def apply_colors(self):
        calendar_style = self.get_module_style('main-calendar')
        self.owner.calendar_surface = calendar_style['background']
        self.owner.calendar_foreground = calendar_style['foreground']
        theme = self.owner.theme_colors
        calendar_colors = dict(theme)
        if calendar_style['background'] or calendar_style['foreground']:
            background, foreground = resolved_colors(calendar_style,theme)
            def blend(first,second,amount):
                a,b = QColor(first),QColor(second)
                return QColor(*(round(x*(1-amount)+y*amount) for x,y in zip(a.getRgb()[:3],b.getRgb()[:3]))).name()
            calendar_colors.update(surface=background,text=foreground,
                alternate=blend(background,foreground,.04),faded=blend(background,foreground,.07),
                selected=blend(background,theme['accent'],.20),grid=blend(background,foreground,.20),
                muted=foreground,dim=blend(background,foreground,.70),
                morning=foreground,noon=foreground,evening=foreground)
        self.owner.calendar_colors = calendar_colors
        for key,panel in self.docks.items():
            apply_panel_style(panel,self.get_module_style(key),theme)
        self.canvas.update()
        for board in getattr(self.owner,'boards',[]):
            board.update()

    def refresh_fonts(self):
        for panel in self.docks.values():
            if isinstance(panel.widget(),ModuleWidget):
                panel.widget().refresh_font()

    def shop(self):
        from module_shop import ModuleShop
        dialog = ModuleShop(self)
        dialog.exec()
        self.save_workspace()
