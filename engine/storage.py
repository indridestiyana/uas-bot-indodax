"""
=============================================================================
MODUL STORAGE PERSISTEN BOT (storage.py)
UAS Algoritma Trading - Bot Dry Run Indodax di Vercel
Mahasiswa   : Indri Destiyana (NIM: 25120200007)
=============================================================================
Menyediakan penyimpanan state bot yang tahan restart serverless:
- Mendukung Upstash Redis / Vercel KV (REST API murni tanpa library luar)
- Mendukung file lokal JSON (untuk pengujian offline & local development)
=============================================================================
"""

import os
import json
import urllib.request
import urllib.error
from typing import Dict, Any

STATE_KEY = "indodax_bot_state_uas"
LOCAL_STATE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "forward_test_state.json"
)
TMP_STATE_FILE = "/tmp/forward_test_state.json"

def create_default_state() -> Dict[str, Any]:
    """State awal bot dengan modal virtual Rp100.000.000."""
    return {
        "initial_capital": 100_000_000.0,
        "cash": 100_000_000.0,
        "equity": 100_000_000.0,
        "kill_switch": False,
        "open_positions": {},      # {SYM: {entry_price, qty, entry_time, highest_price, cost_basis, entry_fee}}
        "closed_trades": [],       # [{symbol, entry_time, exit_time, entry_price, exit_price, qty, pnl_rp, pnl_pct, reason}]
        "processed_candles": {},   # {SYM: last_candle_timestamp}
        "daily_tracking": {
            "date": "",
            "start_equity": 100_000_000.0,
            "min_equity": 100_000_000.0,
            "breached": False
        },
        "daily_equity": {},        # {YYYY-MM-DD: equity}
        "tick_logs": [],           # [{timestamp, wib_time, status, message, equity, cash, open_pos_count}]
        "order_logs": [],          # [{timestamp, symbol, side, qty, fill_price, fee_rp, spread_pct, slippage_pct, reason}]
        "orderbook_snapshots": []  # [{timestamp, symbol, best_bid, best_ask, spread_pct}]
    }

class BotStorage:
    def __init__(self):
        # Cek ketersediaan Upstash Redis / Vercel KV via REST API
        self.kv_url = os.getenv("KV_REST_API_URL") or os.getenv("UPSTASH_REDIS_REST_URL")
        self.kv_token = os.getenv("KV_REST_API_TOKEN") or os.getenv("UPSTASH_REDIS_REST_TOKEN")

    def is_cloud_storage(self) -> bool:
        return bool(self.kv_url and self.kv_token)

    def load_state(self) -> Dict[str, Any]:
        """Memuat state bot dari Cloud Storage (Upstash/KV) atau Berkas Lokal."""
        if self.is_cloud_storage():
            try:
                url = f"{self.kv_url.rstrip('/')}/get/{STATE_KEY}"
                req = urllib.request.Request(
                    url,
                    headers={"Authorization": f"Bearer {self.kv_token}"}
                )
                with urllib.request.urlopen(req, timeout=8) as resp:
                    res = json.loads(resp.read().decode("utf-8"))
                    result_str = res.get("result")
                    if result_str:
                        data = json.loads(result_str) if isinstance(result_str, str) else result_str
                        return data
            except Exception as e:
                print(f"[Storage Warning] Gagal membaca dari Cloud KV: {e}. Beralih ke berkas lokal.")

        # Fallback ke berkas lokal
        for filepath in (LOCAL_STATE_FILE, TMP_STATE_FILE):
            if os.path.exists(filepath):
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception:
                    pass

        return create_default_state()

    def save_state(self, state: Dict[str, Any]):
        """Menyimpan state bot ke Cloud Storage (Upstash/KV) dan Berkas Lokal."""
        # 1. Simpan ke berkas lokal (dengan fallback /tmp untuk runtime serverless Vercel)
        saved_locally = False
        for filepath in (LOCAL_STATE_FILE, TMP_STATE_FILE):
            try:
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(state, f, indent=2)
                saved_locally = True
                break
            except Exception:
                continue

        if not saved_locally:
            print("[Storage Warning] Gagal simpan ke berkas lokal atau /tmp.")

        # 2. Simpan ke Cloud Storage jika tersedia
        if self.is_cloud_storage():
            try:
                url = f"{self.kv_url.rstrip('/')}/set/{STATE_KEY}"
                payload = json.dumps(state).encode("utf-8")
                req = urllib.request.Request(
                    url,
                    data=payload,
                    headers={
                        "Authorization": f"Bearer {self.kv_token}",
                        "Content-Type": "application/json"
                    },
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    pass
            except Exception as e:
                print(f"[Storage Error] Gagal simpan ke Cloud KV: {e}")

