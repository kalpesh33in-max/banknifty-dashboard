import re
from telethon import TelegramClient, events

# --- SETUP ---
API_ID = 'YOUR_API_ID'
API_HASH = 'YOUR_API_HASH'
INPUT_CHANNEL = 'angelk101239_bot' # Source of the flow reports
OUTPUT_CHANNEL = 'YOUR_SUMMARY_BOT_USERNAME' 

def get_atm_strike(price):
    """Rounds Future Price to nearest 100 strike."""
    return round(float(price) / 100) * 100

async def main():
    client = TelegramClient('quick_scanner', API_ID, API_HASH)
    await client.start()
    
    @client.on(events.NewMessage(chats=INPUT_CHANNEL))
    async def handler(event):
        text = event.message.text
        
        # Extract Future Price & ATM Strike
        price_match = re.search(r"BANKNIFTY \(FUT\) : ([\d.]+)", text)
        if not price_match: return
        
        fut_price = float(price_match.group(1))
        atm = get_atm_strike(fut_price)

        # Extract Core Values using Regex
        b_turn = float(re.search(r"Bearish Turn : ([\d.]+)Cr", text).group(1)) if re.search(r"Bearish Turn : ([\d.]+)Cr", text) else 0
        bul_turn = float(re.search(r"Bullish Turn : ([\d.]+)Cr", text).group(1)) if re.search(r"Bullish Turn : ([\d.]+)Cr", text) else 0
        fut_sell = float(re.search(r"FUTURE_SELL.*?([\d.]+)Cr", text).group(1)) if re.search(r"FUTURE_SELL.*?([\d.]+)Cr", text) else 0
        fut_buy = float(re.search(r"FUTURE_BUY.*?([\d.]+)Cr", text).group(1)) if re.search(r"FUTURE_BUY.*?([\d.]+)Cr", text) else 0
        
        # ITM Extraction
        call_write_itm = float(re.search(r"CALL_WRITE.*?([\d.]+)Cr", text).group(1)) if "CALL_WRITE" in text else 0
        put_sc_itm = float(re.search(r"PUT_SC.*?([\d.]+)Cr", text).group(1)) if "PUT_SC" in text else 0
        put_write_itm = float(re.search(r"PUT_WRITE.*?([\d.]+)Cr", text).group(1)) if "PUT_WRITE" in text else 0
        call_sc_itm = float(re.search(r"CALL_SC.*?([\d.]+)Cr", text).group(1)) if "CALL_SC" in text else 0

        # --- BEARISH LOGIC ---
        if ("VERY STRONG BEARISH" in text and b_turn > 10 and bul_turn < 1 and fut_sell > 3 and (call_write_itm > 2 or put_sc_itm > 2)):
            msg = f"🔴 SIGNAL: BUY BANKNIFTY {atm} PE\nSL: 20 pts | TGT: 40 pts"
            await client.send_message(OUTPUT_CHANNEL, msg)

        # --- BULLISH LOGIC ---
        elif ("VERY STRONG BULLISH" in text and bul_turn > 10 and b_turn < 1 and fut_buy > 3 and (put_write_itm > 2 or call_sc_itm > 2)):
            msg = f"🟢 SIGNAL: BUY BANKNIFTY {atm} CE\nSL: 20 pts | TGT: 40 pts"
            await client.send_message(OUTPUT_CHANNEL, msg)

    await client.run_until_disconnected()

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
