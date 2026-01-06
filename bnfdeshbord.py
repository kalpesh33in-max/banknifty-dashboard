import streamlit as st
import pandas as pd
import asyncio
import websockets
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import os
import re

# ==============================================================================
# ============================ CONFIGURATION ===================================
# ==============================================================================

REFRESH_INTERVAL_MINUTES = 15
DATA_FETCH_TIMEOUT_SECONDS = 10

API_KEY = os.environ.get("API_KEY", "YOUR_API_KEY") 
WSS_URL = "wss://nimblewebstream.lisuns.com:4576/"

STRIKE_RANGE = range(59000, 61001, 100)
EXPIRY_PREFIX = "BANKNIFTY27JAN26"

ALL_OPTION_SYMBOLS = [f"{EXPIRY_PREFIX}{strike}{opt_type}" for strike in STRIKE_RANGE for opt_type in ["CE", "PE"]]
SYMBOLS_TO_MONITOR = ALL_OPTION_SYMBOLS + [f"{EXPIRY_PREFIX}FUT"]

# ==============================================================================
# =============================== UI & STYLING =================================
# ==============================================================================

st.set_page_config(page_title="Bank Nifty OI Scanner", layout="wide")

st.markdown("""
    <style>
    /* Force light theme */
    body, .stApp {
        background-color: #FFF !important;
        color: #000 !important;
    }
    /* Style the main header to be purple */
    header {
        background-color: #4B0082 !important; /* Indigo/Purple */
    }
    /* Style the header text and elements */
    .st-emotion-cache-18ni7ap {
        color: white !important;
    }
    .st-emotion-cache-18ni7ap h1 {
        color: white !important;
    }
    /* General text color */
    div, p, span, h1, h2, h3, h4, h5, h6, strong {
        color: #000 !important;
    }
    /* Table header styling */
    .stDataFrame th {
        background-color: #E0E0E0 !important; /* Light grey */
        color: black !important;
        font-weight: bold !important;
    }
    /* Table cell styling */
    .stDataFrame th, .stDataFrame td {
        border: 1px solid #AAA !important;
    }
    /* Specific overrides for status boxes */
    .stAlert {
        color: #000 !important;
    }
    </style>
""", unsafe_allow_html=True)

def style_dashboard(df, selected_atm):
    """Applies color coding for moneyness to the DataFrame."""
    def moneyness_styler(df_to_style: pd.DataFrame):
        df_style = pd.DataFrame('', index=df_to_style.index, columns=df_to_style.columns)
        for col_name in df_to_style.columns:
            try:
                strike = float(col_name.split()[0])
                opt_type = col_name.split()[1]
            except (ValueError, IndexError):
                continue
            style = 'color: black; font-weight: bold;'
            if strike == selected_atm:
                style += 'background-color: yellow;'
            elif opt_type == 'ce' and strike < selected_atm:
                style += 'background-color: palegreen;'
            elif opt_type == 'pe' and strike > selected_atm:
                style += 'background-color: lightsalmon;'
            df_style[col_name] = style
        return df_style
    return df.style.apply(moneyness_styler, axis=None)

# ==============================================================================
# ============================ DATA FETCHING ===================================
# ==============================================================================

async def fetch_latest_data():
    """Connects to WebSocket, fetches data, and disconnects."""
    st.info(f"Connecting to data feed... waiting {DATA_FETCH_TIMEOUT_SECONDS} seconds for data.")
    latest_data = {}
    try:
        async with websockets.connect(WSS_URL) as websocket:
            await websocket.send(json.dumps({"MessageType": "Authenticate", "Password": API_KEY}))
            auth_response = json.loads(await websocket.recv())
            if not auth_response.get("Complete"):
                st.error(f"Authentication Failed. Please check API_KEY. Server says: {auth_response.get('Reason')}")
                return None
            
            for symbol in SYMBOLS_TO_MONITOR:
                await websocket.send(json.dumps({"MessageType": "SubscribeRealtime", "Exchange": "NFO", "Unsubscribe": "false", "InstrumentIdentifier": symbol}))
            
            try:
                async with asyncio.timeout(DATA_FETCH_TIMEOUT_SECONDS):
                    async for message in websocket:
                        data = json.loads(message)
                        if data.get("MessageType") == "RealtimeResult":
                            symbol = data.get("InstrumentIdentifier")
                            if symbol:
                                latest_data[symbol] = {"oi": data.get("OpenInterest", 0), "price": data.get("LastTradePrice", 0)}
            except TimeoutError:
                st.success("Data fetch complete.")
    except Exception as e:
        st.error(f"An error occurred while fetching data: {e}")
        return None
    return latest_data

# ==============================================================================
# ============================ MAIN LOGIC ======================================
# ==============================================================================

# --- Initialize Session State ---
if 'history_df' not in st.session_state:
    st.session_state.history_df = pd.DataFrame()
if 'last_refresh_time' not in st.session_state:
    st.session_state.last_refresh_time = None
if 'future_price' not in st.session_state:
    st.session_state.future_price = 0.0

# --- Check if it's time to refresh ---
now = datetime.now(ZoneInfo("Asia/Kolkata"))
should_refresh = False
if st.session_state.last_refresh_time is None:
    should_refresh = True
else:
    if now - st.session_state.last_refresh_time >= timedelta(minutes=REFRESH_INTERVAL_MINUTES):
        should_refresh = True

# --- Main Refresh & Calculation Logic ---
if should_refresh:
    new_data = asyncio.run(fetch_latest_data())
    if new_data:
        future_symbol = f"{EXPIRY_PREFIX}FUT"
        if future_symbol in new_data and new_data[future_symbol]['price'] > 0:
            st.session_state.future_price = new_data[future_symbol]['price']

        current_time_str = now.strftime("%H:%M:%S")
        new_row_data = {"time": current_time_str}
        
        is_first_run = st.session_state.history_df.empty
        
        for symbol in ALL_OPTION_SYMBOLS:
            live_oi = new_data.get(symbol, {}).get("oi", 0)
            oi_roc = 0.0
            
            if not is_first_run:
                prev_oi = st.session_state.get(symbol, {}).get('oi', 0)
                if prev_oi > 0 and live_oi > 0:
                    oi_roc = ((live_oi - prev_oi) / prev_oi) * 100
            
            match = re.search(r'(\d+)(CE|PE)$', symbol)
            if match:
                col_name = f"{match.group(1)} {match.group(2).lower()}"
                new_row_data[col_name] = f"{oi_roc:.2f}%"
            
            st.session_state[symbol] = {"oi": live_oi}

        new_row_df = pd.DataFrame([new_row_data]).set_index('time')
        st.session_state.history_df = pd.concat([st.session_state.history_df, new_row_df])
        st.session_state.last_refresh_time = now
        st.rerun() # Force a rerun to display the new data immediately

# ==============================================================================
# ============================ UI DRAWING ======================================
# ==============================================================================

# --- Draw Header ---
col1, col2 = st.columns([3, 1])
with col1:
    st.markdown(f'Banknifty future price:- **{st.session_state.future_price:.2f}**')
with col2:
    selected_atm = st.selectbox('strike selection', options=list(STRIKE_RANGE), index=list(STRIKE_RANGE).index(st.session_state.get('atm_strike', 60100)))
    st.session_state.atm_strike = selected_atm

# --- Display DataFrame ---
if st.session_state.history_df.empty:
    st.info("Waiting for the first data fetch to complete...")
else:
    center_strike = selected_atm
    ce_strikes = [f"{center_strike - i*100} ce" for i in range(5, 0, -1)]
    atm_cols = [f"{center_strike} ce", f"{center_strike} pe"]
    pe_strikes = [f"{center_strike + i*100} pe" for i in range(1, 6)]
    
    display_columns = ce_strikes + atm_cols + pe_strikes
    valid_display_columns = [col for col in display_columns if col in st.session_state.history_df.columns]
    
    if valid_display_columns:
        df_display = st.session_state.history_df[valid_display_columns].sort_index(ascending=False)
        styled_table = style_dashboard(df_display, selected_atm)
        st.dataframe(styled_table)

# --- Auto-refresh trigger ---
st.components.v1.html(f"<script>setTimeout(function(){{window.location.reload(true);}}, 60000);</script>", height=0)
st.caption("Page will refresh every minute to check for new data.")