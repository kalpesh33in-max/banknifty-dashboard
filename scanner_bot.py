import os
import re
import asyncio
import datetime
import pytz
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import PeerUser

# ---------------- CONFIG ---------------- #
API_ID = int(os.getenv("TG_API_ID"))
API_HASH = os.getenv("TG_API_HASH")
SESSION_STR = os.getenv("TG_SESSION_STR")

SOURCE_IDS = [int(i.strip()) for i in os.getenv("SOURCE_BOT").split(",")]
TARGET_BOT_ID = int(os.getenv("TARGET_BOT")) 

IST = pytz.timezone("Asia/Kolkata")

# Tracks the last detected signal per timeframe
last_signals = {
    "2 MIN FLOW": {"type": None, "time": datetime.datetime.min},
    "5 MIN FLOW": {"type": None, "time": datetime.datetime.min}
}

last_option_flow_alert = {"type": None, "time": datetime.datetime.min}

# ---------------- FUNCTIONS ---------------- #

def get_atm(price):
    return int(round(price / 100) * 100)

def get_writing_values(label, text):
    pattern = rf"{label}\s+\d+\(([\d.]+)(Cr|L|)\)\s+\d+\(([\d.]+)(Cr|L|)\)"
    matches = re.findall(pattern, text, re.IGNORECASE)
    
    if not matches:
        return 0.0, 0.0
    
    itm_val, itm_unit, otm_val, otm_unit = matches[0]
    itm = float(itm_val) if itm_unit == "Cr" else (float(itm_val) / 100 if itm_unit == "L" else 0.0)
    otm = float(otm_val) if otm_unit == "Cr" else (float(otm_val) / 100 if otm_unit == "L" else 0.0)
    return itm, otm

def get_value(label, text):
    pattern = rf"{label}\s*:\s*([\d.]+)(Cr|L|)"
    matches = re.findall(pattern, text, re.IGNORECASE)
    if not matches:
        return 0.0
    val_str, unit = matches[-1]
    value = float(val_str)
    return value if unit == "Cr" else (value / 100 if unit == "L" else 0.0)

def get_future_price(text):
    match = re.search(r"BANKNIFTY\s*\(FUT:\s*([\d.]+)\)", text, re.IGNORECASE)
    return float(match.group(1)) if match else None

async def safe_send(client, target_id, message):
    """Robust delivery system to prevent PeerUser lookup errors."""
    try:
        # First attempt: Using direct ID with entity resolution
        entity = await client.get_input_entity(target_id)
        await client.send_message(entity, message)
    except Exception as e:
        print(f"⚠️ Initial delivery failed: {e}. Retrying with dialog refresh...")
        try:
            # Fallback: Refresh the cache and try again
            await client.get_dialogs()
            await client.send_message(target_id, message)
        except Exception as e2:
            print(f"❌ Final Railway Delivery Error: {e2}")

async def maybe_send_option_flow_alert(client, now, fut_price, bull_t, bear_t, put_itm, put_otm, call_itm, call_otm):
    global last_option_flow_alert
    # Thresholds for 2 MIN flow alerts
    bull_ok = bull_t >= 10.0 and bear_t < 1.0 and (put_itm > 0 or put_otm > 0)
    bear_ok = bear_t >= 10.0 and bull_t < 1.0 and (call_itm > 0 or call_otm > 0)
    both_ok = bull_t >= 10.0 and bear_t >= 10.0

    if not bull_ok and not bear_ok and not both_ok:
        return

    if both_ok:
        alert_type, emoji = "BOTH", "🟡"
        detail_lines = [
            f"**BULLISH TURN: {bull_t:.2f}Cr | BEARISH TURN: {bear_t:.2f}Cr**",
            f"**PUT WRITER: ITM {put_itm:.2f}Cr | OTM {put_otm:.2f}Cr**",
            f"**CALL WRITER: ITM {call_itm:.2f}Cr | OTM {call_otm:.2f}Cr**",
        ]
    elif bull_ok:
        alert_type, emoji = "CALL", "🟢"
        detail_lines = [
            f"**BULLISH TURN: {bull_t:.2f}Cr | BEARISH TURN: {bear_t:.2f}Cr**",
            f"**PUT WRITER: ITM {put_itm:.2f}Cr | OTM {put_otm:.2f}Cr**",
        ]
    else:
        alert_type, emoji = "PUT", "🔴"
        detail_lines = [
            f"**BULLISH TURN: {bull_t:.2f}Cr | BEARISH TURN: {bear_t:.2f}Cr**",
            f"**CALL WRITER: ITM {call_itm:.2f}Cr | OTM {call_otm:.2f}Cr**",
        ]

    if last_option_flow_alert["type"] == alert_type:
        if (now - last_option_flow_alert["time"]).total_seconds() < 45:
            return

    msg = f"{emoji} **2 MIN OPTION FLOW ALERT** {emoji}\n\n" + "\n".join(detail_lines)
    await safe_send(client, TARGET_BOT_ID, msg)
    last_option_flow_alert = {"type": alert_type, "time": now}

# ---------------- MAIN ---------------- #

async def main():
    client = TelegramClient(StringSession(SESSION_STR), API_ID, API_HASH)
    await client.start()
    
    # Pre-cache dialogs to prevent 'Entity not found' errors
    await client.get_dialogs()
    print("🚀 RAILWAY DEPLOYED: Scanner Bot is Active and Listening...")

    @client.on(events.NewMessage(chats=SOURCE_IDS))
    async def handler(event):
        text = event.message.text
        if not text or "💎 BANKNIFTY" not in text: return
        
        now = datetime.datetime.now()
        print(f"📩 [NEW MESSAGE] From Chat ID: {event.chat_id} | Time: {now.strftime('%H:%M:%S')}")
        
        # 1. IDENTIFY TIMEFRAME & UPDATED THRESHOLDS
        if "2 MIN" in text.upper():
            lbl, short_lbl = "2 MIN FLOW", "2MIN"
            m_turn, m_itm = 10.0, 4.0  # Reduced ITM threshold from 6.5
        elif "5 MIN" in text.upper():
            lbl, short_lbl = "5 MIN FLOW", "5MIN"
            m_turn, m_itm = 2.0, 0.8   # Reduced ITM threshold from 1.0
        else:
            return 

        # 2. DATA EXTRACTION
        try:
            bn_section = text.split("💎 BANKNIFTY")[1].split("💎")[0]
            options_part = bn_section.split("---- FUTURES FLOW ----")[0]
            
            call_itm, call_otm = get_writing_values("CALL_WR", options_part)
            put_itm, put_otm = get_writing_values("PUT_WR", options_part)
            bull_t = get_value("Bullish Turn", options_part)
            bear_t = get_value("Bearish Turn", options_part)
            
            print(f"📊 [{short_lbl} DATA] Bull:{bull_t}Cr | Bear:{bear_t}Cr | PutWR(ITM):{put_itm}Cr")

        except Exception as e:
            print(f"⚠️ Extraction Failed: {e}")
            return 

        if short_lbl == "2MIN":
            fut_price = get_future_price(text)
            await maybe_send_option_flow_alert(client, now, fut_price, bull_t, bear_t, put_itm, put_otm, call_itm, call_otm)

        # 3. SIGNAL LOGIC
        sig_type = None
        if bull_t >= m_turn and put_itm >= m_itm and bear_t < 1.0:
            sig_type = "CALL"
        elif bear_t >= m_turn and call_itm >= m_itm and bull_t < 1.0:
            sig_type = "PUT"

        if sig_type:
            last_signals[lbl] = {"type": sig_type, "time": now}
            print(f"⚡ {short_lbl} {sig_type} SIGNAL DETECTED. Checking Dual Match...")

            # 4. 30-SECOND DUAL MATCH CHECK
            other_lbl = "5 MIN FLOW" if short_lbl == "2MIN" else "2 MIN FLOW"
            other = last_signals.get(other_lbl)

            if other["type"] == sig_type:
                time_diff = (now - other["time"]).total_seconds()
                
                if abs(time_diff) <= 45: # Increased window to 45s for reliability
                    fut_price = get_future_price(text)
                    atm_strike = get_atm(fut_price) if fut_price else "ATM"
                    suffix = "CE" if sig_type == "CALL" else "PE"
                    emoji = "🟢" if sig_type == "CALL" else "🔴"
                    flow_line = f"**BULLISH TURN: {bull_t:.2f}Cr | ITM PUT: {put_itm:.2f}Cr**" if sig_type == "CALL" else f"**BEARISH TURN: {bear_t:.2f}Cr | ITM CALL: {call_itm:.2f}Cr**"
                    
                    msg = (
                        f"{emoji} **INSTITUTIONAL DUAL MATCH** {emoji}\n\n"
                        f"**ACTION: BUY BANKNIFTY {atm_strike} {suffix}**\n"
                        f"**SIGNAL: {sig_type} (Matched in {abs(time_diff):.1f}s)**\n"
                        f"{flow_line}\n\n"
                        f"🛡️ **SL: 30 pts** | 🎯 **TARGET: 60 pts**"
                    )
                    await safe_send(client, TARGET_BOT_ID, msg)
                    
                    # Reset signals after match
                    last_signals["2 MIN FLOW"]["type"] = None
                    last_signals["5 MIN FLOW"]["type"] = None
                    print("✅ SUCCESS: Alert Sent.")

    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
