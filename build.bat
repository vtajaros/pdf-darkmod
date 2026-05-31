@echo off
echo Installing dependencies...
pip install -r requirements.txt

echo Building executable...
pyinstaller --onefile --windowed --name "PDF-DarkMod" --icon favicon.ico main.py

echo.
echo Done. Your exe is in the dist\ folder.
pause
