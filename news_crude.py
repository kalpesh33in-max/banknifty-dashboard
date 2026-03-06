import os, time, requests, yfinance as yf
from datetime import datetime

# Railway Variables
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

def get_global_market_alert():
    try:
        # Fetch Global Crude (WTI) and Dollar Index (DXY)
        # CL=F is the WTI Crude Oil Futures ticker
        tickers = {"Crude Oil": "CL=F", "USD Index": "DX-Y.NYB"}
        data = yf.download(list(tickers.values()), period="1d", interval="1m").iloc[-1]
        
        report = f"🌎 **GLOBAL COMMODITY ALERT**\n_Time: {datetime.now().strftime('%H:%M')}_\n"
        report += "---"
        
        # Crude Price & Change
        crude_price = data['Close']['CL=F']
        report += f"\n🛢️ **WTI Crude: ${crude_price:.2f}**"
        
        # DXY Price (Important for Crude Traders)
        # If DXY goes up, Crude usually falls.
        dxy_price = data['Close']['DX-Y.NYB']
        report += f"\n💵 **USD Index: {dxy_price:.2f}**"
        
        # "Hidden" Trend Logic
        # If Crude is up and Dollar is down, it's a strong Buy signal.
        if crude_price > 75 and dxy_price < 104:
            report += "\n\n🔥 **Signal: Strong Global Bullish Setup**"
        
        return report

    except Exception as e:
        # Instead of crashing, we return a friendly error to Telegram
        return f"⚠️ Global Sync Error: Try again in 10 mins."

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})

if __name__ == "__main__":
    while True:
        report = get_global_market_alert()
        send_telegram(report)
        # 15 minutes is the 'Safe Zone' for Railway
        time.sleep(900)
