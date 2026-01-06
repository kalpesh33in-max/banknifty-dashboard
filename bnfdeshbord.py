
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
    /* Force light theme - more assertive */
    .stApp {
        background-color: #FFF !important;
        color: #000 !important;
    }
    h1, h2, h3, h4, h5, h6, strong {
        color: #000 !important;
    }
    /* Style for table headers */
    .stDataFrame th {
        background-color: #E0E0E0 !important; /* Light grey */
        color: black !important;
        font-weight: bold !important;
    }
    .stDataFrame th, .stDataFrame td {
        border: 1px solid #AAA !important;
        max-width: 100px;
        min-width: 75px;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }
    /* Custom header bar styling */
    .st-emotion-cache-1r6dm1x { /* Target Streamlit's main content wrapper for the header */
        background-color: #4B0082 !important; /* Indigo/Purple */
        color: white !important;
        padding: 10px !important;
        border-radius: 5px !important;
        margin-bottom: 10px !important;
        display: flex !important;
        justify-content: space-between !important;
        align-items: center !important;
    }
    .st-emotion-cache-1r6dm1x h1 {
        color: white !important;
    }
    .header-future-price { /* Custom class for future price display */
        color: white !important;
        font-size: 1.2em !important;
        font-weight: bold !important;
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

        # Get the last row of history for RoC calculation for subsequent fetches
        last_oi_data_for_roc = {}
        if not st.session_state.history_df.empty:
            last_oi_series = st.session_state.history_df.iloc[-1].drop('time', errors='ignore') # Ensure 'time' is not in series
            for col_name, roc_value in last_oi_series.items():
                # Extract strike and type from col_name (e.g., "60100 ce")
                match = re.match(r'(\d+) (ce|pe)', col_name)
                if match:
                    strike_price = match.group(1)
                    option_type = match.group(2).upper()
                    symbol_key = f"{EXPIRY_PREFIX}{strike_price}{option_type}"
                    # Find the actual previous OI for this symbol if stored in session state
                    last_oi_data_for_roc[symbol_key] = st.session_state.get(symbol_key, {}).get('oi', 0)
        
        # Create new row for the DataFrame
        current_time_str = now.strftime("%H:%M:%S")
        new_row_data = {"time": current_time_str}
        
        for symbol in ALL_OPTION_SYMBOLS:
            live_oi = new_data.get(symbol, {}).get("oi", 0)
            
            # Use stored OI for RoC calc, or 0 if first run
            prev_oi_for_roc = last_oi_data_for_roc.get(symbol, 0)

            oi_roc = 0.0
            if prev_oi_for_roc > 0 and live_oi > 0:
                oi_roc = ((live_oi - prev_oi_for_roc) / prev_oi_for_roc) * 100

            # Format for display
            match = re.search(r'(\d+)(CE|PE)$', symbol)
            if match:
                col_name = f"{match.group(1)} {match.group(2).lower()}"
                new_row_data[col_name] = f"{oi_roc:.2f}%"

            # Store current OI for the next run's RoC calculation
            st.session_state[symbol] = {"oi": live_oi} # Store in session state for next iteration's prev_oi

        # Update history DataFrame
        new_row_df = pd.DataFrame([new_row_data]).set_index('time')
        st.session_state.history_df = pd.concat([st.session_state.history_df, new_row_df])
        
        # Update refresh time
        st.session_state.last_refresh_time = now

    # Ensure ATM strike is set even if not selected yet
    if 'atm_strike' not in st.session_state or st.session_state.atm_strike not in STRIKE_RANGE:
        st.session_state.atm_strike = 60100 # Default to a central strike


# --- Draw UI ---
st.markdown("<h1 style='text-align: center; color: white;'>Bank Nifty Interactive OI Dashboard</h1>", unsafe_allow_html=True)

col1, col2 = st.columns([3, 1])
with col1:
    st.markdown(f'<div class="header-future-price">Banknifty future price:- {st.session_state.future_price:.2f}</div>', unsafe_allow_html=True)
with col2:
    selected_atm = st.selectbox(
        'strike selection',
        options=list(STRIKE_RANGE),
        index=list(STRIKE_RANGE).index(st.session_state.get('atm_strike', 60100)),
        label_visibility="collapsed"
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
