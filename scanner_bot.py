import os
import re
import asyncio
from telethon import TelegramClient, events
from telethon.sessions import StringSession

# --- CONFIGURATION ---
API_ID = int(os.getenv('TG_API_ID'))
API_HASH = os.getenv('TG_API_HASH')
SESSION_STR = os.getenv('TG_SESSION_STR')
SOURCE_BOT = os.getenv('SOURCE_BOT', 'angelk101239_bot')
TARGET_BOT = os.getenv('TARGET_BOT', 'Marketmenia_news')

def get_atm_strike(price):
    return round(float(price) / 100) * 100

async def main():
    client = TelegramClient(StringSession(SESSION_STR), API_ID, API_HASH)
    await client.start()
    
    # Get your own ID so the test command only works for you
    me = await client.get_me()
    print(f"Bridge Active as: {me.first_name}. Listening to {SOURCE_BOT}")

    # --- THE TEST TRIGGER ---
    @client.on(events.NewMessage(pattern='!test'))
    async def test_handler(event):
        if event.sender_id == me.id:
            print("Test command received! Sending fake signal to target...")
            test_msg = "🔴 **TEST SIGNAL: BUY BANKNIFTY 52000 PE**\nSL: 20 pts | TGT: 40 pts"
            await client.send_message(TARGET_BOT, test_msg)

    # --- REAL MARKET LISTENER ---
    @client.on(events.NewMessage(chats=SOURCE_BOT))
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

        if ("VERY STRONG BEARISH" in text.upper() and b_turn > 10.0 and bul_turn < 1.0 and fut_sell > 3.0):
            if cw_itm > 2.0 or p_sc_itm > 2.0:
                msg = f"🔴 **SIGNAL: BUY BANKNIFTY {atm} PE**\nSL: 20 pts | TGT: 40 pts"
                await client.send_message(TARGET_BOT, msg)

        elif ("VERY STRONG BULLISH" in text.upper() and bul_turn > 10.0 and b_turn < 1.0 and fut_buy > 3.0):
            if pw_itm > 2.0 or c_sc_itm > 2.0:
                msg = f"🟢 **SIGNAL: BUY BANKNIFTY {atm} CE**\nSL: 20 pts | TGT: 40 pts"
                await client.send_message(TARGET_BOT, msg)

    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
