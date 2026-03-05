import yfinance as yf
import requests
import time
import os
from datetime import datetime

# Railway Environment Variables
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

def send_telegram_msg(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Error sending telegram: {e}")

def get_market_pulse():
    # Global 'Hidden' Drivers: Dollar Index, 10Y Yield, VIX (Fear Index)
    indicators = {
        "DXY (USD Index)": "DX-Y.NYB", 
        "US 10Y Yield": "^TNX",
        "India VIX": "^INDIAVIX"
    }
    
    report = f"📅 *Market Intel: {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n\n"
    report += "*🌍 Global Macro State:*\n"
    
    for name, ticker in indicators.items():
        ticker_data = yf.Ticker(ticker)
        data = ticker_data.history(period="2d")
        
        if len(data) >= 2:
            prev_close = data['Close'].iloc[-2]
            current_price = data['Close'].iloc[-1]
            change = ((current_price - prev_close) / prev_close) * 100
            
            # Logic for "Impact"
            sentiment = "⚠️" if (name == "DXY (USD Index)" and change > 0.2) else "✅"
            if name == "India VIX" and change > 5: sentiment = "🔥 Volatility Spike"
            
            report += f"{sentiment} {name}: {current_price:.2f} ({change:+.2f}%)\n"
            
    report += "\n*🇮🇳 Indian 'Hidden' Movers:*\n"
    report += "• Check NSE: Bulk Deals & Insider Trades\n"
    report += "• Focus: FII/DII Net Flow (Daily Data)\n"
    
    return report

def monitor_loop():
    # Initial alert to confirm it's running
    send_telegram_msg("🛰️ **Market Intelligence System Online**\nScript: `news.py` is active.")
    
    while True:
        # Runs every 4 hours (14400 seconds)
        # You can adjust this for market opening hours (9:15 AM IST)
        report = get_market_pulse()
        send_telegram_msg(report)
        
        time.sleep(14400) 

if __name__ == "__main__":
    monitor_loop()
