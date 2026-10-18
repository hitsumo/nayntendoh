# Builds a portable eshop.exe on Windows. Requires Python 3.10+ in PATH.
#   powershell -ExecutionPolicy Bypass -File build.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt pyinstaller
pyinstaller --onefile --name eshop --console --clean eshop.py
Write-Host "Done: dist\eshop.exe"
