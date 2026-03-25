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

last_signals = {
    "2 MIN FLOW": {"type": None, "time": datetime.datetime.min},
    "5 MIN FLOW": {"type": None, "time": datetime.datetime.min}
}

# ---------------- FUNCTIONS ---------------- #

def get_atm(price):
    return round(price / 100) * 100

def get_itm_value(label, text):
    # Specifically extracts the FIRST column (ITM) value
    matches = re.findall(rf"{label}\s+\d+\(([\d.]+)(Cr|L)\)", text)
    if not matches:
        return 0.0
    val_str, unit = matches[0] 
    value = float(val_str)
    return value if unit == "Cr" else value / 100

def get_value(label, text):
    # General extractor for bottom summary values
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
    except ValueError:
        print(f"⚠️ Entity {target_id} not cached. Refreshing dialogs...")
        await client.get_dialogs() 
        try:
            await client.send_message(PeerUser(user_id=target_id), message)
        except Exception as e:
            print(f"❌ Critical delivery error: {e}")

# ---------------- MAIN ---------------- #

async def main():
    client = TelegramClient(StringSession(SESSION_STR), API_ID, API_HASH)
    await client.start()
    
    print("🚀 Scanner Bot Active | ITM Weightage Logic | Full Logging On")

    @client.on(events.NewMessage(chats=SOURCE_IDS))
    async def handler(event):
        text = event.message.text
        
        # 1. IDENTIFY TIMEFRAME & THRESHOLDS
        if "2 MIN" in text:
            lbl, short_lbl = "2 MIN FLOW", "2MIN"
            m_turn, m_wr = 10.0, 10.0 
        elif "5 MIN" in text:
            lbl, short_lbl = "5 MIN FLOW", "5MIN"
            m_turn, m_wr = 2.0, 2.0   
        else:
            return 

        # 2. DATA EXTRACTION
        try:
            bn_section = text.split("💎 BANKNIFTY")[1].split("💎")[0]
            options_part = bn_section.split("---- FUTURES FLOW ----")[0]
        except (IndexError, ValueError):
            return 

        call_wr_itm = get_itm_value("CALL_WR", options_part)
        put_wr_itm = get_itm_value("PUT_WR", options_part)
        bull_t = get_value("Bullish Turn", options_part)
        bear_t = get_value("Bearish Turn", options_part)

        # FULL LOG OUTPUT: See exactly what the bot is reading
        print(f"🔍 [{short_lbl} READ] BullTurn: {bull_t:.2f}Cr | PutWR(ITM): {put_wr_itm:.2f}Cr | BearTurn: {bear_t:.2f}Cr | CallWR(ITM): {call_wr_itm:.2f}Cr")

        fut_price = get_future_price(text)
        if not fut_price: return
        
        now = datetime.datetime.now()
        atm = get_atm(fut_price)

        # 3. SIGNAL LOGIC
        sig_type = None
        if bull_t >= m_turn and put_wr_itm >= m_wr and bear_t < 1.0:
            sig_type = "CALL"
        elif bear_t >= m_turn and call_wr_itm >= m_wr and bull_t < 1.0:
            sig_type = "PUT"

        # 4. DUAL MATCH CHECK
        if sig_type:
            print(f"⚡ {short_lbl} Pattern: {sig_type} detected. Checking for Dual Match...")
            last_signals[lbl] = {"type": sig_type, "time": now}
            
            other_lbl = "5 MIN FLOW" if short_lbl == "2MIN" else "2 MIN FLOW"
            other = last_signals.get(other_lbl, {"type": None, "time": datetime.datetime.min})
            
            if other["type"] == sig_type:
                time_diff = (now - other["time"]).total_seconds()
                if abs(time_diff) <= 30:
                    print(f"✅ DUAL MATCH CONFIRMED: Sending {sig_type} alert.")
                    emoji = "🟢" if sig_type == "CALL" else "🔴"
                    msg = (
                        f"{emoji} **INSTITUTIONAL DUAL MATCH (ITM)** {emoji}\n\n"
                        f"**ACTION: BUY BANKNIFTY {atm} {sig_type}E**\n\n"
                        f"🛡️ SL: 20 pts | 🎯 TARGET: 50 pts"
                    )
                    await safe_send(client, TARGET_BOT_ID, msg)
                    
                    # Reset to avoid double-firing
                    last_signals["2 MIN FLOW"]["type"] = None
                    last_signals["5 MIN FLOW"]["type"] = None
                else:
                    print(f"⏳ Match found but time diff too large: {abs(time_diff):.1f}s")

    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
