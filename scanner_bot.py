import os
import re
import asyncio
import datetime
import pytz
import json
import uuid
import requests
from telethon import TelegramClient, events
from telethon.sessions import StringSession

# ---------------- CONFIG ---------------- #
def required_env(name):
    value = os.getenv(name)
    if value is None or not str(value).strip():
        raise RuntimeError(f"Missing required environment variable: {name}")
    return str(value).strip()


def required_env_int(name):
    value = required_env(name)
    try:
        return int(value)
    except ValueError as e:
        raise RuntimeError(f"Environment variable {name} must be an integer") from e


def parse_source_ids(value):
    raw = required_env(value)
    ids = [int(i.strip()) for i in raw.split(",") if i.strip()]
    if not ids:
        raise RuntimeError("SOURCE_BOT must contain at least one Telegram source id")
    return ids


API_ID = required_env_int("TG_API_ID")
API_HASH = required_env("TG_API_HASH")
SESSION_STR = required_env("TG_SESSION_STR")

SOURCE_IDS = parse_source_ids("SOURCE_BOT")
TARGET_BOT_RAW = os.getenv("TARGET_BOT", "").strip()

# Matrix / Element X Credentials
MATRIX_HOMESERVER = os.getenv("MATRIX_HOMESERVER", "https://matrix.org")
MATRIX_ACCESS_TOKEN = os.getenv("MATRIX_ACCESS_TOKEN", "")
MATRIX_USER = os.getenv("MATRIX_USER", "")
MATRIX_PASS = os.getenv("MATRIX_PASS", "")
MATRIX_TOKEN_FILE = "matrix_access_token.txt"
# Check for both standard name and your custom name 'banknifty-deshboard'
MATRIX_ROOM_ID = os.getenv("banknifty-deshboard") or os.getenv("MATRIX_ROOM_ID", "")

IST = pytz.timezone("Asia/Kolkata")

def env_bool(name, default="false"):
    return str(os.getenv(name, default)).strip().lower() in ("1", "true", "yes", "on")

# ---------------- INSTRUMENT SPECS ---------------- #
INDEX_SYMBOLS = ["BANKNIFTY", "NIFTY", "SENSEX", "MIDCPNIFTY"]
STOCK_SYMBOLS = ["HDFCBANK", "ICICIBANK", "RELIANCE"]
WATCH_SYMBOLS = INDEX_SYMBOLS + STOCK_SYMBOLS

# Updated Strike Steps based on your requirements
STRIKE_STEPS = {
    "BANKNIFTY": int(os.getenv("BANKNIFTY_STRIKE_STEP", "100")),
    "NIFTY": int(os.getenv("NIFTY_STRIKE_STEP", "50")),
    "SENSEX": int(os.getenv("SENSEX_STRIKE_STEP", "100")),
    "MIDCPNIFTY": int(os.getenv("MIDCPNIFTY_STRIKE_STEP", "25")),
    "HDFCBANK": 5,   # Updated to 5
    "ICICIBANK": 10, # Updated to 10
    "RELIANCE": 10,  # Updated to 10
}

FUT_LOT_THRESHOLD = int(os.getenv("FUT_LOT_THRESHOLD", "3000"))
ITM_WRITER_THRESHOLD_CR = float(os.getenv("ITM_WRITER_THRESHOLD_CR", "11"))
ITM_SC_THRESHOLD_CR = float(os.getenv("ITM_SC_THRESHOLD_CR", "20"))
ITM_WRITER_CONFLICT_CR = float(os.getenv("ITM_WRITER_CONFLICT_CR", "10"))
ENABLE_MATCHED_IN_ALERTS = env_bool("ENABLE_MATCHED_IN_ALERTS", "true")
ENABLE_2MIN_5MIN_DUAL_MATCH_ALERTS = env_bool(
    "ENABLE_2MIN_5MIN_DUAL_MATCH_ALERTS",
    "true",
)
DUAL_MATCH_WINDOW_SECONDS = int(os.getenv("DUAL_MATCH_WINDOW_SECONDS", "60"))
OTM_DUAL_2MIN_TURN_CR = float(os.getenv("OTM_DUAL_2MIN_TURN_CR", "15"))
OTM_DUAL_2MIN_COMPONENT_CR = float(os.getenv("OTM_DUAL_2MIN_COMPONENT_CR", "10"))
OTM_DUAL_5MIN_TURN_CR = float(os.getenv("OTM_DUAL_5MIN_TURN_CR", "2"))
OTM_DUAL_5MIN_COMPONENT_CR = float(os.getenv("OTM_DUAL_5MIN_COMPONENT_CR", "1"))
ENABLE_2MIN_5MIN_OTM_DUAL_MATCH_ALERTS = env_bool(
    "ENABLE_2MIN_5MIN_OTM_DUAL_MATCH_ALERTS",
    "true",
)

# State Tracking
last_index_signals = {}
last_fut_signals = {}
last_signals_by_symbol = {}
last_otm_signals_by_symbol = {}
instant_itm_alerts = {}

# ---------------- UTILITY FUNCTIONS ---------------- #

def parse_target_ref(value):
    if not value:
        raise RuntimeError("TARGET_BOT env var is not set")
    value = value.strip()
    value = re.sub(r"^https?://t\.me/", "", value, flags=re.IGNORECASE).strip("/")
    return int(value) if re.fullmatch(r"-?\d+", value) else value

TARGET_BOT_REF = parse_target_ref(TARGET_BOT_RAW)

def _entity_key(value):
    return re.sub(r"[\s_@]+", "", str(value or "").lower())

async def resolve_target_entity(client, target_ref):
    candidates = [target_ref]
    if isinstance(target_ref, str) and not target_ref.startswith("@"):
        candidates.append(f"@{target_ref}")

    last_error = None
    for candidate in candidates:
        try:
            return await client.get_entity(candidate)
        except Exception as e:
            last_error = e

    target_key = _entity_key(target_ref)
    async for dialog in client.iter_dialogs():
        entity = dialog.entity
        entity_id = str(getattr(entity, "id", ""))
        full_channel_id = f"-100{entity_id}" if entity_id and not entity_id.startswith("-") else entity_id
        values = [
            getattr(entity, "username", None),
            getattr(entity, "title", None),
            getattr(entity, "first_name", None),
            dialog.name,
            entity_id,
            full_channel_id,
        ]
        if any(_entity_key(value) == target_key for value in values):
            return entity

    raise RuntimeError(f"Could not resolve TARGET_BOT={target_ref!r}. Last error: {last_error}")

def get_atm(price, symbol):
    """Uses standard rounding to the nearest strike step for accuracy."""
    step = STRIKE_STEPS.get(symbol.upper(), 100)
    return int(round(float(price) / step) * step)

def risk_points_for(symbol):
    """Returns (SL, Target) based on instrument type."""
    return (3, 6) if symbol.upper() in STOCK_SYMBOLS else (30, 60)

def get_dual_match_thresholds(symbol, short_lbl, now):
    if symbol == "BANKNIFTY" and 1 <= now.day <= 10:
        return (5.0, 5.0) if short_lbl == "2MIN" else (1.0, 1.0)
    return (10.0, 6.5) if short_lbl == "2MIN" else (2.0, 1.0)

def _normalize_cr(value, unit):
    try:
        val = float(value)
        return val if unit == "Cr" else (val / 100 if unit == "L" else 0.0)
    except: return 0.0

def get_writing_values(label, text):
    pattern = rf"{label}\s+\d+\(([\d.]+)(Cr|L|)\)\s+\d+\(([\d.]+)(Cr|L|)\)"
    matches = re.findall(pattern, text, re.IGNORECASE)
    if not matches: return 0.0, 0.0
    itm_val, itm_unit, otm_val, otm_unit = matches[0]
    return _normalize_cr(itm_val, itm_unit), _normalize_cr(otm_val, otm_unit)

def get_value(label, text):
    pattern = rf"{label}\s*:\s*([\d.]+)(Cr|L|)"
    matches = re.findall(pattern, text, re.IGNORECASE)
    if not matches: return 0.0
    val_str, unit = matches[-1]
    return _normalize_cr(val_str, unit)

def get_future_price(text, symbol):
    if not text:
        return None
    pattern = rf"(?<![A-Z0-9_]){re.escape(symbol)}\s*\(FUT:\s*([\d.]+)\)"
    match = re.search(pattern, text, re.IGNORECASE)
    return float(match.group(1)) if match else None

def extract_instrument_section(text, symbol):
    sym_pat = rf"(?<![A-Z0-9_]){re.escape(symbol)}\s*\(FUT:"
    m = re.search(sym_pat, text, re.IGNORECASE)
    if not m: return None
    start = m.start()
    next_pos = [len(text)]
    for sym in WATCH_SYMBOLS:
        if sym == symbol: continue
        m2 = re.search(rf"(?<![A-Z0-9_]){re.escape(sym)}\s*\(FUT:", text[m.end():], re.IGNORECASE)
        if m2: next_pos.append(m.end() + m2.start())
    return text[start:min(next_pos)]

def parse_flow_metrics(section):
    if not section: return None
    opt_part = section.split("---- FUTURES FLOW ----")[0]
    c_itm, c_otm = get_writing_values("CALL_WR", opt_part)
    p_itm, p_otm = get_writing_values("PUT_WR", opt_part)
    cs_itm, cs_otm = get_writing_values("CALL_SC", opt_part)
    ps_itm, ps_otm = get_writing_values("PUT_SC", opt_part)
    return {
        "bull_t": get_value("Bullish Turn", opt_part),
        "bear_t": get_value("Bearish Turn", opt_part),
        "call_itm": c_itm, "call_otm": c_otm,
        "put_itm": p_itm, "put_otm": p_otm,
        "call_sc_itm": cs_itm, "call_sc_otm": cs_otm,
        "put_sc_itm": ps_itm, "put_sc_otm": ps_otm
    }

def get_otm_dual_signal(metrics, short_lbl):
    if short_lbl == "2MIN":
        turn_min = OTM_DUAL_2MIN_TURN_CR
        component_min = OTM_DUAL_2MIN_COMPONENT_CR
    else:
        turn_min = OTM_DUAL_5MIN_TURN_CR
        component_min = OTM_DUAL_5MIN_COMPONENT_CR

    bullish_components = [
        ("PUT_WR OTM", metrics["put_otm"]),
        ("CALL_SC OTM", metrics["call_sc_otm"]),
    ]
    bearish_components = [
        ("CALL_WR OTM", metrics["call_otm"]),
        ("PUT_SC OTM", metrics["put_sc_otm"]),
    ]
    bull_label, bull_component = max(bullish_components, key=lambda item: item[1])
    bear_label, bear_component = max(bearish_components, key=lambda item: item[1])

    call_ok = metrics["bull_t"] >= turn_min and bull_component >= component_min
    put_ok = metrics["bear_t"] >= turn_min and bear_component >= component_min

    if call_ok and not put_ok:
        return {
            "type": "CALL",
            "turn": metrics["bull_t"],
            "component_label": bull_label,
            "component_value": bull_component,
            "turn_min": turn_min,
            "component_min": component_min,
        }
    if put_ok and not call_ok:
        return {
            "type": "PUT",
            "turn": metrics["bear_t"],
            "component_label": bear_label,
            "component_value": bear_component,
            "turn_min": turn_min,
            "component_min": component_min,
        }
    return None

# ---------------- MATRIX UTILS ---------------- #

def perform_matrix_login():
    if not MATRIX_USER or not MATRIX_PASS:
        return None
    
    login_url = f"{MATRIX_HOMESERVER}/_matrix/client/v3/login"
    payload = {
        "type": "m.login.password",
        "user": MATRIX_USER,
        "password": MATRIX_PASS,
        "initial_device_display_name": "BankNiftyDashboardAuto"
    }
    
    try:
        response = requests.post(login_url, json=payload, timeout=15)
        if response.status_code == 200:
            token = response.json().get("access_token")
            if token:
                with open(MATRIX_TOKEN_FILE, "w") as f:
                    f.write(token)
                print("✅ Matrix auto-login successful.")
                return token
        else:
            print(f"❌ Matrix auto-login failed: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"❌ Matrix auto-login error: {e}")
    return None

def get_matrix_token():
    # 1. Try to read from file first
    token = None
    if os.path.exists(MATRIX_TOKEN_FILE):
        try:
            with open(MATRIX_TOKEN_FILE, "r") as f:
                token = f.read().strip()
        except Exception as e:
            print(f"❌ Error reading {MATRIX_TOKEN_FILE}: {e}")
    
    # 2. Fallback to environment variable
    if not token:
        token = MATRIX_ACCESS_TOKEN
        
    # 3. Auto-login if still no token
    if not token:
        token = perform_matrix_login()
        
    return token

async def safe_send(client, target_id, message):
    # Send to Telegram
    try:
        await client.send_message(target_id, message)
    except Exception as e:
        print(f"❌ Telegram Delivery Error: {e}")

    # Send to Matrix / Element X
    token = get_matrix_token()
    if token and MATRIX_ROOM_ID:
        try:
            txn_id = str(uuid.uuid4())
            url = f"{MATRIX_HOMESERVER}/_matrix/client/v3/rooms/{MATRIX_ROOM_ID}/send/m.room.message/{txn_id}"
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            payload = {
                "msgtype": "m.text",
                "body": message
            }
            
            def do_request(h):
                return requests.put(url, headers=h, data=json.dumps(payload), timeout=10)

            # Run in executor since requests is blocking
            loop = asyncio.get_event_loop()
            res = await loop.run_in_executor(None, lambda: do_request(headers))

            if res.status_code == 401:
                print("⚠️ Matrix token expired. Attempting auto-login...")
                new_token = perform_matrix_login()
                if new_token:
                    headers["Authorization"] = f"Bearer {new_token}"
                    res = await loop.run_in_executor(None, lambda: do_request(headers))

            if res.status_code != 200:
                print(f"❌ Matrix Delivery Error: {res.status_code} - {res.text}")
        except Exception as e:
            print(f"❌ Matrix Exception: {e}")

# ---------------- MAIN HANDLER ---------------- #

async def main():
    client = TelegramClient(StringSession(SESSION_STR), API_ID, API_HASH)
    await client.start()
    try:
        target_entity = await resolve_target_entity(client, TARGET_BOT_REF)
        print(f"✅ TARGET_BOT resolved: {getattr(target_entity, 'id', TARGET_BOT_REF)}", flush=True)
    except Exception as e:
        target_entity = TARGET_BOT_REF
        print(f"❌ TARGET_BOT resolve failed: {e}", flush=True)
        print("Set TARGET_BOT to the exact @username, t.me link, numeric -100 channel ID, or exact dialog name visible to this Telegram account.", flush=True)
    print("🚀 SCANNER ACTIVE: Corrected Strike Steps for HDFCBANK (5), ICICI/RELIANCE (10)")

    @client.on(events.NewMessage(chats=SOURCE_IDS))
    async def handler(event):
        text = event.message.text
        if not text: return
        now = datetime.datetime.now(IST)
        
        if "2 MIN" in text.upper(): lbl, short_lbl = "2 MIN FLOW", "2MIN"
        elif "5 MIN" in text.upper(): lbl, short_lbl = "5 MIN FLOW", "5MIN"
        else: return

        # 1. FUTURES LOT MATCH (2MIN only, no 5MIN confirmation)
        for symbol in WATCH_SYMBOLS:
            if short_lbl != "2MIN":
                continue
            section = extract_instrument_section(text, symbol)
            m = re.search(r"(FUT_BUY|FUT_SELL)\s*:\s*(\d+)\s+lots", section or "", re.IGNORECASE)
            if m and int(m.group(2)) >= FUT_LOT_THRESHOLD:
                sig_fut = "CALL" if m.group(1).upper() == "FUT_BUY" else "PUT"
                price = get_future_price(section, symbol)
                strike = get_atm(price, symbol) if price else "ATM"
                sl, tg = risk_points_for(symbol)
                emoji = "🟢" if sig_fut == "CALL" else "🔴"
                msg = (f"{emoji} **INSTITUTIONAL DUAL MATCH** {emoji}\n\n"
                       f"**ACTION: BUY {symbol} {strike} {'CE' if sig_fut == 'CALL' else 'PE'}**\n"
                       f"**SIGNAL: {sig_fut} (2MIN FUT lots >= {FUT_LOT_THRESHOLD})**\n"
                       f"🛡️ **SL: {sl} pts | 🎯 TARGET: {tg} pts**")
                await safe_send(client, target_entity, msg)

        # 2. FLOW & DUAL MATCH (All Symbols)
        for symbol in WATCH_SYMBOLS:
            section = extract_instrument_section(text, symbol)
            metrics = parse_flow_metrics(section)
            if not metrics: continue
            
            price = get_future_price(section, symbol)
            strike = get_atm(price, symbol) if price else "ATM"
            sl, tg = risk_points_for(symbol)

            # Instant ITM writer alert (2MIN only)
            if short_lbl == "2MIN":
                bullish_triggers = []
                bearish_triggers = []
                if metrics["put_itm"] >= ITM_WRITER_THRESHOLD_CR:
                    bullish_triggers.append(("PUT_WR", metrics["put_itm"], ITM_WRITER_THRESHOLD_CR))
                if metrics["call_sc_itm"] >= ITM_SC_THRESHOLD_CR:
                    bullish_triggers.append(("CALL_SC", metrics["call_sc_itm"], ITM_SC_THRESHOLD_CR))
                if metrics["call_itm"] >= ITM_WRITER_THRESHOLD_CR:
                    bearish_triggers.append(("CALL_WR", metrics["call_itm"], ITM_WRITER_THRESHOLD_CR))
                if metrics["put_sc_itm"] >= ITM_SC_THRESHOLD_CR:
                    bearish_triggers.append(("PUT_SC", metrics["put_sc_itm"], ITM_SC_THRESHOLD_CR))

                alert_side = None
                trigger_label = None
                trigger_value = 0.0
                trigger_threshold = ITM_WRITER_THRESHOLD_CR
                conflict = (
                    bool(bullish_triggers)
                    and bool(bearish_triggers)
                )
                if not conflict:
                    if bullish_triggers:
                        trigger_label, trigger_value, trigger_threshold = max(bullish_triggers, key=lambda item: item[1])
                        alert_side = "CALL"
                    elif bearish_triggers:
                        trigger_label, trigger_value, trigger_threshold = max(bearish_triggers, key=lambda item: item[1])
                        alert_side = "PUT"

                if alert_side:
                    akey = f"{symbol}_{alert_side}_{trigger_label}_{now.strftime('%H:%M')}"
                    if akey not in instant_itm_alerts:
                        instant_itm_alerts[akey] = now
                        emoji = "🟢" if alert_side == "CALL" else "🔴"
                        msg = (f"{emoji} **INSTITUTIONAL DUAL MATCH** {emoji}\n\n"
                               f"**ACTION: BUY {symbol} {strike} {'CE' if alert_side == 'CALL' else 'PE'}**\n"
                               f"**SIGNAL: {alert_side} (2MIN ITM {trigger_label} {trigger_value:.2f}Cr >= {trigger_threshold:g}Cr)**\n"
                               f"🛡️ **SL: {sl} pts | 🎯 TARGET: {tg} pts**")
                        await safe_send(client, target_entity, msg)

            # Dual Match logic
            sig_type = None
            if symbol in ("BANKNIFTY", "NIFTY"):
                m_turn, m_itm = get_dual_match_thresholds(symbol, short_lbl, now)
                if metrics["bull_t"] >= m_turn and metrics["put_itm"] >= m_itm and metrics["bear_t"] < 1.0: sig_type = "CALL"
                elif metrics["bear_t"] >= m_turn and metrics["call_itm"] >= m_itm and metrics["bull_t"] < 1.0: sig_type = "PUT"
            else:
                # Other Symbols
                if short_lbl == "2MIN":
                    if metrics["bull_t"] >= 6.0 and metrics["put_itm"] >= 3.5 and metrics["bear_t"] < 1.0: sig_type = "CALL"
                    elif metrics["bear_t"] >= 6.0 and metrics["call_itm"] >= 3.5 and metrics["bull_t"] < 1.0: sig_type = "PUT"
                else: # 5MIN
                    if metrics["bull_t"] >= 1.0 and metrics["put_itm"] < 1.0 and metrics["bear_t"] < 1.0: sig_type = "CALL"
                    elif metrics["bear_t"] >= 1.0 and metrics["call_itm"] < 1.0 and metrics["bull_t"] < 1.0: sig_type = "PUT"

            if sig_type:
                if symbol not in last_signals_by_symbol:
                    last_signals_by_symbol[symbol] = {"2 MIN FLOW": None, "5 MIN FLOW": None}
                last_signals_by_symbol[symbol][lbl] = {"type": sig_type, "time": now}
                
                other_lbl = "5 MIN FLOW" if short_lbl == "2MIN" else "2 MIN FLOW"
                other = last_signals_by_symbol[symbol].get(other_lbl)
                if other and other["type"] == sig_type and abs((now - other["time"]).total_seconds()) <= DUAL_MATCH_WINDOW_SECONDS:
                    if ENABLE_2MIN_5MIN_DUAL_MATCH_ALERTS and ENABLE_MATCHED_IN_ALERTS:
                        emoji = "🟢" if sig_type == "CALL" else "🔴"
                        msg = (f"{emoji} **INSTITUTIONAL DUAL MATCH** {emoji}\n\n"
                               f"**ACTION: BUY {symbol} {strike} {'CE' if sig_type == 'CALL' else 'PE'}**\n"
                               f"**SIGNAL: {sig_type} (Matched in {abs((now-other['time']).total_seconds()):.1f}s)**\n"
                               f"🛡️ **SL: {sl} pts | 🎯 TARGET: {tg} pts**")
                        await safe_send(client, target_entity, msg)
                    last_signals_by_symbol[symbol] = {"2 MIN FLOW": None, "5 MIN FLOW": None}

            # OTM Dual Match logic for BANKNIFTY/NIFTY
            if symbol in ("BANKNIFTY", "NIFTY"):
                otm_sig = get_otm_dual_signal(metrics, short_lbl)
                if otm_sig:
                    if symbol not in last_otm_signals_by_symbol:
                        last_otm_signals_by_symbol[symbol] = {"2 MIN FLOW": None, "5 MIN FLOW": None}
                    last_otm_signals_by_symbol[symbol][lbl] = {"type": otm_sig["type"], "time": now, "signal": otm_sig}

                    other_lbl = "5 MIN FLOW" if short_lbl == "2MIN" else "2 MIN FLOW"
                    other = last_otm_signals_by_symbol[symbol].get(other_lbl)
                    match_seconds = abs((now - other["time"]).total_seconds()) if other else None
                    if other and other["type"] == otm_sig["type"] and match_seconds <= DUAL_MATCH_WINDOW_SECONDS:
                        if ENABLE_2MIN_5MIN_OTM_DUAL_MATCH_ALERTS and ENABLE_MATCHED_IN_ALERTS:
                            sig_type = otm_sig["type"]
                            emoji = "ðŸŸ¢" if sig_type == "CALL" else "ðŸ”´"
                            msg = (f"{emoji} **INSTITUTIONAL DUAL MATCH** {emoji}\n\n"
                                   f"**ACTION: BUY {symbol} {strike} {'CE' if sig_type == 'CALL' else 'PE'}**\n"
                                   f"**SIGNAL: {sig_type} (OTM Matched in {match_seconds:.1f}s)**\n"
                                   f"2MIN+5MIN OTM: Turn >= {OTM_DUAL_2MIN_TURN_CR:g}/{OTM_DUAL_5MIN_TURN_CR:g}Cr, "
                                   f"OTM writing/SC >= {OTM_DUAL_2MIN_COMPONENT_CR:g}/{OTM_DUAL_5MIN_COMPONENT_CR:g}Cr\n"
                                   f"LAST: {otm_sig['component_label']} {otm_sig['component_value']:.2f}Cr, "
                                   f"Turn {otm_sig['turn']:.2f}Cr\n"
                                   f"ðŸ›¡ï¸ **SL: {sl} pts | ðŸŽ¯ TARGET: {tg} pts**")
                            await safe_send(client, target_entity, msg)
                        last_otm_signals_by_symbol[symbol] = {"2 MIN FLOW": None, "5 MIN FLOW": None}

    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
