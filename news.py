import os, time, requests, yfinance as yf
from datetime import datetime

# Railway Config
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

def get_market_alert():
    try:
        # Fetching Global Crude (WTI) and Dollar Index (DXY)
        # We use Global Data because it never blocks Railway IPs
        tickers = {"Crude Oil": "CL=F", "USD Index": "DX-Y.NYB"}
        
        # Safe download to avoid 'N/A' conversion errors
        crude = yf.Ticker("CL=F").history(period="1d")
        dxy = yf.Ticker("DX-Y.NYB").history(period="1d")
        
        if crude.empty or dxy.empty:
            return "⚠️ Market Data currently N/A (Paused/Weekend)."

        crude_price = crude['Close'].iloc[-1]
        dxy_price = dxy['Close'].iloc[-1]
        
        report = f"🌎 **GLOBAL MARKET ALERT**\n_Time: {datetime.now().strftime('%H:%M')}_\n"
        report += "---"
        report += f"\n🛢️ **WTI Crude: ${crude_price:.2f}**"
        report += f"\n💵 **USD Index: {dxy_price:.2f}**"
        
        # Heavy Lot / Trend Logic
        if crude_price > 75:
            report += "\n\n🔥 **Status: High Volume Zone**"
        
        return report

    except Exception as e:
        # This catches errors so your script doesn't stop running
        return f"⚠️ Syncing Data... (Error: {str(e)})"

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})
    except:
        print("Telegram Send Failed")

if __name__ == "__main__":
    send_telegram("🛰️ **Scanner Active**\nHandling errors automatically.")
    while True:
        report = get_market_alert()
        send_telegram(report)
        # 10 minute gap to avoid being flagged as a bot
        time.sleep(600)
