"""Prepare release files only when version and tag agree."""
import hashlib
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from version import VERSION
if len(sys.argv)!=2 or sys.argv[1]!='v'+VERSION:
    raise SystemExit('Release tag must match version.py')
dist = ROOT/'dist'
artifacts = [dist/f'little-calendar-windows-v{VERSION}.exe',dist/f'little-calendar_{VERSION}_all.deb']
if not all(path.is_file() for path in artifacts):
    raise SystemExit('Both verified platform packages are required')
(dist/'SHA256SUMS.txt').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in artifacts),encoding='utf-8')
changelog = (ROOT/'CHANGELOG.md').read_text(encoding='utf-8')
section = changelog.split('\n# ',1)[0]
if not section.startswith('# v'+VERSION+' '):
    raise SystemExit('Changelog must begin with the release version')
(dist/'RELEASE_NOTES.md').write_text(section+'\n\nWindows：下载 EXE 后运行。Ubuntu：sudo apt install ./little-calendar_'+VERSION+'_all.deb。\n\nPython 插件具有本机用户权限，请只启用可信源码。恢复备份后需要重新确认启用插件。\n',encoding='utf-8')
print('Prepared checksums and release notes for '+sys.argv[1])
