import os, time, requests, yfinance as yf
from datetime import datetime

# Railway Variables
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

def get_heavy_lot_analysis():
    try:
        # Using USO (Oil Fund) for reliable strike and volume data
        ticker = yf.Ticker("USO")
        # Get nearest expiry option chain
        expiry = ticker.options[0]
        chain = ticker.option_chain(expiry)
        
        # Analyze Calls for institutional activity
        calls = chain.calls
        # Filter for 'Heavy Lots' (Volume > 100)
        heavy_active = calls[calls['volume'] > 100].nlargest(5, 'volume')
        
        if heavy_active.empty:
            return "⚖️ Market Quiet: No heavy lot activity (>100) detected."

        report = f"🛢️ **CRUDE OIL OI ANALYSIS**\n_Expiry: {expiry}_\n"
        report += "---"

        for _, row in heavy_active.iterrows():
            strike = row['strike']
            vol = row['volume']
            price_change = row['change']
            
            # Sentiment Logic: Price + Volume/OI Action
            if price_change > 0:
                sentiment = "🚀 **Long Buildup (BUY)**"
            else:
                sentiment = "✍️ **Short Buildup (WRITER)**"
            
            # Logic for Covering/Unwinding (Simplified for Global Data)
            if abs(price_change) < 0.05 and vol > 500:
                sentiment = "🔥 **Short Covering / Unwinding**"

            report += f"\n🎯 Strike: `{strike}` | Vol: {vol}"
            report += f"\n💡 Signal: {sentiment}\n"

        return report
    except Exception as e:
        return f"⚠️ Data Syncing: {str(e)}"

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)
    except Exception as e:
        print(f"Telegram Failed: {e}")

if __name__ == "__main__":
    while True:
        msg = get_heavy_lot_analysis()
        send_telegram(msg)
        # Check every 10 minutes to avoid rate limiting
        time.sleep(600)
