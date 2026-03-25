import os
import re
import asyncio
import datetime
import pytz
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import PeerUser

# ---------------- CONFIG ---------------- #
# Pulling all sensitive data from Railway Variables for safety
API_ID = int(os.getenv("TG_API_ID"))
API_HASH = os.getenv("TG_API_HASH")
SESSION_STR = os.getenv("TG_SESSION_STR")

# IDs fetched from environment variables
SOURCE_IDS = [int(i.strip()) for i in os.getenv("SOURCE_BOT").split(",")]
TARGET_BOT_ID = int(os.getenv("TARGET_BOT")) 

IST = pytz.timezone("Asia/Kolkata")

# Tracks signals for Dual-Match logic
last_signals = {
    "2 MIN FLOW": {"type": None, "time": datetime.datetime.min},
    "5 MIN FLOW": {"type": None, "time": datetime.datetime.min}
}

# ---------------- FUNCTIONS ---------------- #

def get_atm(price):
    """Rounds future price to nearest 100 strike."""
    return round(price / 100) * 100

def get_itm_value(label, text):
    """
    Specifically targets the ITM column in the table.
    Regex finds the label and extracts the value inside the FIRST parentheses.
    """
    # Matches: LABEL + spaces + lot count + (ValueCr/L)
    matches = re.findall(rf"{label}\s+\d+\(([\d.]+)(Cr|L)\)", text)
    if not matches:
        return 0.0
    val_str, unit = matches[0] # Taking the first match (ITM Column)
    value = float(val_str)
    return value if unit == "Cr" else value / 100

def get_value(label, text):
    """General extractor for bottom summary values (Bullish/Bearish Turn)."""
    matches = re.findall(rf"{label}.*?([\d.]+)(Cr|L)", text)
    if not matches:
        return 0.0
    val_str, unit = matches[-1]
    value = float(val_str)
    return value if unit == "Cr" else value / 100

def get_future_price(text):
    """Extracts the BANKNIFTY Future price from the header."""
    match = re.search(r"BANKNIFTY \(FUT:\s*([\d.]+)\)", text)
    return float(match.group(1)) if match else None

async def safe_send(client, target_id, message):
    """Prevents 'Could not find input entity' crash by refreshing dialogs if needed."""
    try:
        await client.send_message(target_id, message)
    except ValueError:
        print(f"⚠️ Target ID {target_id} not in cache. Refreshing...")
        await client.get_dialogs() 
        try:
            await client.send_message(PeerUser(user_id=target_id), message)
        except Exception as e:
            print(f"❌ Delivery failed: {e}")

# ---------------- MAIN ---------------- #

async def main():
    client = TelegramClient(StringSession(SESSION_STR), API_ID, API_HASH)
    await client.start()
    
    print("🚀 Scanner Bot Active | ITM Weightage Logic Enabled")

    @client.on(events.NewMessage(chats=SOURCE_IDS))
    async def handler(event):
        text = event.message.text
        
        # 1. SET DYNAMIC THRESHOLDS
        if "2 MIN" in text:
            lbl, short_lbl = "2 MIN FLOW", "2MIN"
            m_turn, m_wr = 10.0, 10.0 # Requirement: 10Cr for 2min
        elif "5 MIN" in text:
            lbl, short_lbl = "5 MIN FLOW", "5MIN"
            m_turn, m_wr = 2.5, 2.5   # Requirement: 2.5Cr for 5min
        else:
            return 

        # 2. DATA EXTRACTION
        try:
            bn_section = text.split("💎 BANKNIFTY")[1].split("💎")[0]
            options_part = bn_section.split("---- FUTURES FLOW ----")[0]
        except (IndexError, ValueError):
            return 

        # Extracting ITM-only writing and total turnover
        call_wr_itm = get_itm_value("CALL_WR", options_part)
        put_wr_itm = get_itm_value("PUT_WR", options_part)
        bull_t = get_value("Bullish Turn", options_part)
        bear_t = get_value("Bearish Turn", options_part)

        print(f"📊 [{short_lbl}] Bull: {bull_t:.2f}Cr | ITM PutWR: {put_wr_itm:.2f}Cr | Bear: {bear_t:.2f}Cr | ITM CallWR: {call_wr_itm:.2f}Cr")

        fut_price = get_future_price(text)
        if not fut_price: return
        
        now = datetime.datetime.now()
        atm = get_atm(fut_price)

        # 3. ITM-BASED SIGNAL LOGIC
        sig_type = None
        if bull_t >= m_turn and put_wr_itm >= m_wr and bear_t < 1.0:
            sig_type = "CALL"
        elif bear_t >= m_turn and call_wr_itm >= m_wr and bull_t < 1.0:
            sig_type = "PUT"

        # 4. DUAL MATCH CHECK
        if sig_type:
            print(f"⚡ {short_lbl} Pattern: {sig_type}. Checking Match...")
            last_signals[lbl] = {"type": sig_type, "time": now}
            
            other_lbl = "5 MIN FLOW" if short_lbl == "2MIN" else "2 MIN FLOW"
            other = last_signals.get(other_lbl, {"type": None, "time": datetime.datetime.min})
            
            # Match within 30 seconds
            if other["type"] == sig_type and abs((now - other["time"]).total_seconds()) <= 30:
                print(f"✅ DUAL MATCH CONFIRMED: Sending {sig_type} alert.")
                emoji = "🟢" if sig_type == "CALL" else "🔴"
                msg = (
                    f"{emoji} **INSTITUTIONAL DUAL MATCH (ITM)** {emoji}\n\n"
                    f"**ACTION: BUY BANKNIFTY {atm} {sig_type}E**\n\n"
                    f"🛡️ SL: 20 pts | 🎯 TARGET: 50 pts"
                )
                await safe_send(client, TARGET_BOT_ID, msg)
                
                # Reset to prevent duplicate alerts
                last_signals["2 MIN FLOW"]["type"] = None
                last_signals["5 MIN FLOW"]["type"] = None

    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
