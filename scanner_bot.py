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

def get_value(label, text):
    matches = re.findall(rf"{label}.*?([\d.]+)(Cr|L)", text)
    if not matches:
        return 0.0
    val_str, unit = matches[-1]
    value = float(val_str)
    if unit == "L":
        value = value / 100
    return value

def get_future_price(text):
    match = re.search(r"BANKNIFTY \(FUT:\s*([\d.]+)\)", text)
    if match:
        return float(match.group(1))
    return None

# ---------------- MAIN ---------------- #

async def main():
    client = TelegramClient(StringSession(SESSION_STR), API_ID, API_HASH)
    await client.start()
    
    print("🚀 Dual-Flow Match Bot Active")
    print(f"📡 Monitoring Source IDs: {SOURCE_IDS}")

    @client.on(events.NewMessage(chats=SOURCE_IDS))
    async def handler(event):
        text = event.message.text
        
        # LOGGING: This allows you to see if the bot is reading the source channels
        source_name = "2 MIN" if event.chat_id == SOURCE_IDS[1] else "5 MIN"
        print(f"📩 [{datetime.datetime.now(IST).strftime('%H:%M:%S')}] Received {source_name} Alert (ID: {event.chat_id})")

        fut_price = get_future_price(text)
        if not fut_price: 
            return

        # ISOLATE BANKNIFTY SECTION
        try:
            bn_section = text.split("💎 BANKNIFTY")[1].split("💎")[0]
            options_part = bn_section.split("---- FUTURES FLOW ----")[0]
        except:
            return 

        now = datetime.datetime.now()
        atm = get_atm(fut_price)

        # 1. EXTRACTION
        call_write = get_value("CALL_WR", options_part)
        put_write = get_value("PUT_WR", options_part)
        bullish_turn = get_value("Bullish Turn", options_part)
        bearish_turn = get_value("Bearish Turn", options_part)

        if event.chat_id == SOURCE_IDS[1]:  # 2 MIN
            current_source = "2 MIN FLOW"
            other_source = "5 MIN FLOW"
            min_turn, min_write = 10.0, 10.0
        else:  # 5 MIN
            current_source = "5 MIN FLOW"
            other_source = "2 MIN FLOW"
            min_turn, min_write = 2.5, 2.5

        signal_type = None
        # CALL LOGIC
        if bullish_turn >= min_turn and put_write >= min_write and bearish_turn < 1.0:
            signal_type = "CALL"
        # PUT LOGIC
        elif bearish_turn >= min_turn and call_write >= min_write and bullish_turn < 1.0:
            signal_type = "PUT"

        if signal_type:
            print(f"⚡ Potential {signal_type} Signal detected in {current_source}. Waiting for Match...")
            last_signals[current_source] = {
                "type": signal_type, 
                "time": now, 
                "val": put_write if signal_type=="CALL" else call_write
            }
            
            other = last_signals[other_source]
            time_diff = (now - other["time"]).total_seconds()

            if other["type"] == signal_type and time_diff <= 30:
                print(f"✅ DUAL MATCH FOUND! Sending alert to Target...")
                emoji = "🟢" if signal_type == "CALL" else "🔴"
                msg = (
                    f"{emoji} **INSTITUTIONAL DUAL MATCH** {emoji}\n\n"
                    f"**ACTION: BUY BANKNIFTY {atm} {signal_type}E**\n\n"
                    f"🛡️ SL: 20 pts | 🎯 TARGET: 50 pts"
                )
                await client.send_message(TARGET_BOT_ID, msg)
                
                # Reset after successful match
                last_signals["2 MIN FLOW"]["type"] = None
                last_signals["5 MIN FLOW"]["type"] = None

    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
