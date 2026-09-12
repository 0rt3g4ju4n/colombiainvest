@echo off
REM Arranque para quien no usa Visual Studio Code.
REM Doble clic sobre este archivo.
chcp 65001 >nul
cd /d "%~dp0"
echo Iniciando ColombiaInvest...
python main.py
if errorlevel 1 (
  echo.
  echo Ocurrio un error. Revise el mensaje anterior.
  pause
)
