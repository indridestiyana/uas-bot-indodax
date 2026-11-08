@echo off
chcp 65001 > nul
title Push Repositori ke GitHub - Indri Destiyana
cls
echo ===============================================================================
echo   PROGRAM PUSH REPOSITORI BOT UAS KE GITHUB
echo ===============================================================================
echo.
set /p REPO_URL="Masukkan URL Repositori GitHub Anda: "

if "%REPO_URL%"=="" (
    echo.
    echo [BATAL] URL repositori tidak boleh kosong.
    pause
    exit /b
)

echo.
echo [1/3] Menyiapkan remote origin...
git remote remove origin 2>nul
git remote add origin %REPO_URL%

echo [2/3] Memastikan branch master...
git branch -M master

echo [3/3] Mengunggah (push) ke GitHub...
git push -u origin master

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ===============================================================================
    echo  [SUKSES] Seluruh kode berhasil di-push ke GitHub!
    echo  Langkah berikutnya: Buka vercel.com dan import repositori ini.
    echo ===============================================================================
) else (
    echo.
    echo [PERINGATAN] Terjadi kendala saat push.
    echo Pastikan repositori GitHub sudah dibuat di github.com/new dan Anda sudah login.
)

echo.
pause

