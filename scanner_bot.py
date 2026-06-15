import os
import re
import asyncio
import datetime
import pytz
from telethon import TelegramClient, events
from telethon.sessions import StringSession

# ---------------- CONFIG ---------------- #
API_ID = int(os.getenv("TG_API_ID", "0"))
API_HASH = os.getenv("TG_API_HASH", "")
SESSION_STR = os.getenv("TG_SESSION_STR", "")

SOURCE_IDS = [int(i.strip()) for i in os.getenv("SOURCE_BOT", "").split(",") if i.strip()]
TARGET_BOT_RAW = os.getenv("TARGET_BOT", "").strip()

IST = pytz.timezone("Asia/Kolkata")

# ---------------- STRATEGY THRESHOLDS ---------------- #
WEIGHT_WR_SC = 1.0
WEIGHT_BUY_UNW = 0.25

EXPLOSIVE_OPT_THRESHOLD = 15.0  # Massive spike to trigger pending alert
EXIT_REVERSAL_THRESHOLD = 20.0  # Bail out if institutions flip

# Trade Management Rules (NO INITIAL SL)
LOCK_IN_POINTS = 150            # Start trailing after 150 pts profit
TRAILING_GAP = 120              # Trail by 120 pts
INTRADAY_EXIT_TIME = datetime.time(15, 20)
MAX_ENTRY_TIME = datetime.time(15, 0)

INDEX_SYMBOLS = ["BANKNIFTY"]
WATCH_SYMBOLS = INDEX_SYMBOLS + ["NIFTY", "SENSEX", "MIDCPNIFTY", "HDFCBANK", "ICICIBANK", "RELIANCE"]

# State Tracking
active_trade = None
pending_alert = None  # {side, trigger_dt, trigger_p}
flow_history_2min = {s: [] for s in INDEX_SYMBOLS}

# ---------------- UTILITY FUNCTIONS ---------------- #

def parse_target_ref(value):
    if not value: return None
    value = value.strip()
    value = re.sub(r"^https?://t\.me/", "", value, flags=re.IGNORECASE).strip("/")
    return int(value) if re.fullmatch(r"-?\d+", value) else value

TARGET_BOT_REF = parse_target_ref(TARGET_BOT_RAW)

async def resolve_target_entity(client, target_ref):
    if not target_ref: return None
    try: return await client.get_entity(target_ref)
    except:
        async for dialog in client.iter_dialogs():
            if str(target_ref) in [dialog.name, getattr(dialog.entity, "username", ""), str(dialog.id)]:
                return dialog.entity
    return None

def _normalize_cr(value, unit):
    try:
        val = float(value)
        return val if unit == "Cr" else (val / 100 if unit == "L" else 0.0)
    except: return 0.0

def parse_weighted_metrics(section):
    if not section: return None
    bull = bear = 0.0
    rows = re.findall(r"([A-Z_]+)\s+[\d.L(Cr)]+\s+[\d.L(Cr)]+\s+\d+\(([\d.]+)(Cr|L|)\)", section)
    for action, val_str, unit in rows:
        val = _normalize_cr(val_str, unit)
        if action in ["PUT_WR", "CALL_SC"]: bull += val * WEIGHT_WR_SC
        elif action in ["CALL_WR", "PUT_SC"]: bear += val * WEIGHT_WR_SC
        elif action in ["CALL_BUY", "PUT_UNW"]: bull += val * WEIGHT_BUY_UNW
        elif action in ["PUT_BUY", "CALL_UNW"]: bear += val * WEIGHT_BUY_UNW
    return {"bull": bull, "bear": bear}

def get_future_price(text, symbol):
    pattern = rf"💎\s*{re.escape(symbol)}\s*\(FUT:\s*([\d.]+)\)"
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        pattern = rf"{re.escape(symbol)}\s*\(FUT:\s*([\d.]+)\)"
        match = re.search(pattern, text, re.IGNORECASE)
    return float(match.group(1)) if match else None

def extract_instrument_section(text, symbol):
    sym_pat = rf"💎\s*{re.escape(symbol)}\s*\(FUT:"
    m = re.search(sym_pat, text, re.IGNORECASE)
    if not m:
        sym_pat = rf"{re.escape(symbol)}\s*\(FUT:"
        m = re.search(sym_pat, text, re.IGNORECASE)
    if not m: return None
    start = m.start()
    next_pos = [len(text)]
    for sym in WATCH_SYMBOLS:
        if sym == symbol: continue
        m2 = re.search(rf"💎\s*{re.escape(sym)}\s*\(FUT:", text[m.end():], re.IGNORECASE)
        if not m2: m2 = re.search(rf"{re.escape(sym)}\s*\(FUT:", text[m.end():], re.IGNORECASE)
        if m2: next_pos.append(m.end() + m2.start())
    return text[start:min(next_pos)]

# ---------------- BOT LOGIC ---------------- #

async def main():
    global active_trade, pending_alert
    
    if not SESSION_STR:
        print("Test Mode: TG_SESSION_STR not found. Logic loaded successfully.")
        return
        
    client = TelegramClient(StringSession(SESSION_STR), API_ID, API_HASH)
    await client.start()
    target_entity = await resolve_target_entity(client, TARGET_BOT_REF)
    
    msg = "🏆 **Scanner Active:** Price-Validated Logic Enabled.\n- Waits 4 mins after 15Cr spike to confirm price direction (Ignores Traps).\n- No Initial SL | +150 Lock-In | 120 Trailing."
    print(msg)
    if target_entity:
        await client.send_message(target_entity, msg)

    @client.on(events.NewMessage(chats=SOURCE_IDS))
    async def handler(event):
        global active_trade, pending_alert
        text = event.message.text
        if not text: return

        now_dt = event.message.date.astimezone(IST)
        curr_time = now_dt.time()

        if "2 MIN" in text.upper():
            s = "BANKNIFTY"
            sec = extract_instrument_section(text, s)
            if not sec: return
            
            m = parse_weighted_metrics(sec)
            p = get_future_price(sec, s)
            if not (m and p): return
            
            flow_history_2min[s].append({"dt": now_dt, "p": p, "bull": m["bull"], "bear": m["bear"]})
            if len(flow_history_2min[s]) > 10: flow_history_2min[s].pop(0)
            
            hist = flow_history_2min[s]

            # 1. TRADE EXIT MANAGEMENT (No Initial SL, Trailing & Reversal Only)
            if active_trade:
                side = active_trade["side"]
                entry_p = active_trade["entry"]
                
                # A. Intraday Close (3:20 PM)
                if curr_time >= INTRADAY_EXIT_TIME:
                    profit = (p - entry_p) if side == "CALL" else (entry_p - p)
                    if target_entity:
                        await client.send_message(target_entity, f"🛑 **AUTO-EXIT {s}**: 3:20 PM Intraday Close.\nPrice: {p}\nProfit: **{profit:.1f} pts**")
                    active_trade = None
                    return
                
                # B. Flow Reversal Bailout
                opp_flow = m["bear"] if side == "CALL" else m["bull"]
                if opp_flow >= EXIT_REVERSAL_THRESHOLD:
                    profit = (p - entry_p) if side == "CALL" else (entry_p - p)
                    if target_entity:
                        await client.send_message(target_entity, f"🛑 **AUTO-EXIT {s}**: Institutional Reversal ({opp_flow:.1f}Cr).\nPrice: {p}\nProfit: **{profit:.1f} pts**")
                    active_trade = None
                    return
                
                # C. Trailing SL Logic
                if side == "CALL":
                    active_trade["peak"] = max(active_trade["peak"], p)
                    profit = p - entry_p
                    if profit >= LOCK_IN_POINTS:
                        sl = active_trade["peak"] - TRAILING_GAP
                        if p <= sl:
                            if target_entity:
                                await client.send_message(target_entity, f"✅ **AUTO-EXIT {s}**: Trailing SL Locked Profit.\nPrice: {p}\nProfit: **{p - entry_p:.1f} pts**")
                            active_trade = None
                else: # PUT
                    active_trade["peak"] = min(active_trade["peak"], p)
                    profit = entry_p - p
                    if profit >= LOCK_IN_POINTS:
                        sl = active_trade["peak"] + TRAILING_GAP
                        if p >= sl:
                            if target_entity:
                                await client.send_message(target_entity, f"✅ **AUTO-EXIT {s}**: Trailing SL Locked Profit.\nPrice: {p}\nProfit: **{entry_p - p:.1f} pts**")
                            active_trade = None

            # 2. PENDING ALERT VALIDATION
            if pending_alert and not active_trade:
                # Count windows received since the trigger
                wait_windows = len([h for h in hist if h["dt"] > pending_alert["trigger_dt"]])
                
                if wait_windows >= 2: # Waited ~4 minutes
                    trigger_p = pending_alert["trigger_p"]
                    side = pending_alert["side"]
                    
                    # Did price move in the SAME direction as the flow?
                    is_valid = False
                    if side == "CALL" and p >= trigger_p:
                        is_valid = True
                    elif side == "PUT" and p <= trigger_p:
                        is_valid = True
                        
                    if is_valid:
                        atm_strike = int(round(p / 100.0)) * 100
                        msg_body = (f"🚨 **VALIDATED BREAKOUT: {s}** 🚨\n\n"
                                    f"Direction: **{side}**\n"
                                    f"Entry Price (FUT): {p}\n\n"
                                    f"{s} {atm_strike} {'CE' if side == 'CALL' else 'PE'} (FULL 2MIN OPTION+FUTURE)\n\n"
                                    f"_Trap Check Passed. Signal sent to execution bots._")
                        if target_entity:
                            await client.send_message(target_entity, msg_body)
                        active_trade = {"side": side, "entry": p, "peak": p}
                    else:
                        # TRAP AVOIDED!
                        msg_body = (f"🚫 **TRAP AVOIDED: {s}** 🚫\n\n"
                                    f"Massive {side} flow detected earlier, but price moved opposite. Ignored trade.")
                        if target_entity:
                            await client.send_message(target_entity, msg_body)
                            
                    pending_alert = None # Clear after validation

            # 3. INITIAL SPIKE DETECTION (Triggers Pending Alert)
            if not active_trade and not pending_alert and curr_time <= MAX_ENTRY_TIME:
                if len(hist) < 2: return
                
                opt_bull_2win = sum(h["bull"] for h in hist[-2:])
                opt_bear_2win = sum(h["bear"] for h in hist[-2:])
                
                if opt_bull_2win >= EXPLOSIVE_OPT_THRESHOLD and opt_bear_2win < 5.0:
                    pending_alert = {"side": "CALL", "trigger_dt": now_dt, "trigger_p": p}
                    if target_entity:
                        await client.send_message(target_entity, f"⏳ **SPIKE DETECTED**: {s} CALL ({opt_bull_2win:.1f}Cr). Waiting 4 mins to validate price action...")
                        
                elif opt_bear_2win >= EXPLOSIVE_OPT_THRESHOLD and opt_bull_2win < 5.0:
                    pending_alert = {"side": "PUT", "trigger_dt": now_dt, "trigger_p": p}
                    if target_entity:
                        await client.send_message(target_entity, f"⏳ **SPIKE DETECTED**: {s} PUT ({opt_bear_2win:.1f}Cr). Waiting 4 mins to validate price action...")

    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
