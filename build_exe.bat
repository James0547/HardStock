@echo off
title Building HardStock Desktop App
echo ========================================
echo   Building HardStock Desktop Application
echo ========================================
echo.

REM Clean previous builds
if exist "build" rmdir /s /q build
if exist "dist" rmdir /s /q dist
if exist "HardStock.spec" del /q HardStock.spec

echo Installing required packages...
pip install pyinstaller pywebview

echo.
echo Building HardStock.exe...
echo This will take 2-3 minutes. Please wait...
echo.

REM Build with all dependencies (without debug flag)
pyinstaller --onefile --windowed --name HardStock --icon="static/im.png" --add-data "templates;templates" --add-data "static;static" desktop.py

echo.
if %errorlevel% equ 0 (
    echo ========================================
    echo   BUILD SUCCESSFUL!
    echo ========================================
    echo.
    echo Your EXE is located at: dist\HardStock.exe
    echo.
    echo Copying to Desktop...
    copy "dist\HardStock.exe" "%USERPROFILE%\Desktop\HardStock.exe" > nul 2>&1
    echo.
    echo Desktop shortcut created!
    echo.
    echo Double-click HardStock.exe on your Desktop to run
) else (
    echo ========================================
    echo   BUILD FAILED!
    echo ========================================
    echo Please check the error messages above
)

echo.
pause