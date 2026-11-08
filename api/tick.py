"""
=============================================================================
ENDPOINT SERVERLESS VERCEL BOT DRY RUN (api/tick.py)
UAS Algoritma Trading - Bot Dry Run Indodax di Vercel
Mahasiswa   : Indri Destiyana (NIM: 25120200007)
=============================================================================
Fungsi ini dipanggil oleh Cron Scheduler (setiap 1 jam / tf=60).
Menerapkan seluruh kepatuhan Soal UAS Halaman 1-4:
1. Keamanan: Verifikasi CRON_SECRET via Header atau Query Param
2. Kill Switch: Berhenti jika aktif
3. Pengambilan Candle Tertutup & Pembuangan candle berjalan
4. Sinyal identik dengan modul strategy.py
5. Eksekusi Realistis di Order Book Live (Ask untuk Buy, Bid untuk Sell, VWAP)
6. Valuasi Ekuitas harian di Best Bid setelah 00.00 WIB
7. Idempotency per candle timestamp
8. Penyimpanan State Persisten
=============================================================================
"""

import os
import sys
import json
import time
from urllib.parse import urlparse, parse_qs
from http.server import BaseHTTPRequestHandler
from datetime import datetime, timezone, timedelta

# Pastikan path modul engine terbaca oleh Vercel
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from engine.indodax_client import IndodaxClient
from engine.strategy import StrategyConfig, evaluasi_sinyal_bar
from engine.risk_manager import RiskManager
from engine.storage import BotStorage

UNIVERSE = ["BTCIDR", "ETHIDR", "DOGEIDR"]
TF_MINUTES = 60

def run_bot_tick(trigger_source: str = "cron") -> dict:
    storage = BotStorage()
    state = storage.load_state()
    client = IndodaxClient(timeout=10)
    risk_mgr = RiskManager(
        max_positions=StrategyConfig.MAX_OPEN_POSITIONS,
        max_allocation_pct=StrategyConfig.ALLOCATION_PER_POS
    )

    tick_start_time = int(time.time())
    wib_now_str = (datetime.fromtimestamp(tick_start_time, tz=timezone.utc) + timedelta(hours=7)).strftime("%Y-%m-%d %H:%M:%S WIB")
    today_wib = RiskManager.get_wib_date_str(tick_start_time)

    tick_summary = {
        "timestamp": tick_start_time,
        "wib_time": wib_now_str,
        "status": "success",
        "trigger": trigger_source,
        "actions": [],
        "errors": []
    }

    # 1. Cek Kill Switch Manual
    kill_active, kill_msg = RiskManager.is_kill_switch_active(state)
    if kill_active:
        tick_summary["status"] = "kill_switch_active"
        tick_summary["message"] = kill_msg
        state.setdefault("tick_logs", []).append({
            "timestamp": tick_start_time,
            "wib_time": wib_now_str,
            "status": "kill_switch_active",
            "message": kill_msg,
            "equity": state.get("equity", 100_000_000.0),
            "cash": state.get("cash", 100_000_000.0),
            "open_positions": len(state.get("open_positions", {}))
        })
        storage.save_state(state)
        return tick_summary

    # 2. Perbarui Snapshot Order Book & Valuasi Posisi Terbuka Berbasis Best Bid
    open_positions = state.setdefault("open_positions", {})
    market_value_holdings = 0.0

    for sym in UNIVERSE:
        pair_id = sym.lower()
        try:
            depth = client.get_order_book(pair_id)
            bids = depth.get("buy", [])
            asks = depth.get("sell", [])
            if bids and asks:
                best_bid = float(bids[0][0])
                best_ask = float(asks[0][0])
                spread_pct = (best_ask - best_bid) / best_bid
                # Simpan snapshot
                state.setdefault("orderbook_snapshots", []).append({
                    "timestamp": tick_start_time,
                    "symbol": sym,
                    "best_bid": best_bid,
                    "best_ask": best_ask,
                    "spread_pct": spread_pct
                })
                # Jika memiliki posisi koin ini, hitung valuasi likuidasi di Best Bid
                if sym in open_positions:
                    pos = open_positions[sym]
                    market_value_holdings += pos["qty"] * best_bid
        except Exception as e:
            err_msg = f"Gagal update depth order book {sym}: {e}"
            tick_summary["errors"].append(err_msg)

    # 3. Hitung Ekuitas Total (Kas + Valuasi Likuidasi Koin)
    cash = state.get("cash", 100_000_000.0)
    current_equity = cash + market_value_holdings
    state["equity"] = current_equity

    # Catat equity harian jika pergantian hari WIB (setelah 00.00 WIB)
    daily_equity_map = state.setdefault("daily_equity", {})
    if today_wib not in daily_equity_map:
        daily_equity_map[today_wib] = current_equity

    # 4. Evaluasi Sinyal Trading (SELL DULU, LALU BUY)
    # A. Evaluasi Posisi Terbuka untuk EXIT
    symbols_to_close = []
    for sym, pos in list(open_positions.items()):
        try:
            bars, val_err = client.get_closed_candles(sym, TF_MINUTES, count=60)
            if val_err:
                tick_summary["errors"].append(f"{sym}: {val_err}")
                continue

            eval_res = evaluasi_sinyal_bar(bars, posisi_terbuka=pos)
            sig = eval_res.get("signal")
            reason = eval_res.get("reason", "")
            last_bar_time = bars[-1]["time"]

            # Catat log sinyal candle-demi-candle (kepatuhan rubrik evaluasi)
            existing_sigs = state.setdefault("candle_signals", [])
            if not any(s.get("symbol") == sym and s.get("timestamp") == last_bar_time for s in existing_sigs):
                existing_sigs.append({
                    "timestamp": last_bar_time,
                    "wib_time": (datetime.fromtimestamp(last_bar_time, tz=timezone.utc) + timedelta(hours=7)).strftime("%Y-%m-%d %H:%M WIB"),
                    "symbol": sym,
                    "close": bars[-1]["close"],
                    "ema_fast": round(eval_res["metrics"].get("ema_fast", 0.0), 2),
                    "ema_slow": round(eval_res["metrics"].get("ema_slow", 0.0), 2),
                    "rsi": round(eval_res["metrics"].get("rsi", 0.0), 2),
                    "vol_sma": round(eval_res["metrics"].get("vol_sma", 0.0), 2),
                    "signal": sig,
                    "reason": reason
                })

            # Update harga tertinggi sejak beli
            if "highest_price" in eval_res:
                pos["highest_price"] = eval_res["highest_price"]

            if sig == "SELL":
                # Eksekusi Jual di BID Live Order Book
                sell_res = client.execute_dry_run_order(
                    pair_id=sym.lower(),
                    side="sell",
                    order_amount_idr=0.0,
                    crypto_amount=pos["qty"]
                )
                if sell_res.get("success"):
                    idr_received = sell_res["idr_received"]
                    fee_rp = sell_res["fee_rp"]
                    net_received = idr_received - fee_rp
                    pnl_rp = net_received - pos["cost_basis"]
                    pnl_pct = (pnl_rp / pos["cost_basis"]) if pos["cost_basis"] > 0 else 0.0

                    cash += net_received
                    state["cash"] = cash

                    trade_record = {
                        "symbol": sym,
                        "entry_time": pos["entry_time"],
                        "entry_price": pos["entry_price"],
                        "exit_time": tick_start_time,
                        "exit_date": wib_now_str,
                        "exit_price": sell_res["avg_fill_price"],
                        "qty": pos["qty"],
                        "cost_basis": pos["cost_basis"],
                        "net_proceeds": net_received,
                        "fee_rp": fee_rp + pos.get("entry_fee", 0.0),
                        "pnl_rp": pnl_rp,
                        "pnl_pct": pnl_pct,
                        "reason": reason,
                        "spread_pct": sell_res["spread_pct"],
                        "slippage_pct": sell_res["slippage_pct"]
                    }
                    state.setdefault("closed_trades", []).append(trade_record)
                    state.setdefault("order_logs", []).append({
                        "time": wib_now_str,
                        "symbol": sym,
                        "side": "SELL",
                        "qty": pos["qty"],
                        "price": sell_res["avg_fill_price"],
                        "fee_rp": fee_rp,
                        "reason": reason
                    })
                    symbols_to_close.append(sym)
                    tick_summary["actions"].append(f"SELL {sym}: PnL {pnl_rp:+,.0f} ({pnl_pct*100:+.2f}%) - {reason}")
                else:
                    tick_summary["errors"].append(f"Gagal eksekusi SELL {sym}: {sell_res.get('reason')}")
        except Exception as e:
            tick_summary["errors"].append(f"Error evaluasi exit {sym}: {e}")

    for sym in symbols_to_close:
        del open_positions[sym]

    # B. Evaluasi Peluang Masuk Posisi Baru (BUY)
    for sym in UNIVERSE:
        if sym in open_positions:
            continue

        try:
            bars, val_err = client.get_closed_candles(sym, TF_MINUTES, count=60)
            if val_err:
                tick_summary["errors"].append(f"{sym}: {val_err}")
                continue

            last_bar_time = bars[-1]["time"]
            # Idempotency check: Jangan proses candle yang sama dua kali
            if not RiskManager.check_idempotency(state, sym, last_bar_time):
                continue

            eval_res = evaluasi_sinyal_bar(bars, posisi_terbuka=None)
            sig = eval_res.get("signal")
            reason = eval_res.get("reason", "")

            # Catat log sinyal candle-demi-candle (kepatuhan rubrik evaluasi)
            existing_sigs = state.setdefault("candle_signals", [])
            if not any(s.get("symbol") == sym and s.get("timestamp") == last_bar_time for s in existing_sigs):
                existing_sigs.append({
                    "timestamp": last_bar_time,
                    "wib_time": (datetime.fromtimestamp(last_bar_time, tz=timezone.utc) + timedelta(hours=7)).strftime("%Y-%m-%d %H:%M WIB"),
                    "symbol": sym,
                    "close": bars[-1]["close"],
                    "ema_fast": round(eval_res["metrics"].get("ema_fast", 0.0), 2),
                    "ema_slow": round(eval_res["metrics"].get("ema_slow", 0.0), 2),
                    "rsi": round(eval_res["metrics"].get("rsi", 0.0), 2),
                    "vol_sma": round(eval_res["metrics"].get("vol_sma", 0.0), 2),
                    "signal": sig,
                    "reason": reason
                })

            if sig == "BUY":
                can_buy, risk_reason, alloc_idr = risk_mgr.can_open_new_position(
                    state, sym, current_equity, tick_start_time
                )
                if can_buy:
                    # Eksekusi Beli di ASK Live Order Book
                    buy_res = client.execute_dry_run_order(
                        pair_id=sym.lower(),
                        side="buy",
                        order_amount_idr=alloc_idr
                    )
                    if buy_res.get("success"):
                        crypto_got = buy_res["crypto_amount"]
                        idr_spent = buy_res["idr_spent"]
                        fee_rp = buy_res["fee_rp"]
                        total_deducted = idr_spent + fee_rp

                        cash -= total_deducted
                        state["cash"] = cash

                        open_positions[sym] = {
                            "entry_price": buy_res["avg_fill_price"],
                            "qty": crypto_got,
                            "entry_time": tick_start_time,
                            "entry_date": wib_now_str,
                            "highest_price": buy_res["avg_fill_price"],
                            "cost_basis": total_deducted,
                            "entry_fee": fee_rp,
                            "reason": reason
                        }
                        state.setdefault("order_logs", []).append({
                            "time": wib_now_str,
                            "symbol": sym,
                            "side": "BUY",
                            "qty": crypto_got,
                            "price": buy_res["avg_fill_price"],
                            "fee_rp": fee_rp,
                            "reason": reason
                        })
                        tick_summary["actions"].append(f"BUY {sym}: Rp{idr_spent:,.0f} @ {buy_res['avg_fill_price']:,.0f} - {reason}")
                    else:
                        tick_summary["errors"].append(f"Gagal eksekusi BUY {sym}: {buy_res.get('reason')}")
                else:
                    # Ditolak oleh Risk Manager (misal kuota penuh atau daily loss limit)
                    pass

            # Tandai candle sudah diproses untuk idempotensi
            RiskManager.mark_candle_processed(state, sym, last_bar_time)

        except Exception as e:
            tick_summary["errors"].append(f"Error evaluasi entry {sym}: {e}")

    # 5. Rekam Log Tick & Simpan State Persisten
    state.setdefault("tick_logs", []).append({
        "timestamp": tick_start_time,
        "wib_time": wib_now_str,
        "status": "success" if not tick_summary["errors"] else "partial_error",
        "equity": state.get("equity", 100_000_000.0),
        "cash": state.get("cash", 100_000_000.0),
        "open_positions": len(open_positions),
        "actions_count": len(tick_summary["actions"]),
        "errors_count": len(tick_summary["errors"])
    })

    # Pangkas log agar hemat ruang penyimpanan (maksimal 500 tick terakhir)
    if len(state["tick_logs"]) > 500:
        state["tick_logs"] = state["tick_logs"][-500:]
    if len(state.get("orderbook_snapshots", [])) > 500:
        state["orderbook_snapshots"] = state["orderbook_snapshots"][-500:]

    storage.save_state(state)
    return tick_summary


# =============================================================================
# HANDLER VERCEL HTTP REQUEST (NATIVE BASE HTTP)
# =============================================================================
class handler(BaseHTTPRequestHandler):
    def _verify_cron_secret(self) -> bool:
        expected_secret = os.getenv("CRON_SECRET", "").strip()
        if not expected_secret:
            # Jika tidak ada CRON_SECRET di env (development mode), izinkan akses
            return True

        # Cek Header Authorization
        auth_header = self.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header.replace("Bearer ", "").strip()
            if token == expected_secret:
                return True

        # Cek Query Param (?secret=...)
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        secret_param = params.get("secret", [None])[0]
        if secret_param == expected_secret:
            return True

        return False

    def do_GET(self):
        # 1. Validasi Keamanan Secret
        if not self._verify_cron_secret():
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "error": "Unauthorized",
                "message": "CRON_SECRET tidak valid atau tidak disertakan."
            }).encode("utf-8"))
            return

        # 2. Jalankan Logika Bot
        try:
            summary = run_bot_tick(trigger_source="http_get")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(summary, indent=2).encode("utf-8"))
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "error": "InternalServerError",
                "message": str(e)
            }).encode("utf-8"))

    def do_POST(self):
        self.do_GET()

if __name__ == "__main__":
    print("Testing bot tick locally...")
    res = run_bot_tick(trigger_source="local_cli")
    print("Result:", json.dumps(res, indent=2))

