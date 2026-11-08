<#
=============================================================================
SKRIP OTOMATIS PUSH REPOSITORI KE GITHUB (push_to_github.ps1)
UAS Algoritma Trading - Indri Destiyana (NIM: 25120200007)
=============================================================================
Petunjuk:
1. Buat repositori baru di GitHub (misal: uas-bot-indodax) pada opsi PUBLIC.
2. Salin URL repositori Anda (misal: https://github.com/username/uas-bot-indodax.git).
3. Jalankan skrip ini di PowerShell, lalu tempel URL tersebut saat diminta.
=============================================================================
#>

Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host " PROGRAM OTOMATISASI PUSH REPOSITORI BOT UAS KE GITHUB" -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host ""

$repoUrl = Read-Host "Masukkan URL Repositori GitHub Anda (contoh: https://github.com/user/repo.git)"

if ([string]::IsNullOrWhiteSpace($repoUrl)) {
    Write-Host "[BATAL] URL repositori tidak boleh kosong." -ForegroundColor Red
    exit
}

Write-Host "`n[1/3] Menyiapkan remote origin..." -ForegroundColor Yellow
git remote remove origin 2>$null
git remote add origin $repoUrl

Write-Host "[2/3] Memastikan branch master..." -ForegroundColor Yellow
git branch -M master

Write-Host "[3/3] Melakukan push ke GitHub..." -ForegroundColor Yellow
git push -u origin master

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n=================================================================" -ForegroundColor Green
    Write-Host " [SUKSES] Repositori berhasil di-push ke GitHub!" -ForegroundColor Green
    Write-Host " Langkah berikutnya: Buka vercel.com dan import repositori ini." -ForegroundColor Green
    Write-Host "=================================================================" -ForegroundColor Green
} else {
    Write-Host "`n[PERINGATAN] Terjadi kendala saat push. Pastikan repositori GitHub sudah dibuat dan Anda sudah login ke Git." -ForegroundColor Red
}
