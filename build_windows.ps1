$ErrorActionPreference = 'Stop'
# Keep unrelated application DLLs out of PyInstaller's dependency search.
$env:PATH = "$env:WINDIR\System32;$env:WINDIR;$PSScriptRoot\.venv\Scripts"
Set-Location -LiteralPath $PSScriptRoot
& '.\.venv\Scripts\python.exe' build_windows.py
if ($LASTEXITCODE -ne 0) { throw 'EXE build failed' }
