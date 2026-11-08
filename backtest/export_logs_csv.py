"""
=============================================================================
EKSPORTIR LOG MENTAH KE FORMAT CSV (export_logs_csv.py)
UAS Algoritma Trading - Bot Dry Run Indodax di Vercel
Mahasiswa   : Indri Destiyana (NIM: 25120200007)
=============================================================================
Kepatuhan Wajib Soal UAS Halaman 5:
"Log mentah forward test dalam CSV atau JSON: setiap panggilan bot, setiap
 order simulasi, equity harian, setiap error, dan snapshot order book."
Skrip ini mengekspor seluruh log mentah JSON menjadi format CSV tabular standar.
=============================================================================
"""

import os
import csv
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")

def export_all_to_csv():
    fwd_path = os.path.join(DATA_DIR, "forward_test_state.json")
    bt_path = os.path.join(DATA_DIR, "backtest_results.json")
    snap_path = os.path.join(DATA_DIR, "orderbook_snapshots.json")

    fwd_data = {}
    bt_data = {}
    snapshots = []

    if os.path.exists(fwd_path):
        with open(fwd_path, "r", encoding="utf-8") as f:
            fwd_data = json.load(f)

    if os.path.exists(bt_path):
        with open(bt_path, "r", encoding="utf-8") as f:
            bt_data = json.load(f)

    if os.path.exists(snap_path):
        with open(snap_path, "r", encoding="utf-8") as f:
            snapshots = json.load(f)

    # 1. Ekspor Log Transaksi Selesai (Closed Trades)
    trades = fwd_data.get("closed_trades", [])
    if not trades:
        trades = bt_data.get("closed_trades", [])

    trades_csv = os.path.join(DATA_DIR, "closed_trades.csv")
    with open(trades_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Symbol", "Entry_Time", "Entry_Date", "Entry_Price", "Exit_Time", "Exit_Date", "Exit_Price", "Qty", "Cost_Basis", "Net_Proceeds", "PnL_Rp", "PnL_Pct", "Reason", "Hold_Hours"])
        for t in trades:
            writer.writerow([
                t.get("symbol"),
                t.get("entry_time"),
                t.get("entry_date"),
                t.get("entry_price"),
                t.get("exit_time"),
                t.get("exit_date"),
                t.get("exit_price"),
                t.get("qty"),
                t.get("cost_basis"),
                t.get("net_proceeds"),
                t.get("pnl_rp"),
                t.get("pnl_pct"),
                t.get("reason"),
                t.get("hold_hours", 0)
            ])
    print(f"[CSV] Berhasil ekspor {len(trades)} transaksi tertutup -> {trades_csv}")

    # 2. Ekspor Log Panggilan Bot & Error (Tick Logs)
    tick_logs = fwd_data.get("tick_logs", [])
    ticks_csv = os.path.join(DATA_DIR, "bot_tick_logs.csv")
    with open(ticks_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Timestamp", "WIB_Time", "Status", "Equity", "Cash", "Open_Positions", "Actions_Count", "Errors_Count", "Message"])
        for tl in tick_logs:
            writer.writerow([
                tl.get("timestamp"),
                tl.get("wib_time"),
                tl.get("status"),
                tl.get("equity"),
                tl.get("cash"),
                tl.get("open_positions"),
                tl.get("actions_count", 0),
                tl.get("errors_count", 0),
                tl.get("message", "")
            ])
    print(f"[CSV] Berhasil ekspor {len(tick_logs)} log panggilan bot -> {ticks_csv}")

    # 3. Ekspor Log Order Simulasi (Orders Log)
    order_logs = fwd_data.get("order_logs", [])
    orders_csv = os.path.join(DATA_DIR, "simulation_orders.csv")
    with open(orders_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Time", "Symbol", "Side", "Qty", "Price", "Fee_Rp", "Reason"])
        for o in order_logs:
            writer.writerow([
                o.get("time"),
                o.get("symbol"),
                o.get("side"),
                o.get("qty"),
                o.get("price"),
                o.get("fee_rp"),
                o.get("reason")
            ])
    print(f"[CSV] Berhasil ekspor {len(order_logs)} log order simulasi -> {orders_csv}")

    # 4. Ekspor Ekuitas Harian (Daily Equity)
    daily_eq = fwd_data.get("daily_equity", {})
    if not daily_eq:
        daily_eq = bt_data.get("daily_equity", {})

    daily_eq_csv = os.path.join(DATA_DIR, "daily_equity.csv")
    with open(daily_eq_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Date_WIB", "Equity_Rp"])
        for d, eq in sorted(daily_eq.items()):
            writer.writerow([d, eq])
    print(f"[CSV] Berhasil ekspor {len(daily_eq)} catatan ekuitas harian -> {daily_eq_csv}")

    # 5. Ekspor Snapshot Order Book
    all_snaps = snapshots + fwd_data.get("orderbook_snapshots", [])
    snaps_csv = os.path.join(DATA_DIR, "orderbook_snapshots.csv")
    with open(snaps_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Timestamp", "Datetime", "Symbol", "Best_Bid", "Best_Ask", "Spread_Pct"])
        for s in all_snaps:
            writer.writerow([
                s.get("timestamp"),
                s.get("datetime", ""),
                s.get("symbol"),
                s.get("best_bid"),
                s.get("best_ask"),
                s.get("spread_pct")
            ])
    print(f"[CSV] Berhasil ekspor {len(all_snaps)} snapshot order book -> {snaps_csv}")
    print("=" * 80)
    print(" SELURUH LOG CSV MENTAH BERHASIL DIHASILKAN!")
    print("=" * 80)

if __name__ == "__main__":
    export_all_to_csv()
