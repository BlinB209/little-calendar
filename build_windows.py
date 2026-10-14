import os
from pathlib import Path
import PyInstaller.__main__

root = Path(__file__).resolve().parent
os.chdir(root)
os.environ['PATH'] = str(Path(os.environ['WINDIR']) / 'System32') + os.pathsep + os.environ['WINDIR']
PyInstaller.__main__.run(['--noconfirm', '--clean', '--onefile', '--windowed', '--name', '小日历', 'app.py'])
