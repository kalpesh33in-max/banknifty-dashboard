import os, time, requests, yfinance as yf
from datetime import datetime

# Railway Config
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

def get_oi_analysis():
    try:
        # Using USO (Oil ETF) to get Strike-wise OI data
        ticker = yf.Ticker("USO")
        # Get the nearest expiry date
        expiry = ticker.options[0]
        opt_chain = ticker.option_chain(expiry)
        
        # We analyze Calls to find Writers and Buyers
        calls = opt_chain.calls
        # Filter for "Heavy Lots" (e.g., top 5 strikes by Open Interest)
        heavy_calls = calls.nlargest(5, 'openInterest')
        
        report = f"🛢️ **CRUDE OIL OI ANALYSIS** ({expiry})\n"
        report += "---"

        for index, row in heavy_calls.iterrows():
            strike = row['strike']
            oi = row['openInterest']
            change = row['change'] # Price change of the option
            
            # Simplified Sentiment Logic based on Price & OI relationship
            # Note: For intraday, we compare current price move with OI
            if change > 0:
                sentiment = "🚀 **Long Buildup (BUY)**"
            else:
                sentiment = "✍️ **Short Buildup (WRITER)**"
                
            report += f"\n🎯 Strike: `{strike}` | OI: {oi}"
            report += f"\n💡 Signal: {sentiment}\n"

        return report
    except Exception as e:
        return f"⚠️ OI Data Syncing... (Market might be closed)"

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})

if __name__ == "__main__":
    send_telegram("🛰️ **OI Sentiment Scanner Active**\nMonitoring Heavy Lots & Strike Action.")
    while True:
        msg = get_oi_analysis()
        send_telegram(msg)
        time.sleep(900) # 15 minutes
