"""Run checks on both Qt bindings; each test gets a fresh QApplication/process."""
import subprocess
import sys

common = ['verify_python_plugins.py','verify_plugin_lifecycle.py','verify_module_appearance.py',
          'verify_appearance_integration.py','verify_backup.py','verify_stability.py']
windows = ['verify.py','verify_preview.py','verify_layout.py','verify_background.py','verify_shop.py','verify_plugin_library_ui.py']
for filename in common + (windows if sys.platform=='win32' else []):
    print('Checking '+filename,flush=True)
    subprocess.run([sys.executable,filename],check=True)
subprocess.run([sys.executable,'app.py','--smoke-test'],check=True)
subprocess.run([sys.executable,'app.py','--smoke-test','--safe-mode'],check=True)
print('PASS: all platform checks')
