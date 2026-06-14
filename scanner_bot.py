import os
import re
import asyncio
import datetime
import pytz
from telethon import TelegramClient, events
from telethon.sessions import StringSession

# ---------------- CONFIG ---------------- #
API_ID = int(os.getenv("TG_API_ID"))
API_HASH = os.getenv("TG_API_HASH")
SESSION_STR = os.getenv("TG_SESSION_STR")

SOURCE_IDS = [int(i.strip()) for i in os.getenv("SOURCE_BOT").split(",")]
TARGET_BOT_RAW = os.getenv("TARGET_BOT", "").strip()

IST = pytz.timezone("Asia/Kolkata")

# ---------------- MASTER LOGIC THRESHOLDS ---------------- #
VOL_2MIN_CUMULATIVE = 15.0      # Cr (Sum of last 3 windows)
FUTURES_LEAD_5MIN = 4.0         # Cr (Instant trigger if futures are massive)
DAILY_TRADE_LIMIT = 3           # Max 3 high-conviction trades
PRICE_HOLD_WINDOWS = 2          # Wait 4 mins (2 windows) to confirm price stability
OPPOSITE_EXIT_THRESHOLD = 5.0   # Cr

INDEX_SYMBOLS = ["BANKNIFTY", "NIFTY"]
WATCH_SYMBOLS = INDEX_SYMBOLS + ["SENSEX", "MIDCPNIFTY", "HDFCBANK", "ICICIBANK", "RELIANCE"]

STRIKE_STEPS = {"BANKNIFTY": 100, "NIFTY": 50}

# State Tracking
flow_history_2min = {s: [] for s in INDEX_SYMBOLS}
last_5min_sync = {s: {"bias": None, "fut_bull": 0.0, "fut_bear": 0.0} for s in INDEX_SYMBOLS}
daily_trade_count = 0
active_trade = None
pending_trade = None # {symbol, side, t0_price, wait_count}

# ---------------- UTILITY FUNCTIONS ---------------- #

def parse_target_ref(value):
    if not value: raise RuntimeError("TARGET_BOT env var is not set")
    value = value.strip()
    value = re.sub(r"^https?://t\.me/", "", value, flags=re.IGNORECASE).strip("/")
    return int(value) if re.fullmatch(r"-?\d+", value) else value

TARGET_BOT_REF = parse_target_ref(TARGET_BOT_RAW)

async def resolve_target_entity(client, target_ref):
    try: return await client.get_entity(target_ref)
    except:
        async for dialog in client.iter_dialogs():
            if str(target_ref) in [dialog.name, getattr(dialog.entity, "username", ""), str(dialog.id)]:
                return dialog.entity
    raise RuntimeError(f"Could not resolve TARGET_BOT={target_ref}")

def get_atm(price, symbol):
    step = STRIKE_STEPS.get(symbol.upper(), 100)
    return int(round(float(price) / step) * step)

def _normalize_cr(value, unit):
    try:
        val = float(value)
        return val if unit == "Cr" else (val / 100 if unit == "L" else 0.0)
    except: return 0.0

def get_value(label, text):
    pattern = rf"{label}\s*:\s*([\d.]+)(Cr|L|)"
    matches = re.findall(pattern, text, re.IGNORECASE)
    if not matches: return 0.0
    val_str, unit = matches[-1]
    return _normalize_cr(val_str, unit)

def get_bias(label, text):
    pattern = rf"{label}\s*:\s*([^\r\n]+)"
    matches = re.findall(pattern, text, re.IGNORECASE)
    return matches[-1].strip() if matches else ""

def get_future_price(text, symbol):
    pattern = rf"{re.escape(symbol)}\s*\(FUT:\s*([\d.]+)\)"
    match = re.search(pattern, text, re.IGNORECASE)
    return float(match.group(1)) if match else None

def extract_instrument_section(text, symbol):
    sym_pat = rf"{re.escape(symbol)}\s*\(FUT:"
    m = re.search(sym_pat, text, re.IGNORECASE)
    if not m: return None
    start = m.start()
    next_pos = [len(text)]
    for sym in WATCH_SYMBOLS:
        if sym == symbol: continue
        m2 = re.search(rf"{re.escape(sym)}\s*\(FUT:", text[m.end():], re.IGNORECASE)
        if m2: next_pos.append(m.end() + m2.start())
    return text[start:min(next_pos)]

def parse_flow_metrics(section):
    if not section: return None
    parts = section.split("---- FUTURES FLOW ----", 1)
    opt_part = parts[0]
    fut_part = parts[1] if len(parts) > 1 else ""
    return {
        "opt_bias": get_bias("Option Bias", opt_part),
        "bull_t": get_value("Bullish Turn", opt_part),
        "bear_t": get_value("Bearish Turn", opt_part),
        "fut_bull": get_value("Bullish Turn", fut_part),
        "fut_bear": get_value("Bearish Turn", fut_part),
    }

def side_from_bias(bias):
    up = str(bias or "").upper()
    if ("BULLISH" in up or "🚀" in up or "🔥" in up) and "BEARISH" not in up: return "CALL"
    if ("BEARISH" in up or "📉" in up or "🩸" in up) and "BULLISH" not in up: return "PUT"
    return None

# ---------------- MASTER TRIGGER LOGIC ---------------- #

def evaluate_master_trigger(symbol):
    # 1. Mandatory 5MIN Sync Check
    bn_5 = last_5min_sync["BANKNIFTY"]
    nf_5 = last_5min_sync["NIFTY"]
    
    bn_bias = side_from_bias(bn_5["bias"])
    nf_bias = side_from_bias(nf_5["bias"])
    
    if not bn_bias or bn_bias != nf_bias: return None # No sync
    side = bn_bias
    
    # 2. Aggressive Futures Lead Fast-Track
    fut_vol = bn_5["fut_bull"] if side == "CALL" else bn_5["fut_bear"]
    if fut_vol >= FUTURES_LEAD_5MIN:
        return {"side": side, "label": "5MIN FUTURES LEAD"}

    # 3. 2MIN Cumulative Volume Confirmation
    hist = flow_history_2min[symbol]
    if len(hist) < 3: return None
    
    cum_vol = sum(h["bull_t"] if side == "CALL" else h["bear_t"] for h in hist[-3:])
    opp_vol = sum(h["bear_t"] if side == "CALL" else h["bull_t"] for h in hist[-3:])
    
    if cum_vol >= VOL_2MIN_CUMULATIVE and opp_vol < 2.0:
        return {"side": side, "label": "STRUCTURAL SYNC + VOL"}
        
    return None

async def main():
    global daily_trade_count, active_trade, pending_trade
    client = TelegramClient(StringSession(SESSION_STR), API_ID, API_HASH)
    await client.start()
    target_entity = await resolve_target_entity(client, TARGET_BOT_REF)
    print("🏆 MASTER SCANNER ACTIVE: Structural Synchrony Logic Enabled (Max 3 Trades)")

    @client.on(events.NewMessage(chats=SOURCE_IDS))
    async def handler(event):
        global daily_trade_count, active_trade, pending_trade
        text = event.message.text
        if not text: return
        now = datetime.datetime.now(IST)

        # A. PROCESS 5 MIN DATA
        if "5 MIN" in text.upper():
            for s in INDEX_SYMBOLS:
                sec = extract_instrument_section(text, s)
                m = parse_flow_metrics(sec)
                if m:
                    last_5min_sync[s] = {"bias": m["opt_bias"], "fut_bull": m["fut_bull"], "fut_bear": m["fut_bear"]}
            return

        # B. PROCESS 2 MIN DATA
        if "2 MIN" in text.upper():
            current_prices = {}
            current_metrics = {}
            for s in INDEX_SYMBOLS:
                sec = extract_instrument_section(text, s)
                m = parse_flow_metrics(sec)
                p = get_future_price(sec, s)
                if m and p:
                    flow_history_2min[s].append(m)
                    if len(flow_history_2min[s]) > 10: flow_history_2min[s].pop(0)
                    current_prices[s] = p
                    current_metrics[s] = m

            # 1. Exit Logic
            if active_trade:
                s = active_trade["symbol"]
                m = current_metrics.get(s)
                if m:
                    opp = m["bear_t"] if active_trade["side"] == "CALL" else m["bull_t"]
                    if opp >= OPPOSITE_EXIT_THRESHOLD:
                        await client.send_message(target_entity, f"🛑 **MASTER EXIT {s}**: Reversal {opp:.2f}Cr detected.")
                        active_trade = None

            # 2. Pending Verification (Wait 4 mins / 2 windows)
            if pending_trade:
                s = pending_trade["symbol"]
                p = current_prices.get(s)
                m = current_metrics.get(s)
                if p and m:
                    pending_trade["wait_count"] += 1
                    # Price reversal check
                    rev = (pending_trade["side"] == "CALL" and p < pending_trade["t0_price"]) or \
                          (pending_trade["side"] == "PUT" and p > pending_trade["t0_price"])
                    if rev:
                        pending_trade = None
                    elif pending_trade["wait_count"] >= PRICE_HOLD_WINDOWS:
                        # TRIGGER FINAL ALERT
                        side = pending_trade["side"]
                        strike = get_atm(p, s)
                        msg = (f"💎 **MASTER TRADE ALERT** 💎\n\n"
                               f"**ACTION: BUY {s} {strike} {'CE' if side == 'CALL' else 'PE'}**\n"
                               f"REASON: Structural Breakout Confirmed\n"
                               f"PRICE: {p} | SL: 60 pts")
                        await client.send_message(target_entity, msg)
                        active_trade = {"symbol": s, "side": side, "entry": p}
                        daily_trade_count += 1
                        pending_trade = None

            # 3. New Trigger Search
            if not active_trade and not pending_trade and daily_trade_count < DAILY_TRADE_LIMIT:
                for s in INDEX_SYMBOLS:
                    trigger = evaluate_master_trigger(s)
                    if trigger:
                        pending_trade = {
                            "symbol": s, 
                            "side": trigger["side"], 
                            "t0_price": current_prices[s],
                            "wait_count": 0
                        }
                        break

    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
