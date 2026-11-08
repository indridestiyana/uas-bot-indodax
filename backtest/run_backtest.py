"""
=============================================================================
MESIN BACKTEST KUANTITATIF 3 TAHUN INDODAX (run_backtest.py - HIGH PERFORMANCE)
UAS Algoritma Trading - Bot Dry Run Indodax di Vercel
Mahasiswa   : Indri Destiyana (NIM: 25120200007)
=============================================================================
"""

import os
import sys
import json
import math
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Tuple

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from engine.strategy import StrategyConfig, hitung_seluruh_indikator, evaluasi_sinyal_bar

MODAL_AWAL = 100_000_000.0
FEE_TAKER = 0.0021          # 0.21% Taker fee all-in Indodax
MIN_ORDER_IDR = 25_000.0
DEFAULT_SPREAD_PCT = 0.0012 # 0.12% median spread bid-ask dari order book
DEFAULT_SLIPPAGE_PCT = 0.0008 # 0.08% estimasi slippage rata-rata

def muat_data_simbol(data_dir: str, symbol: str) -> List[Dict[str, Any]]:
    path = os.path.join(data_dir, f"{symbol}_1h_3y.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"File data tidak ditemukan: {path}. Jalankan fetch_data_3thn.py terlebih dahulu.")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def muat_median_spread(data_dir: str) -> float:
    path = os.path.join(data_dir, "orderbook_snapshots.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                snaps = json.load(f)
                spreads = [s.get("spread_pct", DEFAULT_SPREAD_PCT) for s in snaps if s.get("spread_pct", 0) > 0]
                if spreads:     
                    spreads.sort()
                    return spreads[len(spreads) // 2]
        except Exception:
            pass
    return DEFAULT_SPREAD_PCT

def hitung_mdd(equity_history: List[Tuple[int, float]]) -> Tuple[float, str, str]:
    if not equity_history:
        return 0.0, "", ""
    peak = -float('inf')
    peak_date = ""
    cur_peak_date = ""
    trough_date = ""
    max_dd = 0.0
    for ts, eq in equity_history:
        dt_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        if eq > peak:
            peak = eq
            cur_peak_date = dt_str
        dd = (eq - peak) / peak
        if dd < max_dd:
            max_dd = dd
            peak_date = cur_peak_date
            trough_date = dt_str
    return abs(max_dd), peak_date, trough_date

def jalankan_backtest():
    data_dir = os.path.join(BASE_DIR, "data")
    symbols = ["BTCIDR", "ETHIDR", "DOGEIDR"]
    spread_pct = muat_median_spread(data_dir)
    slippage_pct = DEFAULT_SLIPPAGE_PCT

    print("=" * 80)
    print(" MENJALANKAN SIMULASI BACKTEST KUANTITATIF 3 TAHUN (INDODAX)")
    print(f" Modal Awal         : Rp {MODAL_AWAL:,.0f}")
    print(f" Universe Kripto    : {', '.join(symbols)}")
    print(f" Fee Taker All-in   : {FEE_TAKER * 100:.2f}%")
    print(f" Measured Spread    : {spread_pct * 100:.3f}% (Median dari order book)")
    print(f" Estimated Slippage : {slippage_pct * 100:.3f}%")
    print("=" * 80)

    # 1. Muat bar dan pre-compute seluruh indikator
    symbol_bars = {}
    symbol_indicators = {}
    symbol_time_to_idx = {}

    for sym in symbols:
        bars = muat_data_simbol(data_dir, sym)
        symbol_bars[sym] = bars
        symbol_indicators[sym] = hitung_seluruh_indikator(bars)
        symbol_time_to_idx[sym] = {b["time"]: i for i, b in enumerate(bars)}

    # Sinkronisasi timeline bersama
    common_times = set(symbol_time_to_idx[symbols[0]].keys())
    for sym in symbols[1:]:
        common_times = common_times.intersection(set(symbol_time_to_idx[sym].keys()))
    sorted_times = sorted(list(common_times))

    warmup_period = 35
    if len(sorted_times) <= warmup_period:
        raise ValueError("Data historis terlalu pendek.")

    sim_times = sorted_times[warmup_period:]
    print(f" Total Bar Sinkron Disimulasikan: {len(sim_times):,} jam candle")

    cash = MODAL_AWAL
    open_positions = {} # sym: {entry_price, qty, entry_time, highest_price, cost_basis, entry_fee}
    closed_trades = []
    equity_curve = []
    daily_equity_log = {}

    total_fees_paid = 0.0
    total_spread_cost = 0.0
    total_slippage_cost = 0.0

    btc_first_price = None
    btc_last_price = None

    for i in range(len(sim_times) - 1):
        curr_time = sim_times[i]
        next_time = sim_times[i + 1]

        # 1. Valuasi Portofolio Berbasis Best Bid Realistis
        current_portfolio_value = cash
        for sym, pos in open_positions.items():
            sym_idx = symbol_time_to_idx[sym][curr_time]
            bar = symbol_bars[sym][sym_idx]
            cur_bid = bar["close"] * (1.0 - (spread_pct / 2.0))
            current_portfolio_value += pos["qty"] * cur_bid

        equity_curve.append((curr_time, current_portfolio_value))

        wib_date = (datetime.fromtimestamp(curr_time, tz=timezone.utc) + timedelta(hours=7)).strftime("%Y-%m-%d")
        if wib_date not in daily_equity_log:
            daily_equity_log[wib_date] = current_portfolio_value

        # Benchmark BTC
        btc_idx = symbol_time_to_idx["BTCIDR"][curr_time]
        btc_close = symbol_bars["BTCIDR"][btc_idx]["close"]
        if btc_first_price is None:
            btc_first_price = btc_close
        btc_last_price = btc_close

        # 2. Evaluasi Sinyal Trading (O(1) look-up)
        pending_sells = []
        pending_buys = []

        for sym in symbols:
            sym_idx = symbol_time_to_idx[sym][curr_time]
            pos = open_positions.get(sym)

            eval_res = evaluasi_sinyal_bar(
                bars=symbol_bars[sym],
                posisi_terbuka=pos,
                indicators=symbol_indicators[sym],
                bar_index=sym_idx
            )
            sig = eval_res.get("signal")
            reason = eval_res.get("reason", "")

            if pos is not None and "highest_price" in eval_res:
                pos["highest_price"] = eval_res["highest_price"]

            if sig == "SELL" and pos is not None:
                pending_sells.append({"sym": sym, "reason": reason, "pos": pos})
            elif sig == "BUY" and pos is None:
                if len(open_positions) < StrategyConfig.MAX_OPEN_POSITIONS:
                    pending_buys.append({"sym": sym, "reason": reason})

        # 3. Eksekusi Order di Open Bar Berikutnya (next_time)
        # Eksekusi SELL
        for order in pending_sells:
            sym = order["sym"]
            pos = order["pos"]
            next_idx = symbol_time_to_idx[sym][next_time]
            next_open = symbol_bars[sym][next_idx]["open"]

            exec_price = next_open * (1.0 - (spread_pct / 2.0) - slippage_pct)
            gross_proceeds = pos["qty"] * exec_price
            fee = gross_proceeds * FEE_TAKER
            net_proceeds = gross_proceeds - fee

            cost_spread = pos["qty"] * next_open * (spread_pct / 2.0)
            cost_slip = pos["qty"] * next_open * slippage_pct

            cash += net_proceeds
            pnl_net_rp = net_proceeds - pos["cost_basis"]
            pnl_pct = (pnl_net_rp / pos["cost_basis"]) if pos["cost_basis"] > 0 else 0.0

            total_fees_paid += fee + pos["entry_fee"]
            total_spread_cost += cost_spread
            total_slippage_cost += cost_slip

            closed_trades.append({
                "symbol": sym,
                "entry_time": pos["entry_time"],
                "entry_date": datetime.fromtimestamp(pos["entry_time"], tz=timezone.utc).strftime("%Y-%m-%d %H:%M"),
                "entry_price": round(pos["entry_price"], 2),
                "exit_time": next_time,
                "exit_date": datetime.fromtimestamp(next_time, tz=timezone.utc).strftime("%Y-%m-%d %H:%M"),
                "exit_price": round(exec_price, 2),
                "qty": pos["qty"],
                "cost_basis": round(pos["cost_basis"], 2),
                "net_proceeds": round(net_proceeds, 2),
                "pnl_rp": round(pnl_net_rp, 2),
                "pnl_pct": round(pnl_pct, 4),
                "reason": order["reason"],
                "hold_hours": int((next_time - pos["entry_time"]) / 3600),
            })
            del open_positions[sym]

        # Eksekusi BUY
        for order in pending_buys:
            sym = order["sym"]
            if sym in open_positions or len(open_positions) >= StrategyConfig.MAX_OPEN_POSITIONS:
                continue

            next_idx = symbol_time_to_idx[sym][next_time]
            next_open = symbol_bars[sym][next_idx]["open"]

            target_alloc = current_portfolio_value * StrategyConfig.ALLOCATION_PER_POS
            alloc_idr = min(target_alloc, cash)

            if alloc_idr < MIN_ORDER_IDR:
                continue

            exec_price = next_open * (1.0 + (spread_pct / 2.0) + slippage_pct)
            fee = alloc_idr * FEE_TAKER
            net_alloc = alloc_idr - fee
            qty = net_alloc / exec_price

            cost_spread = net_alloc * (spread_pct / 2.0)
            cost_slip = net_alloc * slippage_pct
            total_spread_cost += cost_spread
            total_slippage_cost += cost_slip

            cash -= alloc_idr
            open_positions[sym] = {
                "entry_price": exec_price,
                "qty": qty,
                "entry_time": next_time,
                "highest_price": exec_price,
                "cost_basis": alloc_idr,
                "entry_fee": fee,
            }

    # Final mark-to-market
    final_time = sim_times[-1]
    final_equity = cash
    for sym, pos in open_positions.items():
        last_idx = symbol_time_to_idx[sym][final_time]
        cur_bid = symbol_bars[sym][last_idx]["close"] * (1.0 - (spread_pct / 2.0))
        final_equity += pos["qty"] * cur_bid

    total_return_pct = (final_equity - MODAL_AWAL) / MODAL_AWAL
    t_start = sim_times[0]
    t_end = sim_times[-1]
    years = (t_end - t_start) / (365.25 * 86400)
    cagr = math.pow(final_equity / MODAL_AWAL, 1.0 / years) - 1.0 if years > 0 and final_equity > 0 else 0.0

    mdd_pct, peak_d, trough_d = hitung_mdd(equity_curve)

    n_trades = len(closed_trades)
    wins = [t for t in closed_trades if t["pnl_rp"] > 0]
    losses = [t for t in closed_trades if t["pnl_rp"] < 0]
    win_rate = (len(wins) / n_trades) if n_trades > 0 else 0.0

    total_win_rp = sum(t["pnl_rp"] for t in wins)
    total_loss_rp = abs(sum(t["pnl_rp"] for t in losses))
    profit_factor = (total_win_rp / total_loss_rp) if total_loss_rp > 0 else float('inf')

    avg_win_pct = (sum(t["pnl_pct"] for t in wins) / len(wins)) if wins else 0.0
    avg_loss_pct = (sum(t["pnl_pct"] for t in losses) / len(losses)) if losses else 0.0
    avg_win_rp = (total_win_rp / len(wins)) if wins else 0.0
    avg_loss_rp = (-total_loss_rp / len(losses)) if losses else 0.0
    payoff_ratio = abs(avg_win_pct / avg_loss_pct) if avg_loss_pct != 0 else 0.0

    total_cost_all = total_fees_paid + total_spread_cost + total_slippage_cost
    laba_kotor = total_win_rp + total_cost_all
    porsi_biaya = (total_cost_all / laba_kotor) if laba_kotor > 0 else 0.0

    btc_return_pct = ((btc_last_price - btc_first_price) / btc_first_price) if btc_first_price else 0.0

    sepuluh_hari_detik = 10 * 86400
    cutoff_10d = t_end - sepuluh_hari_detik
    trades_10d = [t for t in closed_trades if t["exit_time"] >= cutoff_10d]
    eq_10d = [p for p in equity_curve if p[0] >= cutoff_10d]
    ret_10d = (eq_10d[-1][1] - eq_10d[0][1]) / eq_10d[0][1] if len(eq_10d) >= 2 else 0.0

    hasil_ringkas = {
        "meta": {
            "judul": "Backtest 3 Tahun Indodax (Dual EMA Momentum & ATR)",
            "mahasiswa": "Indri Destiyana (NIM: 25120200007)",
            "modal_awal": MODAL_AWAL,
            "modal_akhir": round(final_equity, 2),
            "start_date": datetime.fromtimestamp(t_start, tz=timezone.utc).strftime("%Y-%m-%d"),
            "end_date": datetime.fromtimestamp(t_end, tz=timezone.utc).strftime("%Y-%m-%d"),
            "durasi_tahun": round(years, 2),
            "timeframe": "1 Jam (tf=60)",
            "universe": symbols
        },
        "metrik_utama": {
            "total_return_pct": round(total_return_pct, 4),
            "cagr": round(cagr, 4),
            "max_drawdown": round(mdd_pct, 4),
            "peak_date": peak_d,
            "trough_date": trough_d,
            "profit_factor": round(profit_factor, 2),
            "win_rate": round(win_rate, 4),
            "total_trades": n_trades,
            "avg_win_pct": round(avg_win_pct, 4),
            "avg_loss_pct": round(avg_loss_pct, 4),
            "avg_win_rp": round(avg_win_rp, 2),
            "avg_loss_rp": round(avg_loss_rp, 2),
            "payoff_ratio": round(payoff_ratio, 2),
            "porsi_biaya": round(porsi_biaya, 4),
            "total_fees_paid": round(total_fees_paid, 2),
            "total_spread_cost": round(total_spread_cost, 2),
            "total_slippage_cost": round(total_slippage_cost, 2),
            "benchmark_btc_return": round(btc_return_pct, 4),
        },
        "jendela_10_hari": {
            "return_10d_pct": round(ret_10d, 4),
            "trades_10d_count": len(trades_10d),
            "trades_10d": trades_10d
        },
        "equity_curve": [(p[0], round(p[1], 2)) for p in equity_curve[::6]],
        "daily_equity": daily_equity_log,
        "closed_trades": closed_trades
    }

    out_file = os.path.join(data_dir, "backtest_results.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(hasil_ringkas, f, indent=2)

    print("\n" + "=" * 80)
    print(" HASIL BACKTEST 3 TAHUN INDODAX:")
    print("=" * 80)
    print(f" 1. Modal Awal           : Rp {MODAL_AWAL:,.0f}")
    print(f" 2. Ekuitas Akhir        : Rp {final_equity:,.0f} (Net Return: {total_return_pct*100:+.2f}%)")
    print(f" 3. CAGR                 : {cagr*100:+.2f}% / tahun")
    print(f" 4. Maximum Drawdown     : {mdd_pct*100:.2f}% (Puncak: {peak_d} -> Lembah: {trough_d})")
    print(f" 5. Total Trades Selesai : {n_trades} trade (Win: {len(wins)} / Loss: {len(losses)})")
    print(f" 6. Win Rate             : {win_rate*100:.2f}%")
    print(f" 7. Profit Factor        : {profit_factor:.2f}")
    print(f" 8. Payoff Ratio         : {payoff_ratio:.2f}x")
    print(f" 9. Porsi Biaya Total    : {porsi_biaya*100:.2f}% dari Laba Kotor")
    print(f"    - Fee Taker Terbayar : Rp {total_fees_paid:,.0f}")
    print(f"    - Spread Cost Est.   : Rp {total_spread_cost:,.0f}")
    print(f"    - Slippage Cost Est. : Rp {total_slippage_cost:,.0f}")
    print(f" 10. Benchmark BTC B&H   : {btc_return_pct*100:+.2f}%")
    print(f" 11. Jendela 10 Hari Terakhir: Return {ret_10d*100:+.2f}%, Trades: {len(trades_10d)}")
    print("=" * 80)
    print(f" Berkas ringkasan tersimpan di: {out_file}\n")

    return hasil_ringkas

if __name__ == "__main__":
    jalankan_backtest()
