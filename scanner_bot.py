import os
import re
import asyncio
import datetime
import pytz
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import PeerUser

# ---------------- CONFIG ---------------- #
API_ID = int(os.getenv("TG_API_ID"))
API_HASH = os.getenv("TG_API_HASH")
SESSION_STR = os.getenv("TG_SESSION_STR")

SOURCE_IDS = [int(i.strip()) for i in os.getenv("SOURCE_BOT").split(",")]
TARGET_BOT_ID = int(os.getenv("TARGET_BOT")) 

IST = pytz.timezone("Asia/Kolkata")

# Tracks the last detected signal per timeframe
last_signals = {
    "2 MIN FLOW": {"type": None, "time": datetime.datetime.min},
    "5 MIN FLOW": {"type": None, "time": datetime.datetime.min}
}

last_option_flow_alert = {"type": None, "time": datetime.datetime.min}
last_signals_by_symbol = {}
instant_itm_alerts = {}

# ---------------- FUNCTIONS ---------------- #

WATCH_SYMBOLS = ["BANKNIFTY", "NIFTY", "HDFCBANK", "ICICIBANK", "MIDCPNIFTY"]


def get_atm(price):
    return int(round(price / 100) * 100)


def _normalize_cr(value, unit):
    try:
        value = float(value)
    except Exception:
        return 0.0
    return value if unit == "Cr" else (value / 100 if unit == "L" else 0.0)

def get_writing_values(label, text):
    # Updated Regex to handle: Label LOTS(VAL_UNIT) LOTS(VAL_UNIT) with flexible spacing
    # Matches: PUT_WR     194(2.42Cr)          0(0)
    pattern = rf"{label}\s+\d+\(([\d.]+)(Cr|L|)\)\s+\d+\(([\d.]+)(Cr|L|)\)"
    matches = re.findall(pattern, text, re.IGNORECASE)
    
    if not matches:
        return 0.0, 0.0
    
    itm_val, itm_unit, otm_val, otm_unit = matches[0]
    
    itm = _normalize_cr(itm_val, itm_unit)
    otm = _normalize_cr(otm_val, otm_unit)
    
    return itm, otm


def get_writing_values_any(labels, text):
    for label in labels:
        itm, otm = get_writing_values(label, text)
        if itm > 0 or otm > 0:
            return itm, otm, label
    return 0.0, 0.0, None

def get_value(label, text):
    # Flexible regex for Turnovers: Bullish Turn: 15.35Cr or 88.78L
    pattern = rf"{label}\s*:\s*([\d.]+)(Cr|L|)"
    matches = re.findall(pattern, text, re.IGNORECASE)
    
    if not matches:
        return 0.0
        
    val_str, unit = matches[-1]
    value = float(val_str)
    return _normalize_cr(value, unit)


def get_future_price(text, symbol="BANKNIFTY"):
    match = re.search(rf"{re.escape(symbol)}\s*\(FUT:\s*([\d.]+)\)", text, re.IGNORECASE)
    return float(match.group(1)) if match else None


def extract_instrument_section(text, symbol):
    m = re.search(rf"{re.escape(symbol)}\s*\(FUT:", text, re.IGNORECASE)
    if not m:
        return None
    start = m.start()

    next_positions = []
    for sym in WATCH_SYMBOLS:
        if sym.upper() == symbol.upper():
            continue
        m2 = re.search(rf"{re.escape(sym)}\s*\(FUT:", text[m.end():], re.IGNORECASE)
        if m2:
            next_positions.append(m.end() + m2.start())
    end = min(next_positions) if next_positions else len(text)
    return text[start:end]


def parse_flow_metrics(section_text):
    if not section_text:
        return None
    options_part = section_text.split("---- FUTURES FLOW ----")[0]

    # Some reports use CALL_SC instead of CALL_WR; treat it as a call-side writer metric.
    call_itm, call_otm, _ = get_writing_values_any(["CALL_WR", "CALL_SC"], options_part)
    put_itm, put_otm, _ = get_writing_values_any(["PUT_WR"], options_part)
    bull_t = get_value("Bullish Turn", options_part)
    bear_t = get_value("Bearish Turn", options_part)
    return {
        "bull_t": bull_t,
        "bear_t": bear_t,
        "call_itm": call_itm,
        "call_otm": call_otm,
        "put_itm": put_itm,
        "put_otm": put_otm,
    }

async def safe_send(client, target_id, message):
    try:
        await client.send_message(target_id, message)
    except Exception as e:
        print(f"❌ Railway Delivery Error: {e}")
        await client.get_dialogs()
        await client.send_message(PeerUser(user_id=target_id), message)


async def maybe_send_option_flow_alert(client, now, fut_price, bull_t, bear_t, put_itm, put_otm, call_itm, call_otm):
    global last_option_flow_alert

    bull_ok = bull_t >= 10.0 and bear_t < 1.0 and (put_itm > 0 or put_otm > 0)
    bear_ok = bear_t >= 10.0 and bull_t < 1.0 and (call_itm > 0 or call_otm > 0)
    both_ok = bull_t >= 10.0 and bear_t >= 10.0 and (
        (put_itm > 0 or put_otm > 0) or (call_itm > 0 or call_otm > 0)
    )

    if not bull_ok and not bear_ok and not both_ok:
        return

    if both_ok:
        alert_type = "BOTH"
        emoji = "🟡"
        detail_lines = [
            f"**BULLISH TURN: {bull_t:.2f}Cr | BEARISH TURN: {bear_t:.2f}Cr**",
            f"**PUT WRITER: ITM {put_itm:.2f}Cr | OTM {put_otm:.2f}Cr**",
            f"**CALL WRITER: ITM {call_itm:.2f}Cr | OTM {call_otm:.2f}Cr**",
        ]
    elif bull_ok:
        alert_type = "CALL"
        emoji = "🟢"
        detail_lines = [
            f"**BULLISH TURN: {bull_t:.2f}Cr | BEARISH TURN: {bear_t:.2f}Cr**",
            f"**PUT WRITER: ITM {put_itm:.2f}Cr | OTM {put_otm:.2f}Cr**",
        ]
    else:
        alert_type = "PUT"
        emoji = "🔴"
        detail_lines = [
            f"**BULLISH TURN: {bull_t:.2f}Cr | BEARISH TURN: {bear_t:.2f}Cr**",
            f"**CALL WRITER: ITM {call_itm:.2f}Cr | OTM {call_otm:.2f}Cr**",
        ]

    if last_option_flow_alert["type"] == alert_type:
        time_diff = (now - last_option_flow_alert["time"]).total_seconds()
        if time_diff < 45:
            return

    msg = (
        f"{emoji} **2 MIN OPTION FLOW ALERT** {emoji}\n\n"
        + "\n".join(detail_lines)
    )
    await safe_send(client, TARGET_BOT_ID, msg)
    last_option_flow_alert = {"type": alert_type, "time": now}

# ---------------- MAIN ---------------- #

async def main():
    client = TelegramClient(StringSession(SESSION_STR), API_ID, API_HASH)
    await client.start()
    
    print("🚀 RAILWAY DEPLOYED: Scanner Bot is Active and Listening...")

    @client.on(events.NewMessage(chats=SOURCE_IDS))
    async def handler(event):
        text = event.message.text
        if not text: return
        
        now = datetime.datetime.now()
        
        # LOG EVERY MESSAGE RECEIVED FOR VISIBILITY
        print(f"📩 [NEW MESSAGE] From Chat ID: {event.chat_id} | Time: {now.strftime('%H:%M:%S')}")
        
        # 1. IDENTIFY TIMEFRAME
        if "2 MIN" in text.upper():
            lbl, short_lbl = "2 MIN FLOW", "2MIN"
            m_turn = 10.0
            m_itm, m_otm = 6.5, None
        elif "5 MIN" in text.upper():
            lbl, short_lbl = "5 MIN FLOW", "5MIN"
            m_turn, m_itm, m_otm = 2.0, 1.0, None
        else:
            return 

        # 2. DATA EXTRACTION
        try:
            if "💎 BANKNIFTY" not in text:
                return
                
            bn_section = text.split("💎 BANKNIFTY")[1].split("💎")[0]
            options_part = bn_section.split("---- FUTURES FLOW ----")[0]
            
            call_itm, call_otm = get_writing_values("CALL_WR", options_part)
            put_itm, put_otm = get_writing_values("PUT_WR", options_part)
            bull_t = get_value("Bullish Turn", options_part)
            bear_t = get_value("Bearish Turn", options_part)
            
            # LOG THE READ DATA
            print(f"📊 [{short_lbl} DATA] Bull:{bull_t}Cr | Bear:{bear_t}Cr | PutWR(ITM/OTM):{put_itm}/{put_otm}Cr | CallWR(ITM/OTM):{call_itm}/{call_otm}Cr")

        except Exception as e:
            print(f"⚠️ Extraction Failed: {e}")
            return 

        if short_lbl == "2MIN":
            fut_price = get_future_price(text)
            await maybe_send_option_flow_alert(
                client,
                now,
                fut_price,
                bull_t,
                bear_t,
                put_itm,
                put_otm,
                call_itm,
                call_otm,
            )

        # 3. SIGNAL LOGIC
        sig_type = None
        if bull_t >= m_turn and put_itm >= m_itm and bear_t < 1.0:
            sig_type = "CALL"
        elif bear_t >= m_turn and call_itm >= m_itm and bull_t < 1.0:
            sig_type = "PUT"

        if sig_type:
            last_signals[lbl] = {"type": sig_type, "time": now}
            print(f"⚡ {short_lbl} {sig_type} SIGNAL DETECTED. Waiting for Dual Match (30s)...")

            # 4. 30-SECOND DUAL MATCH CHECK
            other_lbl = "5 MIN FLOW" if short_lbl == "2MIN" else "2 MIN FLOW"
            other = last_signals.get(other_lbl)

            if other["type"] == sig_type:
                time_diff = (now - other["time"]).total_seconds()
                
                if abs(time_diff) <= 30:
                    fut_price = get_future_price(text)
                    atm_strike = get_atm(fut_price) if fut_price else "ATM"
                    suffix = "CE" if sig_type == "CALL" else "PE"
                    emoji = "🟢" if sig_type == "CALL" else "🔴"
                    flow_line = (
                        f"**BULLISH TURN: {bull_t:.2f}Cr | ITM PUT: {put_itm:.2f}Cr**"
                        if sig_type == "CALL"
                        else f"**BEARISH TURN: {bear_t:.2f}Cr | ITM CALL: {call_itm:.2f}Cr**"
                    )
                    
                    print(f"✅ SUCCESS: Dual Match confirmed in {abs(time_diff):.1f}s. Sending Alert.")
                    
                    msg = (
                        f"{emoji} **INSTITUTIONAL DUAL MATCH** {emoji}\n\n"
                        f"**ACTION: BUY BANKNIFTY {atm_strike} {suffix}**\n"
                        f"**SIGNAL: {sig_type} (Matched in {abs(time_diff):.1f}s)**\n"
                        f"{flow_line}\n\n"
                        f"🛡️ **SL: 30 pts**\n"
                        f"🎯 **TARGET: 60 pts**"
                    )
                    await safe_send(client, TARGET_BOT_ID, msg)
                    
                    # Reset
                    last_signals["2 MIN FLOW"]["type"] = None
                    last_signals["5 MIN FLOW"]["type"] = None
                else:
                    print(f"⏳ Match found but time difference too high: {abs(time_diff):.1f}s")

        # 5. Additional logic for other symbols (non-BANKNIFTY only)
        # - Keep legacy BANKNIFTY logic unchanged above.
        # - For other symbols, add:
        #   a) Instant 2MIN alert if ITM writer >= 10Cr (no 5MIN confirmation)
        #   b) Additional dual-match thresholds (2MIN+5MIN within 30s) as requested
        if short_lbl == "2MIN":
            for symbol in [s for s in WATCH_SYMBOLS if s != "BANKNIFTY"]:
                section = extract_instrument_section(text, symbol)
                metrics = parse_flow_metrics(section)
                if not metrics:
                    continue

                if symbol not in last_signals_by_symbol:
                    last_signals_by_symbol[symbol] = {
                        "2 MIN FLOW": {"type": None, "time": datetime.datetime.min},
                        "5 MIN FLOW": {"type": None, "time": datetime.datetime.min},
                    }

                fut_price = get_future_price(text, symbol=symbol)
                atm_strike = get_atm(fut_price) if fut_price else "ATM"

                # (a) Instant 2MIN ITM writer >= 10Cr
                if metrics["put_itm"] >= 10.0:
                    alert_key = f"{symbol}_CALL_{now.strftime('%Y-%m-%d_%H:%M')}"
                    if instant_itm_alerts.get(alert_key) is not None:
                        continue
                    instant_itm_alerts[alert_key] = now
                    msg = (
                        f"🟢 **INSTITUTIONAL DUAL MATCH** 🟢\n\n"
                        f"**ACTION: BUY {symbol} {atm_strike} CE**\n"
                        f"**SIGNAL: CALL (2MIN ITM WRITER >= 10Cr)**\n"
                        f"**BULLISH TURN: {metrics['bull_t']:.2f}Cr | ITM PUT: {metrics['put_itm']:.2f}Cr**\n\n"
                        f"🛡️ **SL: 30 pts**\n"
                        f"🎯 **TARGET: 60 pts**"
                    )
                    await safe_send(client, TARGET_BOT_ID, msg)
                    continue

                if metrics["call_itm"] >= 10.0:
                    alert_key = f"{symbol}_PUT_{now.strftime('%Y-%m-%d_%H:%M')}"
                    if instant_itm_alerts.get(alert_key) is not None:
                        continue
                    instant_itm_alerts[alert_key] = now
                    msg = (
                        f"🔴 **INSTITUTIONAL DUAL MATCH** 🔴\n\n"
                        f"**ACTION: BUY {symbol} {atm_strike} PE**\n"
                        f"**SIGNAL: PUT (2MIN ITM WRITER >= 10Cr)**\n"
                        f"**BEARISH TURN: {metrics['bear_t']:.2f}Cr | ITM CALL: {metrics['call_itm']:.2f}Cr**\n\n"
                        f"🛡️ **SL: 30 pts**\n"
                        f"🎯 **TARGET: 60 pts**"
                    )
                    await safe_send(client, TARGET_BOT_ID, msg)
                    continue

                # (b) Additional dual-match thresholds (NON-BANKNIFTY)
                # 2MIN: turnover >= 6Cr, ITM writer >= 3.5Cr, opposite turnover < 1Cr
                # 5MIN: turnover >= 1Cr, ITM writer < 1Cr, opposite turnover < 1Cr
                sig2 = None
                if metrics["bull_t"] >= 6.0 and metrics["put_itm"] >= 3.5 and metrics["bear_t"] < 1.0:
                    sig2 = "CALL"
                elif metrics["bear_t"] >= 6.0 and metrics["call_itm"] >= 3.5 and metrics["bull_t"] < 1.0:
                    sig2 = "PUT"
                if not sig2:
                    continue

                last_signals_by_symbol[symbol][lbl] = {"type": sig2, "time": now}
                other_lbl = "5 MIN FLOW" if short_lbl == "2MIN" else "2 MIN FLOW"
                other = last_signals_by_symbol[symbol].get(other_lbl)

                if other and other["type"] == sig2:
                    time_diff = (now - other["time"]).total_seconds()
                    if abs(time_diff) <= 30:
                        suffix = "CE" if sig2 == "CALL" else "PE"
                        emoji = "🟢" if sig2 == "CALL" else "🔴"
                        flow_line = (
                            f"**BULLISH TURN: {metrics['bull_t']:.2f}Cr | ITM PUT: {metrics['put_itm']:.2f}Cr**"
                            if sig2 == "CALL"
                            else f"**BEARISH TURN: {metrics['bear_t']:.2f}Cr | ITM CALL: {metrics['call_itm']:.2f}Cr**"
                        )
                        msg = (
                            f"{emoji} **INSTITUTIONAL DUAL MATCH** {emoji}\n\n"
                            f"**ACTION: BUY {symbol} {atm_strike} {suffix}**\n"
                            f"**SIGNAL: {sig2} (Matched in {abs(time_diff):.1f}s)**\n"
                            f"{flow_line}\n\n"
                            f"🛡️ **SL: 30 pts**\n"
                            f"🎯 **TARGET: 60 pts**"
                        )
                        await safe_send(client, TARGET_BOT_ID, msg)

        # Store 5MIN side for the additional (NON-BANKNIFTY) dual-match rules.
        if short_lbl == "5MIN":
            for symbol in [s for s in WATCH_SYMBOLS if s != "BANKNIFTY"]:
                section = extract_instrument_section(text, symbol)
                metrics = parse_flow_metrics(section)
                if not metrics:
                    continue

                if symbol not in last_signals_by_symbol:
                    last_signals_by_symbol[symbol] = {
                        "2 MIN FLOW": {"type": None, "time": datetime.datetime.min},
                        "5 MIN FLOW": {"type": None, "time": datetime.datetime.min},
                    }

                # 5MIN thresholds (as requested):
                # - turnover >= 1Cr
                # - ITM writer < 1Cr
                # - opposite turnover < 1Cr
                sig5 = None
                if metrics["bull_t"] >= 1.0 and metrics["put_itm"] < 1.0 and metrics["bear_t"] < 1.0:
                    sig5 = "CALL"
                elif metrics["bear_t"] >= 1.0 and metrics["call_itm"] < 1.0 and metrics["bull_t"] < 1.0:
                    sig5 = "PUT"

                if sig5:
                    last_signals_by_symbol[symbol]["5 MIN FLOW"] = {"type": sig5, "time": now}

    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
