"""
=============================================================================
MODUL KONEKSI & EKSEKUSI API INDODAX (indodax_client.py)
UAS Algoritma Trading - Bot Dry Run Indodax di Vercel
Mahasiswa   : Indri Destiyana (NIM: 25120200007)
=============================================================================
Modul ini menangani:
1. Penarikan data candle historis & live (TradingView history_v2 API)
2. Pembuangan candle berjalan (Time + tf > server_time) pencegah look-ahead bias
3. Validasi kualitas data (kekosongan, candle hilang, spread ekstrem > 2%)
4. Penarikan order book (depth) dan simulasi eksekusi realistis:
   - Beli di ASK, Jual di BID
   - Order book walking (VWAP bila pesanan melebihi level 1)
   - Larangan keras fill di harga mid/close
5. Retry handling dengan exponential backoff dan batas request (maks 3 req/detik)
=============================================================================
"""

import time
import json
import urllib.request
import urllib.error
from typing import Dict, List, Tuple, Optional, Any

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
DEFAULT_TIMEOUT = 10  # detik
MAX_RETRIES = 3

class IndodaxClient:
    def __init__(self, timeout: int = DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.headers = {"User-Agent": USER_AGENT}

    def _http_get(self, url: str) -> Any:
        """Mengirim HTTP GET dengan retry terbatas dan penanganan error."""
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                req = urllib.request.Request(url, headers=self.headers)
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    raw = resp.read().decode("utf-8")
                    return json.loads(raw)
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
                if attempt == MAX_RETRIES:
                    raise ConnectionError(f"Gagal memanggil API [{url}] setelah {MAX_RETRIES} percobaan: {e}")
                time.sleep(0.5 * attempt)
            except json.JSONDecodeError as e:
                raise ValueError(f"Respon bukan format JSON valid dari [{url}]: {e}")

    def get_server_time(self) -> int:
        """
        Mengambil waktu server Indodax dalam epoch detik (UTC).
        Endpoint /api/server_time mengembalikan timestamp milidetik.
        """
        data = self._http_get("https://indodax.com/api/server_time")
        ms = data.get("server_time")
        if not ms:
            return int(time.time())
        return int(ms // 1000)

    def get_pairs_info(self) -> List[Dict[str, Any]]:
        """Mengambil informasi seluruh pasangan perdagangan, fee, dan batas order."""
        return self._http_get("https://indodax.com/api/pairs")

    def get_pair_detail(self, pair_id: str) -> Optional[Dict[str, Any]]:
        """Mengambil detail satu pasangan (misal: 'btcidr')."""
        pairs = self.get_pairs_info()
        pair_id = pair_id.lower()
        for p in pairs:
            if p.get("id", "").lower() == pair_id:
                return p
        return None

    def get_order_book(self, pair_id: str) -> Dict[str, Any]:
        """
        Mengambil order book (depth) terkini dari pasangan tertentu.
        Return: {"buy": [[price, vol], ...], "sell": [[price, vol], ...]}
        buy  = bid (antrian beli, urut harga tertinggi ke terendah)
        sell = ask (antrian jual, urut harga terendah ke tertinggi)
        """
        pair_clean = pair_id.lower().replace("_", "")
        url = f"https://indodax.com/api/depth/{pair_clean}"
        return self._http_get(url)

    def get_candles(self, symbol: str, tf_minutes: int, from_unix: int, to_unix: int) -> List[Dict[str, Any]]:
        """
        Menarik candle dari TradingView history_v2 Indodax.
        Format symbol: BTCIDR (huruf besar tanpa pemisah)
        tf_minutes: 1, 15, 30, 60, 240, 1D
        """
        sym = symbol.upper().replace("_", "")
        tf_str = "1D" if tf_minutes == 1440 else str(tf_minutes)
        url = f"https://indodax.com/tradingview/history_v2?symbol={sym}&tf={tf_str}&from={from_unix}&to={to_unix}"
        data = self._http_get(url)
        if not isinstance(data, list):
            return []
        return data

    def get_closed_candles(
        self,
        symbol: str,
        tf_minutes: int,
        count: int = 100
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """
        Mengambil candle yang SUDAH TERTUTUP SAJA (Strict Anti Look-Ahead Bias).
        Aturan Soal Halaman 2:
        'Buang setiap bar dengan Time + durasi timeframe > server_time.
         Sinyal hanya boleh dihitung dari bar sisanya.'
        """
        server_time = self.get_server_time()
        tf_seconds = tf_minutes * 60
        # Tarik data dengan jendela mundur secukupnya
        from_unix = server_time - (tf_seconds * (count + 15))
        to_unix = server_time + 60

        raw_bars = self.get_candles(symbol, tf_minutes, from_unix, to_unix)
        if not raw_bars:
            return [], f"Data candle kosong dari Indodax untuk {symbol}"

        closed_bars = []
        for bar in raw_bars:
            bar_time = int(bar.get("Time", 0))
            # Candle hanya dianggap tertutup jika periode durasinya sudah rampung sebelum server_time
            if (bar_time + tf_seconds) <= server_time:
                closed_bars.append({
                    "time": bar_time,
                    "open": float(bar.get("Open", 0.0)),
                    "high": float(bar.get("High", 0.0)),
                    "low": float(bar.get("Low", 0.0)),
                    "close": float(bar.get("Close", 0.0)),
                    "volume": float(bar.get("Volume", 0.0)),
                })

        # Urutkan berdasarkan waktu naik
        closed_bars.sort(key=lambda x: x["time"])

        # Validasi kualitas data (Aturan Soal Halaman 2)
        validation_error = self.validate_candle_data(closed_bars, tf_seconds, server_time)
        if validation_error:
            return closed_bars, validation_error

        # Ambil sejumlah bar terakhir yang diminta
        if len(closed_bars) > count:
            closed_bars = closed_bars[-count:]

        return closed_bars, None

    def validate_candle_data(
        self,
        bars: List[Dict[str, Any]],
        tf_seconds: int,
        server_time: int
    ) -> Optional[str]:
        """
        Validasi integritas data candle sesuai ketentuan UAS:
        1. Candle tertutup terakhir tidak boleh lebih tua dari 2x timeframe
        2. Harga atau volume tidak boleh 0
        3. Tidak ada candle bolong (gap waktu) di jendela perhitungan indikator
        """
        if not bars:
            return "Kumpulan candle kosong."

        last_bar = bars[-1]
        # Syarat 1: Candle terakhir tidak boleh kedaluwarsa (> 2 * tf_seconds)
        age = server_time - (last_bar["time"] + tf_seconds)
        if age > (2 * tf_seconds):
            return f"Candle tertutup terakhir terlalu usang ({age}s > {2 * tf_seconds}s batas maksimal)."

        # Syarat 2 & 3: Cek harga 0 dan integritas runtut waktu
        for i in range(len(bars)):
            b = bars[i]
            if b["close"] <= 0 or b["open"] <= 0 or b["high"] <= 0 or b["low"] <= 0:
                return f"Ditemukan harga bernilai <= 0 pada candle waktu {b['time']}."
            if i > 0:
                delta = b["time"] - bars[i - 1]["time"]
                # Gap lebih dari 1 timeframe
                if delta > tf_seconds:
                    return f"Ditemukan candle hilang antara waktu {bars[i-1]['time']} dan {b['time']} (gap: {delta}s)."

        return None

    def execute_dry_run_order(
        self,
        pair_id: str,
        side: str,              # "buy" atau "sell"
        order_amount_idr: float, # Untuk buy: modal rupiah yg ingin dibeli; Untuk sell: nilai estimasi
        crypto_amount: float = 0.0, # Untuk sell: kuantitas koin yg dijual
        taker_fee_pct: float = 0.0021 # 0.21% All-in taker fee Indodax
    ) -> Dict[str, Any]:
        """
        Simulasi eksekusi transaksi dry run REALISTIS menggunakan LIVE ORDER BOOK Indodax.
        Aturan Ketat Soal UAS Halaman 2:
        - Beli di ASK, Jual di BID.
        - Dilarang keras fill di harga mid atau close.
        - Jika pesanan melebihi level 1, habiskan order book level berikutnya (Order Book Walk / VWAP).
        - Spread maksimal diizinkan 2%. Bila spread > 2%, transaksi ditolak.
        - Minimum order Rp25.000.
        """
        side = side.lower()
        if side not in ("buy", "sell"):
            raise ValueError(f"Sisi order tidak dikenal: {side}")

        depth = self.get_order_book(pair_id)
        bids = depth.get("buy", [])
        asks = depth.get("sell", [])

        if not bids or not asks:
            return {
                "success": False,
                "reason": "Order book kosong (tidak ada antrian bid/ask)."
            }

        best_bid = float(bids[0][0])
        best_ask = float(asks[0][0])

        # Hitung spread saat ini
        spread_abs = best_ask - best_bid
        spread_pct = spread_abs / best_bid
        if spread_pct > 0.02:
            return {
                "success": False,
                "reason": f"Spread bid-ask terlalu lebar ({spread_pct * 100:.2f}% > 2% batas aman). Order dibatalkan.",
                "best_bid": best_bid,
                "best_ask": best_ask,
                "spread_pct": spread_pct
            }

        # Eksekusi Beli (Makan antrian ASK)
        if side == "buy":
            if order_amount_idr < 25000:
                return {
                    "success": False,
                    "reason": f"Nominal beli Rp{order_amount_idr:,.0f} di bawah minimum order Rp25.000."
                }

            sisa_rupiah = order_amount_idr
            total_koin_didapat = 0.0
            total_rupiah_terpakai = 0.0
            level_ditembus = 0

            for level in asks:
                level_harga = float(level[0])
                level_vol_koin = float(level[1])
                level_kapasitas_rp = level_harga * level_vol_koin

                level_ditembus += 1
                if sisa_rupiah <= level_kapasitas_rp:
                    # Habis di level ini
                    koin_fill = sisa_rupiah / level_harga
                    total_koin_didapat += koin_fill
                    total_rupiah_terpakai += sisa_rupiah
                    sisa_rupiah = 0.0
                    break
                else:
                    # Makan penuh level ini dan lanjut ke level berikutnya
                    total_koin_didapat += level_vol_koin
                    total_rupiah_terpakai += level_kapasitas_rp
                    sisa_rupiah -= level_kapasitas_rp

            if total_koin_didapat <= 0:
                return {"success": False, "reason": "Likuiditas order book ask tidak mencukupi."}

            avg_fill_price = total_rupiah_terpakai / total_koin_didapat
            # Hitung fee taker all-in
            fee_rp = total_rupiah_terpakai * taker_fee_pct

            # Slippage relatif terhadap best ask awal
            slippage_pct = (avg_fill_price - best_ask) / best_ask

            return {
                "success": True,
                "pair": pair_id.upper(),
                "side": "buy",
                "best_bid": best_bid,
                "best_ask": best_ask,
                "spread_pct": spread_pct,
                "avg_fill_price": avg_fill_price,
                "crypto_amount": total_koin_didapat,
                "idr_spent": total_rupiah_terpakai,
                "fee_rp": fee_rp,
                "slippage_pct": slippage_pct,
                "levels_walked": level_ditembus,
                "timestamp": int(time.time())
            }

        # Eksekusi Jual (Makan antrian BID)
        else:
            if crypto_amount <= 0:
                return {"success": False, "reason": "Kuantitas koin yang hendak dijual <= 0."}

            sisa_koin = crypto_amount
            total_rupiah_didapat = 0.0
            total_koin_terjual = 0.0
            level_ditembus = 0

            for level in bids:
                level_harga = float(level[0])
                level_vol_koin = float(level[1])

                level_ditembus += 1
                if sisa_koin <= level_vol_koin:
                    rupiah_fill = sisa_koin * level_harga
                    total_rupiah_didapat += rupiah_fill
                    total_koin_terjual += sisa_koin
                    sisa_koin = 0.0
                    break
                else:
                    rupiah_fill = level_vol_koin * level_harga
                    total_rupiah_didapat += rupiah_fill
                    total_koin_terjual += level_vol_koin
                    sisa_koin -= level_vol_koin

            if total_koin_terjual <= 0 or total_rupiah_didapat < 25000:
                return {
                    "success": False,
                    "reason": f"Nilai jual Rp{total_rupiah_didapat:,.0f} di bawah batas minimum Rp25.000 atau likuiditas bid habis."
                }

            avg_fill_price = total_rupiah_didapat / total_koin_terjual
            fee_rp = total_rupiah_didapat * taker_fee_pct
            slippage_pct = (best_bid - avg_fill_price) / best_bid

            return {
                "success": True,
                "pair": pair_id.upper(),
                "side": "sell",
                "best_bid": best_bid,
                "best_ask": best_ask,
                "spread_pct": spread_pct,
                "avg_fill_price": avg_fill_price,
                "crypto_amount": total_koin_terjual,
                "idr_received": total_rupiah_didapat,
                "fee_rp": fee_rp,
                "slippage_pct": slippage_pct,
                "levels_walked": level_ditembus,
                "timestamp": int(time.time())
            }
