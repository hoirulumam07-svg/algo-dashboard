import streamlit as st
import pandas as pd
import plotly.express as px

# --- Konfigurasi Halaman ---
st.set_page_config(page_title="Algo Dashboard", layout="wide")
st.title("📈 Dashboard Trading Algo")

# --- Link CSV ---
SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSiHk0WKndyGH-uOKzKmr0L5sE8a4d7H80msQTq-cL-EwShOjbE3xl5D01Isd0OdqufAbNl7CGx7qL-/pub?gid=0&single=true&output=csv"

# --- Fungsi Narik Data ---
@st.cache_data(ttl=60)
def load_data():
    try:
        df = pd.read_csv(SHEET_CSV_URL)
        return df
    except Exception as e:
        return pd.DataFrame()

df = load_data()

# --- Tampilan Dashboard ---
if df.empty:
    st.warning("Belum ada data sinyal atau link CSV salah. Tunggu market open jam 09.00 ya!")
else:
    # ==========================================
    # 🧠 OTAK BARU: SMART TRADING ASSISTANT V2.0
    # ==========================================
    st.header("🧠 Rekomendasi AI & Combo Algo")
    
    if 'Ticker' in df.columns and 'Algo' in df.columns:
        summary_data = []
        
        for ticker in df['Ticker'].unique():
            algos_saham_ini = df[df['Ticker'] == ticker]['Algo'].tolist()
            
            # Status default
            status = "⏳ WAIT (Butuh Konfirmasi / Nunggu Sinyal Tambahan)"
            
            # --- 1. JALUR BAHAYA (PRIORITAS TERTINGGI) ---
            if "ALARM Guyuran Bandar" in algos_saham_ini:
                status = "🩸 SELL / JANGAN MASUK (Guyuran Bandar!)"
                
            # --- 2. JALUR SEROK BAWAH (REBOUND) ---
            elif "Tangkap Pantulan ARB" in algos_saham_ini:
                status = "🎣 STRONG BUY REBOUND (Potensi Mantul ARB)"
            elif "14_Serok_Harga_Merah_Berbalik" in algos_saham_ini and "merah_dihaka" in algos_saham_ini:
                status = "🎣 BUY REBOUND (Merah Di-HAKA Valid)"
                
            # --- 3. JALUR BSJP / BUNGKUS SORE ---
            elif "Day_Bungkus_Sore" in algos_saham_ini or "Day_Bsjp" in algos_saham_ini:
                if "Breakout Penutupan" in algos_saham_ini:
                    status = "🛍️ SUPER BSJP (Bungkus Sore + Breakout Valid!)"
                else:
                    status = "🛍️ BUY SORE (Siap Bungkus BSJP)"
                    
            # --- 4. JALUR COPET PAGI ---
            elif "Ledakan Vol Pembuka" in algos_saham_ini:
                if any(algo in algos_saham_ini for algo in ["Scalping Pagi Bullish", "HAKA Banteng Pagi", "Open Low Uptrend", "Turbo Akselerasi Awal"]):
                    status = "⚡ COMBO BUY PAGI (Ledakan Volume Terkonfirmasi!)"
                else:
                    status = "🔥 FAST BUY (Ledakan Vol Pembuka)"
                    
            # --- 5. JALUR BREAKOUT SIANG ---
            elif any(algo in algos_saham_ini for algo in ["Persiapan Tembus Siang", "Konsolidasi Sehat Siang"]):
                if any(algo in algos_saham_ini for algo in ["Tarikan Tengah Hari", "Breakout Smart Money", "Jebol Atap Kemarin"]):
                    status = "🚀 COMBO BREAKOUT SIANG (Tembus Resisten Valid!)"
                else:
                    status = "👀 PANTAU KETAT (Lagi Konsolidasi/Akumulasi)"

            # --- 6. JALUR TREND & BANDAR SENYAP ---
            elif "bandar senyap potensial MELEDAK" in algos_saham_ini:
                status = "💣 BUY & HOLD (Bandar Senyap, Siap Meledak)"
            elif "Uptrend Kuat Bandar RLA 1" in algos_saham_ini or "Smart_Trend_Valid" in algos_saham_ini:
                status = "📈 BUY (Trend Kuat Valid)"
                
            # --- 7. JALUR DIRECT BUY (Momentum Kuat) ---
            elif "Copet HAKA Deras" in algos_saham_ini or "GMMA Turbo Breakout" in algos_saham_ini:
                status = "🔥 BUY MOMENTUM (HAKA Deras / Turbo Breakout)"
            
            summary_data.append({
                "Saham": ticker,
                "Rekomendasi": status,
                "Trigger Algo": ", ".join(set(algos_saham_ini))
            })
            
        df_summary = pd.DataFrame(summary_data)
        
        # Bikin warna biar UI-nya enak dilihat (Opsional)
        def highlight_status(val):
            if "BUY" in val or "BSJP" in val:
                return 'background-color: rgba(0, 204, 150, 0.2)'
            elif "SELL" in val:
                return 'background-color: rgba(239, 85, 59, 0.2)'
            elif "PANTAU" in val or "WAIT" in val:
                return 'background-color: rgba(255, 165, 0, 0.2)'
            return ''

        st.dataframe(df_summary.style.map(highlight_status, subset=['Rekomendasi']), use_container_width=True, hide_index=True)
    else:
        st.info("Pastiin kolom di Google Sheets lu namanya 'Ticker' dan 'Algo' ya.")

    st.divider()

    # ==========================================
    # 📊 STATISTIK & METRIK
    # ==========================================
    total_signal = len(df)
    win = len(df[df['Result'].str.upper() == 'WIN']) if 'Result' in df.columns else 0
    loss = len(df[df['Result'].str.upper() == 'LOSS']) if 'Result' in df.columns else 0
    running = len(df[df['Result'].str.upper() == 'RUNNING']) if 'Result' in df.columns else 0
    
    finished_trades = win + loss
    win_rate = (win / finished_trades * 100) if finished_trades > 0 else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Sinyal", total_signal)
    col2.metric("Win Rate", f"{win_rate:.1f}%")
    col3.metric("Running", running)
    col4.metric("Loss", loss)

    st.divider()

    col_chart, col_table = st.columns([1, 2])

    with col_chart:
        st.subheader("Rasio Win/Loss")
        pie_data = pd.DataFrame({
            'Status': ['Win', 'Loss', 'Running'],
            'Jumlah': [win, loss, running]
        })
        pie_data = pie_data[pie_data['Jumlah'] > 0]
        
        if not pie_data.empty:
            # BAGIAN INI GUA JADIKAN SATU BARIS BIAR AMAN DARI ERROR SPASI/TERPOTONG
            fig = px.pie(pie_data, values='Jumlah', names='Status', hole=0.4, color='Status', color_discrete_map={'Win':'#00cc96', 'Loss':'#ef553b', 'Running':'#636efa'})
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.write("Belum ada status yang bisa ditampilin.")

    with col_table:
        st.subheader("Detail Riwayat Sinyal")
        st.dataframe(df, use_container_width=True, hide_index=True)