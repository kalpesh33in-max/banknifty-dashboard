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
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return 0.0
    try:
        value = float(match.group(1))
        unit = match.group(2).upper()
        if unit == "L":
            value = value / 100
        return value
    except:
        return 0.0

def get_future_price(text):
    match = re.search(r"BANKNIFTY \(FUT:\s*([\d.]+)\)", text)
    return float(match.group(1)) if match else None

# ---------------- MAIN ---------------- #

async def main():
    client = TelegramClient(StringSession(SESSION_STR), API_ID, API_HASH)
    await client.start()

    print("🚀 Dual Flow Bot (FINAL LOGIC ACTIVE)")

    @client.on(events.NewMessage(chats=SOURCE_IDS))
    async def handler(event):
        text = event.message.text

        fut_price = get_future_price(text)
        if not fut_price:
            return

        now = datetime.datetime.now()
        atm = get_atm(fut_price)

        # -------- EXTRACTION -------- #
        call_write = extract_value(r"CALL_WR\s+\d+\(([\d.]+)\s*(Cr|L)\)", text)
        put_write = extract_value(r"PUT_WR\s+\d+\(([\d.]+)\s*(Cr|L)\)", text)
        bullish_turn = extract_value(r"Bullish Turn:\s*([\d.]+)(Cr|L)", text)
        bearish_turn = extract_value(r"Bearish Turn:\s*([\d.]+)(Cr|L)", text)

        print("\nDEBUG:",
              "CALL_WR:", call_write,
              "PUT_WR:", put_write,
              "BULL:", bullish_turn,
              "BEAR:", bearish_turn)

        # -------- SOURCE -------- #

        if event.chat_id == SOURCE_IDS[1]:
            current_source = "2 MIN FLOW"
            other_source = "5 MIN FLOW"
            min_turn, min_write = 10.0, 10.0
        else:
            current_source = "5 MIN FLOW"
            other_source = "2 MIN FLOW"
            min_turn, min_write = 2.5, 2.5

        # -------- SIGNAL LOGIC -------- #

        signal_type = None
        current_val = 0.0

        # 🟢 CALL BUY
        if (
            bullish_turn >= min_turn and
            put_write >= min_write and
            bearish_turn <= 1.0   # 🔥 purity filter
        ):
            signal_type = "CALL"
            current_val = put_write

        # 🔴 PUT BUY
        elif (
            bearish_turn >= min_turn and
            call_write >= min_write and
            bullish_turn <= 1.0   # 🔥 purity filter
        ):
            signal_type = "PUT"
            current_val = call_write

        # -------- STORE -------- #

        if signal_type:
            print(f"✅ {current_source} SIGNAL: {signal_type}")

            last_signals[current_source] = {
                "type": signal_type,
                "time": now,
                "val": current_val
            }

            other = last_signals[other_source]
            time_diff = (now - other["time"]).total_seconds()

            print(f"Check match → {other_source}, Type: {other['type']}, Gap: {time_diff}s")

            # -------- MATCH -------- #

            if other["type"] == signal_type and time_diff <= 30:

                print("🔥 FINAL MATCH TRIGGERED")

                emoji = "🟢" if signal_type == "CALL" else "🔴"

                msg = (
                    f"{emoji} BUY BANKNIFTY {atm} {signal_type}E\n\n"
                    f"2M: {last_signals['2 MIN FLOW']['val']:.2f}Cr | "
                    f"5M: {last_signals['5 MIN FLOW']['val']:.2f}Cr\n"
                    f"Gap: {int(time_diff)}s"
                )

                await client.send_message(TARGET_BOT_ID, msg)

                # RESET
                last_signals["2 MIN FLOW"]["type"] = None
                last_signals["5 MIN FLOW"]["type"] = None

    await client.run_until_disconnected()

# ---------------- RUN ---------------- #

if __name__ == "__main__":
    asyncio.run(main())
