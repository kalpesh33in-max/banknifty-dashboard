import os
import re
import asyncio
from telethon import TelegramClient, events
from telethon.sessions import StringSession

# --- CONFIGURATION FROM RAILWAY VARIABLES ---
API_ID = int(os.getenv('TG_API_ID'))
API_HASH = os.getenv('TG_API_HASH')
SESSION_STR = os.getenv('TG_SESSION_STR')
SOURCE_BOT = 'angelk101239_bot'
TARGET_BOT = 'Marketmenia_news'

def get_atm_strike(price):
    """Rounds Future Price to nearest 100 for BankNifty ATM."""
    return round(float(price) / 100) * 100

async def main():
    # Connect using the StringSession you just generated
    client = TelegramClient(StringSession(SESSION_STR), API_ID, API_HASH)
    await client.start()
    print("Successfully connected! Monitoring Flow Reports...")

    @client.on(events.NewMessage(chats=SOURCE_BOT))
    async def handler(event):
        text = event.message.text
        
        # 1. Extract Future Price
        price_match = re.search(r"BANKNIFTY \(FUT\) : ([\d.]+)", text)
        if not price_match: return
        
        fut_price = float(price_match.group(1))
        atm = get_atm_strike(fut_price)

        # 2. Extract Values for Logic (with safe fallbacks)
        def get_val(pattern, content):
            match = re.search(pattern, content)
            return float(match.group(1)) if match else 0.0

        b_turn = get_val(r"Bearish Turn : ([\d.]+)Cr", text)
        bul_turn = get_val(r"Bullish Turn : ([\d.]+)Cr", text)
        fut_sell = get_val(r"FUTURE_SELL.*?([\d.]+)Cr", text)
        fut_buy = get_val(r"FUTURE_BUY.*?([\d.]+)Cr", text)
        
        # ITM Logic
        cw_itm = get_val(r"CALL_WRITE.*?([\d.]+)Cr", text)
        p_sc_itm = get_val(r"PUT_SC.*?([\d.]+)Cr", text)
        pw_itm = get_val(r"PUT_WRITE.*?([\d.]+)Cr", text)
        c_sc_itm = get_val(r"CALL_SC.*?([\d.]+)Cr", text)

        # --- BEARISH CRITERIA ---
        if ("VERY STRONG BEARISH" in text.upper() and b_turn > 10.0 and bul_turn < 1.0 and fut_sell > 3.0):
            if cw_itm > 2.0 or p_sc_itm > 2.0:
                msg = f"🔴 **SIGNAL: BUY BANKNIFTY {atm} PE**\nSL: 20 pts | TGT: 40 pts"
                await client.send_message(TARGET_BOT, msg)
                print(f"Sent Bearish Signal for {atm} PE")

        # --- BULLISH CRITERIA ---
        elif ("VERY STRONG BULLISH" in text.upper() and bul_turn > 10.0 and b_turn < 1.0 and fut_buy > 3.0):
            if pw_itm > 2.0 or c_sc_itm > 2.0:
                msg = f"🟢 **SIGNAL: BUY BANKNIFTY {atm} CE**\nSL: 20 pts | TGT: 40 pts"
                await client.send_message(TARGET_BOT, msg)
                print(f"Sent Bullish Signal for {atm} CE")

    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
