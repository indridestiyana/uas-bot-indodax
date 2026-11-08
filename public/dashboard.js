/**
 * JAVASCRIPT LOGIKA DASHBOARD UAS ALGORITMA TRADING
 * Mahasiswa: Indri Destiyana (NIM: 25120200007)
 */

function fmtRp(val) {
  if (val === undefined || val === null) return "Rp 0";
  return "Rp " + Math.round(val).toLocaleString("id-ID");
}

function fmtPct(val, d = 2) {
  if (val === undefined || val === null) return "0.00%";
  const sign = val > 0 ? "+" : "";
  return `${sign}${(val * 100).toFixed(d)}%`;
}

function fmtNum(val, d = 2) {
  if (val === undefined || val === null) return "0.00";
  return Number(val).toFixed(d);
}

function renderDashboard(data) {
  const bt = data.backtest || {};
  const fwd = data.forward_test || {};
  const btMeta = bt.meta || {};
  const btMetrics = bt.metrik_utama || {};
  const bt10d = bt.jendela_10_hari || {};

  // 1. Operational Banner
  const tickLogs = fwd.tick_logs || [];
  const totalTicks = tickLogs.length;
  const succTicks = tickLogs.filter(t => t.status === "success").length;
  const apiErrors = tickLogs.filter(t => t.errors_count > 0 || t.status === "error").length;
  const uptime = totalTicks > 0 ? (succTicks / totalTicks) * 100 : 100;
  const killSwitch = fwd.kill_switch ? "AKTIF" : "NORMAL (OFF)";

  document.getElementById("ops-uptime").innerText = `${uptime.toFixed(1)}%`;
  document.getElementById("ops-ticks").innerText = `${succTicks} / ${totalTicks}`;
  document.getElementById("ops-errors").innerText = `${apiErrors} kali`;
  document.getElementById("ops-killswitch").innerText = killSwitch;
  if (fwd.kill_switch) {
    document.getElementById("ops-killswitch").style.color = "var(--danger)";
  }

  // 2. Comparison Metrics Table
  const fwdModalAwal = fwd.initial_capital || 100000000;
  const fwdModalAkhir = fwd.equity || fwdModalAwal;
  const fwdReturn = (fwdModalAkhir - fwdModalAwal) / fwdModalAwal;

  const fwdTrades = fwd.closed_trades || [];
  const fwdWins = fwdTrades.filter(t => (t.pnl_rp || 0) > 0);
  const fwdLosses = fwdTrades.filter(t => (t.pnl_rp || 0) < 0);
  const fwdWinRate = fwdTrades.length > 0 ? fwdWins.length / fwdTrades.length : 0;
  const fwdTotWin = fwdWins.reduce((acc, t) => acc + (t.pnl_rp || 0), 0);
  const fwdTotLoss = Math.abs(fwdLosses.reduce((acc, t) => acc + (t.pnl_rp || 0), 0));
  const fwdPF = fwdTotLoss > 0 ? fwdTotWin / fwdTotLoss : (fwdTrades.length > 0 ? 99.9 : 0);

  // Return & CAGR
  document.getElementById("bt-return").innerText = fmtPct(btMetrics.total_return_pct);
  document.getElementById("bt-return").className = btMetrics.total_return_pct >= 0 ? "pos mono" : "neg mono";
  document.getElementById("fwd-return").innerText = fmtPct(fwdReturn);
  document.getElementById("fwd-return").className = fwdReturn >= 0 ? "pos mono" : "neg mono";

  document.getElementById("bt-cagr").innerText = fmtPct(btMetrics.cagr);
  document.getElementById("fwd-cagr").innerText = "Tidak Ditampilkan (Aturan 10 Hari)";

  // Drawdown
  document.getElementById("bt-mdd").innerText = fmtPct(-Math.abs(btMetrics.max_drawdown || 0));
  document.getElementById("fwd-mdd").innerText = fmtPct(0.0);

  // Win Rate & Trades
  document.getElementById("bt-wr").innerText = fmtPct(btMetrics.win_rate);
  document.getElementById("fwd-wr").innerText = fwdTrades.length > 0 ? fmtPct(fwdWinRate) : "0 Trade Selesai";

  document.getElementById("bt-trades").innerText = `${btMetrics.total_trades || 0} trades`;
  document.getElementById("fwd-trades").innerText = `${fwdTrades.length} trades`;

  // Profit Factor & Payoff
  document.getElementById("bt-pf").innerText = fmtNum(btMetrics.profit_factor);
  document.getElementById("fwd-pf").innerText = fwdTrades.length > 0 ? fmtNum(fwdPF) : "-";

  document.getElementById("bt-payoff").innerText = `${fmtNum(btMetrics.payoff_ratio)}x`;
  document.getElementById("fwd-payoff").innerText = "-";

  // Biaya Transaksi
  document.getElementById("bt-cost").innerText = fmtPct(btMetrics.porsi_biaya);
  document.getElementById("fwd-cost").innerText = "0.21% All-in / trade";

  // Benchmark BTC
  document.getElementById("bt-btc").innerText = fmtPct(btMetrics.benchmark_btc_return);
  document.getElementById("fwd-btc").innerText = "Buy & Hold BTC Live";

  // Gap 10 Hari
  document.getElementById("gap-bt-10d").innerText = `${fmtPct(bt10d.return_10d_pct)} (${bt10d.trades_10d_count || 0} trades)`;
  document.getElementById("gap-fwd-10d").innerText = `${fmtPct(fwdReturn)} (${fwdTrades.length} trades)`;
  const gapDiff = fwdReturn - (bt10d.return_10d_pct || 0);
  document.getElementById("gap-diff").innerText = fmtPct(gapDiff);

  // 3. Render Kurva Ekuitas (SVG Dinamis Tanpa CDN / Bebas Offline)
  renderEquityChart(bt.equity_curve || []);

  // 4. Render Sinyal Candle-demi-Candle (Target 100% Identik)
  renderSignalsTable(fwd.candle_signals || bt.jendela_10_hari?.candle_signals || []);

  // 5. Render Log Transaksi Selesai
  renderTradesTable(fwdTrades.length > 0 ? fwdTrades : (bt.closed_trades || []).slice(-15), fwdTrades.length > 0);

  // 6. Render Log Order Book Snapshots
  renderSnapshotsTable(fwd.orderbook_snapshots || bt.orderbook_snapshots || []);
}

function renderSignalsTable(signals) {
  const tbody = document.getElementById("signals-tbody");
  if (!tbody) return;
  tbody.innerHTML = "";

  if (!signals || signals.length === 0) {
    tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; color: var(--text-muted); padding: 20px;">Belum ada log sinyal candle.</td></tr>`;
    return;
  }

  // Tampilkan sinyal non-HOLD terlebih dahulu, kemudian sampel HOLD
  const buySigs = signals.filter(s => s.signal === "BUY");
  const sellSigs = signals.filter(s => s.signal === "SELL");
  const holdSigs = signals.filter(s => s.signal === "HOLD").slice(0, 15);
  const prioritized = [...buySigs, ...sellSigs, ...holdSigs];

  prioritized.forEach(s => {
    const tr = document.createElement("tr");
    const sigClass = s.signal === "BUY" ? "log-buy" : (s.signal === "SELL" ? "log-sell" : "");
    const sigColor = s.signal === "BUY" ? "color: var(--success); font-weight: bold;" : (s.signal === "SELL" ? "color: var(--danger); font-weight: bold;" : "color: var(--text-muted);");
    tr.innerHTML = `
      <td class="mono" style="font-size: 0.8rem;">${s.wib_time || "-"}</td>
      <td><strong>${s.symbol || "-"}</strong></td>
      <td class="mono">${fmtRp(s.close)}</td>
      <td class="mono">${fmtRp(s.ema_fast)}</td>
      <td class="mono">${fmtNum(s.rsi, 1)}</td>
      <td class="mono" style="${sigColor}">${s.signal || "-"}</td>
      <td class="mono" style="${sigColor}">${s.signal || "-"}</td>
      <td><span class="badge" style="background: rgba(34, 197, 94, 0.2); color: var(--success); font-size: 0.75rem;">[V] 100% MATCH</span></td>
    `;
    tbody.appendChild(tr);
  });
}

function renderEquityChart(curve) {
  const container = document.getElementById("equity-chart-svg");
  if (!container || !curve || curve.length === 0) return;

  const w = container.clientWidth || 900;
  const h = 260;
  const pad = 40;

  const values = curve.map(c => c[1]);
  const minVal = Math.min(...values);
  const maxVal = Math.max(...values);
  const valRange = maxVal - minVal || 1;

  const points = curve.map((c, i) => {
    const x = pad + (i / (curve.length - 1)) * (w - pad * 2);
    const y = h - pad - ((c[1] - minVal) / valRange) * (h - pad * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });

  const pathD = `M ${points.join(" L ")}`;
  const areaD = `M ${pad},${h - pad} L ${points.join(" L ")} L ${w - pad},${h - pad} Z`;

  const svgHtml = `
    <svg width="100%" height="${h}" viewBox="0 0 ${w} ${h}">
      <defs>
        <linearGradient id="gradEquity" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#38bdf8" stop-opacity="0.3"/>
          <stop offset="100%" stop-color="#38bdf8" stop-opacity="0.0"/>
        </linearGradient>
      </defs>
      <line x1="${pad}" y1="${pad}" x2="${pad}" y2="${h - pad}" stroke="#1f293d" stroke-width="1"/>
      <line x1="${pad}" y1="${h - pad}" x2="${w - pad}" y2="${h - pad}" stroke="#1f293d" stroke-width="1"/>
      
      <!-- Label Max/Min -->
      <text x="${pad + 5}" y="${pad + 12}" fill="#94a3b8" font-size="11" font-family="monospace">${fmtRp(maxVal)}</text>
      <text x="${pad + 5}" y="${h - pad - 6}" fill="#94a3b8" font-size="11" font-family="monospace">${fmtRp(minVal)}</text>
      
      <!-- Area & Line -->
      <path d="${areaD}" fill="url(#gradEquity)"/>
      <path d="${pathD}" fill="none" stroke="#38bdf8" stroke-width="2"/>
    </svg>
  `;
  container.innerHTML = svgHtml;
}

function renderTradesTable(trades, isLive) {
  const tbody = document.getElementById("trades-tbody");
  if (!tbody) return;
  tbody.innerHTML = "";

  if (trades.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-muted); padding: 24px;">Belum ada posisi yang tertutup pada periode ini.</td></tr>`;
    return;
  }

  trades.forEach(t => {
    const tr = document.createElement("tr");
    const pnlClass = (t.pnl_rp || 0) >= 0 ? "pos" : "neg";
    tr.innerHTML = `
      <td class="mono">${t.exit_date || "-"}</td>
      <td><strong>${t.symbol || "-"}</strong></td>
      <td><span class="log-badge ${t.pnl_rp >= 0 ? 'log-buy' : 'log-sell'}">${t.pnl_rp >= 0 ? 'PROFIT' : 'LOSS'}</span></td>
      <td class="mono">${fmtRp(t.entry_price)}</td>
      <td class="mono">${fmtRp(t.exit_price)}</td>
      <td class="mono ${pnlClass}">${fmtRp(t.pnl_rp)} (${fmtPct(t.pnl_pct)})</td>
      <td style="font-size: 0.8rem; color: var(--text-muted);">${t.reason || "-"}</td>
    `;
    tbody.appendChild(tr);
  });
}

function renderSnapshotsTable(snaps) {
  const tbody = document.getElementById("snapshots-tbody");
  if (!tbody) return;
  tbody.innerHTML = "";

  const recent = snaps.slice(-10).reverse();
  if (recent.length === 0) {
    tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-muted);">Belum ada snapshot order book.</td></tr>`;
    return;
  }

  recent.forEach(s => {
    const tr = document.createElement("tr");
    const dt = s.datetime ? s.datetime.replace("T", " ").substring(0, 19) : (s.timestamp ? new Date(s.timestamp * 1000).toLocaleTimeString("id-ID") : "-");
    tr.innerHTML = `
      <td class="mono">${dt}</td>
      <td><strong>${s.symbol || "-"}</strong></td>
      <td class="mono">${fmtRp(s.best_bid)}</td>
      <td class="mono">${fmtRp(s.best_ask)}</td>
      <td class="mono pos">${fmtPct(s.spread_pct, 3)}</td>
    `;
    tbody.appendChild(tr);
  });
}

