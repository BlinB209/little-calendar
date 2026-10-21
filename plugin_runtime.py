"""Local Python plugin packages. Import/inspection never executes package code.

Approved packages execute with the desktop application's full user permissions.
The digest gate prevents accidentally running new/changed code, not malicious code.
"""
import hashlib
import importlib.abc
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import tempfile
import uuid
import zipfile

from calendar_plugin_api import API_VERSION, PluginContext, QtWidgets

MAX_FILES = 256
MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_PACKAGE_BYTES = 20 * 1024 * 1024
MANIFEST = 'manifest.json'
ID_RE = re.compile(r'[a-z][a-z0-9_-]{1,63}\Z')


class PluginError(Exception):
    pass


class PluginApprovalRequired(PluginError):
    pass


def _relative_path(value):
    if not isinstance(value, str) or not value or '\\' in value or ':' in value:
        raise PluginError('插件文件路径无效')
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ('', '.', '..') for part in value.split('/')):
        raise PluginError('插件包中含有绝对路径或越界路径')
    if any(part.rstrip(' .') != part or part.split('.')[0].upper() in
           {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)),
            *(f'LPT{i}' for i in range(1, 10))} for part in path.parts):
        raise PluginError('插件文件名不兼容 Windows')
    return path


def _manifest(data):
    if not isinstance(data, dict) or data.get('schema') != 1:
        raise PluginError('Python 插件需要 schema: 1 的 manifest.json')
    allowed = {'schema', 'api_version', 'id', 'title', 'version', 'description', 'kind', 'entry', 'author'}
    if set(data) - allowed:
        raise PluginError('manifest.json 含未知字段：' + ', '.join(sorted(set(data) - allowed)))
    if data.get('api_version') != API_VERSION:
        raise PluginError(f'不兼容的插件 API；当前支持 api_version: {API_VERSION}')
    if not isinstance(data.get('id'), str) or not ID_RE.fullmatch(data['id']):
        raise PluginError('插件 id 必须为 2–64 位小写字母、数字、下划线或连字符')
    if data.get('kind', 'python') != 'python':
        raise PluginError('Python 插件的 kind 必须是 python')
    for key, maximum in [('title', 60), ('version', 40)]:
        if not isinstance(data.get(key), str) or not 1 <= len(data[key]) <= maximum:
            raise PluginError(f'插件 {key} 长度必须为 1–{maximum} 字符')
    for key, maximum in [('description', 2000), ('author', 120)]:
        if not isinstance(data.get(key, ''), str) or len(data.get(key, '')) > maximum:
            raise PluginError(f'插件 {key} 必须是最多 {maximum} 字符的文本')
    entry = _relative_path(data.get('entry', 'main.py'))
    if entry.suffix != '.py' or any(not part.isidentifier() for part in entry.with_suffix('').parts):
        raise PluginError('entry 必须是 Python 文件路径，例如 main.py')
    return dict(data, kind='python', entry=str(entry))


def _files(folder):
    """Read a bounded immutable snapshot, excluding interpreter-generated caches."""
    folder = Path(folder)
    if folder.is_symlink() or getattr(folder, 'is_junction', lambda: False)():
        raise PluginError('插件目录不能是符号链接')
    result, total, names = {}, 0, set()
    for current, dirs, files in os.walk(folder, followlinks=False):
        for name in dirs + files:
            path = Path(current) / name
            if path.is_symlink() or getattr(path, 'is_junction', lambda: False)():
                raise PluginError('插件包不能包含符号链接或目录联接')
        dirs[:] = [name for name in dirs if name != '__pycache__']
        for name in files:
            path = Path(current) / name
            if name.endswith(('.pyc', '.pyo')):
                continue
            if not path.is_file():
                raise PluginError('插件包只允许普通文件')
            relative = str(_relative_path(path.relative_to(folder).as_posix()))
            if relative.casefold() in names:
                raise PluginError('插件文件名大小写冲突')
            names.add(relative.casefold())
            if len(result) >= MAX_FILES or path.stat().st_size > MAX_FILE_BYTES:
                raise PluginError('插件包文件过多或单文件超过 4 MiB')
            data = path.read_bytes()
            total += len(data)
            if total > MAX_PACKAGE_BYTES or len(data) > MAX_FILE_BYTES:
                raise PluginError('插件包总大小不能超过 20 MiB')
            result[relative] = data
    if MANIFEST not in result:
        raise PluginError('插件包中找不到 manifest.json')
    return result


def _read_zip(path):
    result, total, seen = {}, 0, set()
    try:
        with zipfile.ZipFile(path) as archive:
            if len(archive.infolist()) > MAX_FILES * 2:
                raise PluginError('ZIP 文件条目过多')
            for item in archive.infolist():
                relative = str(_relative_path(item.filename.rstrip('/')))
                mode = item.external_attr >> 16
                if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) and not (stat.S_ISREG(mode) or stat.S_ISDIR(mode))):
                    raise PluginError('ZIP 不能包含链接或特殊文件')
                if item.is_dir():
                    continue
                if relative.casefold() in seen:
                    raise PluginError('ZIP 包含重复或大小写冲突文件')
                seen.add(relative.casefold())
                if len(result) >= MAX_FILES or item.file_size > MAX_FILE_BYTES:
                    raise PluginError('插件包文件过多或单文件超过 4 MiB')
                total += item.file_size
                if total > MAX_PACKAGE_BYTES:
                    raise PluginError('插件包总大小不能超过 20 MiB')
                result[relative] = archive.read(item)
    except (OSError, zipfile.BadZipFile, RuntimeError) as error:
        raise PluginError(f'无法读取 ZIP：{error}') from error
    if MANIFEST not in result:
        roots = {name.split('/')[0] for name in result}
        if len(roots) == 1:
            prefix = next(iter(roots)) + '/'
            result = {name[len(prefix):]: data for name, data in result.items() if name.startswith(prefix)}
    if MANIFEST not in result:
        raise PluginError('ZIP 根目录或唯一顶层文件夹内需要 manifest.json')
    return result


def _inspect(files):
    try:
        value = json.loads(files[MANIFEST].decode('utf-8-sig'))
    except (KeyError, ValueError, UnicodeError) as error:
        raise PluginError('manifest.json 必须是 UTF-8 JSON') from error
    metadata = _manifest(value)
    if metadata['entry'] not in files:
        raise PluginError('manifest.json 指定的 Python 入口文件不存在')
    digest = hashlib.sha256()
    for name, data in sorted(files.items()):
        digest.update(name.encode('utf-8'))
        digest.update(b'\0')
        digest.update(len(data).to_bytes(8, 'big'))
        digest.update(data)
    return dict(metadata, digest=digest.hexdigest())


class _SnapshotLoader(importlib.abc.Loader):
    def __init__(self, data, filename):
        self.data, self.filename = data, filename

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        module.__file__ = self.filename
        exec(compile(self.data, self.filename, 'exec'), module.__dict__)


class _SnapshotFinder(importlib.abc.MetaPathFinder):
    """Relative imports use the approved bytes, and never stale .pyc files."""
    def __init__(self, prefix, files, folder):
        self.prefix, self.files, self.folder = prefix, files, folder

    def find_spec(self, fullname, path=None, target=None):
        if not fullname.startswith(self.prefix + '.'):
            return None
        relative = fullname[len(self.prefix) + 1:].replace('.', '/')
        for name, is_package in [(relative + '/__init__.py', True), (relative + '.py', False)]:
            if name in self.files:
                loader = _SnapshotLoader(self.files[name], str(self.folder / name))
                spec = importlib.util.spec_from_loader(fullname, loader, is_package=is_package)
                if is_package:
                    spec.submodule_search_locations = [str(self.folder / relative)]
                return spec
        if any(name.startswith(relative + '/') for name in self.files):
            spec = importlib.machinery.ModuleSpec(fullname, None, is_package=True)
            spec.submodule_search_locations = [str(self.folder / relative)]
            return spec
        # Block filesystem fallback beneath this private package namespace.
        raise ModuleNotFoundError(f'插件中没有模块 {relative}')


class PluginInstance:
    def __init__(self, widget, context, prefix, finder):
        self.widget, self.context = widget, context
        self._prefix, self._finder = prefix, finder
        self._closed = False

    def cleanup(self):
        if self._closed:
            return
        self._closed = True
        try:
            hook = getattr(self.widget, 'cleanup', None)
            if callable(hook):
                hook()
        except BaseException as error:
            self.context.report_error(error)
        finally:
            self.context._cleanup()
            try:
                self.widget.close()
                self.widget.deleteLater()
            except BaseException as error:
                self.context.report_error(error)
            _unload(self._prefix, self._finder)


def _unload(prefix, finder):
    if finder in sys.meta_path:
        sys.meta_path.remove(finder)
    for name in list(sys.modules):
        if name == prefix or name.startswith(prefix + '.'):
            sys.modules.pop(name, None)


class PluginLibrary:
    def __init__(self, store, root=None):
        self.store = store
        self._temporary = None
        if root is None:
            rows = store.db.execute('PRAGMA database_list').fetchall()
            database_path = next((row[2] for row in rows if row[1] == 'main'), '')
            if not database_path:
                self._temporary = tempfile.TemporaryDirectory(prefix='calendar-plugins-')
                root = Path(self._temporary.name)
            else:
                root = Path(database_path).resolve().parent / 'plugins'
        self.root = Path(root).resolve()
        self.packages = self.root / 'packages'
        if self.packages.is_symlink() or getattr(self.packages, 'is_junction', lambda: False)():
            raise PluginError('插件 packages 目录不能是符号链接或目录联接')
        self.packages.mkdir(parents=True, exist_ok=True)

    def source_path(self, plugin_id):
        if not isinstance(plugin_id, str) or not ID_RE.fullmatch(plugin_id):
            raise PluginError('插件 id 无效')
        return self.packages / plugin_id

    def data_path(self, plugin_id, instance_id):
        self.source_path(plugin_id)
        if not isinstance(instance_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', instance_id):
            raise PluginError('插件实例 id 无效')
        return self.root / 'data' / plugin_id / instance_id

    def import_package(self, path, reserved_ids=()):
        path = Path(path)
        try:
            if path.suffix.lower() == '.zip':
                files = _read_zip(path)
            elif path.name == MANIFEST and path.is_file():
                files = _files(path.parent)
            else:
                raise PluginError('请选择插件 ZIP 或 manifest.json')
            metadata = _inspect(files)
            if metadata['id'] in reserved_ids:
                raise PluginError('插件 id 与已有内置配件或 JSON 模板冲突，请更换 id')
            destination = self.source_path(metadata['id'])
            if destination.exists():
                raise PluginError('已存在同名插件。请打开源码目录编辑，然后重新加载；也可更换插件 id。')
            staging = Path(tempfile.mkdtemp(prefix='.import-', dir=self.root))
            try:
                for name, data in files.items():
                    target = staging / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(data)
                staging.rename(destination)
            finally:
                if staging.exists():
                    shutil.rmtree(staging)
            self.revoke(metadata['id'])
            return self.metadata(metadata['id'])
        except OSError as error:
            raise PluginError(f'无法导入插件：{error}') from error

    def metadata(self, plugin_id):
        try:
            result = _inspect(_files(self.source_path(plugin_id)))
            if result['id'] != plugin_id:
                raise PluginError('manifest.json 的 id 与插件目录不一致')
            approved = self.store.get('python-plugins:approved', {})
            result['approved'] = approved.get(plugin_id) == result['digest']
            return result
        except OSError as error:
            raise PluginError(f'无法读取插件：{error}') from error

    def catalog(self):
        result = []
        for folder in sorted(self.packages.iterdir()):
            if not ID_RE.fullmatch(folder.name):
                continue
            try:
                result.append(self.metadata(folder.name))
            except PluginError as error:
                result.append(dict(id=folder.name, title=folder.name, kind='python',
                                   description='', version='', digest='', approved=False, error=str(error)))
        return result

    def is_approved(self, plugin_id):
        try:
            return self.metadata(plugin_id)['approved']
        except PluginError:
            return False

    def approve(self, plugin_id, digest=None):
        result = self.metadata(plugin_id)
        if digest is not None and digest != result['digest']:
            raise PluginApprovalRequired('确认期间插件文件发生变化，请重新查看并确认')
        approved = self.store.get('python-plugins:approved', {})
        approved[plugin_id] = result['digest']
        self.store.put('python-plugins:approved', approved)
        return dict(result, approved=True)

    def revoke(self, plugin_id):
        approved = self.store.get('python-plugins:approved', {})
        approved.pop(plugin_id, None)
        self.store.put('python-plugins:approved', approved)

    def export_example(self, destination):
        return export_example(destination)

    def create_widget(self, plugin_id, instance_id, owner=None):
        folder = self.source_path(plugin_id)
        try:
            files = _files(folder)
            metadata = _inspect(files)
        except OSError as error:
            raise PluginError(f'无法读取插件：{error}') from error
        if metadata['id'] != plugin_id:
            raise PluginError('插件 id 与目录不一致')
        if self.store.get('python-plugins:approved', {}).get(plugin_id) != metadata['digest']:
            raise PluginApprovalRequired('插件尚未允许运行，或源码已修改；请在插件库确认后启用')
        context = PluginContext(self.store, plugin_id, instance_id, self.data_path(plugin_id, instance_id), owner)
        prefix = '_little_calendar_plugin_' + uuid.uuid4().hex
        finder = _SnapshotFinder(prefix, files, folder)
        spec = importlib.machinery.ModuleSpec(prefix, None, is_package=True)
        spec.submodule_search_locations = [str(folder)]
        module = importlib.util.module_from_spec(spec)
        sys.modules[prefix] = module
        sys.meta_path.insert(0, finder)
        widget = None
        try:
            entry_name = prefix + '.' + str(PurePosixPath(metadata['entry']).with_suffix('')).replace('/', '.')
            entry = __import__(entry_name, fromlist=['create_widget'])
            factory = getattr(entry, 'create_widget', None)
            if not callable(factory):
                raise PluginError('插件入口需要定义 create_widget(context)')
            widget = factory(context)
            if not isinstance(widget, QtWidgets.QWidget) or isinstance(widget, QtWidgets.QMainWindow):
                raise PluginError('create_widget(context) 必须返回 QWidget，不能返回 QMainWindow')
            return PluginInstance(widget, context, prefix, finder)
        except BaseException as error:
            context._cleanup()
            _unload(prefix, finder)
            if isinstance(widget, QtWidgets.QWidget):
                widget.deleteLater()
            raise PluginError(f'插件启动失败：{type(error).__name__}: {error}') from error


def export_example(destination):
    """Write the built-in source example, also available from a frozen EXE."""
    destination = Path(destination)
    if destination.exists():
        raise PluginError('目标文件已存在，请换一个文件名')
    manifest = dict(schema=1, api_version=1, id='python-note', title='Python 便签示例',
                    version='1.0.0', kind='python', entry='main.py',
                    description='带独立存储和时间按钮的可编辑 Python 插件示例')
    source = '''from calendar_plugin_api import QtWidgets\n\ndef create_widget(context):\n    widget = QtWidgets.QWidget()\n    layout = QtWidgets.QVBoxLayout(widget)\n    note = QtWidgets.QPlainTextEdit()\n    note.setPlaceholderText("编辑此插件的 main.py 可以自定义功能")\n    note.setPlainText(context.get_value("text", ""))\n    note.textChanged.connect(context.guard(lambda: context.set_value("text", note.toPlainText())))\n    button = QtWidgets.QPushButton("插入所选日期")\n    button.clicked.connect(context.guard(lambda checked=False: note.appendPlainText(context.selected_date.isoformat())))\n    layout.addWidget(note)\n    layout.addWidget(button)\n    return widget\n'''
    try:
        with zipfile.ZipFile(destination, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2))
            archive.writestr('main.py', source)
            archive.writestr('README.md', '导入到插件库，确认允许运行后添加到桌面。编辑库内 main.py 后点击重新加载并确认。\n')
    except OSError as error:
        raise PluginError(f'无法导出示例：{error}') from error
    return destination
