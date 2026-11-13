@echo off
cd /d "%~dp0\.."
if not exist .venv (
    python -m venv .venv || goto :erro
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt pyinstaller || goto :erro
pyinstaller packaging\lsync.spec --noconfirm --distpath dist --workpath build || goto :erro
set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if exist "%ISCC%" (
    "%ISCC%" packaging\installer.iss || goto :erro
) else (
    echo Inno Setup nao encontrado, o instalador nao foi gerado.
)
echo.
echo Pronto: dist\Lsync\Lsync.exe e dist\Lsync-Setup.exe
goto :eof
:erro
echo.
echo Algo deu errado. Veja as mensagens acima.
exit /b 1
