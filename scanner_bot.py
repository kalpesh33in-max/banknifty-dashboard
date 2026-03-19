import os
import re
import asyncio
import datetime
import pytz
from telethon import TelegramClient, events
from telethon.sessions import StringSession

# ---------------- CONFIG ---------------- #

API_ID = int(os.getenv("TG_API_ID"))
API_HASH = os.getenv("TG_API_HASH")
SESSION_STR = os.getenv("TG_SESSION_STR")

# SOURCE_IDS[0] = turnover_flow_bot (5 MIN)
# SOURCE_IDS[1] = angelk101239_bot (2 MIN)
SOURCE_IDS = [int(i.strip()) for i in os.getenv("SOURCE_BOT").split(",")]
TARGET_BOT_ID = int(os.getenv("TARGET_BOT"))

IST = pytz.timezone("Asia/Kolkata")

# State storage for cross-checking between flows
last_signals = {
    "2 MIN FLOW": {"type": None, "time": datetime.datetime.min, "val": 0.0},
    "5 MIN FLOW": {"type": None, "time": datetime.datetime.min, "val": 0.0}
}

# ---------------- FUNCTIONS ---------------- #

def get_atm(price):
    return round(price / 100) * 100

def get_value(label, text):
    # Matches the LAST value on a line to get the 'TOT' column from the table
    # Example: CALL_WR   100(1.3Cr)    400(5.0Cr)    500(6.3Cr) -> captures 6.3
    matches = re.findall(rf"{label}.*?([\d.]+)(Cr|L)", text)
    if not matches:
        return 0.0

    # We take the last match because the TOTAL (TOT) is always at the end of the table row
    val_str, unit = matches[-1]
    value = float(val_str)

    if unit == "L":
        value = value / 100 # Convert Lakhs to Crores

    return value

def get_future_price(text):
    match = re.search(r"BANKNIFTY \(FUT:\s*([\d.]+)\)", text)
    if match:
        return float(match.group(1))
    return None

# ---------------- MAIN ---------------- #

async def main():
    client = TelegramClient(StringSession(SESSION_STR), API_ID, API_HASH)
    await client.start()
    
    print("🚀 Dual-Flow Match Bot Active")
    print(f"Monitoring Sources: {SOURCE_IDS}")

    @client.on(events.NewMessage(chats=SOURCE_IDS))
    async def handler(event):
        text = event.message.text
        fut_price = get_future_price(text)
        
        if not fut_price:
            return

        now = datetime.datetime.now()
        atm = get_atm(fut_price)

        # 1. EXTRACTION
        call_write = get_value("CALL_WR", text)
        put_write = get_value("PUT_WR", text)
        bullish_turn = get_value("Bullish Turn", text)
        bearish_turn = get_value("Bearish Turn", text)

        # 2. SOURCE & CRITERIA ASSIGNMENT
        if event.chat_id == SOURCE_IDS[1]:  # angelk101239_bot (2 MIN)
            current_source = "2 MIN FLOW"
            other_source = "5 MIN FLOW"
            min_turn, min_write = 10.0, 10.0
        else:  # turnover_flow_bot (5 MIN)
            current_source = "5 MIN FLOW"
            other_source = "2 MIN FLOW"
            min_turn, min_write = 2.5, 2.5

        # 3. EVALUATE CURRENT FLOW CRITERIA
        signal_type = None
        current_val = 0.0
        
        # Bullish: Put Writers must dominate
        if bullish_turn >= min_turn and put_write >= min_write and bearish_turn < 1.0:
            signal_type = "CALL"
            current_val = put_write
            
        # Bearish: Call Writers must dominate
        elif bearish_turn >= min_turn and call_write >= min_write and bullish_turn < 1.0:
            signal_type = "PUT"
            current_val = call_write

        if signal_type:
            # Save valid state for the current flow
            last_signals[current_source] = {
                "type": signal_type,
                "time": now,
                "val": current_val
            }

            # 4. CROSS-CHECK WITH OTHER FLOW
            other = last_signals[other_source]
            time_diff = (now - other["time"]).total_seconds()

            # Verify if they match direction and time window (60s)
            if other["type"] == signal_type and time_diff <= 60:
                emoji = "🟢" if signal_type == "CALL" else "🔴"
                
                # Format Alert Message
                msg = (
                    f"{emoji} **INSTITUTIONAL DUAL MATCH** {emoji}\n\n"
                    f"**ACTION: BUY BANKNIFTY {atm} {signal_type}E**\n\n"
                    f"📊 **FLOW SUMMARY**\n"
                    f"• 2 MIN Flow: ✅ Verified ({last_signals['2 MIN FLOW']['val']:.2f} Cr)\n"
                    f"• 5 MIN Flow: ✅ Verified ({last_signals['5 MIN FLOW']['val']:.2f} Cr)\n"
                    f"• Time Gap: {int(time_diff)}s\n\n"
                    f"📈 Future: {fut_price}\n"
                    f"🛡️ SL: 20 pts | 🎯 TARGET: 50 pts"
                )

                await client.send_message(TARGET_BOT_ID, msg)
                
                # Clear states to prevent repeat alerts for the same match
                last_signals["2 MIN FLOW"]["type"] = None
                last_signals["5 MIN FLOW"]["type"] = None

    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
