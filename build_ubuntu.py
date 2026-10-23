"""Build an architecture-independent Debian package using standard Python.

No native binaries are cross-compiled: Ubuntu provides Python and Qt via apt.
"""
import gzip
import hashlib
import io
from pathlib import Path, PurePosixPath
import tarfile

ROOT = Path(__file__).resolve().parent
from version import VERSION
OUTPUT = ROOT / 'dist' / f'little-calendar_{VERSION}_all.deb'


def tar_gz(files):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode='w', format=tarfile.GNU_FORMAT) as archive:
        # dpkg does not synthesize missing directories from file paths.
        directories = {str(parent) for name,_,_ in files for parent in PurePosixPath(name).parents if str(parent)!='.'}
        for name in sorted(directories,key=lambda name:(name.count('/'),name)):
            info = tarfile.TarInfo('./'+name)
            info.type = tarfile.DIRTYPE
            info.mode,info.mtime = 0o755,0
            info.uid = info.gid = 0
            info.uname = info.gname = 'root'
            archive.addfile(info)
        for name, content, mode in files:
            info = tarfile.TarInfo('./' + name)
            info.size, info.mode, info.mtime = len(content), mode, 0
            info.uid = info.gid = 0
            info.uname = info.gname = 'root'
            archive.addfile(info, io.BytesIO(content))
    return gzip.compress(output.getvalue(), mtime=0)


def ar_member(name, content):
    header = f'{name + "/":<16}{0:<12}{0:<6}{0:<6}{"100644":<8}{len(content):<10}`\n'.encode('ascii')
    assert len(header) == 60
    return header + content + (b'\n' if len(content) % 2 else b'')


def build():
    files = [
        ('usr/bin/little-calendar', b'#!/bin/sh\nexec /usr/bin/python3 /usr/share/little-calendar/app.py "$@"\n', 0o755),
        ('usr/share/little-calendar/app.py', (ROOT / 'app.py').read_bytes(), 0o644),
        ('usr/share/little-calendar/theme.py', (ROOT / 'theme.py').read_bytes(), 0o644),
        ('usr/share/applications/little-calendar.desktop', (ROOT / 'packaging/little-calendar.desktop').read_bytes(), 0o644),
        ('usr/share/icons/hicolor/scalable/apps/little-calendar.svg', (ROOT / 'packaging/little-calendar.svg').read_bytes(), 0o644),
        ('usr/share/doc/little-calendar/README.md', (ROOT / 'UBUNTU.md').read_bytes(), 0o644),
        ('usr/share/doc/little-calendar/PLUGINS.md', (ROOT / 'PLUGINS.md').read_bytes(), 0o644),
    ]
    for filename in ('qt_compat.py','workspace.py','free_canvas.py','module_shop.py','preferences.py','markings.py',
                     'module_appearance.py','plugin_library_ui.py','plugin_runtime.py','calendar_plugin_api.py',
                     'version.py','backup.py','backup_ui.py','layout_history.py','exchange.py','exchange_ui.py',
                     'entry_search.py','reminders.py','autobackup.py','status_tray.py',
                     'review.py','review_ui.py','templates.py','templates_ui.py'):
        files.append(('usr/share/little-calendar/'+filename,(ROOT/filename).read_bytes(),0o644))
    for filename in ('manifest.json','main.py','helpers.py','README.md'):
        relative = 'examples/python-note/' + filename
        files.append(('usr/share/little-calendar/'+relative,(ROOT/relative).read_bytes(),0o644))
    size = (sum(len(content) for _, content, _ in files) + 1023)//1024
    control = f'''Package: little-calendar
Version: {VERSION}
Section: utils
Priority: optional
Architecture: all
Maintainer: Little Calendar Project <maintainer@little-calendar.invalid>
Depends: python3 (>= 3.10), python3-pyqt6 (>= 6.2), fonts-noto-cjk
Installed-Size: {size}
Description: Customizable personal calendar with local Python plugins
 Offline desktop calendar with a rolling 21-year range and six daily tasks,
 morning/noon/evening categories, drawing and local storage. Includes a free
 module canvas, module colors and opacity, and an editable Python plugin API.
'''.encode('utf-8')
    md5sums = ''.join(hashlib.md5(content).hexdigest() + '  ' + name + '\n' for name, content, _ in files).encode()
    parts = [('debian-binary', b'2.0\n'),
             ('control.tar.gz', tar_gz([('control', control, 0o644), ('md5sums', md5sums, 0o644)])),
             ('data.tar.gz', tar_gz(files))]
    OUTPUT.parent.mkdir(exist_ok=True)
    OUTPUT.write_bytes(b'!<arch>\n' + b''.join(ar_member(name, content) for name, content in parts))
    # Read back the actual artifact; verify the archive, executable mode and payload.
    blob = OUTPUT.read_bytes()
    assert blob[:8] == b'!<arch>\n'
    cursor, recovered = 8, {}
    while cursor < len(blob):
        header = blob[cursor:cursor+60]
        assert header[58:] == b'`\n'
        length = int(header[48:58])
        name = header[:16].decode().strip().rstrip('/')
        recovered[name] = blob[cursor+60:cursor+60+length]
        cursor += 60 + length + length % 2
    assert cursor == len(blob) and recovered['debian-binary'] == b'2.0\n'
    with tarfile.open(fileobj=io.BytesIO(recovered['data.tar.gz']), mode='r:gz') as archive:
        for name, content, mode in files:
            for parent in PurePosixPath(name).parents:
                if str(parent)!='.':
                    assert archive.getmember('./'+str(parent)).isdir()
            assert archive.getmember('./'+name).mode == mode
            assert archive.extractfile('./'+name).read() == content
    with tarfile.open(fileobj=io.BytesIO(recovered['control.tar.gz']), mode='r:gz') as archive:
        assert archive.extractfile('./control').read() == control
    checksum = hashlib.sha256(blob).hexdigest()
    OUTPUT.with_suffix('.deb.sha256').write_text(checksum + '  ' + OUTPUT.name + '\n', encoding='ascii')
    print(f'PASS: Debian archive structure, metadata, payload and launcher permissions\n{OUTPUT}\nSHA256: {checksum}')


if __name__ == '__main__':
    build()
