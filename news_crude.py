import os, time, requests, yfinance as yf
from datetime import datetime

# Railway Config
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

def get_world_crude_data():
    try:
        # Fetching WTI Crude Oil Futures (Current Contract)
        crude = yf.Ticker("CL=F")
        data = crude.history(period="1d")
        
        if data.empty:
            return "⚠️ World Market is currently paused (Weekend/Holiday)."

        ltp = data['Close'].iloc[-1]
        change = ltp - data['Open'].iloc[-1]
        pct_change = (change / data['Open'].iloc[-1]) * 100
        
        report = f"🌎 **WORLD CRUDE OIL (WTI)**\n"
        report += f"🕒 Time: {datetime.now().strftime('%H:%M')} IST\n"
        report += "---"
        report += f"\n💰 **Price: ${ltp:.2f}**"
        report += f"\n📈 Change: {'+' if change > 0 else ''}{change:.2f} ({pct_change:.2f}%)"
        
        # Adding Global Sentiment
        sentiment = "🚀 Bullish" if pct_change > 0.5 else "📉 Bearish" if pct_change < -0.5 else "⚖️ Side-ways"
        report += f"\n\n📊 **Global Sentiment:** {sentiment}"
        
        return report
    except Exception as e:
        return f"❌ Global Data Error: {str(e)}"

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})

if __name__ == "__main__":
    while True:
        msg = get_world_crude_data()
        send_telegram(msg)
        # 10 minute alerts
        time.sleep(600)
