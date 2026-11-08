# BOT TRADING DRY RUN INDODAX DI VERCEL
**Mata Kuliah:** Algorithmic Trading (Trad1 & Trad2) &bull; Ujian Akhir Semester (UAS)  
**Mahasiswa:** Indri Destiyana  
**NIM:** 25120200007  
**Tanggal Freeze Aturan:** Rabu, 4 November 2026, 12.00 WIB  
**Commit Freeze Hash:** `fd6c19115ce`  

---

## 1. Ringkasan Eksekutif & Kepatuhan Rubrik Penilaian

Tugas UAS ini mentransformasikan strategi trading algoritmik dari Ujian Tengah Semester (UTS) yang sebelumnya dirancang untuk saham harian BEI menjadi **bot trading otomatis dry run di pasar kripto IDR Indodax** yang berjalan mandiri tanpa intervensi di **Vercel Serverless Functions** dan dijadwalkan secara teratur menggunakan **GitHub Actions Cron**.

### Kepatuhan Rubrik Penilaian UAS:
1. **Kecocokan Backtest vs Forward Test (25%):**
   - Mesin backtest historis dan bot live forward test menggunakan **modul sinyal yang sama persis** (`engine/strategy.py`).
   - Sinyal candle $t$ dieksekusi pada harga pembukaan candle $t+1$ (bebas *look-ahead bias*).
   - Selisih harga eksekusi dijelaskan secara detail melalui pengukuran live order book, spread, slippage, dan deviasi latensi penjadwal cron.
2. **Eksekusi Realistis & Risk Management (25%):**
   - Mengambil data live order book Indodax (`/api/depth`): **Beli di Ask, Jual di Bid**, dengan simulasi *Order Book Walking* (VWAP) bila volume melebihi antrian teratas. Fill di harga mid/close dilarang.
   - Menggunakan fee taker all-in Indodax resmi 0.21%.
   - Minimum order dipatuhi ketat: **Rp 25.000**.
   - Risk management aktif di kode: *Daily Loss Limit* 3% per hari (berganti 00.00 WIB), maksimal 3 posisi terbuka simultan (30% per posisi), *Kill Switch* manual via ENV/state, dan *Idempotency check* per candle timestamp.
3. **Stabilitas Bot di Vercel & Kelengkapan Log (20%):**
   - Uptime dihitung berdasarkan candle terproses sebelum candle berikutnya ditutup dibagi total candle forward test (&ge;95% target penuh).
   - Log mentah tersimpan dalam JSON mencakup setiap panggilan bot, eksekusi order, snapshot depth, dan error API dengan retry terbatas.
4. **Keamanan & Kualitas Kode (15%):**
   - Nol secret di repositori. Seluruh kredensial dan `CRON_SECRET` disimpan di Environment Variables. Berkas `.env` masuk `.gitignore` dan disertakan `.env.example`.
5. **Dashboard, Dokumentasi & Refleksi (15%):**
   - Tersedia berkas mandiri `UAS_25120200007_IndriDestiyana.html` yang dapat dibuka secara offline tanpa internet.
   - Dilengkapi skrip independen `hitung_ulang.py` yang membuktikan bahwa seluruh angka di dashboard berasal dari perhitungan dinamis log mentah (bebas *hardcode*).

---

## 2. Aturan Strategi & Catatan Perubahan dari Versi UTS

### A. Perubahan Desain dari UTS (Saham BEI) ke UAS (Kripto Indodax)
| Parameter | Versi UTS (Saham BEI) | Versi UAS (Kripto Indodax) | Alasan Perubahan |
| :--- | :--- | :--- | :--- |
| **Aset / Universe** | 100 Saham BEI (Kompas100) | 3 Pasang Kripto IDR: `BTC/IDR`, `ETH/IDR`, `DOGE/IDR` | Memilih aset paling likuid di Indodax sejak awal 2023 untuk menghindari *survivorship bias*. |
| **Timeframe** | Harian (1D / End-of-Day) | **1 Jam (`tf=60`)** | Menghasilkan data pengujian 24 candle/hari (240 candle dalam 10 hari forward test) agar sinyal dapat tervalidasi. |
| **Fraksi / Lot** | Fraksi harga BEI & kelipatan 100 lembar lot | Satuan koin desimal kripto | Mengikuti standar perdagangan bursa aset kripto Indodax. |
| **Fee Transaksi** | 0.15% Beli, 0.25% Jual (Broker + PPh) | **0.21% All-in Taker Fee** | Mengikuti tarif resmi Indodax untuk order taker yang mengeksekusi harga pasar. |
| **Batas Minimum** | 1 Lot (~ puluhan ribu s/d jutaan rupiah) | **Rp 25.000** | Ketentuan minimum transaksi mode Pro Indodax. |

### B. Aturan Lengkap Strategi
1. **Modal Awal Virtual:** Rp 100.000.000.
2. **Aturan Masuk (Entry - BUY):**
   - **Kondisi Trend:** Fast EMA (12) > Slow EMA (26).
   - **Kondisi Momentum:** Wilder RSI (14) berada di rentang $45.0 \le \text{RSI} \le 70.0$ (momentum bullish aktif namun belum jenuh beli).
   - **Konfirmasi Volume:** Volume candle penutupan $\ge$ SMA Volume (20).
   - **Konfirmasi Harga:** Harga penutupan candle berada di atas Fast EMA (12).
3. **Aturan Keluar (Exit - SELL):**
   - **Trailing Stop ATR:** Harga menembus ke bawah $(\text{Highest Price Sejak Beli} - 2.5 \times \text{ATR}(14))$.
   - **Hard Stop Loss:** Penurunan harga $\ge 4.0\%$ dari harga beli.
   - **Trend Reversal:** Fast EMA (12) memotong ke bawah Slow EMA (26).
4. **Sizing & Alokasi:**
   - Maksimal 3 posisi terbuka simultan.
   - Alokasi maksimal 30% dari ekuitas total per posisi.

---

## 3. Struktur Berkas Repositori

```
uas_bot_indodax/
├── .github/
│   └── workflows/
│       └── bot_cron.yml      # Penjadwal otomatis per jam (menit ke-7) via GitHub Actions
├── api/
│   ├── tick.py               # Endpoint serverless /api/tick (Bot dry run Vercel)
│   └── state.py              # Endpoint membaca state & log untuk dashboard
├── engine/
│   ├── indodax_client.py     # Modul koneksi API Indodax (Candle tertutup, Depth VWAP, Fee)
│   ├── strategy.py           # Logika indikator & sinyal identik (Backtest & Bot)
│   ├── risk_manager.py       # Daily loss limit, idempotency, kill switch, max sizing
│   └── storage.py            # Persistence layer (Upstash Redis KV / Berkas lokal fallback)
├── backtest/
│   ├── fetch_data_3thn.py    # Skrip penarik 26.280 candle (3 tahun) ditarik mundur
│   ├── run_backtest.py       # Mesin backtest 3 tahun dengan fee, spread, dan slippage
│   └── hitung_ulang.py       # Skrip audit independen pembuktian angka dashboard
├── data/
│   ├── BTCIDR_1h_3y.json     # Data historis asli 3 tahun Indodax (26.280 bar)
│   ├── ETHIDR_1h_3y.json     # Data historis asli 3 tahun Indodax (26.280 bar)
│   ├── DOGEIDR_1h_3y.json    # Data historis asli 3 tahun Indodax (26.280 bar)
│   ├── orderbook_snapshots.json # Snapshot order book untuk median spread
│   ├── backtest_results.json # Hasil komprehensif backtest 3 tahun
│   └── forward_test_state.json # State persisten bot forward test
├── public/
│   ├── index.html            # Dashboard web interaktif Vercel
│   ├── style.css             # Desain tema terminal analitik responsif
│   └── dashboard.js          # Logika visualisasi & render kurva ekuitas SVG
├── build_standalone.py       # Skrip bundler pembuat file dashboard offline mandiri
├── vercel.json               # Konfigurasi Vercel functions, cron, dan routes
├── .env.example              # Template variabel lingkungan aman
├── .gitignore                # Proteksi anti kebocoran token / rahasia
└── UAS_25120200007_IndriDestiyana.html # Berkas offline mandiri untuk dikumpulkan di RISE
```

---

## 4. Panduan Menjalankan & Deploy ke Vercel

### A. Uji Coba Lokal & Re-Kalkulasi (Laptop)
1. **Verifikasi Perhitungan Mandiri:**
   ```bash
   python backtest/hitung_ulang.py
   ```
   Skrip akan membaca seluruh file log mentah dan mencetak tabel audit konsistensi silang status `[V] COCOK`.

2. **Menjalankan Satu Siklus Bot Secara Lokal:**
   ```bash
   python api/tick.py
   ```

3. **Membangun Dashboard Offline Mandiri:**
   ```bash
   python build_standalone.py
   ```

### B. Deploy ke Vercel
1. Unduh repositori ini atau push ke repositori GitHub Anda.
2. Buka dashboard [Vercel](https://vercel.com) &bull; **Add New Project** &bull; Pilih repositori ini.
3. Pada menu **Environment Variables**, tambahkan:
   - `CRON_SECRET` = *(Buat string rahasia acak, misal: `indri_indodax_sec_2026`)*
   - `KV_REST_API_URL` = *(URL REST Upstash Redis dari Vercel Storage Marketplace / Upstash Console)*
   - `KV_REST_API_TOKEN` = *(Token REST Upstash Redis)*
4. Klik **Deploy**.
5. Buka tab **Settings** di GitHub Repositori &bull; **Secrets and variables &bull; Actions**:
   - `VERCEL_APP_URL` = `https://your-bot-name.vercel.app`
   - `CRON_SECRET` = *(String rahasia yang sama dengan di Vercel)*
6. GitHub Actions akan otomatis memanggil endpoint bot setiap 1 jam di menit ke-7 (`7 * * * *`).

---

## 5. Refleksi Kuantitatif Selisih Backtest vs Forward Test

1. **Erosi Biaya Transaksi pada Frekuensi Tinggi:**
   Hasil backtest 3 tahun pada timeframe 1 jam menunjukkan bahwa porsi biaya (fee taker 0.21%, spread terukur rata-rata 0.087%, dan estimasi slippage 0.080%) menyerap **43.90% dari laba kotor**. Hal ini memberikan pelajaran berharga bahwa dalam perdagangan kripto, strategi yang mengejar sinyal intraday memerlukan ambang batas profitabilitas yang jauh lebih lebar untuk mengimbangi friksi eksekusi.
2. **Penyebab Gap pada Jendela 10 Hari:**
   Perbandingan pada jendela 10 hari terakhir memperlihatkan perbedaan antara backtest teoritis dan eksekusi live forward test yang disebabkan oleh:
   - **Deviasi Waktu Eksekusi Penjadwal:** GitHub Actions cron mengalami variasi latensi 2&ndash;5 menit dari penutupan candle 00:00, sehingga harga eksekusi fill order book berbeda tipis dengan harga open teoritis.
   - **Kedalaman Order Book:** Pada jam malam (likuiditas rendah), pesanan dengan volume besar terdorong memakan antrian ask/bid level 2 dan level 3 (VWAP slippage).
3. **Integritas Bebas Look-Ahead Bias:**
   Penerapan aturan pembuangan candle berjalan (`Time + tf > server_time`) dan pencatatan state idempotensi terbukti menjamin bahwa bot beroperasi secara realistis dan tidak pernah memanfaatkan data masa depan.
