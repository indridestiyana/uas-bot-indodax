"""
=============================================================================
MODUL MANAJEMEN RISIKO & INTEGRITAS BOT (risk_manager.py)
UAS Algoritma Trading - Bot Dry Run Indodax di Vercel
Mahasiswa   : Indri Destiyana (NIM: 25120200007)
=============================================================================
Kepatuhan Wajib Soal UAS Halaman 3:
1. Batas Jumlah Posisi Terbuka (Max 3 posisi simultan)
2. Ukuran Maksimum per Posisi (Max 30% dari total ekuitas)
3. Daily Loss Limit (Maksimum rugi 3% per hari kalender)
   -> Pergantian hari mengikuti WIB (UTC+7, yaitu pukul 17.00 UTC / 00.00 WIB)
4. Kill Switch Manual (bisa diaktifkan via ENV atau flag state tanpa redeploy)
5. Idempotency Check (candle timestamp hanya diproses tepat 1 kali)
=============================================================================
"""

import os
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Tuple, Optional

WIB_OFFSET = timedelta(hours=7)
MAX_DAILY_LOSS_PCT = 0.03  # 3.0% batas toleransi rugi per hari

class RiskManager:
    def __init__(self, max_positions: int = 3, max_allocation_pct: float = 0.30):
        self.max_positions = max_positions
        self.max_allocation_pct = max_allocation_pct

    @staticmethod
    def get_wib_date_str(timestamp_epoch: Optional[int] = None) -> str:
        """Mengembalikan tanggal kalender WIB (YYYY-MM-DD). Berganti pukul 00.00 WIB (17.00 UTC)."""
        if timestamp_epoch is None:
            dt_utc = datetime.now(timezone.utc)
        else:
            dt_utc = datetime.fromtimestamp(timestamp_epoch, tz=timezone.utc)
        dt_wib = dt_utc + WIB_OFFSET
        return dt_wib.strftime("%Y-%m-%d")

    @staticmethod
    def is_kill_switch_active(state: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Mengecek apakah Kill Switch aktif:
        1. Dari environment variable BOT_KILL_SWITCH (true/1)
        2. Dari flag di dalam state JSON/DB (state.get("kill_switch") == True)
        """
        env_val = os.getenv("BOT_KILL_SWITCH", "").strip().lower()
        if env_val in ("1", "true", "yes", "on"):
            return True, "Kill Switch aktif via Environment Variable BOT_KILL_SWITCH."

        if state.get("kill_switch", False) is True:
            return True, "Kill Switch aktif via Flag State persisten."

        return False, "Bot beroperasi normal (Kill Switch OFF)."

    @staticmethod
    def check_idempotency(state: Dict[str, Any], symbol: str, candle_timestamp: int) -> bool:
        """
        Mengecek apakah candle ini sudah pernah diproses.
        Mencegah double buy bila cron Vercel terpanggil dua kali pada candle yang sama.
        Return True jika AMAN diproses (belum pernah diproses sebelumnya).
        Return False jika DUPLIKAT (sudah pernah diproses).
        """
        processed = state.setdefault("processed_candles", {})
        last_processed = processed.get(symbol.upper(), 0)
        if candle_timestamp <= last_processed:
            return False
        return True

    @staticmethod
    def mark_candle_processed(state: Dict[str, Any], symbol: str, candle_timestamp: int):
        """Mencatat candle timestamp sebagai sudah diproses."""
        processed = state.setdefault("processed_candles", {})
        processed[symbol.upper()] = max(processed.get(symbol.upper(), 0), candle_timestamp)

    def evaluate_daily_loss(self, state: Dict[str, Any], current_equity: float, current_epoch: int) -> Tuple[bool, str]:
        """
        Evaluasi Daily Loss Limit.
        Bila kerugian hari ini melampaui MAX_DAILY_LOSS_PCT (3%),
        bot berhenti membuka posisi baru sampai pergantian hari 00.00 WIB berikutnya.
        """
        today_wib = self.get_wib_date_str(current_epoch)
        daily_tracking = state.setdefault("daily_tracking", {})

        # Jika hari baru berganti (00.00 WIB), rekam baseline awal hari
        if daily_tracking.get("date") != today_wib:
            daily_tracking["date"] = today_wib
            daily_tracking["start_equity"] = current_equity
            daily_tracking["min_equity"] = current_equity
            daily_tracking["breached"] = False

        start_equity = daily_tracking.get("start_equity", current_equity)
        if current_equity < daily_tracking.get("min_equity", current_equity):
            daily_tracking["min_equity"] = current_equity

        # Hitung persentase drawdown hari ini
        daily_dd_pct = (current_equity - start_equity) / start_equity if start_equity > 0 else 0.0

        if daily_dd_pct <= -MAX_DAILY_LOSS_PCT:
            daily_tracking["breached"] = True
            return True, (
                f"Daily Loss Limit TERLAMPAUI: penurunan {daily_dd_pct * 100:.2f}% "
                f"(Start Rp{start_equity:,.0f} -> Current Rp{current_equity:,.0f}). "
                f"Posisi baru diblokir hingga pergantian 00.00 WIB."
            )

        if daily_tracking.get("breached", False):
            return True, "Daily Loss Limit hari ini terkunci. Posisi baru tetap diblokir hingga besok."

        return False, f"Daily Loss aman ({daily_dd_pct * 100:+.2f}% vs batas -{MAX_DAILY_LOSS_PCT * 100:.1f}%)."

    def can_open_new_position(
        self,
        state: Dict[str, Any],
        symbol: str,
        current_equity: float,
        current_epoch: int
    ) -> Tuple[bool, str, float]:
        """
        Validasi komprehensif apakah diizinkan membuka posisi baru:
        1. Cek Kill Switch
        2. Cek Daily Loss Limit
        3. Cek apakah koin ini sudah memiliki posisi aktif
        4. Cek apakah kuota maksimal posisi terbuka (3) sudah penuh
        5. Hitung besaran alokasi modal yang boleh dipakai (30% equity)
        
        Return: (boleh_buka: bool, alasan: str, alokasi_idr: float)
        """
        # 1. Kill Switch
        kill_active, kill_msg = self.is_kill_switch_active(state)
        if kill_active:
            return False, kill_msg, 0.0

        # 2. Daily Loss Limit
        loss_breached, loss_msg = self.evaluate_daily_loss(state, current_equity, current_epoch)
        if loss_breached:
            return False, loss_msg, 0.0

        # 3. Koin sudah ada
        open_positions = state.setdefault("open_positions", {})
        if symbol.upper() in open_positions:
            return False, f"Koin {symbol.upper()} sudah memiliki posisi terbuka aktif.", 0.0

        # 4. Kuota posisi
        if len(open_positions) >= self.max_positions:
            return False, f"Batas kuota posisi terbuka ({len(open_positions)}/{self.max_positions}) sudah penuh.", 0.0

        # 5. Sizing alokasi modal
        kas_tersedia = state.get("cash", 0.0)
        target_alokasi = current_equity * self.max_allocation_pct

        # Tidak boleh melebihi sisa kas tunai
        alokasi_idr = min(target_alokasi, kas_tersedia)

        if alokasi_idr < 25_000:
            return False, f"Sisa kas (Rp{kas_tersedia:,.0f}) atau alokasi (Rp{alokasi_idr:,.0f}) kurang dari minimum order Rp25.000.", 0.0

        return True, "Lolos seluruh kriteria risk management.", alokasi_idr

