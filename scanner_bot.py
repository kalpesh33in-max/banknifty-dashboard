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

# IDs: 7882220741 (2-Min) and 8502514107 (5-Min)
SOURCE_IDS = [int(i.strip()) for i in os.getenv('SOURCE_BOT').split(',')]
TARGET_BOT_ID = int(os.getenv('TARGET_BOT'))

IST = pytz.timezone('Asia/Kolkata')

def get_atm_strike(price):
    return round(float(price) / 100) * 100

async def market_alerts(client):
    while True:
        now = datetime.datetime.now(IST)
        if now.weekday() <= 4:
            current_time = now.strftime("%H:%M")
            if current_time == "09:15":
                await client.send_message(TARGET_BOT_ID, "🚀 **Market Open:** Bridge is active.")
                await asyncio.sleep(61)
            elif current_time == "15:30":
                await client.send_message(TARGET_BOT_ID, "🏁 **Market Closed:** Standing by.")
                await asyncio.sleep(61)
        await asyncio.sleep(30)

async def main():
    client = TelegramClient(StringSession(SESSION_STR), API_ID, API_HASH)
    await client.start()
    await client.get_dialogs()
    
    print(f"Bridge Active: Monitoring {len(SOURCE_IDS)} sources with clean output.")
    asyncio.create_task(market_alerts(client))

    @client.on(events.NewMessage(chats=SOURCE_IDS))
    async def handler(event):
        text = event.message.text
        
        # Dynamic Threshold and Target Logic
        if event.chat_id == 7882220741:
            source_label = "2-MIN FLOW"
            threshold_cr = 10.0
            target_pts = 40 
        else:
            source_label = "5-MIN FLOW"
            threshold_cr = 15.0
            target_pts = 60 
        
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

        # CLEAN SIGNAL LOGIC
        if ("VERY STRONG BEARISH" in text.upper() and b_turn > threshold_cr and bul_turn < 1.0 and fut_sell > 3.0):
            if cw_itm > 2.0 or p_sc_itm > 2.0:
                msg = (f"🔴 **SIGNAL: BUY BANKNIFTY {atm} PE**\n"
                       f"**Source:** {source_label}\n"
                       f"**SL:** 20 pts | **TGT:** {target_pts} pts")
                await client.send_message(TARGET_BOT_ID, msg)

        elif ("VERY STRONG BULLISH" in text.upper() and bul_turn > threshold_cr and b_turn < 1.0 and fut_buy > 3.0):
            if pw_itm > 2.0 or c_sc_itm > 2.0:
                msg = (f"🟢 **SIGNAL: BUY BANKNIFTY {atm} CE**\n"
                       f"**Source:** {source_label}\n"
                       f"**SL:** 20 pts | **TGT:** {target_pts} pts")
                await client.send_message(TARGET_BOT_ID, msg)

    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
