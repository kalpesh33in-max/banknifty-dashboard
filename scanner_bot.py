import re
import os
from telethon import TelegramClient, events

# --- CONFIGURATION FROM RAILWAY VARIABLES ---
API_ID = int(os.environ.get('TG_API_ID'))
API_HASH = os.environ.get('TG_API_HASH')
SESSION_STR = os.environ.get('TG_SESSION_STR') # String session for cloud deployment

# Bot Usernames from your screenshots
SOURCE_BOT = 'angelk101239_bot' 
TARGET_BOT = 'Marketmenia_news'

def get_atm_strike(price):
    return round(float(price) / 100) * 100

async def main():
    # Use StringSession for Railway to avoid losing login on every deploy
    from telethon.sessions import StringSession
    client = TelegramClient(StringSession(SESSION_STR), API_ID, API_HASH)
    await client.start()
    
    print(f"Connected. Monitoring {SOURCE_BOT}...")

    @client.on(events.NewMessage(chats=SOURCE_BOT))
    async def handler(event):
        text = event.message.text
        
        # 1. Quick Future Price & ATM Extraction
        price_match = re.search(r"BANKNIFTY \(FUT\) : ([\d.]+)", text)
        if not price_match: return
        
        fut_price = float(price_match.group(1))
        atm = get_atm_strike(fut_price)

        # 2. Strict Criteria Extraction (as per your sheet)
        b_turn = float(re.search(r"Bearish Turn : ([\d.]+)Cr", text).group(1)) if "Bearish Turn" in text else 0
        bul_turn = float(re.search(r"Bullish Turn : ([\d.]+)Cr", text).group(1)) if "Bullish Turn" in text else 0
        fut_sell = float(re.search(r"FUTURE_SELL.*?([\d.]+)Cr", text).group(1)) if "FUTURE_SELL" in text else 0
        fut_buy = float(re.search(r"FUTURE_BUY.*?([\d.]+)Cr", text).group(1)) if "FUTURE_BUY" in text else 0
        
        # ITM Logic
        call_w = float(re.search(r"CALL_WRITE.*?([\d.]+)Cr", text).group(1)) if "CALL_WRITE" in text else 0
        put_sc = float(re.search(r"PUT_SC.*?([\d.]+)Cr", text).group(1)) if "PUT_SC" in text else 0
        put_w = float(re.search(r"PUT_WRITE.*?([\d.]+)Cr", text).group(1)) if "PUT_WRITE" in text else 0
        call_sc = float(re.search(r"CALL_SC.*?([\d.]+)Cr", text).group(1)) if "CALL_SC" in text else 0

        # --- BEARISH SIGNAL ---
        if ("VERY STRONG BEARISH" in text.upper() and b_turn > 10 and bul_turn < 1 and fut_sell > 3 and (call_w > 2 or put_sc > 2)):
            await client.send_message(TARGET_BOT, f"🔴 BUY BANKNIFTY {atm} PE | SL: 20 | TGT: 40")

        # --- BULLISH SIGNAL ---
        elif ("VERY STRONG BULLISH" in text.upper() and bul_turn > 10 and b_turn < 1 and fut_buy > 3 and (put_w > 2 or call_sc > 2)):
            await client.send_message(TARGET_BOT, f"🟢 BUY BANKNIFTY {atm} CE | SL: 20 | TGT: 40")

    await client.run_until_disconnected()

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
