"""
=============================================================================
PENARIK DATA HISTORIS 3 TAHUN INDODAX (fetch_data_3thn.py)
UAS Algoritma Trading - Bot Dry Run Indodax di Vercel
Mahasiswa   : Indri Destiyana (NIM: 25120200007)
=============================================================================
Kepatuhan Ketat Aturan Soal UAS Halaman 2:
1. Satu request history_v2 tf=60 hanya mengembalikan ~650 bar terakhir (±27 hari).
2. Data ditarik mundur bertahap: mulai dari to = sekarang, lalu geser to ke waktu
   bar paling awal yang sudah didapat, diulang sampai mencapai tanggal 3 tahun lalu.
3. Jeda delay 0.35 detik per request (maksimal 3 request per detik, sekuensial)
   agar IP tidak diblokir Indodax.
4. Candle berjalan (Time + tf > server_time) dibuang untuk mencegah look-ahead bias.
5. Menyimpan snapshot order book live terkini untuk estimasi median spread backtest.
=============================================================================
"""

import os
import sys
import time
import json
import urllib.request
from datetime import datetime, timezone, timedelta

# Target Universe Kripto Likuid Bebas Survivorship Bias
DEFAULT_SYMBOLS = ["BTCIDR", "ETHIDR", "DOGEIDR"]
TF_MINUTES = 60
TF_SECONDS = TF_MINUTES * 60
YEARS_BACK = 3
TARGET_HOURS = YEARS_BACK * 365 * 24  # ±26,280 jam

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) IndodaxDataFetcher/1.0 (Student UAS)"
}

def get_server_time() -> int:
    """Mengambil server time Indodax dalam epoch detik."""
    url = "https://indodax.com/api/server_time"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=10) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        return int(res["server_time"] // 1000)

def fetch_single_chunk(symbol: str, from_unix: int, to_unix: int) -> list:
    """Mengambil satu potongan ~650 candle dari TradingView Indodax."""
    url = f"https://indodax.com/tradingview/history_v2?symbol={symbol}&tf={TF_MINUTES}&from={from_unix}&to={to_unix}"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        if isinstance(data, list):
            return data
        return []

def fetch_order_book_snapshot(symbol: str) -> dict:
    """Menyimpan snapshot depth untuk pengukuran median spread & slippage."""
    pair_clean = symbol.lower().replace("_", "")
    url = f"https://indodax.com/api/depth/{pair_clean}"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=10) as resp:
        depth = json.loads(resp.read().decode("utf-8"))
        bids = depth.get("buy", [])
        asks = depth.get("sell", [])
        best_bid = float(bids[0][0]) if bids else 0.0
        best_ask = float(asks[0][0]) if asks else 0.0
        spread_pct = (best_ask - best_bid) / best_bid if best_bid > 0 else 0.0
        return {
            "symbol": symbol,
            "timestamp": int(time.time()),
            "datetime": datetime.now(timezone.utc).isoformat(),
            "best_bid": best_bid,
            "best_ask": best_ask,
            "spread_pct": spread_pct,
            "depth_bids_top5": bids[:5],
            "depth_asks_top5": asks[:5],
        }

def download_3y_data_for_symbol(symbol: str, output_dir: str):
    print(f"\n" + "=" * 70)
    print(f" Memulai Penarikan Data 3 Tahun Mundur: {symbol} (Timeframe: {TF_MINUTES}m)")
    print("=" * 70)

    server_time = get_server_time()
    three_years_ago = server_time - (YEARS_BACK * 365 * 86400)
    start_dt = datetime.fromtimestamp(three_years_ago, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    end_dt = datetime.fromtimestamp(server_time, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    print(f" Rentang Target: {start_dt} s/d {end_dt}")
    print(f" Target Total  : ±{TARGET_HOURS:,} candle bars")

    all_bars_map = {}
    current_to = server_time
    iteration = 1

    while current_to > three_years_ago:
        chunk_from = max(three_years_ago, current_to - (30 * 86400))
        try:
            bars = fetch_single_chunk(symbol, chunk_from, current_to)
        except Exception as e:
            print(f"   [Peringatan] Gagal ambil chunk iterasi {iteration}: {e}. Retry dalam 2 detik...")
            time.sleep(2.0)
            continue

        if not bars:
            print(f"   Tidak ada data tambahan sebelum timestamp {current_to}. Pengunduhan selesai.")
            break

        # Filter bar: buang candle berjalan jika melebihi server_time
        new_count = 0
        min_time_in_chunk = current_to

        for b in bars:
            b_time = int(b.get("Time", 0))
            if (b_time + TF_SECONDS) <= server_time:
                if b_time not in all_bars_map:
                    all_bars_map[b_time] = {
                        "time": b_time,
                        "open": float(b.get("Open", 0.0)),
                        "high": float(b.get("High", 0.0)),
                        "low": float(b.get("Low", 0.0)),
                        "close": float(b.get("Close", 0.0)),
                        "volume": float(b.get("Volume", 0.0)),
                    }
                    new_count += 1
            if b_time < min_time_in_chunk:
                min_time_in_chunk = b_time

        earliest_dt = datetime.fromtimestamp(min_time_in_chunk, tz=timezone.utc).strftime("%Y-%m-%d")
        print(f"   Chunk #{iteration:<2}: Didapat {len(bars):<3} bar | Mundur ke: {earliest_dt} | Total Terkumpul: {len(all_bars_map):<5}")

        # Jika chunk tidak mundur lagi, hentikan loop
        if min_time_in_chunk >= current_to:
            print("   Batas historis paling awal dari server telah tercapai.")
            break

        # Geser to mundur ke waktu bar paling awal yang didapat
        current_to = min_time_in_chunk - 1
        iteration += 1

        # Jeda aman (maks 3 req/detik)
        time.sleep(0.35)

    # Urutkan secara kronologis (dari masa lalu ke sekarang)
    sorted_bars = sorted(all_bars_map.values(), key=lambda x: x["time"])
    print(f"\n -> Selesai! Total bar terkumpul dan terurut untuk {symbol}: {len(sorted_bars):,} bar.")

    # Simpan ke file JSON
    os.makedirs(output_dir, exist_ok=True)
    filename = os.path.join(output_dir, f"{symbol}_1h_3y.json")
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(sorted_bars, f, indent=2)
    print(f" -> Berkas tersimpan di: {filename}")

    return sorted_bars


def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.path.join(os.path.dirname(base_dir), "data")
    snapshot_file = os.path.join(output_dir, "orderbook_snapshots.json")

    print("=" * 80)
    print(" PROGRAM PENARIK DATA HISTORIS 3 TAHUN & SNAPSHOT ORDER BOOK INDODAX")
    print(" UAS Algoritma Trading - Indri Destiyana (NIM: 25120200007)")
    print("=" * 80)

    # 1. Simpan Snapshot Order Book untuk Spread & Slippage Backtest
    print("\n[1/2] Mengambil snapshot live order book untuk estimasi spread...")
    snapshots = []
    if os.path.exists(snapshot_file):
        try:
            with open(snapshot_file, "r", encoding="utf-8") as f:
                snapshots = json.load(f)
        except Exception:
            snapshots = []

    for sym in DEFAULT_SYMBOLS:
        try:
            snap = fetch_order_book_snapshot(sym)
            snapshots.append(snap)
            print(f"   - {sym:<8}: Bid {snap['best_bid']:,.0f} | Ask {snap['best_ask']:,.0f} | Spread {snap['spread_pct']*100:.3f}%")
        except Exception as e:
            print(f"   - {sym:<8}: Gagal snapshot order book: {e}")
        time.sleep(0.35)

    with open(snapshot_file, "w", encoding="utf-8") as f:
        json.dump(snapshots, f, indent=2)
    print(f"   -> Snapshot order book tersimpan di: {snapshot_file}")

    # 2. Penarikan Data 3 Tahun Mundur untuk Setiap Simbol
    print("\n[2/2] Mengunduh data historis 3 tahun per simbol secara bertahap mundur...")
    for sym in DEFAULT_SYMBOLS:
        download_3y_data_for_symbol(sym, output_dir)

    print("\n" + "=" * 80)
    print(" Seluruh proses penarikan data 3 tahun Indodax telah selesai!")
    print(" Data siap digunakan oleh mesin backtest.")
    print("=" * 80)

if __name__ == "__main__":
    main()
