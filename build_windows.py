import os
from pathlib import Path
import PyInstaller.__main__

VERSION = '0.5.0'
# User-authored plugins are imported after freezing, so static analysis cannot
# discover their dependencies. Bundle this explicit, documented stdlib baseline.
PLUGIN_STDLIB = (
    'argparse', 'asyncio', 'base64', 'calendar', 'collections',
    'concurrent.futures', 'contextlib', 'csv', 'dataclasses', 'datetime',
    'decimal', 'difflib', 'email', 'fractions', 'functools', 'hashlib', 'html',
    'http.client', 'inspect', 'io', 'itertools', 'json', 'logging', 'math',
    'mimetypes', 'os', 'pathlib', 'platform', 'pprint', 'queue', 'random', 're',
    'shutil', 'socket', 'sqlite3', 'ssl', 'statistics', 'string', 'struct',
    'subprocess', 'tempfile', 'threading', 'time', 'traceback', 'types', 'typing',
    'unicodedata', 'urllib.parse', 'urllib.request', 'uuid',
    'xml.etree.ElementTree', 'zipfile', 'zoneinfo',
)

root = Path(__file__).resolve().parent
os.chdir(root)
os.environ['PATH'] = str(Path(os.environ['WINDIR']) / 'System32') + os.pathsep + os.environ['WINDIR']
arguments = ['--noconfirm', '--clean', '--onefile', '--windowed', '--name', f'小日历-v{VERSION}',
             '--add-data', f'examples/python-note{os.pathsep}examples/python-note',
             '--add-data', f'PLUGINS.md{os.pathsep}.']
for module in PLUGIN_STDLIB + ('calendar_plugin_api', 'plugin_runtime'):
    arguments += ['--hidden-import', module]
PyInstaller.__main__.run(arguments + ['app.py'])
