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
    return int(round(price / 100) * 100)

def get_writing_values(label, text):
    # Regex to capture ITM and OTM specifically: Label 123(ITM)(OTM)
    matches = re.findall(rf"{label}\s+\d+\(([\d.]+)(Cr|L)\)\(([\d.]+)(Cr|L)\)", text)
    if not matches:
        return 0.0, 0.0
    
    itm_val, itm_unit, otm_val, otm_unit = matches[0]
    itm = float(itm_val) if itm_unit == "Cr" else float(itm_val) / 100
    otm = float(otm_val) if otm_unit == "Cr" else float(otm_val) / 100
    return itm, otm

def get_value(label, text):
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
        print(f"❌ Railway Delivery Error: {e}")
        await client.get_dialogs()
        await client.send_message(PeerUser(user_id=target_id), message)

# ---------------- MAIN ---------------- #

async def main():
    client = TelegramClient(StringSession(SESSION_STR), API_ID, API_HASH)
    await client.start()
    
    print("🚀 RAILWAY DEPLOYED: Scanner Bot is Active and Listening...")

    @client.on(events.NewMessage(chats=SOURCE_IDS))
    async def handler(event):
        text = event.message.text
        now = datetime.datetime.now()
        
        # LOG EVERY MESSAGE RECEIVED FOR VISIBILITY
        print(f"📩 [NEW MESSAGE] From Chat ID: {event.chat_id} | Time: {now.strftime('%H:%M:%S')}")

        # 1. IDENTIFY TIMEFRAME
        if "2 MIN" in text:
            lbl, short_lbl = "2 MIN FLOW", "2MIN"
            m_turn = 10.0
            m_itm, m_otm = 7.0, 3.0 
        elif "5 MIN" in text:
            lbl, short_lbl = "5 MIN FLOW", "5MIN"
            m_turn, m_itm, m_otm = 1.0, 1.0, 0.0  
        else:
            print(f"⏩ Skipping message: No '2 MIN' or '5 MIN' keyword found.")
            return 

        # 2. DATA EXTRACTION
        try:
            bn_section = text.split("💎 BANKNIFTY")[1].split("💎")[0]
            options_part = bn_section.split("---- FUTURES FLOW ----")[0]
            
            call_itm, call_otm = get_writing_values("CALL_WR", options_part)
            put_itm, put_otm = get_writing_values("PUT_WR", options_part)
            bull_t = get_value("Bullish Turn", options_part)
            bear_t = get_value("Bearish Turn", options_part)
            
            # LOG THE READ DATA
            print(f"📊 [{short_lbl} DATA] Bull:{bull_t}Cr | Bear:{bear_t}Cr | PutWR(ITM/OTM):{put_itm}/{put_otm}Cr | CallWR(ITM/OTM):{call_itm}/{call_otm}Cr")

        except Exception as e:
            print(f"⚠️ Extraction Failed: {e}")
            return 

        # 3. SIGNAL LOGIC
        sig_type = None
        if bull_t >= m_turn and put_itm >= m_itm and put_otm >= m_otm and bear_t < 1.0:
            sig_type = "CALL"
        elif bear_t >= m_turn and call_itm >= m_itm and call_otm >= m_otm and bull_t < 1.0:
            sig_type = "PUT"

        if sig_type:
            last_signals[lbl] = {"type": sig_type, "time": now}
            print(f"⚡ {short_lbl} {sig_type} SIGNAL DETECTED. Waiting for Dual Match (30s)...")

            # 4. 30-SECOND DUAL MATCH CHECK
            other_lbl = "5 MIN FLOW" if short_lbl == "2MIN" else "2 MIN FLOW"
            other = last_signals.get(other_lbl)

            if other["type"] == sig_type:
                time_diff = (now - other["time"]).total_seconds()
                
                if abs(time_diff) <= 30:
                    fut_price = get_future_price(text)
                    atm_strike = get_atm(fut_price) if fut_price else "ATM"
                    suffix = "CE" if sig_type == "CALL" else "PE"
                    emoji = "🟢" if sig_type == "CALL" else "🔴"
                    
                    print(f"✅ SUCCESS: Dual Match confirmed in {abs(time_diff):.1f}s. Sending Alert.")
                    
                    msg = (
                        f"{emoji} **INSTITUTIONAL DUAL MATCH** {emoji}\n\n"
                        f"**ACTION: BUY BANKNIFTY {atm_strike} {suffix}**\n"
                        f"**SIGNAL: {sig_type} (Matched in {abs(time_diff):.1f}s)**\n\n"
                        f"🛡️ **SL: 30 pts**\n"
                        f"🎯 **TARGET: 60 pts**"
                    )
                    await safe_send(client, TARGET_BOT_ID, msg)
                    
                    # Reset
                    last_signals["2 MIN FLOW"]["type"] = None
                    last_signals["5 MIN FLOW"]["type"] = None
                else:
                    print(f"⏳ Match found but time difference too high: {abs(time_diff):.1f}s")

    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
