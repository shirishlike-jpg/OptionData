import streamlit as st
import time
from nse_fetcher import NSEOptionChainFetcher

# पेज लेआउट सेटिंग
st.set_page_config(page_title="NSE Reversal & Greeks Dashboard", layout="wide")

st.title("📊 NSE Live Option Chain & Reversal Levels")

# साइडबार कंट्रोल्स
symbol = st.sidebar.selectbox("Select Index", ["NIFTY", "BANKNIFTY"])
refresh_rate = st.sidebar.slider("Auto-Refresh Interval (Seconds)", 5, 60, 10)

fetcher = NSEOptionChainFetcher(symbol=symbol)

placeholder = st.empty()

while True:
    df, spot_price = fetcher.fetch_data()
    
    with placeholder.container():
        if df is not None and not df.empty:
            # स्पॉट प्राईस मेट्रिक कार्ड
            st.metric(label=f"🟢 {symbol} Spot Price", value=spot_price)
            
            st.subheader("🎯 Calculated Reversal Levels & Data")
            
            # डॅशबोर्डवर दिसणारे मॅनिन कॉलम्स
            display_cols = [
                'Call_OI', 'Call_Change_OI', 'Call_LTP', 'Call_Delta', 'Call_Rev',
                'Strike', 
                'Put_Rev', 'Put_Delta', 'Put_LTP', 'Put_Change_OI', 'Put_OI'
            ]
            
            # डेटाफ्रेम टेबल स्वरूपात दाखवणे
            st.dataframe(df[display_cols], use_container_width=True, hide_index=True)
            
            st.info(f"Last updated: Live from NSE (Auto-refreshes every {refresh_rate} seconds)")
        else:
            st.error("NSE डेटा लोड होत आहे किंवा सर्व्हर व्यस्त आहे... कृपया थोडा वेळ थांबा.")
            
    time.sleep(refresh_rate)