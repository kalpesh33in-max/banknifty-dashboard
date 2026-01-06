
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
DATA_FETCH_TIMEOUT_SECONDS = 10  # How long to wait for data from WebSocket

# --- GDFL Configuration ---
API_KEY = os.environ.get("API_KEY", "YOUR_API_KEY") 
WSS_URL = "wss://nimblewebstream.lisuns.com:4576/"

# --- Symbol Configuration ---
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
    body { color: #000; background-color: #FFF; }
    .stDataFrame th { background-color: #E0E0E0; color: black; font-weight: bold; }
    .stDataFrame th, .stDataFrame td { border: 1px solid #AAA; }
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
    """Connects to WebSocket, fetches one complete tick of data, and disconnects."""
    st.info(f"Connecting to data feed... Will wait {DATA_FETCH_TIMEOUT_SECONDS} seconds for data.")
    latest_data = {}
    
    try:
        async with websockets.connect(WSS_URL) as websocket:
            # Authenticate
            await websocket.send(json.dumps({"MessageType": "Authenticate", "Password": API_KEY}))
            auth_response = json.loads(await websocket.recv())
            if not auth_response.get("Complete"):
                st.error(f"WebSocket Authentication Failed: {auth_response.get('Reason')}. Please check your API_KEY variable on Railway.")
                return None

            # Subscribe
            for symbol in SYMBOLS_TO_MONITOR:
                await websocket.send(json.dumps({"MessageType": "SubscribeRealtime", "Exchange": "NFO", "Unsubscribe": "false", "InstrumentIdentifier": symbol}))

            # Listen for data for a short period
            try:
                async with asyncio.timeout(DATA_FETCH_TIMEOUT_SECONDS): # Wrap the entire block
                    async for message in websocket: # This is the awaitable that should be timed out
                        data = json.loads(message)
                        if data.get("MessageType") == "RealtimeResult":
                            symbol = data.get("InstrumentIdentifier")
                            if symbol:
                                latest_data[symbol] = {
                                    "oi": data.get("OpenInterest", 0),
                                    "price": data.get("LastTradePrice", 0)
                                }
            except TimeoutError:
                st.success("Data fetch complete (timeout reached).")
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
    st.toast("First run, fetching initial data...")
else:
    time_since_last_refresh = now - st.session_state.last_refresh_time
    if time_since_last_refresh >= timedelta(minutes=REFRESH_INTERVAL_MINUTES):
        should_refresh = True
        st.toast(f"15 minutes have passed. Fetching new data...")

# --- Main Refresh Logic ---
if should_refresh:
    new_data = asyncio.run(fetch_latest_data())
    
    if new_data:
        # Update future price
        future_symbol = f"{EXPIRY_PREFIX}FUT"
        if future_symbol in new_data and new_data[future_symbol]['price'] > 0:
            st.session_state.future_price = new_data[future_symbol]['price']

        # Get the last row of history for RoC calculation
        last_oi_data = {}
        if not st.session_state.history_df.empty:
            last_oi_series = st.session_state.history_df.iloc[-1]
            last_oi_data = last_oi_series.to_dict()

        # Create new row for the DataFrame
        new_row_data = {"time": now.strftime("%H:%M:%S")}
        new_oi_state = {}

        for symbol in ALL_OPTION_SYMBOLS:
            # Calculate RoC
            live_oi = new_data.get(symbol, {}).get("oi", 0)
            
            # For RoC calc, we need the OI from the previous 15-min interval
            prev_oi = 0
            if symbol in st.session_state:
                prev_oi = st.session_state.get(symbol, {}).get('oi', 0)

            oi_roc = 0.0
            if prev_oi > 0 and live_oi > 0:
                oi_roc = ((live_oi - prev_oi) / prev_oi) * 100

            # Format for display
            match = re.search(r'(\d+)(CE|PE)$', symbol)
            if match:
                col_name = f"{match.group(1)} {match.group(2).lower()}"
                new_row_data[col_name] = f"{oi_roc:.2f}%"

            # Store current OI for the next run
            st.session_state[symbol] = {"oi": live_oi}

        # Update history DataFrame
        new_row_df = pd.DataFrame([new_row_data]).set_index('time')
        st.session_state.history_df = pd.concat([st.session_state.history_df, new_row_df])
        
        # Update refresh time
        st.session_state.last_refresh_time = now

# --- Draw UI ---
col1, col2 = st.columns([3, 1])
with col1:
    st.markdown(f'Banknifty future price:- **{st.session_state.future_price:.2f}**')
with col2:
    selected_atm = st.selectbox(
        'strike selection',
        options=list(STRIKE_RANGE),
        index=list(STRIKE_RANGE).index(st.session_state.get('atm_strike', 60100))
    )
    st.session_state.atm_strike = selected_atm

# --- Display DataFrame ---
if st.session_state.history_df.empty:
    st.info("Waiting for the first 15-minute data fetch to complete...")
else:
    center_strike = selected_atm
    ce_strikes = [f"{center_strike - i*100} ce" for i in range(5, 0, -1)]
    atm_cols = [f"{center_strike} ce", f"{center_strike} pe"]
    pe_strikes = [f"{center_strike + i*100} pe" for i in range(1, 6)]
    
    display_columns = ce_strikes + atm_cols + pe_strikes
    valid_display_columns = [col for col in display_columns if col in st.session_state.history_df.columns]
    
    if valid_display_columns:
        df_display = st.session_state.history_df[valid_display_columns]
        styled_table = style_dashboard(df_display, selected_atm)
        st.dataframe(styled_table)
    else:
        st.info("Data has been fetched, but columns for the selected strike range are not yet available.")

# --- Auto-refresh JavaScript ---
# This will reload the page, triggering the script to run again.
# The script's internal logic will decide if it's time to fetch new data.
st.components.v1.html(f"<script>setTimeout(function(){{window.location.reload(true);}}, 60000);</script>", height=0) # Reload every 60s
st.caption("This page will automatically refresh every minute to check if it's time for a new data fetch.")
