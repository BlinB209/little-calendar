"""Portable, bounded backups. Restores keep a recovery copy and revoke Python trust."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import stat
import tempfile
import uuid
import zipfile
from contextlib import closing
from datetime import datetime
from version import VERSION

LIMIT = 512 * 1024 * 1024


def data_root(store):
    path = next(row[2] for row in store.db.execute('PRAGMA database_list') if row[1] == 'main')
    if not path:
        raise ValueError('备份需要使用磁盘数据库')
    return Path(path).resolve().parent


def snapshot(store, destination):
    with closing(sqlite3.connect(destination)) as target:
        store.db.backup(target)


def export_backup(store, destination):
    root = data_root(store)
    destination = Path(destination).resolve()
    if destination.suffix.lower()!='.zip':
        raise ValueError('备份文件名必须以 .zip 结尾')
    if destination == root/'calendar.sqlite3' or any(destination.is_relative_to(root/p) for p in ('plugins','backgrounds')):
        raise ValueError('请将备份保存到插件和背景目录之外')
    with tempfile.TemporaryDirectory(prefix='calendar-export-') as temporary:
        staging = Path(temporary)
        snapshot(store, staging/'calendar.sqlite3')
        payload = {'calendar.sqlite3': staging/'calendar.sqlite3'}
        for folder in ('backgrounds','plugins'):
            source = root/folder
            if source.is_symlink() or getattr(source,'is_junction',lambda:False)():
                raise ValueError('数据目录不能是链接')
            if source.exists():
                for path in source.rglob('*'):
                    if path.is_symlink() or getattr(path,'is_junction',lambda:False)():
                        raise ValueError('备份不支持链接文件：'+str(path))
                    if path.is_file() and '__pycache__' not in path.parts and path.suffix not in ('.pyc','.pyo'):
                        payload[path.relative_to(root).as_posix()] = path
        prefs = store.get('customization:v1',{})
        image = Path(prefs.get('background_image',''))
        if prefs.get('background_image'):
            if not image.is_file():
                raise ValueError('当前背景文件缺失，请重新选择背景后再备份')
            name = 'backgrounds/'+hashlib.sha256(image.read_bytes()).hexdigest()+image.suffix.lower()
            payload[name] = image
            with closing(sqlite3.connect(staging/'calendar.sqlite3')) as db:
                prefs = dict(prefs, background_image=name)
                db.execute('INSERT OR REPLACE INTO entries VALUES (?,?)',('customization:v1',json.dumps(prefs)))
                db.commit()
        if len(payload)>5000 or sum(p.stat().st_size for p in payload.values())>LIMIT:
            raise ValueError('备份最多支持 5000 个文件、512 MiB 数据')
        manifest = dict(schema=1,version=VERSION,created=datetime.now().isoformat(),files={})
        temporary_output = destination.with_name(destination.name+'.'+uuid.uuid4().hex+'.tmp')
        try:
            with zipfile.ZipFile(temporary_output,'x',compression=zipfile.ZIP_DEFLATED) as archive:
                for name,path in payload.items():
                    content = path.read_bytes()
                    manifest['files'][name] = hashlib.sha256(content).hexdigest()
                    archive.writestr(name,content)
                archive.writestr('backup.json',json.dumps(manifest,ensure_ascii=False))
            os.replace(temporary_output,destination)
        finally:
            temporary_output.unlink(missing_ok=True)
    return destination


class PreparedRestore:
    def __init__(self,path):
        self.temp = tempfile.TemporaryDirectory(prefix='calendar-restore-')
        self.root = Path(self.temp.name)
        try:
            self._read(path)
        except BaseException:
            self.close()
            raise

    def _read(self,path):
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            if len(infos)>5001 or sum(i.file_size for i in infos)>LIMIT:
                raise ValueError('备份文件数量或大小超出限制')
            seen = set()
            for item in infos:
                name = item.filename
                relative = PurePosixPath(name)
                parts = name.split('/')
                if (relative.is_absolute() or '\\' in name or ':' in name or
                    any(p in ('','..','.') or p.rstrip(' .')!=p for p in parts) or
                    any(p.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))} for p in parts) or
                    name.casefold() in seen or stat.S_ISLNK(item.external_attr>>16) or
                    (name not in ('backup.json','calendar.sqlite3') and parts[0] not in ('backgrounds','plugins'))):
                    raise ValueError('备份包含不合法的路径或重复文件')
                seen.add(name.casefold())
                target = self.root/name
                target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes(archive.read(item))
        self.manifest = json.loads((self.root/'backup.json').read_text(encoding='utf-8'))
        files = self.manifest.get('files')
        actual = {p.relative_to(self.root).as_posix() for p in self.root.rglob('*') if p.is_file()}-{'backup.json'}
        if self.manifest.get('schema')!=1 or not isinstance(files,dict) or set(files)!=actual:
            raise ValueError('备份清单不完整或版本不支持')
        for name,digest in files.items():
            if hashlib.sha256((self.root/name).read_bytes()).hexdigest()!=digest:
                raise ValueError('备份校验失败：'+name)
        if 'calendar.sqlite3' not in files:
            raise ValueError('备份缺少日历数据库')
        with closing(sqlite3.connect(self.root/'calendar.sqlite3')) as db:
            if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
                raise ValueError('备份数据库损坏')
            objects = db.execute("SELECT type,name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()
            if objects != [('table','entries')]:
                raise ValueError('备份数据库结构不支持')
            if [r[1] for r in db.execute('PRAGMA table_info(entries)')]!=['key','value']:
                raise ValueError('备份数据库字段不支持')
            self.entries = dict(db.execute('SELECT key,value FROM entries'))
            for key,value in self.entries.items():
                if not isinstance(key,str):
                    raise ValueError('备份数据键无效')
                json.loads(value)

    def close(self):
        self.temp.cleanup()


def restore_backup(store,prepared):
    root = data_root(store)
    recovery = root/('recovery-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]+'.zip')
    export_backup(store,recovery)
    # Source is read and verified first. Build replacement trees on the same disk.
    staging = Path(tempfile.mkdtemp(prefix='.restore-',dir=root))
    moved,installed = [],[]
    try:
        for folder in ('backgrounds','plugins'):
            source = prepared.root/folder
            target = staging/folder
            if source.exists():
                shutil.copytree(source,target)
            else:
                target.mkdir()
        values = dict(prepared.entries)
        values['python-plugins:approved'] = '{}'
        catalog = json.loads(values.get('plugins:installed','[]'))
        python_ids = {p.name for p in (staging/'plugins'/'packages').iterdir()} if (staging/'plugins'/'packages').exists() else set()
        records = json.loads(values.get('workspace:modules','[]'))
        python_ids.update(r['plugin'] for r in records if r.get('kind')=='python')
        values['plugins:installed'] = json.dumps([key for key in catalog if key not in python_ids])
        prefs = json.loads(values.get('customization:v1','{}'))
        if prefs.get('background_image'):
            relative = PurePosixPath(prefs['background_image'])
            if relative.is_absolute() or '..' in relative.parts or relative.parts[0]!='backgrounds' or not (prepared.root/str(relative)).is_file():
                raise ValueError('备份背景路径无效')
            prefs['background_image'] = str(root/str(relative))
            values['customization:v1'] = json.dumps(prefs)
        for folder in ('backgrounds','plugins'):
            original = root/folder
            if original.exists():
                original.rename(staging/(folder+'-old'))
                moved.append(folder)
            (staging/folder).rename(original)
            installed.append(folder)
        with store.db:
            store.db.execute('DELETE FROM entries')
            store.db.executemany('INSERT INTO entries VALUES (?,?)',values.items())
    except BaseException:
        for folder in reversed(installed):
            shutil.rmtree(root/folder)
        for folder in reversed(moved):
            (staging/(folder+'-old')).rename(root/folder)
        raise
    finally:
        shutil.rmtree(staging)
    return recovery
