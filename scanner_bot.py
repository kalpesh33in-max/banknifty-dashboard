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

# RAW IDs from env
SOURCE_IDS = [int(i.strip()) for i in os.getenv("SOURCE_BOT").split(",")]
TARGET_BOT_ID = int(os.getenv("TARGET_BOT"))

IST = pytz.timezone("Asia/Kolkata")

# Using standard keys to avoid KeyError
last_signals = {
    "2 MIN FLOW": {"type": None, "time": datetime.datetime.min},
    "5 MIN FLOW": {"type": None, "time": datetime.datetime.min}
}

# ---------------- FUNCTIONS ---------------- #
def get_atm(price):
    return round(price / 100) * 100

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

# ---------------- MAIN ---------------- #
async def main():
    client = TelegramClient(StringSession(SESSION_STR), API_ID, API_HASH)
    await client.start()
    
    print("🚀 Dual-Flow Match Bot Active")

    @client.on(events.NewMessage(chats=SOURCE_IDS))
    async def handler(event):
        text = event.message.text
        
        # 1. IDENTIFY SOURCE FROM TEXT HEADER (Ensures labels are never swapped)
        if "2 MIN" in text:
            lbl = "2 MIN FLOW"
            short_lbl = "2MIN"
            m_turn, m_wr = 10.0, 10.0
        elif "5 MIN" in text:
            lbl = "5 MIN FLOW"
            short_lbl = "5MIN"
            m_turn, m_wr = 2.5, 2.5
        else:
            return # Not a summary message

        # 2. SCOPE TO BANKNIFTY SECTION
        try:
            bn_section = text.split("💎 BANKNIFTY")[1].split("💎")[0]
            options_part = bn_section.split("---- FUTURES FLOW ----")[0]
        except (IndexError, ValueError):
            return 

        # 3. EXTRACT DATA
        call_wr = get_value("CALL_WR", options_part)
        put_wr = get_value("PUT_WR", options_part)
        bull_t = get_value("Bullish Turn", options_part)
        bear_t = get_value("Bearish Turn", options_part)

        # Correct Log Output
        print(f"📊 [{short_lbl}] Bull: {bull_t:.2f}Cr | PutWR: {put_wr:.2f}Cr | Bear: {bear_t:.2f}Cr | CallWR: {call_wr:.2f}Cr")

        fut_price = get_future_price(text)
        if not fut_price: return
        
        now = datetime.datetime.now()
        atm = get_atm(fut_price)

        # 4. SIGNAL LOGIC
        sig_type = None
        if bull_t >= m_turn and put_wr >= m_wr and bear_t < 1.0:
            sig_type = "CALL"
        elif bear_t >= m_turn and call_wr >= m_wr and bull_t < 1.0:
            sig_type = "PUT"

        if sig_type:
            print(f"⚡ {short_lbl} Pattern: {sig_type}. Checking Dual Match...")
            last_signals[lbl] = {"type": sig_type, "time": now}
            
            # Check for match within 30 seconds
            other_lbl = "5 MIN FLOW" if short_lbl == "2MIN" else "2 MIN FLOW"
            other = last_signals.get(other_lbl, {"type": None, "time": datetime.datetime.min})
            
            if other["type"] == sig_type:
                time_diff = (now - other["time"]).total_seconds()
                # Check if signals are within 30 seconds of each other
                if abs(time_diff) <= 30:
                    print(f"✅ DUAL MATCH CONFIRMED: Sending {sig_type} alert.")
                    emoji = "🟢" if sig_type == "CALL" else "🔴"
                    msg = (
                        f"{emoji} **INSTITUTIONAL DUAL MATCH** {emoji}\n\n"
                        f"**ACTION: BUY BANKNIFTY {atm} {sig_type}E**\n\n"
                        f"🛡️ SL: 20 pts | 🎯 TARGET: 50 pts"
                    )
                    await client.send_message(TARGET_BOT_ID, msg)
                    
                    # Reset to prevent double alerts
                    last_signals["2 MIN FLOW"]["type"] = None
                    last_signals["5 MIN FLOW"]["type"] = None

    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
