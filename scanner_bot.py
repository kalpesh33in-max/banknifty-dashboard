import os
import re
import asyncio
import datetime
import pytz
from telethon import TelegramClient, events
from telethon.sessions import StringSession

# --- CONFIGURATION ---
API_ID = int(os.getenv('TG_API_ID'))
API_HASH = os.getenv('TG_API_HASH')
SESSION_STR = os.getenv('TG_SESSION_STR')
SOURCE_BOT_ID = int(os.getenv('SOURCE_BOT'))
TARGET_BOT_ID = int(os.getenv('TARGET_BOT'))

IST = pytz.timezone('Asia/Kolkata')

def get_atm_strike(price):
    return round(float(price) / 100) * 100

async def market_alerts(client):
    """Sends Market Open/Close status messages to your Target Bot."""
    while True:
        now = datetime.datetime.now(IST)
        # 0 = Monday, 4 = Friday
        if now.weekday() <= 4:
            current_time = now.strftime("%H:%M")
            
            if current_time == "09:15":
                await client.send_message(TARGET_BOT_ID, "🚀 **Market Open:** Bridge is active and scanning for signals.")
                await asyncio.sleep(61) # Prevent double sending
            
            elif current_time == "15:30":
                await client.send_message(TARGET_BOT_ID, "🏁 **Market Closed:** Bridge is going into standby mode.")
                await asyncio.sleep(61)

        await asyncio.sleep(30) # Check time every 30 seconds

async def main():
    client = TelegramClient(StringSession(SESSION_STR), API_ID, API_HASH)
    await client.start()
    await client.get_dialogs()
    
    me = await client.get_me()
    print(f"Bridge Active: {me.first_name} | Monitoring IST Market Hours")

    # Start the 9:15 AM / 3:30 PM Scheduler in the background
    asyncio.create_task(market_alerts(client))

    @client.on(events.NewMessage(chats=SOURCE_BOT_ID))
    async def handler(event):
        text = event.message.text
        price_match = re.search(r"BANKNIFTY \(FUT\) : ([\d.]+)", text)
        if not price_match: return
        
        fut_price = float(price_match.group(1))
        atm = get_atm_strike(fut_price)

        def get_cr(label, content):
            match = re.search(rf"{label}.*?([\d.]+)Cr", content)
            return float(match.group(1)) if match else 0.0

        b_turn = get_cr("Bearish Turn", text)
        bul_turn = get_cr("Bullish Turn", text)
        fut_sell = get_cr("FUTURE_SELL", text)
        fut_buy = get_cr("FUTURE_BUY", text)
        cw_itm = get_cr("CALL_WRITE", text)
        p_sc_itm = get_cr("PUT_SC", text)
        pw_itm = get_cr("PUT_WRITE", text)
        c_sc_itm = get_cr("CALL_SC", text)

        # BEARISH
        if ("VERY STRONG BEARISH" in text.upper() and b_turn > 10.0 and bul_turn < 1.0 and fut_sell > 3.0):
            if cw_itm > 2.0 or p_sc_itm > 2.0:
                msg = f"🔴 **SIGNAL: BUY BANKNIFTY {atm} PE**\nSL: 20 pts | TGT: 40 pts"
                await client.send_message(TARGET_BOT_ID, msg)

        # BULLISH
        elif ("VERY STRONG BULLISH" in text.upper() and bul_turn > 10.0 and b_turn < 1.0 and fut_buy > 3.0):
            if pw_itm > 2.0 or c_sc_itm > 2.0:
                msg = f"🟢 **SIGNAL: BUY BANKNIFTY {atm} CE**\nSL: 20 pts | TGT: 40 pts"
                await client.send_message(TARGET_BOT_ID, msg)

    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
