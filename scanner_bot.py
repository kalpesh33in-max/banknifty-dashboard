import os
import re
import asyncio
from telethon import TelegramClient, events
from telethon.sessions import StringSession

# --- CONFIGURATION FROM RAILWAY ---
API_ID = int(os.getenv('TG_API_ID'))
API_HASH = os.getenv('TG_API_HASH')
SESSION_STR = os.getenv('TG_SESSION_STR')

# Convert IDs to integers to avoid "Entity Not Found" errors
SOURCE_BOT_ID = int(os.getenv('SOURCE_BOT'))
TARGET_BOT_ID = int(os.getenv('TARGET_BOT'))

def get_atm_strike(price):
    """Rounds Future Price to nearest 100 for BankNifty ATM."""
    return round(float(price) / 100) * 100

async def main():
    # Initialize Client
    client = TelegramClient(StringSession(SESSION_STR), API_ID, API_HASH)
    await client.start()
    
    # 1. WAKE UP SESSION: This forces the script to 'remember' your bots
    print("Waking up session memory...")
    await client.get_dialogs()
    
    me = await client.get_me()
    print(f"Bridge Active as: {me.first_name}")
    print(f"Listening to ID: {SOURCE_BOT_ID} | Sending to ID: {TARGET_BOT_ID}")

    # --- THE TEST TRIGGER ---
    @client.on(events.NewMessage(pattern='!test'))
    async def test_handler(event):
        if event.sender_id == me.id:
            print("Test command received! Sending demo signal...")
            try:
                test_msg = (
                    "🔴 **TEST SIGNAL (DEMO)**\n"
                    "**Instrument:** BANKNIFTY 52000 PE\n"
                    "**Entry:** Market Price\n"
                    "**SL:** 20 pts | **TGT:** 40 pts\n"
                    "--- Status: System Working ✅ ---"
                )
                await client.send_message(TARGET_BOT_ID, test_msg)
                print("Test signal delivered successfully to target bot!")
            except Exception as e:
                print(f"Error sending test: {e}")

    # --- REAL MARKET LISTENER ---
    @client.on(events.NewMessage(chats=SOURCE_BOT_ID))
    async def handler(event):
        text = event.message.text
        
        # Extract Future Price
        price_match = re.search(r"BANKNIFTY \(FUT\) : ([\d.]+)", text)
        if not price_match: return
        
        fut_price = float(price_match.group(1))
        atm = get_atm_strike(fut_price)

        # Extract Values
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

        # --- BEARISH STRATEGY ---
        if ("VERY STRONG BEARISH" in text.upper() and b_turn > 10.0 and bul_turn < 1.0 and fut_sell > 3.0):
            if cw_itm > 2.0 or p_sc_itm > 2.0:
                msg = f"🔴 **SIGNAL: BUY BANKNIFTY {atm} PE**\nSL: 20 pts | TGT: 40 pts"
                await client.send_message(TARGET_BOT_ID, msg)

        # --- BULLISH STRATEGY ---
        elif ("VERY STRONG BULLISH" in text.upper() and bul_turn > 10.0 and b_turn < 1.0 and fut_buy > 3.0):
            if pw_itm > 2.0 or c_sc_itm > 2.0:
                msg = f"🟢 **SIGNAL: BUY BANKNIFTY {atm} CE**\nSL: 20 pts | TGT: 40 pts"
                await client.send_message(TARGET_BOT_ID, msg)

    print("Now waiting for signals...")
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
