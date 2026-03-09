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

# ---------------- FUNCTIONS ---------------- #

def get_atm(price):
    return round(price / 100) * 100


def get_value(label, text):
    match = re.search(rf"{label}.*?([\d.]+)(Cr|L)", text)
    if not match:
        return 0.0

    value = float(match.group(1))
    unit = match.group(2)

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
    await client.get_dialogs()

    print("Bridge Active : Monitoring Sources")

    @client.on(events.NewMessage(chats=SOURCE_IDS))
    async def handler(event):

        text = event.message.text

        print("MESSAGE RECEIVED")
        print(text)

        fut_price = get_future_price(text)

        if not fut_price:
            return

        atm = get_atm(fut_price)

        # OPTION DATA

        call_write = get_value("CALL_WRITE", text)
        put_write = get_value("PUT_WRITE", text)

        call_sc = get_value("CALL_SC", text)
        put_sc = get_value("PUT_SC", text)

        bullish_turn = get_value("Bullish Turn", text)
        bearish_turn = get_value("Bearish Turn", text)

        # SOURCE

        if event.chat_id == SOURCE_IDS[0]:
            source = "2 MIN FLOW"
            target = 40
        else:
            source = "5 MIN FLOW"
            target = 60

        # ==============================
        # 🟢 CALL BUY
        # ==============================

        if (
            bullish_turn > 10 and
            bearish_turn < 1 and
            (put_write > 2 or call_sc > 2)
        ):

            msg = (
                f"🟢 INSTITUTIONAL CALL BUY\n\n"
                f"BUY BANKNIFTY {atm} CE\n\n"
                f"Future : {fut_price}\n"
                f"Source : {source}\n\n"
                f"PUT WRITE : {put_write:.2f}Cr\n"
                f"CALL SHORT COVER : {call_sc:.2f}Cr\n\n"
                f"Bullish Turn : {bullish_turn:.2f}Cr\n"
                f"Bearish Turn : {bearish_turn:.2f}Cr\n\n"
                f"SL : 20 pts\n"
                f"TARGET : {target} pts"
            )

            await client.send_message(TARGET_BOT_ID, msg)

        # ==============================
        # 🔴 PUT BUY
        # ==============================

        if (
            bearish_turn > 10 and
            bullish_turn < 1 and
            (call_write > 2 or put_sc > 2)
        ):

            msg = (
                f"🔴 INSTITUTIONAL PUT BUY\n\n"
                f"BUY BANKNIFTY {atm} PE\n\n"
                f"Future : {fut_price}\n"
                f"Source : {source}\n\n"
                f"CALL WRITE : {call_write:.2f}Cr\n"
                f"PUT SHORT COVER : {put_sc:.2f}Cr\n\n"
                f"Bearish Turn : {bearish_turn:.2f}Cr\n"
                f"Bullish Turn : {bullish_turn:.2f}Cr\n\n"
                f"SL : 20 pts\n"
                f"TARGET : {target} pts"
            )

            await client.send_message(TARGET_BOT_ID, msg)

    await client.run_until_disconnected()


# ---------------- START ---------------- #

if __name__ == "__main__":
    asyncio.run(main())
