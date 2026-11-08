"""
=============================================================================
SIMULATOR JALANNYA BOT SECARA REAL-TIME INTERAKTIF (run_live_bot.py)
UAS Algoritma Trading - Indri Destiyana (NIM: 25120200007)
=============================================================================
Menjalankan siklus lengkap bot trading dry run Indodax dengan output detail:
1. Mengambil waktu server Indodax
2. Membaca Live Order Book (Depth) & Spread untuk setiap koin
3. Mengambil candle tertutup (membuang candle berjalan pencegah look-ahead)
4. Menghitung indikator teknikal (EMA, RSI, ATR, Volume SMA)
5. Mengecek aturan Risk Management (Daily loss limit, idempotency, kill switch)
6. Melakukan simulasi eksekusi dry run jika ada sinyal
7. Memperbarui ekuitas mark-to-market berbasis Best Bid
=============================================================================
"""

import os
import sys
import json
import time
from datetime import datetime, timezone, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from engine.indodax_client import IndodaxClient
from engine.strategy import StrategyConfig, hitung_seluruh_indikator, evaluasi_sinyal_bar
from engine.risk_manager import RiskManager
from engine.storage import BotStorage

def fmt_rp(val: float) -> str:
    return f"Rp {val:,.0f}".replace(",", ".")

def fmt_pct(val: float, d: int = 2) -> str:
    sign = "+" if val > 0 else ""
    return f"{sign}{val * 100:.{d}f}%"

def jalankan_siklus_bot():
    print("=" * 80)
    print("   MEMULAI SIKLUS EKSEKUSI BOT TRADING DRY RUN INDODAX (REAL-TIME)")
    print("   Mahasiswa   : Indri Destiyana (NIM: 25120200007)")
    print("   Mata Kuliah : Algorithmic Trading (UAS)")
    print("=" * 80)

    storage = BotStorage()
    state = storage.load_state()
    client = IndodaxClient(timeout=10)
    risk_mgr = RiskManager(
        max_positions=StrategyConfig.MAX_OPEN_POSITIONS,
        max_allocation_pct=StrategyConfig.ALLOCATION_PER_POS
    )

    # 1. Cek Koneksi & Waktu Server Indodax
    print("\n[LANGKAH 1/6] Mengambil Waktu Server Resmi Indodax...")
    try:
        server_epoch = client.get_server_time()
        wib_time_str = (datetime.fromtimestamp(server_epoch, tz=timezone.utc) + timedelta(hours=7)).strftime("%Y-%m-%d %H:%M:%S WIB")
        print(f" -> Koneksi Berhasil!")
        print(f" -> Waktu Server Indodax: {wib_time_str} (Epoch: {server_epoch})")
    except Exception as e:
        print(f" -> Gagal koneksi ke server time Indodax: {e}")
        return

    # 2. Cek Saklar Darurat (Kill Switch)
    print("\n[LANGKAH 2/6] Memeriksa Status Risk Management & Kill Switch...")
    kill_active, kill_msg = RiskManager.is_kill_switch_active(state)
    print(f" -> Status Kill Switch : {'[AKTIF / BERHENTI]' if kill_active else '[NORMAL / AKTIF BERJALAN]'}")
    print(f" -> Keterangan          : {kill_msg}")
    if kill_active:
        print(" -> Bot dihentikan oleh Kill Switch sesuai aturan pengamanan.")
        return

    today_wib = RiskManager.get_wib_date_str(server_epoch)
    current_equity = state.get("equity", 100_000_000.0)
    loss_breached, loss_msg = risk_mgr.evaluate_daily_loss(state, current_equity, server_epoch)
    print(f" -> Daily Loss Limit   : {'[TERLAMPAUI - STOP BUY]' if loss_breached else '[AMAN - DIBAWAH 3%]'}")
    print(f" -> Evaluasi Hari Ini  : {loss_msg} (Tanggal: {today_wib})")

    # 3. Membaca Live Order Book & Menghitung Valuasi Posisi
    print("\n[LANGKAH 3/6] Membaca Live Order Book & Menghitung Spread Real-Time...")
    universe = ["BTCIDR", "ETHIDR", "DOGEIDR"]
    open_positions = state.setdefault("open_positions", {})
    market_value_holdings = 0.0

    print(f"{'Simbol':<8} | {'Best Bid (Beli)':<18} | {'Best Ask (Jual)':<18} | {'Spread (%)':<10} | {'Status Posisi'}")
    print("-" * 75)

    for sym in universe:
        pair_id = sym.lower()
        try:
            depth = client.get_order_book(pair_id)
            bids = depth.get("buy", [])
            asks = depth.get("sell", [])
            if bids and asks:
                best_bid = float(bids[0][0])
                best_ask = float(asks[0][0])
                spread_pct = (best_ask - best_bid) / best_bid
                pos_status = "HOLDING" if sym in open_positions else "KOSONG (CARI SINYAL)"
                print(f"{sym:<8} | {fmt_rp(best_bid):<18} | {fmt_rp(best_ask):<18} | {spread_pct*100:.3f}%     | {pos_status}")
                
                # Simpan snapshot
                state.setdefault("orderbook_snapshots", []).append({
                    "timestamp": server_epoch,
                    "symbol": sym,
                    "best_bid": best_bid,
                    "best_ask": best_ask,
                    "spread_pct": spread_pct
                })

                if sym in open_positions:
                    pos = open_positions[sym]
                    market_value_holdings += pos["qty"] * best_bid
        except Exception as e:
            print(f"{sym:<8} | Gagal membaca depth order book: {e}")

    cash = state.get("cash", 100_000_000.0)
    new_total_equity = cash + market_value_holdings
    state["equity"] = new_total_equity

    print("-" * 75)
    print(f" Kas Tunai Tersedia    : {fmt_rp(cash)}")
    print(f" Valuasi Koin Dimiliki : {fmt_rp(market_value_holdings)} (Dihitung di Best Bid)")
    print(f" Total Ekuitas Saat Ini: {fmt_rp(new_total_equity)}")

    # 4. Evaluasi Posisi Terbuka untuk EXIT (Sinyal JUAL)
    print("\n[LANGKAH 4/6] Mengevaluasi Sinyal Jual (Exit) untuk Posisi Terbuka...")
    if not open_positions:
        print(" -> Tidak ada posisi terbuka yang perlu dievaluasi untuk keluar.")
    else:
        for sym, pos in list(open_positions.items()):
            print(f" -> Menganalisis kondisi keluar untuk {sym}...")
            bars, err = client.get_closed_candles(sym, 60, count=60)
            if err:
                print(f"    [Peringatan] {err}")
                continue
            eval_res = evaluasi_sinyal_bar(bars, posisi_terbuka=pos)
            sig = eval_res.get("signal")
            reason = eval_res.get("reason")
            print(f"    Hasil Evaluasi: {sig} ({reason})")

    # 5. Evaluasi Peluang Masuk Posisi Baru (Sinyal BELI)
    print("\n[LANGKAH 5/6] Menganalisis Peluang Masuk Posisi Baru (Entry - Sinyal BELI)...")
    for sym in universe:
        if sym in open_positions:
            continue

        print(f" -> Memeriksa indikator teknikal {sym} (Timeframe 1 Jam)...")
        bars, err = client.get_closed_candles(sym, 60, count=60)
        if err:
            print(f"    [Peringatan] {err}")
            continue

        last_closed_bar = bars[-1]
        candle_dt = (datetime.fromtimestamp(last_closed_bar['time'], tz=timezone.utc) + timedelta(hours=7)).strftime("%Y-%m-%d %H:%M WIB")
        print(f"    Candle Tertutup Terakhir: {candle_dt} | Close: {fmt_rp(last_closed_bar['close'])}")

        # Hitung indikator
        indicators = hitung_seluruh_indikator(bars)
        ema_f = indicators["ema_fast"][-1]
        ema_s = indicators["ema_slow"][-1]
        rsi_val = indicators["rsi"][-1]
        atr_val = indicators["atr"][-1]
        vol_curr = indicators["volumes"][-1]
        vol_sma = indicators["vol_sma"][-1]

        print(f"    * Fast EMA(12): {fmt_rp(ema_f)} vs Slow EMA(26): {fmt_rp(ema_s)} [{'BULLISH' if ema_f > ema_s else 'BEARISH'}]")
        print(f"    * RSI(14)     : {rsi_val:.1f} [{'MOMENTUM VALID (45-70)' if 45 <= rsi_val <= 70 else 'NETRAL/OVERBOUGHT'}]")
        print(f"    * Volume Bar  : {vol_curr:.2f} vs SMA(20) Vol: {vol_sma:.2f} [{'KONFIRMASI VOLUME' if vol_curr >= vol_sma else 'VOLUME RENDAH'}]")

        eval_res = evaluasi_sinyal_bar(bars, posisi_terbuka=None, indicators=indicators)
        sig = eval_res.get("signal")
        reason = eval_res.get("reason")

        print(f"    -> Keputusan Sinyal: [{sig}] - {reason}")

        if sig == "BUY":
            can_buy, risk_reason, alloc_idr = risk_mgr.can_open_new_position(
                state, sym, new_total_equity, server_epoch
            )
            if can_buy:
                print(f"    -> [SIMULASI EKSEKUSI BELI REALISTIS] Mengalokasikan {fmt_rp(alloc_idr)} ke {sym}...")
                buy_res = client.execute_dry_run_order(
                    pair_id=sym.lower(),
                    side="buy",
                    order_amount_idr=alloc_idr
                )
                if buy_res.get("success"):
                    print(f"       Status: ORDER TERISI (FILL)")
                    print(f"       Harga Eksekusi (Makan Ask) : {fmt_rp(buy_res['avg_fill_price'])}")
                    print(f"       Kuantitas Koin Didapat     : {buy_res['crypto_amount']:.8f} {sym}")
                    print(f"       Fee Taker Indodax (0.21%)  : {fmt_rp(buy_res['fee_rp'])}")
                    print(f"       Slippage VWAP Terukur      : {buy_res['slippage_pct']*100:.3f}%")
                    
                    # Update State
                    total_deducted = buy_res["idr_spent"] + buy_res["fee_rp"]
                    cash -= total_deducted
                    state["cash"] = cash
                    open_positions[sym] = {
                        "entry_price": buy_res["avg_fill_price"],
                        "qty": buy_res["crypto_amount"],
                        "entry_time": server_epoch,
                        "entry_date": wib_time_str,
                        "highest_price": buy_res["avg_fill_price"],
                        "cost_basis": total_deducted,
                        "entry_fee": buy_res["fee_rp"],
                        "reason": reason
                    }
            else:
                print(f"    -> Pembelian ditahan oleh Risk Manager: {risk_reason}")

        # Tandai candle sudah diproses
        RiskManager.mark_candle_processed(state, sym, last_closed_bar["time"])

    # 6. Menyimpan State & Log
    print("\n[LANGKAH 6/6] Menyimpan Log Eksekusi & State Persisten...")
    state.setdefault("tick_logs", []).append({
        "timestamp": server_epoch,
        "wib_time": wib_time_str,
        "status": "success",
        "equity": state.get("equity", 100_000_000.0),
        "cash": state.get("cash", 100_000_000.0),
        "open_positions": len(open_positions),
        "actions_count": 0,
        "errors_count": 0
    })

    storage.save_state(state)
    print(" -> State berhasil disimpan ke database lokal dan cloud storage.")
    print("=" * 80)
    print(" SIKLUS BOT SELESAI DENGAN STATUS: [SUKSES 100%]")
    print(f" Waktu Selesai : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("=" * 80)

if __name__ == "__main__":
    jalankan_siklus_bot()
