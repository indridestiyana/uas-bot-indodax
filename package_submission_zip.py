"""
=============================================================================
PEMBUAT FILE ZIP PENGUMPULAN AKHIR RISE (package_submission_zip.py)
UAS Algoritma Trading - Indri Destiyana (NIM: 25120200007)
=============================================================================
Membuat satu file arsip ZIP lengkap yang menyertakan:
1. Seluruh source code bot dan backtest
2. Folder .git utuh (Bukti commit riwayat freeze date)
3. Berkas data mentah historis 3 tahun & snapshot order book
4. Seluruh log CSV dan JSON mentah
5. Dashboard offline mandiri (UAS_25120200007_IndriDestiyana.html)
6. README.md lengkap dan file konfigurasi (.env.example, vercel.json)
=============================================================================
"""

import os
import zipfile

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(BASE_DIR)
ZIP_NAME = "UAS_25120200007_IndriDestiyana.zip"
OUTPUT_ZIP_PATH = os.path.join(PARENT_DIR, ZIP_NAME)

def make_submission_zip():
    print("=" * 80)
    print(f" MEMBUAT FILE ARSIP PENGUMPULAN: {ZIP_NAME}")
    print("=" * 80)

    # File / ekstensi yang diabaikan (hanya cache python)
    exclude_dirs = {"__pycache__", ".pytest_cache", "venv", ".venv"}
    exclude_files = {".env", ".DS_Store", "Thumbs.db"}

    total_files = 0
    with zipfile.ZipFile(OUTPUT_ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(BASE_DIR):
            # Filter direktori yang dikecualikan
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            
            for file in files:
                if file in exclude_files or file.endswith(".pyc"):
                    continue
                
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, BASE_DIR)
                # Simpan ke dalam folder uas_bot_indodax di dalam zip
                arc_name = os.path.join("uas_bot_indodax", rel_path)
                zipf.write(full_path, arc_name)
                total_files += 1

        # Sertakan juga file HTML mandiri di root zip
        standalone_html = os.path.join(PARENT_DIR, "UAS_25120200007_IndriDestiyana.html")
        if os.path.exists(standalone_html):
            zipf.write(standalone_html, "UAS_25120200007_IndriDestiyana.html")
            total_files += 1

    size_mb = os.path.getsize(OUTPUT_ZIP_PATH) / (1024 * 1024)
    print(f"\n[SUKSES] Berkas ZIP berhasil dibuat!")
    print(f" -> Lokasi : {OUTPUT_ZIP_PATH}")
    print(f" -> Ukuran : {size_mb:.2f} MB")
    print(f" -> Berisi : {total_files} file (termasuk folder .git utuh untuk audit commit)")
    print("=" * 80)

if __name__ == "__main__":
    make_submission_zip()
