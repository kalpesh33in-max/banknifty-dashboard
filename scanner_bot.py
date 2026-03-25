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

# SOURCE_IDS[0] = 5 MIN, SOURCE_IDS[1] = 2 MIN
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

def get_value(label, text):
    # Extracts number and unit (Cr/L) and converts all to Crore
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
        
        # 1. ONLY READ BANKNIFTY SECTION
        try:
            # Isolates text between BANKNIFTY and the next symbol
            bn_section = text.split("💎 BANKNIFTY")[1].split("💎")[0]
            options_part = bn_section.split("---- FUTURES FLOW ----")[0]
        except (IndexError, ValueError):
            return 

        # 2. EXTRACT DATA
        call_wr = get_value("CALL_WR", options_part)
        put_wr = get_value("PUT_WR", options_part)
        bull_t = get_value("Bullish Turn", options_part)
        bear_t = get_value("Bearish Turn", options_part)

        # 3. LIVE LOG OUTPUT (As requested)
        is_2min = (event.chat_id == SOURCE_IDS[1])
        lbl = "2MIN" if is_2min else "5MIN"
        print(f"📊 [{lbl}] Bull: {bull_t:.2f}Cr | PutWR: {put_wr:.2f}Cr | Bear: {bear_t:.2f}Cr | CallWR: {call_wr:.2f}Cr")

        fut_price = get_future_price(text)
        if not fut_price: return
        
        now = datetime.datetime.now()
        atm = get_atm(fut_price)

        # 4. SIGNAL LOGIC
        # Thresholds: 10Cr for 2MIN, 2.5Cr for 5MIN
        m_turn, m_wr = (10.0, 10.0) if is_2min else (2.5, 2.5)
        
        sig_type = None
        if bull_t >= m_turn and put_wr >= m_wr and bear_t < 1.0:
            sig_type = "CALL"
        elif bear_t >= m_turn and call_wr >= m_wr and bull_t < 1.0:
            sig_type = "PUT"

        if sig_type:
            print(f"⚡ {lbl} Detected {sig_type} Pattern. Checking for Dual Match...")
            last_signals[f"{lbl} FLOW"] = {"type": sig_type, "time": now}
            
            # Check for match within 30 seconds
            other_lbl = "5MIN FLOW" if is_2min else "2MIN FLOW"
            other = last_signals[other_lbl]
            
            if other.get("type") == sig_type and (now - other["time"]).total_seconds() <= 30:
                print(f"✅ DUAL MATCH CONFIRMED: Sending {sig_type} alert.")
                emoji = "🟢" if sig_type == "CALL" else "🔴"
                msg = (
                    f"{emoji} **INSTITUTIONAL DUAL MATCH** {emoji}\n\n"
                    f"**ACTION: BUY BANKNIFTY {atm} {sig_type}E**\n\n"
                    f"🛡️ SL: 20 pts | 🎯 TARGET: 50 pts"
                )
                await client.send_message(TARGET_BOT_ID, msg)
                # Reset after signal
                last_signals["2MIN FLOW"]["type"] = None
                last_signals["5MIN FLOW"]["type"] = None

    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
