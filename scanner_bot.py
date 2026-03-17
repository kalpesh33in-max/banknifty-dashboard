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
TARGET_BOT_ID = int(os.getenv("TARGET_BOT"))

IST = pytz.timezone("Asia/Kolkata")

last_signals = {
    "2 MIN FLOW": {"type": None, "time": datetime.datetime.min, "val": 0.0},
    "5 MIN FLOW": {"type": None, "time": datetime.datetime.min, "val": 0.0}
}

# ---------------- FUNCTIONS ---------------- #

def get_atm(price):
    return round(price / 100) * 100

def extract_value(pattern, text):
    match = re.search(pattern, text)
    if not match:
        return 0.0

    value = float(match.group(1))
    unit = match.group(2)

    if unit == "L":
        value = value / 100

    return value

def get_future_price(text):
    match = re.search(r"BANKNIFTY \(FUT:\s*([\d.]+)\)", text)
    return float(match.group(1)) if match else None

# ---------------- MAIN ---------------- #

async def main():
    client = TelegramClient(StringSession(SESSION_STR), API_ID, API_HASH)
    await client.start()
    
    print("🚀 Dual-Flow Match Bot Active")
    print(f"Monitoring Sources: {SOURCE_IDS}")

    @client.on(events.NewMessage(chats=SOURCE_IDS))
    async def handler(event):
        text = event.message.text

        fut_price = get_future_price(text)
        if not fut_price:
            return

        now = datetime.datetime.now()
        atm = get_atm(fut_price)

        # ✅ Correct extraction
        call_write = extract_value(r"CALL_WR.*?\(([\d.]+)(Cr|L)\)", text)
        put_write = extract_value(r"PUT_WR.*?\(([\d.]+)(Cr|L)\)", text)
        bullish_turn = extract_value(r"Bullish Turn:\s*([\d.]+)(Cr|L)", text)
        bearish_turn = extract_value(r"Bearish Turn:\s*([\d.]+)(Cr|L)", text)

        # ---------------- SOURCE ---------------- #

        if event.chat_id == SOURCE_IDS[1]:
            current_source = "2 MIN FLOW"
            other_source = "5 MIN FLOW"
            min_turn, min_write = 10.0, 10.0
        else:
            current_source = "5 MIN FLOW"
            other_source = "2 MIN FLOW"
            min_turn, min_write = 2.5, 2.5

        # ---------------- YOUR ORIGINAL LOGIC ---------------- #

        signal_type = None
        current_val = 0.0
        
        if bullish_turn >= min_turn and put_write >= min_write and bearish_turn < 1.0:
            signal_type = "CALL"
            current_val = put_write
            
        elif bearish_turn >= min_turn and call_write >= min_write and bullish_turn < 1.0:
            signal_type = "PUT"
            current_val = call_write

        if signal_type:
            last_signals[current_source] = {
                "type": signal_type,
                "time": now,
                "val": current_val
            }

            other = last_signals[other_source]
            time_diff = (now - other["time"]).total_seconds()

            if other["type"] == signal_type and time_diff <= 60:

                # ✅ FINAL CLEAN ALERT (YOUR FORMAT)
                msg = (
                    f"BUY BANKNIFTY {atm} {signal_type}E\n"
                    f"SL = 30 POINT\n"
                    f"TARGET = 50 POINT"
                )

                await client.send_message(TARGET_BOT_ID, msg)

                # Reset after alert
                last_signals["2 MIN FLOW"]["type"] = None
                last_signals["5 MIN FLOW"]["type"] = None

    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
