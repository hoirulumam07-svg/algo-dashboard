import streamlit as st
import pandas as pd
import yfinance as yf
import time
import re
import io
import redis

st.set_page_config(page_title="Capelang Algo App", layout="wide")

REDIS_URL = "rediss://default:gQAAAAAAAXJKAAIgcDJmMGY1OGMyYWE2ZDM0NWMzODA1YTAxMDFmMTE4Yzk4ZQ@engaged-tapir-94794.upstash.io:6379"

@st.cache_resource
def get_redis_client():
    try: return redis.Redis.from_url(REDIS_URL, decode_responses=True, socket_timeout=5)
    except: return None

r_client = get_redis_client()

if 'manual_txt' not in st.session_state: st.session_state['manual_txt'] = ""
if 'eod_mentah' not in st.session_state: st.session_state['eod_mentah'] = pd.DataFrame()
if 'eod_idx' not in st.session_state: st.session_state['eod_idx'] = {}
if 'eod_hasil' not in st.session_state: st.session_state['eod_hasil'] = None

st.markdown("""
    <style>
    .stApp { background-color: #111526; color: white; }
    .panel-kiri { background-color: #181b2f; padding: 20px; border-radius: 10px; margin-bottom: 20px;}
    .trade-card { background-color: #181b2f; padding: 15px; border-radius: 8px; border-left: 5px solid #2d334a; margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center; }
    .trade-card.buy { border-left-color: #00cc96; }
    .trade-card.sell { border-left-color: #ff4b4b; }
    .trade-card.wait { border-left-color: #ffa500; }
    .trade-card.naga { border-left-color: #ff00ff; box-shadow: 0 0 10px #ff00ff; }
    .ticker-name { font-size: 20px; font-weight: bold; margin-right: 10px; }
    .ticker-name.buy { color: #00cc96; }
    .ticker-name.sell { color: #ff4b4b; }
    .ticker-name.wait { color: #ffa500; }
    .ticker-name.naga { color: #ff00ff; text-shadow: 0 0 5px #ff00ff; }
    .badge { font-size: 11px; padding: 4px 8px; border-radius: 4px; background-color: #2d334a; color: #a1a9cc; margin-right: 5px; font-weight: bold; }
    .badge.purple { background-color: #5b2a86; color: #d4b3ff; }
    .badge.green { background-color: rgba(0, 204, 150, 0.2); color: #00cc96; }
    .badge.red { background-color: rgba(239, 85, 59, 0.2); color: #ff4b4b; }
    .badge.orange { background-color: rgba(255, 165, 0, 0.2); color: #ffa500; }
    .badge.pink { background-color: rgba(255, 0, 255, 0.2); color: #ff00ff; }
    .trade-details { font-size: 12px; color: #8a92b2; margin-top: 8px; }
    .pl-amount { font-size: 16px; font-weight: bold; text-align: right; }
    div[role="radiogroup"] { justify-content: center; margin-bottom: 10px; }
    </style>
""", unsafe_allow_html=True)

SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSiHk0WKndyGH-uOKzKmr0L5sE8a4d7H80msQTq-cL-EwShOjbE3xl5D01Isd0OdqufAbNl7CGx7qL-/pub?gid=0&single=true&output=csv"

def standarisasi_kolom(df):
    col_rename = {}
    for col in df.columns:
        col_lower = str(col).lower().strip()
        if any(k in col_lower for k in ['price', 'harga', 'entry', 'buy']): col_rename[col] = 'Price'
        elif any(k in col_lower for k in ['ticker', 'saham', 'emitten', 'nama']): col_rename[col] = 'Ticker'
        elif any(k in col_lower for k in ['algo', 'screener', 'combo']): col_rename[col] = 'Algo'
        elif any(k in col_lower for k in ['waktu', 'time', 'timestamp', 'tanggal']): col_rename[col] = 'Waktu'
    df = df.rename(columns=col_rename)
    if 'Price' not in df.columns and len(df.columns) >= 4:
        df.rename(columns={df.columns[0]: 'Waktu', df.columns[1]: 'Algo', df.columns[2]: 'Ticker', df.columns[3]: 'Price'}, inplace=True)
    return df

def parse_telegram_log_bulletproof(file_bytes):
    content = file_bytes.getvalue().decode("utf-8", errors="ignore")
    lines = content.split('\n')
    data = []
    current_algo = "Algo Tidak Dikenal"
    for line in lines:
        line_clean = line.strip()
        algo_match = re.search(r'Algo Name\s*:\s*(.+)', line_clean, re.IGNORECASE)
        if algo_match:
            current_algo = algo_match.group(1).strip()
            continue
        pola = r'\b([A-Z]{4})\b[\s|]+(\d+)'
        match = re.search(pola, line_clean)
        if match:
            ticker = match.group(1)
            price = match.group(2)
            if ticker not in ['NAMA', 'DATA', 'HARG', 'GAIN', 'TIME', 'CODE']:
                data.append({'Waktu': 'History Telegram', 'Algo': current_algo, 'Ticker': ticker, 'Price': int(price)})
    return pd.DataFrame(data)

def parse_idx_data(file):
    try:
        file_bytes = file.read()
        df_raw = None
        try: dfs = pd.read_html(io.BytesIO(file_bytes)); df_raw = dfs[0] if dfs else None
        except: pass
        if df_raw is None or df_raw.empty:
            try: df_raw = pd.read_excel(io.BytesIO(file_bytes), engine='openpyxl')
            except: pass
        if df_raw is None or df_raw.empty:
            try: df_raw = pd.read_excel(io.BytesIO(file_bytes))
            except: pass
        if df_raw is None or df_raw.empty:
            try: df_raw = pd.read_csv(io.BytesIO(file_bytes), sep=None, engine='python')
            except: return {}
        if df_raw is None or df_raw.empty: return {}

        header_idx = -1
        col_str = " ".join(str(c).lower() for c in df_raw.columns)
        if any(k in col_str for k in ['kode', 'code', 'ticker']) and any(k in col_str for k in ['close', 'penutupan', 'akhir', 'last']):
            header_idx = -2; df = df_raw.copy()
        else:
            for i in range(min(20, len(df_raw))):
                row_str = " ".join(str(x).lower() for x in df_raw.iloc[i].values)
                if any(k in row_str for k in ['kode', 'code', 'ticker']) and any(k in row_str for k in ['close', 'penutupan', 'akhir', 'last']):
                    header_idx = i; break
            if header_idx >= 0: df = df_raw.iloc[header_idx+1:].copy(); df.columns = df_raw.iloc[header_idx]
            else: df = df_raw.copy()

        df.columns = df.columns.astype(str).str.strip().str.lower()
        col_map = {}
        for c in df.columns:
            if any(x == c or f" {x}" in c or f"{x} " in c for x in ['kode', 'code', 'ticker', 'symbol']): col_map[c] = 'Ticker'
            elif any(x in c for x in ['close', 'penutupan', 'akhir', 'last']): 
                if 'prev' not in c and 'sebelum' not in c: col_map[c] = 'Close'
                    
        df = df.rename(columns=col_map)
        if 'Ticker' in df.columns and 'Close' in df.columns:
            df = df.dropna(subset=['Ticker', 'Close'])
            df['Ticker'] = df['Ticker'].astype(str).str.strip().str.upper()
            df['Close'] = pd.to_numeric(df['Close'].astype(str).str.replace(',', '').str.replace('.', ''), errors='coerce')
            return dict(zip(df['Ticker'], df['Close']))
        else: return {}
    except: return {}

st.markdown("<h2 style='text-align: center;'>⚙️ Capelang Algo App <span style='font-size:16px; color:#8a92b2;'>v10.1 (TXT Data Support)</span></h2>", unsafe_allow_html=True)
menu = st.radio("Mode:", ["📡 Live Radar", "📋 Evaluator Manual", "🏆 Evaluator EOD"], horizontal=True, label_visibility="collapsed")
st.divider()

if menu == "📡 Live Radar":
    df_live = pd.DataFrame()
    engine_status = "⚠️ Mode Google Sheets (Normal Delay)"
    
    if r_client:
        try:
            raw_signals = r_client.lrange("live_signals", 0, -1)
            if raw_signals:
                signals_list = [{'Waktu': p[0], 'Algo': p[1], 'Ticker': p[2], 'Price': float(p[3])} for p in (sig.split("|") for sig in raw_signals) if len(p) == 4]
                df_live = pd.DataFrame(signals_list)
                engine_status = "⚡ Mode Redis Kilat (0 Detik Delay)"
        except: pass

    if df_live.empty:
        try:
            df_temp = pd.read_csv(SHEET_CSV_URL)
            if not df_temp.empty: df_live = standarisasi_kolom(df_temp).dropna(subset=['Ticker', 'Price'])
        except: pass

    col_kiri, col_kanan = st.columns([1, 2.5], gap="large")

    with col_kiri:
        st.markdown('<div class="panel-kiri">', unsafe_allow_html=True)
        st.markdown(f"### 📡 Live Engine\n<span style='font-size:12px; color:#00cc96;'>{engine_status}</span>", unsafe_allow_html=True)
        st.divider()
        st.markdown(f"""<div style='font-size:12px; color:#8a92b2;'><div style='display:flex; justify-content:space-between;'><span>Status Server:</span> <span style='color:#00cc96;'>✅ Terhubung</span></div><div style='display:flex; justify-content:space-between;'><span>Total Balok Saat Ini:</span> <span style='color:#3b82f6;'>{len(df_live) if not df_live.empty else 0} Balok</span></div></div>""", unsafe_allow_html=True)
        st.write("")
        if st.button("🧹 Bersihkan Radar (Mulai Hari Baru)", use_container_width=True):
            if r_client:
                r_client.delete("live_signals"); st.rerun()
            else: st.error("⚠️ Koneksi Redis terputus, gagal membersihkan.")
        st.markdown('</div>', unsafe_allow_html=True)

    with col_kanan:
        st.markdown("### 📡 Radar Rekomendasi AI")
        if df_live.empty: st.info("✅ Menunggu balok sinyal pertama masuk...")
        else:
            df_live_reversed = df_live.iloc[::-1]
            tickers_terbaru = df_live_reversed['Ticker'].drop_duplicates().tolist()
            
            for ticker in tickers_terbaru:
                data_saham = df_live[df_live['Ticker'] == ticker]
                if data_saham.empty: continue
                
                list_balok = list(set(data_saham['Algo'].dropna().tolist()))
                jumlah_balok = len(list_balok)
                last_price, last_time = data_saham['Price'].iloc[-1], data_saham['Waktu'].iloc[-1]
                
                status_text, css_class, badge_class = "🧱 WAIT (Kumpul Balok)", "wait", "orange"
                
                if "merah dihaka" in list_balok and not any(x in list_balok for x in ["14_Serok_Harga_Merah_Berbalik", "Rebound botbox", "Pantulan Cepat Pagi", "Kawal Atas VWAP", "Smart Money Akumulasi"]):
                    status_text = f"⚠️ AVOID: PISAU JATUH (Jebakan Ritel!)"; css_class, badge_class = "sell", "red"
                elif any(x in list_balok for x in ["MO_Trend_Ngegas_ADX", "MF_RMF_Kuat"]) and any(x in list_balok for x in ["TR_Super_Bullish", "Momentum Bandar Rasio"]) and any(x in list_balok for x in ["MO_Speed_Cepat", "Cross Up VWAP"]):
                    status_text = f"🔥 NAGA BANGKIT (Potensi Cuan 32%!)"; css_class, badge_class = "naga", "pink"
                elif "Pantulan Cepat Pagi" in list_balok and "Rebound botbox" in list_balok and "Cross Up VWAP" in list_balok:
                    status_text = f"⚡ STRONG BUY: V-SHAPE REVERSAL ({jumlah_balok} Balok!)"; css_class, badge_class = "naga", "pink"
                elif "Cross Up VWAP" in list_balok and "GC MA Cleanmoney" in list_balok and any(x in list_balok for x in ["Breakout Siang Valid", "Ledakan Vol ma20", "Pantulan Cepat Pagi"]):
                    status_text = f"💎 SUPER BUY: TEMBUS VWAP ({jumlah_balok} Balok)"; css_class, badge_class = "buy", "green"
                elif any(x in list_balok for x in ["14_Serok_Harga_Merah_Berbalik", "MF_Bandar_Serok"]) and any(x in list_balok for x in ["Pantulan Cepat Pagi", "Rebound botbox", "Kawal Atas VWAP"]):
                    status_text = f"🎣 BUY: SEROK BAWAH ({jumlah_balok} Balok)"; css_class, badge_class = "buy", "green"
                elif any(x in list_balok for x in ["Konsolidasi Sehat Siang", "Breakout Siang Valid"]) and any(x in list_balok for x in ["Breakout Penutupan", "Value Transaksi Besar", "Gap Up Lanjut Naik"]):
                    status_text = f"🛍️ BUY: BREAKOUT SIANG ({jumlah_balok} Balok)"; css_class, badge_class = "buy", "green"
                elif jumlah_balok >= 2: status_text = f"⚙️ MERAKIT COMBO ({jumlah_balok} Balok)"; css_class, badge_class = "wait", "orange"
                else: status_text = "🧱 WAIT (Cuma 1 Balok)"; css_class, badge_class = "wait", "orange"

                gabungan_balok = " + ".join(list_balok)
                st.markdown(f"""
                <div class="trade-card {css_class}">
                    <div><div style="display:flex; align-items:center;"><span class="ticker-name {css_class}">{ticker}</span><span class="badge {badge_class}">{status_text}</span></div>
                    <div class="trade-details">Komponen: <strong style='color:white;'>[{gabungan_balok}]</strong> <br> Jam Terakhir: {last_time}</div></div>
                    <div><div class="pl-amount" style="color:white;">Price: Rp {int(last_price)}</div></div>
                </div>""", unsafe_allow_html=True)
    time.sleep(1); st.rerun()

elif menu == "📋 Evaluator Manual":
    col_in, col_out = st.columns([1, 2.5], gap="large")
    with col_in:
        st.markdown('<div class="panel-kiri">', unsafe_allow_html=True)
        st.markdown("### 📋 Evaluator Teks")
        teks_input = st.text_area("Paste Sinyal Telegram di sini:", value=st.session_state['manual_txt'], height=250)
        if teks_input != st.session_state['manual_txt']: st.session_state['manual_txt'] = teks_input; st.rerun()
        if st.button("🗑️ Bersihkan Teks", use_container_width=True): st.session_state['manual_txt'] = ""; st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
    with col_out:
        if st.session_state['manual_txt']:
            algo_match = re.search(r'Algo Name\s*:\s*(.+)', st.session_state['manual_txt'], re.IGNORECASE)
            algo_name = algo_match.group(1).strip() if algo_match else "Simulasi Algo Manual"
            matches = re.findall(r'\b([A-Z]{4})\b[\s|]+(\d+)', st.session_state['manual_txt'])
            if matches:
                st.success(f"✅ Berhasil mendeteksi {len(matches)} saham.")
                data_sim = [{"No": i+1, "Ticker": m[0], "Algo": algo_name, "Harga Entry": int(m[1]), "Status": "RUNNING"} for i, m in enumerate(matches) if m[0] not in ['NAMA', 'DATA', 'HARG']]
                st.dataframe(pd.DataFrame(data_sim), use_container_width=True, hide_index=True)
        else: st.info("👈 Silakan tempel teks sinyal dari Telegram.")

elif menu == "🏆 Evaluator EOD":
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### 1️⃣ Sumber Data Sinyal")
        sumber_sinyal = st.radio("Pilih sumber sinyal lu:", ["📂 Upload Sinyal Manual (Telegram/CSV)", "📡 Otomatis (Google Sheets)"], key="rad_sinyal")
        if sumber_sinyal == "📂 Upload Sinyal Manual (Telegram/CSV)":
            if st.session_state['eod_mentah'].empty:
                files_sinyal = st.file_uploader("Upload File Sinyal (Bisa Blok Banyak File Sekaligus)", type=['csv', 'txt'], accept_multiple_files=True)
                if files_sinyal:
                    all_data = [parse_telegram_log_bulletproof(f) for f in files_sinyal if not parse_telegram_log_bulletproof(f).empty]
                    if all_data: st.session_state['eod_mentah'] = pd.concat(all_data, ignore_index=True); st.session_state['eod_hasil'] = None; st.rerun()
                    else: st.warning("⚠️ Tidak ada format sinyal valid yang ditemukan di file-file tersebut.")
            else:
                st.success(f"✅ Data Sinyal Tersimpan di Memori ({len(st.session_state['eod_mentah'])} Sinyal).")
                if st.button("🗑️ Ganti File Sinyal"): st.session_state['eod_mentah'] = pd.DataFrame(); st.session_state['eod_hasil'] = None; st.rerun()
        else:
            try:
                df_temp = pd.read_csv(SHEET_CSV_URL)
                if not df_temp.empty: st.session_state['eod_mentah'] = standarisasi_kolom(df_temp); st.success(f"✅ Sinkronisasi Google Sheets Sukses ({len(st.session_state['eod_mentah'])} Sinyal).")
                else: st.warning("Sheets Kosong")
            except Exception as e: st.error(f"⚠️ Gagal terhubung ke Google Sheets: {e}")

    with col2:
        st.markdown("### 2️⃣ Sumber Harga EOD (Penutupan)")
        # ⚡ NEW: .txt ditambahkan di menu radio dan uploader
        sumber_eod = st.radio("Pilih sumber harga EOD lu:", ["📊 Upload Data Resmi IDX (.xls/.xlsx/.csv/.txt)", "📡 Otomatis (Yahoo Finance)"], key="rad_eod")
        if sumber_eod == "📊 Upload Data Resmi IDX (.xls/.xlsx/.csv/.txt)":
            if not st.session_state['eod_idx']:
                file_idx = st.file_uploader("Upload File dari IDX", type=['xlsx', 'xls', 'csv', 'txt'])
                if file_idx: st.session_state['eod_idx'] = parse_idx_data(file_idx); st.session_state['eod_hasil'] = None; st.rerun()
            else:
                st.success(f"✅ Data IDX Tersimpan di Memori ({len(st.session_state['eod_idx'])} Emiten).")
                if st.button("🗑️ Ganti File IDX"): st.session_state['eod_idx'] = {}; st.session_state['eod_hasil'] = None; st.rerun()
        else:
            if st.session_state['eod_idx']: st.session_state['eod_idx'] = {}; st.session_state['eod_hasil'] = None; st.rerun()
            st.info("📡 AI akan menarik harga langsung dari Yahoo Finance.")

    st.divider()

    def proses_data_eod(df, harga_idx_manual):
        df_olah = df.copy()
        df_olah['Price'] = pd.to_numeric(df_olah['Price'], errors='coerce')
        df_olah = df_olah.dropna(subset=['Ticker', 'Price'])
        tickers = df_olah['Ticker'].unique()
        close_prices, high_prices = {}, {} 
        
        if len(tickers) > 0:
            st.write("🤖 **Memproses Evaluasi End of Day & Intraday Max Profit...**")
            progress_bar = st.progress(0)
            for i, ticker in enumerate(tickers):
                try:
                    data_saham = yf.Ticker(f"{ticker}.JK").history(period="5d")
                    if not data_saham.empty: yahoo_close, yahoo_high = float(data_saham['Close'].iloc[-1]), float(data_saham['High'].iloc[-1])
                    else: yahoo_close = yahoo_high = float(df_olah[df_olah['Ticker']==ticker]['Price'].iloc[-1])
                except: yahoo_close = yahoo_high = float(df_olah[df_olah['Ticker']==ticker]['Price'].iloc[-1])
                
                if harga_idx_manual and ticker in harga_idx_manual:
                    close_prices[ticker] = float(harga_idx_manual[ticker])
                    high_prices[ticker] = max(yahoo_high, close_prices[ticker])
                else:
                    close_prices[ticker], high_prices[ticker] = yahoo_close, yahoo_high
                progress_bar.progress((i + 1) / len(tickers))
            progress_bar.empty()
            
        df_olah['EOD_Close'] = df_olah['Ticker'].map(close_prices)
        df_olah['Max_High'] = df_olah['Ticker'].map(high_prices)
        df_olah['Profit_%'] = ((df_olah['EOD_Close'] - df_olah['Price']) / df_olah['Price']) * 100
        df_olah['Max_Profit_%'] = ((df_olah['Max_High'] - df_olah['Price']) / df_olah['Price']) * 100
        df_olah['Status'] = df_olah['Profit_%'].apply(lambda x: 'WIN 🟢' if x > 0 else ('LOSS 🔴' if x < 0 else 'BEP ⚪'))
        return df_olah

    if not st.session_state['eod_mentah'].empty:
        if st.session_state['eod_hasil'] is None: st.session_state['eod_hasil'] = proses_data_eod(st.session_state['eod_mentah'], st.session_state['eod_idx'])
        df_eod = st.session_state['eod_hasil']
        
        if not df_eod.empty:
            col_head1, col_head2 = st.columns([4, 1])
            with col_head1: st.subheader("🔥 Ranking Performa Lego Hari Ini")
            with col_head2:
                if st.button("🔄 Hitung Ulang", use_container_width=True): st.session_state['eod_hasil'] = None; st.rerun()
            if 'Algo' in df_eod.columns:
                algo_stats = df_eod.groupby('Algo').apply(
                    lambda x: pd.Series({
                        'Total Sinyal': len(x), 'Win (EOD)': len(x[x['Status'] == 'WIN 🟢']), 'Loss (EOD)': len(x[x['Status'] == 'LOSS 🔴']), 
                        'Win Rate EOD (%)': (len(x[x['Status'] == 'WIN 🟢']) / len(x)) * 100, 'Rata-rata Profit EOD (%)': x['Profit_%'].mean(),
                        'Rata-rata Max Potensi Cuan (%)': x['Max_Profit_%'].mean(), 'Max Potensi Cuan Tertinggi (%)': x['Max_Profit_%'].max()
                    })
                ).reset_index().sort_values(by=['Rata-rata Max Potensi Cuan (%)', 'Win Rate EOD (%)'], ascending=[False, False])
                st.dataframe(algo_stats.style.format({'Total Sinyal': '{:.0f}', 'Win (EOD)': '{:.0f}', 'Loss (EOD)': '{:.0f}', 'Win Rate EOD (%)': '{:.1f}%', 'Rata-rata Profit EOD (%)': '{:+.2f}%', 'Rata-rata Max Potensi Cuan (%)': '{:+.2f}%', 'Max Potensi Cuan Tertinggi (%)': '{:+.2f}%'}), use_container_width=True, hide_index=True)
            
            st.divider()
            st.subheader("🧬 Saham dengan Rakitan Combo Lego")
            if 'Algo' in df_eod.columns:
                combo_data = df_eod.groupby('Ticker').apply(
                    lambda x: pd.Series({
                        'Jumlah Balok': len(x['Algo'].unique()), 'Komponen Balok Lego': " + ".join(x['Algo'].unique()), 
                        'Harga Entry': x['Price'].iloc[0], 'Harga Puncak (High)': x['Max_High'].iloc[0], 'Harga Penutupan (EOD)': x['EOD_Close'].iloc[0], 
                        'Max Potensi Cuan (%)': x['Max_Profit_%'].iloc[0], 'Profit EOD (%)': x['Profit_%'].iloc[0], 'Hasil Akhir': x['Status'].iloc[0]
                    })
                ).reset_index()
                combo_data_only = combo_data[combo_data['Jumlah Balok'] > 1].sort_values(by='Max Potensi Cuan (%)', ascending=False)
                if not combo_data_only.empty: st.dataframe(combo_data_only.style.format({'Harga Entry': '{:.0f}', 'Harga Puncak (High)': '{:.0f}', 'Harga Penutupan (EOD)': '{:.0f}', 'Max Potensi Cuan (%)': '{:+.2f}%', 'Profit EOD (%)': '{:+.2f}%'}), use_container_width=True, hide_index=True)
                else: st.info("Tidak ada saham yang berhasil merakit Combo Lego di data ini.")