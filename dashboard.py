
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

REFRESH_INTERVAL_SECONDS = 15
DATA_FETCH_TIMEOUT_SECONDS = 10

API_KEY = os.environ.get("API_KEY", "YOUR_API_KEY") 
WSS_URL = "wss://nimblewebstream.lisuns.com:4576/"

STRIKE_RANGE = range(58000, 62001, 100)
EXPIRY_PREFIX = "BANKNIFTY27JAN26"

ALL_OPTION_SYMBOLS = [f"{EXPIRY_PREFIX}{strike}{opt_type}" for strike in STRIKE_RANGE for opt_type in ["CE", "PE"]]
SYMBOLS_TO_MONITOR = ALL_OPTION_SYMBOLS + [f"{EXPIRY_PREFIX}FUT"]

# ==============================================================================
# =============================== UI & STYLING =================================
# ==============================================================================

st.set_page_config(page_title="Bank Nifty OI Scanner", layout="wide", initial_sidebar_state="collapsed")

# Using the default dark theme as requested. The styling function handles cell colors.

def style_dashboard(df, selected_atm):
    def moneyness_styler(df_to_style: pd.DataFrame):
        df_style = pd.DataFrame('', index=df_to_style.index, columns=df_to_style.columns)
        for col_name in df_to_style.columns:
            try:
                strike = float(col_name.split()[0])
                opt_type = col_name.split()[1]
            except (ValueError, IndexError):
                continue
            # Black text for readability inside colored cells
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
    latest_data = {}
    try:
        async with websockets.connect(WSS_URL) as websocket:
            await websocket.send(json.dumps({"MessageType": "Authenticate", "Password": API_KEY}))
            auth_response = json.loads(await websocket.recv())
            if not auth_response.get("Complete"):
                print(f"Authentication Failed: {auth_response.get('Reason')}")
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
                pass 
    except Exception as e:
        print(f"An error occurred while fetching data: {e}")
        return None
    return latest_data

# ==============================================================================
# ============================ MAIN LOGIC ======================================
# ==============================================================================

if 'history_df' not in st.session_state:
    st.session_state.history_df = pd.DataFrame()
if 'last_refresh_time' not in st.session_state:
    st.session_state.last_refresh_time = None
if 'future_price' not in st.session_state:
    st.session_state.future_price = 0.0

now = datetime.now(ZoneInfo("Asia/Kolkata"))
should_refresh = False
if st.session_state.last_refresh_time is None:
    should_refresh = True
else:
    if now - st.session_state.last_refresh_time >= timedelta(seconds=REFRESH_INTERVAL_SECONDS):
        should_refresh = True

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
            
            match = re.search(r'\d{2}[A-Z]{3}\d{2}(\d+)(CE|PE)$', symbol)
            if match:
                strike_price = match.group(1)
                option_type = match.group(2).lower()
                col_name = f"{strike_price} {option_type}"
                new_row_data[col_name] = f"{oi_roc:.2f}%"
            
            st.session_state[symbol] = {"oi": live_oi}

        new_row_df = pd.DataFrame([new_row_data]).set_index('time')
        st.session_state.history_df = pd.concat([st.session_state.history_df, new_row_df])
        st.session_state.last_refresh_time = now
        st.rerun()

# ==============================================================================
# ============================ UI DRAWING ======================================
# ==============================================================================

st.title("Bank Nifty Interactive OI Dashboard")
st.markdown(f'Banknifty future price:- **{st.session_state.future_price:.2f}**')

if st.session_state.history_df.empty:
    st.info("Waiting for the first data fetch to complete...")
else:
    live_price = st.session_state.future_price
    if live_price > 0:
        all_strikes = list(STRIKE_RANGE)
        
        itm_calls = sorted([s for s in all_strikes if s < live_price])[-5:]
        itm_call_cols = [f"{s} ce" for s in itm_calls]
        
        itm_puts = sorted([s for s in all_strikes if s > live_price])[:5]
        itm_put_cols = [f"{s} pe" for s in itm_puts]
        
        atm_strike = min(all_strikes, key=lambda x:abs(x-live_price))
        atm_cols = [f"{atm_strike} ce", f"{atm_strike} pe"]

        display_columns = sorted(itm_call_cols + atm_cols + itm_put_cols)
        
        valid_display_columns = [col for col in display_columns if col in st.session_state.history_df.columns]
        
        if valid_display_columns:
            df_display = st.session_state.history_df[valid_display_columns].sort_index(ascending=False).head(20)
            # For coloring, we still need a selected ATM concept, let's use the calculated ATM
            styled_table = style_dashboard(df_display, atm_strike)
            st.dataframe(styled_table, use_container_width=True)
        else:
            st.warning("Data fetched, but could not find columns for dynamic ITM strikes. Waiting for next refresh.")
    else:
        st.info("Live future price is 0. Waiting for market data to determine ITM strikes.")

st.components.v1.html(f"<script>setTimeout(function(){{window.location.reload(true);}}, {REFRESH_INTERVAL_SECONDS * 1000});</script>", height=0)
st.caption(f"Page will refresh every {REFRESH_INTERVAL_SECONDS} seconds.")
