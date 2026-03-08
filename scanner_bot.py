import os
import re
import asyncio
from telethon import TelegramClient, events
from telethon.sessions import StringSession

# --- CONFIGURATION FROM RAILWAY ---
API_ID = int(os.getenv('TG_API_ID'))
API_HASH = os.getenv('TG_API_HASH')
SESSION_STR = os.getenv('TG_SESSION_STR')

# Numerical IDs for zero-error routing
SOURCE_BOT_ID = int(os.getenv('SOURCE_BOT'))
TARGET_BOT_ID = int(os.getenv('TARGET_BOT'))

def get_atm_strike(price):
    """Rounds BankNifty Future Price to nearest 100 for ATM strike."""
    return round(float(price) / 100) * 100

async def main():
    # Initialize the Bridge Client
    client = TelegramClient(StringSession(SESSION_STR), API_ID, API_HASH)
    await client.start()
    
    # Pre-load session memory so IDs are recognized immediately
    await client.get_dialogs()
    
    me = await client.get_me()
    print(f"Bridge Active as: {me.first_name}")
    print(f"Monitoring Source: {SOURCE_BOT_ID} | Sending to: {TARGET_BOT_ID}")

    # --- THE PRODUCTION LISTENER ---
    @client.on(events.NewMessage(chats=SOURCE_BOT_ID))
    async def handler(event):
        text = event.message.text
        
        # 1. Identify valid BankNifty Future Reports
        price_match = re.search(r"BANKNIFTY \(FUT\) : ([\d.]+)", text)
        if not price_match: 
            return
        
        fut_price = float(price_match.group(1))
        atm = get_atm_strike(fut_price)

        # 2. Extract Data Points (Cr values)
        def get_cr(label, content):
            match = re.search(rf"{label}.*?([\d.]+)Cr", content)
            return float(match.group(1)) if match else 0.0

        b_turn = get_cr("Bearish Turn", text)
        bul_turn = get_cr("Bullish Turn", text)
        fut_sell = get_cr("FUTURE_SELL", text)
        fut_buy = get_cr("FUTURE_BUY", text)
        
        # ITM Logic components
        cw_itm = get_cr("CALL_WRITE", text)
        p_sc_itm = get_cr("PUT_SC", text)
        pw_itm = get_cr("PUT_WRITE", text)
        c_sc_itm = get_cr("CALL_SC", text)

        # --- SIGNAL EXECUTION LOGIC ---
        
        # BEARISH SIGNAL CRITERIA
        if ("VERY STRONG BEARISH" in text.upper() and b_turn > 10.0 and bul_turn < 1.0 and fut_sell > 3.0):
            if cw_itm > 2.0 or p_sc_itm > 2.0:
                msg = f"🔴 **SIGNAL: BUY BANKNIFTY {atm} PE**\nSL: 20 pts | TGT: 40 pts"
                await client.send_message(TARGET_BOT_ID, msg)
                print(f"Bearish Signal Sent: {atm} PE")

        # BULLISH SIGNAL CRITERIA
        elif ("VERY STRONG BULLISH" in text.upper() and bul_turn > 10.0 and b_turn < 1.0 and fut_buy > 3.0):
            if pw_itm > 2.0 or c_sc_itm > 2.0:
                msg = f"🟢 **SIGNAL: BUY BANKNIFTY {atm} CE**\nSL: 20 pts | TGT: 40 pts"
                await client.send_message(TARGET_BOT_ID, msg)
                print(f"Bullish Signal Sent: {atm} CE")

    print("System is online. Standing by for market reports...")
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
