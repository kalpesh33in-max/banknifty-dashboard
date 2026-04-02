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

# ---------------- FUNCTIONS ---------------- #

def get_atm(price):
    return round(price / 100) * 100

def get_writing_values(label, text):
    """
    Extracts two values from formats like: CALL_WR 123(4.50Cr)(6.20Cr)
    Returns: (ITM_Value, OTM_Value) in Crores
    """
    # Regex looks for: Label -> Space -> Digits -> (Val1)(Val2)
    matches = re.findall(rf"{label}\s+\d+\(([\d.]+)(Cr|L)\)\(([\d.]+)(Cr|L)\)", text)
    if not matches:
        return 0.0, 0.0
    
    itm_val, itm_unit, otm_val, otm_unit = matches[0]
    
    itm = float(itm_val) if itm_unit == "Cr" else float(itm_val) / 100
    otm = float(otm_val) if otm_unit == "Cr" else float(otm_val) / 100
    return itm, otm

def get_value(label, text):
    # General extractor for Bullish/Bearish Turn
    matches = re.findall(rf"{label}.*?([\d.]+)(Cr|L)", text)
    if not matches:
        return 0.0
    val_str, unit = matches[-1]
    value = float(val_str)
    return value if unit == "Cr" else value / 100

def get_future_price(text):
    match = re.search(r"BANKNIFTY \(FUT:\s*([\d.]+)\)", text)
    return float(match.group(1)) if match else None

async def safe_send(client, target_id, message):
    try:
        await client.send_message(target_id, message)
    except Exception as e:
        print(f"⚠️ Delivery error: {e}. Refreshing dialogs...")
        await client.get_dialogs()
        await client.send_message(PeerUser(user_id=target_id), message)

# ---------------- MAIN ---------------- #

async def main():
    client = TelegramClient(StringSession(SESSION_STR), API_ID, API_HASH)
    await client.start()
    
    print("🚀 Scanner Active | 10s Dual-Match | 4Cr ITM + 6Cr OTM Logic")

    @client.on(events.NewMessage(chats=SOURCE_IDS))
    async def handler(event):
        text = event.message.text
        now = datetime.datetime.now()
        
        # 1. IDENTIFY TIMEFRAME & THRESHOLDS
        if "2 MIN" in text:
            lbl, short_lbl = "2 MIN FLOW", "2MIN"
            m_turn = 10.0
            m_itm, m_otm = 4.0, 6.0  # Your updated 2min criteria
        elif "5 MIN" in text:
            lbl, short_lbl = "5 MIN FLOW", "5MIN"
            m_turn = 1.0             # Keeping standard 5min thresholds
            m_itm, m_otm = 1.0, 0.0  
        else:
            return 

        # 2. DATA EXTRACTION
        try:
            bn_section = text.split("💎 BANKNIFTY")[1].split("💎")[0]
            options_part = bn_section.split("---- FUTURES FLOW ----")[0]
        except (IndexError, ValueError):
            return 

        call_itm, call_otm = get_writing_values("CALL_WR", options_part)
        put_itm, put_otm = get_writing_values("PUT_WR", options_part)
        bull_t = get_value("Bullish Turn", options_part)
        bear_t = get_value("Bearish Turn", options_part)

        print(f"🔍 [{short_lbl}] Bull:{bull_t} | Bear:{bear_t} | ITM/OTM: {put_itm}/{put_otm}")

        # 3. SIGNAL LOGIC
        sig_type = None
        # CALL Logic: High Bull Turn + High Put Writing (ITM/OTM)
        if bull_t >= m_turn and put_itm >= m_itm and put_otm >= m_otm and bear_t < 1.0:
            sig_type = "CALL"
        # PUT Logic: High Bear Turn + High Call Writing (ITM/OTM)
        elif bear_t >= m_turn and call_itm >= m_itm and call_otm >= m_otm and bull_t < 1.0:
            sig_type = "PUT"

        if sig_type:
            last_signals[lbl] = {"type": sig_type, "time": now}
            print(f"⚡ {short_lbl} {sig_type} detected. Checking match...")

            # 4. 10-SECOND DUAL MATCH CHECK
            other_lbl = "5 MIN FLOW" if short_lbl == "2MIN" else "2 MIN FLOW"
            other = last_signals.get(other_lbl)

            if other["type"] == sig_type:
                time_diff = (now - other["time"]).total_seconds()
                
                # Check if the other timeframe's alert arrived within 10 seconds
                if abs(time_diff) <= 10:
                    fut_price = get_future_price(text)
                    atm = get_atm(fut_price) if fut_price else "ATM"
                    
                    print(f"✅ DUAL MATCH ({time_diff:.1f}s) - Sending Alert!")
                    emoji = "🟢" if sig_type == "CALL" else "🔴"
                    msg = (
                        f"{emoji} **INSTITUTIONAL DUAL MATCH** {emoji}\n\n"
                        f"**ACTION: BUY BANKNIFTY {atm} {sig_type}E**\n"
                        f"**WINDOW: {abs(time_diff):.1f}s Match**\n\n"
                        f"🛡️ SL: 20 pts | 🎯 TARGET: 50 pts"
                    )
                    await safe_send(client, TARGET_BOT_ID, msg)
                    
                    # Reset to prevent duplicate alerts
                    last_signals["2 MIN FLOW"]["type"] = None
                    last_signals["5 MIN FLOW"]["type"] = None

    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
