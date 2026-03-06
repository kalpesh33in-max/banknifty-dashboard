import os
import time
import requests
import pandas as pd
from datetime import datetime

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

def get_mcx_crude_oi():
    # NSE provides a commodity watch that includes MCX Crude Oil
    url = "https://www.nseindia.com/api/commodity-derivatives?index=all"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.nseindia.com/market-data/commodity-derivatives"
    }

    try:
        session = requests.Session()
        # Get cookies first
        session.get("https://www.nseindia.com", headers=headers, timeout=10)
        response = session.get(url, headers=headers, timeout=10)
        data = response.json()

        # Filter for Crude Oil
        crude_data = [item for item in data['data'] if item['symbol'] == 'CRUDEOIL']
        
        if not crude_data:
            return "⚠️ No Crude data found (Market might be closed)."

        report = f"🛢️ **MCX CRUDE OIL SCANNER**\n_{datetime.now().strftime('%H:%M')}_\n"
        report += "---"

        total_ce_oi = 0
        total_pe_oi = 0
        
        # Sort by Open Interest to find 'Hidden' big writers
        report += "\n🎯 **Top OI Strikes (The Writers):**\n"
        for contract in crude_data[:8]: # Top 8 active strikes
            strike = contract['strikePrice']
            opt_type = contract['optionType']
            oi = contract['openInterest']
            ltp = contract['lastPrice']
            
            if opt_type == 'Call': total_ce_oi += oi
            else: total_pe_oi += oi
            
            report += f"• `{strike} {opt_type[0]}`: OI {oi} | ₹{ltp}\n"

        # Sentiment Logic
        pcr = round(total_pe_oi / total_ce_oi, 2) if total_ce_oi > 0 else 0
        sentiment = "🟢 Bullish (Put Writing)" if pcr > 1.1 else "🔴 Bearish (Call Writing)" if pcr < 0.8 else "🟡 Neutral"
        
        report += f"\n📊 **Sentiment:** {sentiment}\n📈 **PCR:** {pcr}"
        return report

    except Exception as e:
        return f"❌ Blocked by NSE/MCX: {str(e)}"

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})

if __name__ == "__main__":
    while True:
        report = get_mcx_crude_oi()
        send_telegram(report)
        time.sleep(600) # 10 Minutes to avoid IP Ban
