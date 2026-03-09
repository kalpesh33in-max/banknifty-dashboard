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
    """
    Extract value in Cr or L and convert to Crore
    """
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


# ---------------- MARKET ALERT ---------------- #

async def market_alerts(client):

    while True:

        now = datetime.datetime.now(IST)

        if now.weekday() <= 4:

            t = now.strftime("%H:%M")

            if t == "09:15":
                await client.send_message(
                    TARGET_BOT_ID,
                    "🚀 MARKET OPEN\nInstitutional Flow Scanner Active"
                )
                await asyncio.sleep(60)

            elif t == "15:30":
                await client.send_message(
                    TARGET_BOT_ID,
                    "🏁 MARKET CLOSED\nScanner Stopped"
                )
                await asyncio.sleep(60)

        await asyncio.sleep(20)


# ---------------- MAIN ---------------- #

async def main():

    client = TelegramClient(StringSession(SESSION_STR), API_ID, API_HASH)

    await client.start()
    await client.get_dialogs()

    print("Bridge Active : Monitoring Sources")

    asyncio.create_task(market_alerts(client))

    @client.on(events.NewMessage(chats=SOURCE_IDS))
    async def handler(event):

        text = event.message.text

        print("MESSAGE RECEIVED")
        print(text)

        fut_price = get_future_price(text)

        if not fut_price:
            return

        atm = get_atm(fut_price)

        # -------- OPTION VALUES -------- #

        call_buy = get_value("CALL_BUY", text)
        put_buy = get_value("PUT_BUY", text)

        call_write = get_value("CALL_WRITE", text)
        put_write = get_value("PUT_WRITE", text)

        call_sc = get_value("CALL_SC", text)
        put_sc = get_value("PUT_SC", text)

        # -------- FUTURES -------- #

        fut_buy = get_value("FUTURE_BUY", text)
        fut_sell = get_value("FUTURE_SELL", text)

        # -------- TURNS -------- #

        bullish_turn = get_value("Bullish Turn", text)
        bearish_turn = get_value("Bearish Turn", text)

        # -------- SOURCE -------- #

        if event.chat_id == SOURCE_IDS[0]:

            source = "2 MIN FLOW"
            target = 40

        else:

            source = "5 MIN FLOW"
            target = 60

        # ==============================
        # 🟢 CALL BUY SIGNAL
        # ==============================

        if (
            call_buy > 2 and
            (put_write > 2 or call_sc > 2) and
            bullish_turn > 10 and
            bearish_turn < 1
        ):

            msg = (
                f"🟢 INSTITUTIONAL CALL BUY\n\n"
                f"BUY BANKNIFTY {atm} CE\n\n"
                f"Future : {fut_price}\n"
                f"Source : {source}\n\n"
                f"CALL BUY : {call_buy:.2f}Cr\n"
                f"PUT WRITE : {put_write:.2f}Cr\n"
                f"CALL SC : {call_sc:.2f}Cr\n"
                f"FUTURE BUY : {fut_buy:.2f}Cr\n\n"
                f"Bullish Turn : {bullish_turn:.2f}Cr\n"
                f"Bearish Turn : {bearish_turn:.2f}Cr\n\n"
                f"SL : 20 pts\n"
                f"TARGET : {target} pts"
            )

            await client.send_message(TARGET_BOT_ID, msg)

        # ==============================
        # 🔴 PUT BUY SIGNAL
        # ==============================

        if (
            put_buy > 2 and
            (call_write > 2 or put_sc > 2) and
            bearish_turn > 10 and
            bullish_turn < 1
        ):

            msg = (
                f"🔴 INSTITUTIONAL PUT BUY\n\n"
                f"BUY BANKNIFTY {atm} PE\n\n"
                f"Future : {fut_price}\n"
                f"Source : {source}\n\n"
                f"PUT BUY : {put_buy:.2f}Cr\n"
                f"CALL WRITE : {call_write:.2f}Cr\n"
                f"PUT SC : {put_sc:.2f}Cr\n"
                f"FUTURE SELL : {fut_sell:.2f}Cr\n\n"
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
