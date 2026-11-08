@echo off
chcp 65001 > nul
title Uji Coba Bot & Verifikasi Audit - Indri Destiyana (25120200007)
cls
echo ===============================================================================
echo  SISTEM AUDIT & UJI COBA BOT INDODAX (UAS ALGORITMA TRADING)
echo  Mahasiswa : Indri Destiyana (NIM: 25120200007)
echo ===============================================================================
echo.
echo [1/2] Menjalankan Skrip Audit Kuantitatif Dinamis (hitung_ulang.py)...
echo.
py backtest\hitung_ulang.py
echo.
echo -------------------------------------------------------------------------------
echo [2/2] Menjalankan Satu Siklus Live Bot Dry Run Indodax (api/tick.py)...
echo -------------------------------------------------------------------------------
echo.
py api\tick.py
echo.
echo ===============================================================================
echo  PENGUJIAN SELESAI. Tekan sembarang tombol untuk menutup jendela ini.
echo ===============================================================================
pause > nul

