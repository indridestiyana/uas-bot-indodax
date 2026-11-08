"""
=============================================================================
GENERATOR BERKAS DASHBOARD OFFLINE MANDIRI (build_standalone.py)
UAS Algoritma Trading - Bot Dry Run Indodax di Vercel
Mahasiswa   : Indri Destiyana (NIM: 25120200007)
=============================================================================
Menyatukan HTML, CSS, JavaScript, dan seluruh data JSON mentah
ke dalam SATU FILE MANDIRI: UAS_25120200007_IndriDestiyana.html
Dapat dibuka langsung dengan klik dua kali di peramban tanpa internet & server.
=============================================================================
"""

import os
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def build_standalone_html():
    public_dir = os.path.join(BASE_DIR, "public")
    data_dir = os.path.join(BASE_DIR, "data")

    # Baca file sumber
    with open(os.path.join(public_dir, "index.html"), "r", encoding="utf-8") as f:
        html_content = f.read()

    with open(os.path.join(public_dir, "style.css"), "r", encoding="utf-8") as f:
        css_content = f.read()

    with open(os.path.join(public_dir, "dashboard.js"), "r", encoding="utf-8") as f:
        js_content = f.read()

    # Baca data JSON
    bt_path = os.path.join(data_dir, "backtest_results.json")
    fwd_path = os.path.join(data_dir, "forward_test_state.json")

    bt_data = {}
    fwd_data = {}

    if os.path.exists(bt_path):
        with open(bt_path, "r", encoding="utf-8") as f:
            bt_data = json.load(f)

    if os.path.exists(fwd_path):
        with open(fwd_path, "r", encoding="utf-8") as f:
            fwd_data = json.load(f)

    embedded_payload = {
        "backtest": bt_data,
        "forward_test": fwd_data
    }
    payload_json = json.dumps(embedded_payload)

    # Sisipkan CSS inline
    html_content = html_content.replace(
        '<link rel="stylesheet" href="style.css">',
        f'<style>\n{css_content}\n</style>'
    )

    # Sisipkan JS dan Data Payload inline
    embedded_script = f"""
<script>
{js_content}

// Data Mentah Tertanam Penuh (100% Offline Tanpa Koneksi Server)
const EMBEDDED_DATA = {payload_json};

window.addEventListener('DOMContentLoaded', () => {{
  renderDashboard(EMBEDDED_DATA);
}});
</script>
"""

    # Ganti pemanggilan script external
    html_content = html_content.replace('<script src="dashboard.js"></script>', '')
    # Ganti fetch script lama
    fetch_part_start = html_content.find('<script>')
    if fetch_part_start != -1:
        fetch_part_end = html_content.find('</script>', fetch_part_start) + len('</script>')
        html_content = html_content[:fetch_part_start] + embedded_script + html_content[fetch_part_end:]

    # Simpan ke file luaran
    out_path_1 = os.path.join(BASE_DIR, "UAS_25120200007_IndriDestiyana.html")
    out_path_2 = os.path.join(os.path.dirname(BASE_DIR), "UAS_25120200007_IndriDestiyana.html")

    with open(out_path_1, "w", encoding="utf-8") as f:
        f.write(html_content)

    with open(out_path_2, "w", encoding="utf-8") as f:
        f.write(html_content)

    print("=" * 80)
    print(" SUKSES: Dashboard Offline Mandiri Berhasil Dibuat!")
    print(f" 1. {out_path_1}")
    print(f" 2. {out_path_2}")
    print(" Berkas ini dapat langsung dibuka dengan klik dua kali di peramban.")
    print("=" * 80)

if __name__ == "__main__":
    build_standalone_html()
