import asyncio
import websockets
import json
import time
import requests
from datetime import datetime
import re
import functools
import os
import sys
from zoneinfo import ZoneInfo

# ==============================================================================
# ============================== CONFIGURATION =================================
# ==============================================================================

# --- Environment Variable Loading ---
# Load credentials securely from environment variables
API_KEY = os.environ.get("API_KEY")
ULTRAMSG_INSTANCE = os.environ.get("ULTRAMSG_INSTANCE")
ULTRAMSG_TOKEN = os.environ.get("ULTRAMSG_TOKEN")
ULTRAMSG_GROUP_ID = os.environ.get("ULTRAMSG_GROUP_ID")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# --- Validation ---
# Ensure all required environment variables are set
required_vars = {
    "API_KEY": API_KEY,
    "ULTRAMSG_INSTANCE": ULTRAMSG_INSTANCE,
    "ULTRAMSG_TOKEN": ULTRAMSG_TOKEN,
    "ULTRAMSG_GROUP_ID": ULTRAMSG_GROUP_ID,
    "TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
    "TELEGRAM_CHAT_ID": TELEGRAM_CHAT_ID,
}

missing_vars = [key for key, value in required_vars.items() if value is None]

if missing_vars:
    print(f"❌ Critical Error: Missing required environment variables: {', '.join(missing_vars)}", flush=True)
    print("Please set these variables in your deployment environment and restart the application.", flush=True)
    sys.exit(1) # Exit the script with a non-zero status code to indicate failure

# --- API and Connection ---
WSS_URL = "wss://nimblewebstream.lisuns.com:4576/"

# --- WhatsApp Alerting (UltraMSG) ---
ULTRAMSG_API_URL = f"https://api.ultramsg.com/{ULTRAMSG_INSTANCE}/messages/chat"
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

# --- Symbol List (Options & Futures) ---
SYMBOLS_TO_MONITOR = [
    # BANKNIFTY Options
    "BANKNIFTY27JAN2660000CE", "BANKNIFTY27JAN2660000PE",
    "BANKNIFTY27JAN2659900CE", "BANKNIFTY27JAN2659900PE",
    "BANKNIFTY27JAN2659800CE", "BANKNIFTY27JAN2659800PE",
    "BANKNIFTY27JAN2659700CE", "BANKNIFTY27JAN2659700PE",
    "BANKNIFTY27JAN2659600CE", "BANKNIFTY27JAN2659600PE",
    "BANKNIFTY27JAN2659500CE", "BANKNIFTY27JAN2659500PE",
    "BANKNIFTY27JAN2660100CE", "BANKNIFTY27JAN2660100PE",
    "BANKNIFTY27JAN2660200CE", "BANKNIFTY27JAN2660200PE",
    "BANKNIFTY27JAN2660300CE", "BANKNIFTY27JAN2660300PE",
    "BANKNIFTY27JAN2660400CE", "BANKNIFTY27JAN2660400PE",
    "BANKNIFTY27JAN2660500CE", "BANKNIFTY27JAN2660500PE",

    # HDFCBANK Options
    "HDFCBANK27JAN26980CE", "HDFCBANK27JAN26980PE",
    "HDFCBANK27JAN26975CE", "HDFCBANK27JAN26975PE",
    "HDFCBANK27JAN26970CE", "HDFCBANK27JAN26970PE",
    "HDFCBANK27JAN26985CE", "HDFCBANK27JAN26985PE",
    "HDFCBANK27JAN26990CE", "HDFCBANK27JAN26990PE",

    # ICICIBANK Options
    "ICICIBANK27JAN261370CE", "ICICIBANK27JAN261370PE",
    "ICICIBANK27JAN261360CE", "ICICIBANK27JAN261360PE",
    "ICICIBANK27JAN261350CE", "ICICIBANK27JAN261350PE",
    "ICICIBANK27JAN261380CE", "ICICIBANK27JAN261380PE",
    "ICICIBANK27JAN261390CE", "ICICIBANK27JAN261390PE",

    # SBIN Options
    "SBIN27JAN261005CE", "SBIN27JAN261005PE",
    "SBIN27JAN261000CE", "SBIN27JAN261000PE",
    "SBIN27JAN26995CE", "SBIN27JAN26995PE",
    "SBIN27JAN261010CE", "SBIN27JAN261010PE",
    "SBIN27JAN261015CE", "SBIN27JAN261015PE",
    
    # Futures
    "BANKNIFTY27JAN26FUT", "HDFCBANK27JAN26FUT", "ICICIBANK27JAN26FUT", "SBIN27JAN26FUT",
]

# --- Logic & Thresholds ---
LOT_SIZES = {
    "BANKNIFTY": 30,
    "HDFCBANK": 550,
    "ICICIBANK": 700,
    "SBIN": 750,
}
DEFAULT_LOT_SIZE = 75 # For any other symbol
OI_ROC_THRESHOLD = 2.0 # Temporarily lowered for IV testing

# ==============================================================================
# =============================== STATE & UTILITIES ============================
# ==============================================================================

# State now supports None for IV to track missing data
symbol_data_state = {
    symbol: {
        "price": 0, "price_prev": 0,
        "oi": 0, "oi_prev": 0,
    } for symbol in SYMBOLS_TO_MONITOR
}

# Dictionary to hold the latest price of the underlying futures
future_prices = {
    "BANKNIFTY": 0,
    "HDFCBANK": 0,
    "ICICIBANK": 0,
    "SBIN": 0,
}

def now():
    return datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%H:%M:%S")

async def send_whatsapp(msg: str):
    """Sends a message to the configured UltraMSG group without blocking the event loop."""
    print(f"📦 [{now()}] Preparing to send WhatsApp message...", flush=True)
    loop = asyncio.get_running_loop()
    
    params = {'token': ULTRAMSG_TOKEN, 'to': ULTRAMSG_GROUP_ID, 'body': msg, 'priority': 10}
    
    # Use functools.partial to prepare the blocking function with its arguments
    blocking_call = functools.partial(requests.post, ULTRAMSG_API_URL, params=params, timeout=10)

    try:
        # Run the blocking call in a separate thread
        response = await loop.run_in_executor(None, blocking_call)
        response.raise_for_status() 
        print(f"✅ [{now()}] WhatsApp message sent successfully. Response: {response.text}", flush=True)
    except requests.exceptions.RequestException as e:
        print(f"❌ [{now()}] FAILED to send WhatsApp message: {e}", flush=True)
    except Exception as e:
        print(f"❌ [{now()}] An unexpected error occurred while sending WhatsApp message: {e}", flush=True)



async def send_telegram(msg: str):
    """Sends a message to the configured Telegram chat without blocking the event loop."""
    print(f"📦 [{now()}] Preparing to send Telegram message...", flush=True)
    loop = asyncio.get_running_loop()
    
    params = {'chat_id': TELEGRAM_CHAT_ID, 'text': msg, 'parse_mode': 'Markdown'}
    
    # Use functools.partial to prepare the blocking function with its arguments
    blocking_call = functools.partial(requests.post, TELEGRAM_API_URL, params=params, timeout=10)

    try:
        # Run the blocking call in a separate thread
        response = await loop.run_in_executor(None, blocking_call)
        response.raise_for_status() 
        print(f"✅ [{now()}] Telegram message sent successfully. Response: {response.text}", flush=True)
    except requests.exceptions.RequestException as e:
        print(f"❌ [{now()}] FAILED to send Telegram message: {e}", flush=True)
    except Exception as e:
        print(f"❌ [{now()}] An unexpected error occurred while sending Telegram message: {e}", flush=True)

async def send_alert(msg: str):
    """Dispatches the alert to all configured channels concurrently."""
    await asyncio.gather(
        send_whatsapp(msg),
        send_telegram(msg)
    )

# ==============================================================================
# =============================== CORE LOGIC ===================================
# ==============================================================================

def lots_from_oi_change(symbol, oi_change):
    """Calculates the number of lots from a change in Open Interest."""
    lot_size = DEFAULT_LOT_SIZE
    for name, size in LOT_SIZES.items():
        if name in symbol:
            lot_size = size
            break
    if lot_size == 0: return 0
    return int(abs(oi_change) / lot_size)

def lot_bucket(lots):
    """Classifies the number of lots into qualitative buckets."""
    if lots >= 200: return "EXTREME HIGH"
    if lots >= 150: return "EXTRA HIGH"
    if lots >= 100: return "HIGH"
    if lots >= 75: return "MEDIUM"
    if lots >= 1: return "LOW"
    return "IGNORE"

def classify_option(oi_change, price_change, symbol):
    if price_change == 0:
        if oi_change > 0:
            return "WRITING / HEDGING"
        elif oi_change < 0:
            return "POSITION UNWINDING / PROFIT BOOKING"
    elif oi_change > 0:
        if price_change > 0:
            return "BUYERS DOMINANT (LONG BUILD-UP)"
        else:  # price_change < 0
            return "WRITERS DOMINANT (SHORT / PUT WRITING)"
    elif oi_change < 0:
        if price_change > 0:
            return "SHORT COVERING"
        else:  # price_change < 0
            return "LONG UNWINDING"
    
    return "Indecisive Movement"

def get_option_moneyness(symbol, future_prices):
    """
    Checks if an option is ITM, ATM, or OTM based on the latest future price.
    Returns a string: "ITM", "ATM", or "OTM".
    """
    # This filter does not apply to future contracts themselves
    if "FUT" in symbol:
        return "N/A"

    # Identify underlying and get its future price
    underlying = None
    if "HDFCBANK" in symbol: underlying = "HDFCBANK"
    elif "ICICIBANK" in symbol: underlying = "ICICIBANK"
    elif "SBIN" in symbol: underlying = "SBIN"
    elif "BANKNIFTY" in symbol: underlying = "BANKNIFTY"

    if not underlying:
        return "N/A" # If it's not one of our known underlyings, don't block it

    future_price = future_prices.get(underlying)
    if not future_price or future_price == 0:
        print(f"⏳ [{now()}] {symbol}: Waiting for future price of {underlying} to check moneyness.", flush=True)
        return "OTM" # Treat as OTM if we don't have the future price yet

    # Extract strike and type
    try:
        match = re.search(r'.*?(\d{2})(\d+)(CE|PE)$', symbol)
        strike_price = int(match.group(2))
        option_type = match.group(3)
    except (AttributeError, TypeError, ValueError):
        return "N/A" # If we can't parse the option, don't block it

    # Define ATM band (0.5% of future price)
    atm_band = future_price * 0.005
    
    # Check ATM first
    if abs(future_price - strike_price) <= atm_band:
        return "ATM"
    
    # Check ITM
    is_itm = False
    if option_type == 'CE' and strike_price < future_price:
        is_itm = True
    if option_type == 'PE' and strike_price > future_price:
        is_itm = True

    if is_itm:
        return "ITM"
    else:
        # If not ATM and not ITM, it must be OTM
        print(f"ℹ️ [{now()}] {symbol}: OTM (Future: {future_price:.2f}, Strike: {strike_price}), alert suppressed.", flush=True)
        return "OTM"

def format_alert_message(symbol, action, bucket, lots, state, oi_chg, oi_roc, moneyness):
    """Formats the alert message, showing N/A for missing IV."""
    price_chg = state['price'] - state['price_prev']
    if price_chg > 0:
        price_dir = "↑"
    elif price_chg < 0:
        price_dir = "↓"
    else:
        price_dir = "↔"

    # Dynamically determine product name
    product_name = "UNKNOWN" # Default
    if "HDFCBANK" in symbol:
        product_name = "HDFCBANK"
    elif "ICICIBANK" in symbol:
        product_name = "ICICI" # As requested by user
    elif "SBIN" in symbol:
        product_name = "SBIN"
    elif "BANKNIFTY" in symbol:
        product_name = "BANKNIFTY"

    year, strike_display, option_type_display = "", "", ""
    is_future = "FUT" in symbol # Determine if it's a future

    try:
        if is_future:
            match = re.search(r'.*?(\d{2})FUT$', symbol)
            if match:
                year = match.group(1)
            strike_display = "FUT" # For internal logic, but won't be displayed in main_message
            option_type_display = ""
        else: # For options
            match = re.search(r'.*?(\d{2})(\d+)(CE|PE)$', symbol)
            if match:
                year = match.group(1)
                strike_display = match.group(2)
                option_type_display = match.group(3)
            else: # Fallback for old format without date
                match = re.search(r'(\d+)(CE|PE)$', symbol)
                strike_display = match.group(1)
                option_type_display = match.group(2)
    except Exception:
        year, strike_display, option_type_display = "", "N/A", "" # Fallback if parsing completely fails

    if is_future:
        main_message = f"""{product_name} | FUTURE
ACTION: {action}
SIZE: {bucket} ({lots} lots)
EXISTING OI: {state['oi_prev']}
OI Δ: {oi_chg}
OI RoC: {oi_roc:.2f}%
PRICE: {price_dir}
TIME: {now()}
"""
        added_section = f"""{year} {product_name} FUT

{state['price']:.2f}
"""
        return f"{main_message}\n\n{added_section}"
    else:
        line1 = f"{product_name} | OPTIONSTRIKE: {strike_display}{option_type_display} {moneyness}"
        line2 = f"ACTION: {action}"
        line3 = f"SIZE: {bucket} ({lots} lots)"
        line4 = f"EXISTING OI: {state['oi_prev']}"
        line5 = f"OI Δ: {oi_chg}"
        line6 = f"OI RoC: {oi_roc:.2f}%"
        line7 = f"PRICE: {price_dir}"
        line8 = f"TIME: {now()}"
        line9 = f"{year} {product_name} {strike_display}{option_type_display}"
        line10 = f"LAST PRICE: {state['price']:.2f}"

        return f"{line1}\n{line2}\n{line3}\n{line4}\n{line5}\n{line6}\n{line7}\n{line8}\n{line9}\n{line10}"

# ==============================================================================
# ============================ MAIN SCANNER & WEBSOCKET ========================
# ==============================================================================

async def process_data(data):
    """
    Processes a single data packet, updating future prices or sending option alerts.
    Option alerts are filtered to only include ITM/ATM strikes.
    """
    global symbol_data_state, future_prices
    
    symbol = data.get("InstrumentIdentifier")
    if not symbol or symbol not in symbol_data_state:
        return

    new_price = data.get("LastTradePrice")
    if new_price is None:
        return

    # If the symbol is a future, update its price and stop processing
    if "FUT" in symbol:
        underlying = None
        if "HDFCBANK" in symbol: underlying = "HDFCBANK"
        elif "ICICIBANK" in symbol: underlying = "ICICIBANK"
        elif "SBIN" in symbol: underlying = "SBIN"
        elif "BANKNIFTY" in symbol: underlying = "BANKNIFTY"
        
        if underlying and new_price > 0: # Ensure price is valid
            future_prices[underlying] = new_price
        return

    # --- Standard processing for Option contracts ---
    state = symbol_data_state[symbol]
    new_oi = data.get("OpenInterest")

    if new_oi is None:
        return

    state["price_prev"], state["oi_prev"] = state["price"], state["oi"]
    state["price"], state["oi"] = new_price, new_oi

    if state["oi_prev"] == 0:
        print(f"ℹ️ [{now()}] {symbol}: Initializing option data state.", flush=True)
        return

    oi_chg = state["oi"] - state["oi_prev"]
    if oi_chg == 0:
        return

    # --- Calculations ---
    price_chg = state["price"] - state["price_prev"]
    
    try:
        oi_roc = (oi_chg / state["oi_prev"]) * 100
    except ZeroDivisionError:
        oi_roc = 0.0

    # --- Alert Logic ---
    if abs(oi_roc) > OI_ROC_THRESHOLD:
        print(f"🚨 [{now()}] {symbol}: OI RoC {oi_roc:.2f}% > {OI_ROC_THRESHOLD}%. Potential Alert.", flush=True)
        
        lots = lots_from_oi_change(symbol, oi_chg)
        if lots > 50:
            bucket = lot_bucket(lots)
            
            if bucket != "IGNORE":
                #
                # <<< NEW: Filter for ITM/ATM options before sending alert >>>
                #
                moneyness = get_option_moneyness(symbol, future_prices)
                if moneyness in ["ITM", "ATM"]:
                    print(f"📊 [{now()}] {symbol}: {moneyness}, lots: {lots}, Bucket: {bucket}. TRIGGERING ALERT.", flush=True)
                    action = classify_option(oi_chg, price_chg, symbol)
                    alert_msg = format_alert_message(symbol, action, bucket, lots, state, oi_chg, oi_roc, moneyness)
                    await send_alert(alert_msg)

async def run_scanner():
    """The main function to connect, authenticate, subscribe, and process data."""
    while True:
        try:
            async with websockets.connect(WSS_URL, ping_interval=20, ping_timeout=20) as websocket:
                print(f"✅ [{now()}] Connected to WebSocket. Authenticating...", flush=True)
                
                auth_request = {"MessageType": "Authenticate", "Password": API_KEY}
                await websocket.send(json.dumps(auth_request))
                auth_response = json.loads(await websocket.recv())
                
                if not auth_response.get("Complete"):
                    print(f"❌ [{now()}] Authentication FAILED: {auth_response.get('Comment')}. Retrying in 30s.", flush=True)
                    await asyncio.sleep(30)
                    continue
                
                print(f"✅ [{now()}] Authentication successful. Subscribing to {len(SYMBOLS_TO_MONITOR)} symbols...", flush=True)

                for symbol in SYMBOLS_TO_MONITOR:
                    await websocket.send(json.dumps({
                        "MessageType": "SubscribeRealtime", "Exchange": "NFO",
                        "Unsubscribe": "false", "InstrumentIdentifier": symbol
                    }))
                print(f"✅ [{now()}] Subscriptions sent. Scanner is now live.", flush=True)
                await send_alert("✅ GFDL Scanner is LIVE and monitoring the market.")

                async for message in websocket:
                    try:
                        data = json.loads(message)
                        if data.get("MessageType") == "RealtimeResult":
                            await process_data(data)                        
                    except json.JSONDecodeError:
                        print(f"⚠️ [{now()}] Warning: Received a non-JSON message.", flush=True)
                    except Exception as e:
                        print(f"❌ [{now()}] Error during message processing for {message}: {e}", flush=True)

        except websockets.exceptions.ConnectionClosed as e:
            print(f"⚠️ [{now()}] WebSocket connection closed: {e}. Reconnecting in 10 seconds...", flush=True)
            await asyncio.sleep(10)
        except Exception as e:
            print(f"❌ [{now()}] An unexpected error occurred in the main loop: {e}. Reconnecting in 30 seconds...", flush=True)
            await asyncio.sleep(30)

if __name__ == "__main__":
    print("🚀 GFDL Scanner Starting...", flush=True)
    try:
        asyncio.run(run_scanner())
    except KeyboardInterrupt:
        print("\n🛑 Scanner stopped by user.", flush=True)
        # In a real async app, you'd await this, but for shutdown it's okay to fire and forget
        asyncio.run(send_alert("🛑 GFDL Scanner was stopped manually."))
    except Exception as e:
        error_message = f"💥 GFDL Scanner CRASHED with a critical error: {e}"
        print(error_message, flush=True)
        asyncio.run(send_alert(error_message))
