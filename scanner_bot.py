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

SOURCE_IDS = [int(i.strip()) for i in os.getenv("SOURCE_BOT").split(",")]
TARGET_BOT_RAW = os.getenv("TARGET_BOT", "").strip()

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
SC_BOTH_SIDE_LEG_THRESHOLD_CR = float(os.getenv("SC_BOTH_SIDE_LEG_THRESHOLD_CR", "10"))
SC_BOTH_SIDE_TOTAL_THRESHOLD_CR = float(os.getenv("SC_BOTH_SIDE_TOTAL_THRESHOLD_CR", "20"))
BANKNIFTY_OTM_WR_2MIN_TURN_CR = float(os.getenv("BANKNIFTY_OTM_WR_2MIN_TURN_CR", "10"))
BANKNIFTY_OTM_WR_2MIN_WRITER_CR = float(os.getenv("BANKNIFTY_OTM_WR_2MIN_WRITER_CR", "10"))
BANKNIFTY_OTM_WR_5MIN_TURN_CR = float(os.getenv("BANKNIFTY_OTM_WR_5MIN_TURN_CR", "2"))
BANKNIFTY_OTM_WR_5MIN_WRITER_CR = float(os.getenv("BANKNIFTY_OTM_WR_5MIN_WRITER_CR", "2"))
REVERSE_CONFIRM_TURN_CR = float(os.getenv("REVERSE_CONFIRM_TURN_CR", "5"))
REVERSE_CONFIRM_OPPOSITE_MAX_CR = float(os.getenv("REVERSE_CONFIRM_OPPOSITE_MAX_CR", "2"))
REVERSE_LATE_START = os.getenv("REVERSE_LATE_START", "14:45")
REVERSE_LATE_CONFIRMATIONS = int(os.getenv("REVERSE_LATE_CONFIRMATIONS", "2"))
REVERSE_VERY_STRONG_TURN_CR = float(os.getenv("REVERSE_VERY_STRONG_TURN_CR", "10"))
REVERSE_VERY_STRONG_OPPOSITE_MAX_CR = float(os.getenv("REVERSE_VERY_STRONG_OPPOSITE_MAX_CR", "1"))
ACTIVE_SIGNAL_MAX_AGE_MIN = int(os.getenv("ACTIVE_SIGNAL_MAX_AGE_MIN", "90"))
ENABLE_MATCHED_IN_ALERTS = env_bool("ENABLE_MATCHED_IN_ALERTS", "true")
ENABLE_2MIN_5MIN_DUAL_MATCH_ALERTS = env_bool(
    "ENABLE_2MIN_5MIN_DUAL_MATCH_ALERTS",
    "true",
)

# State Tracking
last_index_signals = {}
last_fut_signals = {}
last_signals_by_symbol = {}
last_otm_signals_by_symbol = {}
active_signals_by_symbol = {}
pending_reverses_by_symbol = {}
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

def get_bias(label, text):
    pattern = rf"{label}\s*:\s*([^\r\n]+)"
    matches = re.findall(pattern, text, re.IGNORECASE)
    return matches[-1].strip() if matches else ""

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
    parts = section.split("---- FUTURES FLOW ----", 1)
    opt_part = parts[0]
    fut_part = parts[1] if len(parts) > 1 else ""
    c_itm, c_otm = get_writing_values("CALL_WR", opt_part)
    p_itm, p_otm = get_writing_values("PUT_WR", opt_part)
    cs_itm, cs_otm = get_writing_values("CALL_SC", opt_part)
    ps_itm, ps_otm = get_writing_values("PUT_SC", opt_part)
    return {
        "option_bias": get_bias("Option Bias", opt_part),
        "bull_t": get_value("Bullish Turn", opt_part),
        "bear_t": get_value("Bearish Turn", opt_part),
        "future_bias": get_bias("Future Bias", fut_part),
        "future_bull_t": get_value("Bullish Turn", fut_part),
        "future_bear_t": get_value("Bearish Turn", fut_part),
        "call_itm": c_itm, "call_otm": c_otm,
        "put_itm": p_itm, "put_otm": p_otm,
        "call_sc_itm": cs_itm, "call_sc_otm": cs_otm,
        "put_sc_itm": ps_itm, "put_sc_otm": ps_otm
    }

async def safe_send(client, target_id, message):
    try:
        await client.send_message(target_id, message)
    except Exception as e:
        print(f"❌ Delivery Error: {e}")

def option_type_for_side(side):
    return "CE" if side == "CALL" else "PE"

def emoji_for_side(side):
    return "🟢" if side == "CALL" else "🔴"

def hhmm_time(value):
    return datetime.datetime.strptime(value, "%H:%M").time()

def is_late_reverse_window(now):
    return now.time() >= hhmm_time(REVERSE_LATE_START)

def is_strong_option_bias(metrics, side):
    bias = str(metrics.get("option_bias", "")).upper()
    need = "BULLISH" if side == "CALL" else "BEARISH"
    return need in bias and "MILD" not in bias and "STRONG" in bias

def is_strong_opposite_future(metrics, side):
    bias = str(metrics.get("future_bias", "")).upper()
    if not bias or "MILD" in bias:
        return False
    if side == "CALL":
        return "BEARISH" in bias and "STRONG" in bias
    return "BULLISH" in bias and "STRONG" in bias

def reverse_flow_confirmed(metrics, side):
    if not is_strong_option_bias(metrics, side):
        return False
    if is_strong_opposite_future(metrics, side):
        return False
    if side == "CALL":
        return (
            metrics["bull_t"] >= REVERSE_CONFIRM_TURN_CR
            and metrics["bear_t"] <= REVERSE_CONFIRM_OPPOSITE_MAX_CR
        )
    return (
        metrics["bear_t"] >= REVERSE_CONFIRM_TURN_CR
        and metrics["bull_t"] <= REVERSE_CONFIRM_OPPOSITE_MAX_CR
    )

def reverse_flow_very_strong(metrics, side):
    bias = str(metrics.get("option_bias", "")).upper()
    if "VERY STRONG" not in bias:
        return False
    if is_strong_opposite_future(metrics, side):
        return False
    if side == "CALL":
        return (
            metrics["bull_t"] >= REVERSE_VERY_STRONG_TURN_CR
            and metrics["bear_t"] <= REVERSE_VERY_STRONG_OPPOSITE_MAX_CR
        )
    return (
        metrics["bear_t"] >= REVERSE_VERY_STRONG_TURN_CR
        and metrics["bull_t"] <= REVERSE_VERY_STRONG_OPPOSITE_MAX_CR
    )

def build_buy_alert(symbol, strike, side, reason, sl, tg):
    emoji = emoji_for_side(side)
    return (
        f"{emoji} **INSTITUTIONAL DUAL MATCH** {emoji}\n\n"
        f"**ACTION: BUY {symbol} {strike} {option_type_for_side(side)}**\n"
        f"**SIGNAL: {side} ({reason})**\n"
        f"🛡️ **SL: {sl} pts | 🎯 TARGET: {tg} pts**"
    )

def active_signal_for(symbol, now):
    active = active_signals_by_symbol.get(symbol)
    if not active:
        return None
    if now - active["time"] > datetime.timedelta(minutes=ACTIVE_SIGNAL_MAX_AGE_MIN):
        active_signals_by_symbol.pop(symbol, None)
        return None
    return active

async def handle_candidate_signal(client, target_id, symbol, strike, side, reason, sl, tg, now, created_pending_symbols, reverse_confirmed=False):
    if not reverse_confirmed and symbol in pending_reverses_by_symbol:
        return False

    active = active_signal_for(symbol, now)
    if not reverse_confirmed and active and active["side"] != side:
        pending_reverses_by_symbol[symbol] = {
            "side": side,
            "strike": strike,
            "reason": reason,
            "sl": sl,
            "tg": tg,
            "time": now,
            "confirmations": 0,
        }
        created_pending_symbols.add(symbol)
        active_signals_by_symbol.pop(symbol, None)

        msg = (
            "⚠️ **REVERSE EXIT ONLY**\n\n"
            f"**ACTION: EXIT {symbol}**\n"
            f"OLD: {symbol} {active['strike']} {option_type_for_side(active['side'])}\n"
            f"PENDING: BUY {symbol} {strike} {option_type_for_side(side)}\n"
            "WAIT: NEXT 2MIN CONFIRMATION"
        )
        await safe_send(client, target_id, msg)
        return False

    await safe_send(
        client,
        target_id,
        build_buy_alert(symbol, strike, side, reason, sl, tg),
    )
    active_signals_by_symbol[symbol] = {
        "side": side,
        "strike": strike,
        "time": now,
        "reverse": reverse_confirmed,
    }
    return True

async def process_pending_reverse(client, target_id, symbol, metrics, now, created_pending_symbols):
    if symbol in created_pending_symbols:
        return

    pending = pending_reverses_by_symbol.get(symbol)
    if not pending:
        return

    side = pending["side"]
    confirmed = reverse_flow_confirmed(metrics, side)
    very_strong = reverse_flow_very_strong(metrics, side)

    if not confirmed:
        msg = (
            "🚫 **REVERSE CANCELLED**\n\n"
            f"PENDING: BUY {symbol} {pending['strike']} {option_type_for_side(side)}\n"
            "REASON: NEXT 2MIN FLOW NOT CONFIRMED"
        )
        await safe_send(client, target_id, msg)
        pending_reverses_by_symbol.pop(symbol, None)
        return

    if is_late_reverse_window(now) and not very_strong:
        pending["confirmations"] += 1
        if pending["confirmations"] < REVERSE_LATE_CONFIRMATIONS:
            return
        reason = f"REVERSE CONFIRMED {REVERSE_LATE_CONFIRMATIONS}X AFTER {REVERSE_LATE_START}"
    else:
        reason = "REVERSE CONFIRMED NEXT 2MIN"

    pending_reverses_by_symbol.pop(symbol, None)
    await handle_candidate_signal(
        client,
        target_id,
        symbol,
        pending["strike"],
        side,
        reason,
        pending["sl"],
        pending["tg"],
        now,
        created_pending_symbols,
        reverse_confirmed=True,
    )

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

        created_pending_symbols = set()

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
                await handle_candidate_signal(
                    client,
                    target_entity,
                    symbol,
                    strike,
                    sig_fut,
                    f"2MIN FUT lots >= {FUT_LOT_THRESHOLD}",
                    sl,
                    tg,
                    now,
                    created_pending_symbols,
                )

        # 2. FLOW & DUAL MATCH (All Symbols)
        for symbol in WATCH_SYMBOLS:
            section = extract_instrument_section(text, symbol)
            metrics = parse_flow_metrics(section)
            if not metrics: continue

            if short_lbl == "2MIN":
                await process_pending_reverse(
                    client,
                    target_entity,
                    symbol,
                    metrics,
                    now,
                    created_pending_symbols,
                )
            
            price = get_future_price(section, symbol)
            strike = get_atm(price, symbol) if price else "ATM"
            sl, tg = risk_points_for(symbol)

            # Instant ITM writer alert (2MIN only)
            if short_lbl == "2MIN":
                bullish_triggers = []
                bearish_triggers = []
                if metrics["put_itm"] >= ITM_WRITER_THRESHOLD_CR:
                    bullish_triggers.append((
                        "PUT_WR",
                        metrics["put_itm"],
                        ITM_WRITER_THRESHOLD_CR,
                        f"2MIN ITM PUT_WR {metrics['put_itm']:.2f}Cr >= {ITM_WRITER_THRESHOLD_CR:g}Cr",
                    ))
                if metrics["call_sc_itm"] >= ITM_SC_THRESHOLD_CR:
                    bullish_triggers.append((
                        "CALL_SC",
                        metrics["call_sc_itm"],
                        ITM_SC_THRESHOLD_CR,
                        f"2MIN ITM CALL_SC {metrics['call_sc_itm']:.2f}Cr >= {ITM_SC_THRESHOLD_CR:g}Cr",
                    ))
                if metrics["call_itm"] >= ITM_WRITER_THRESHOLD_CR:
                    bearish_triggers.append((
                        "CALL_WR",
                        metrics["call_itm"],
                        ITM_WRITER_THRESHOLD_CR,
                        f"2MIN ITM CALL_WR {metrics['call_itm']:.2f}Cr >= {ITM_WRITER_THRESHOLD_CR:g}Cr",
                    ))
                if metrics["put_sc_itm"] >= ITM_SC_THRESHOLD_CR:
                    bearish_triggers.append((
                        "PUT_SC",
                        metrics["put_sc_itm"],
                        ITM_SC_THRESHOLD_CR,
                        f"2MIN ITM PUT_SC {metrics['put_sc_itm']:.2f}Cr >= {ITM_SC_THRESHOLD_CR:g}Cr",
                    ))

                call_sc_total = metrics["call_sc_itm"] + metrics["call_sc_otm"]
                put_sc_total = metrics["put_sc_itm"] + metrics["put_sc_otm"]

                if (
                    metrics["call_sc_itm"] >= SC_BOTH_SIDE_LEG_THRESHOLD_CR
                    and metrics["call_sc_otm"] >= SC_BOTH_SIDE_LEG_THRESHOLD_CR
                    and call_sc_total >= SC_BOTH_SIDE_TOTAL_THRESHOLD_CR
                ):
                    bullish_triggers.append((
                        "CALL_SC_TOT",
                        call_sc_total,
                        SC_BOTH_SIDE_TOTAL_THRESHOLD_CR,
                        (
                            f"2MIN CALL_SC TOT {call_sc_total:.2f}Cr >= "
                            f"{SC_BOTH_SIDE_TOTAL_THRESHOLD_CR:g}Cr, "
                            f"ITM/OTM >= {SC_BOTH_SIDE_LEG_THRESHOLD_CR:g}Cr"
                        ),
                    ))

                if (
                    metrics["put_sc_itm"] >= SC_BOTH_SIDE_LEG_THRESHOLD_CR
                    and metrics["put_sc_otm"] >= SC_BOTH_SIDE_LEG_THRESHOLD_CR
                    and put_sc_total >= SC_BOTH_SIDE_TOTAL_THRESHOLD_CR
                ):
                    bearish_triggers.append((
                        "PUT_SC_TOT",
                        put_sc_total,
                        SC_BOTH_SIDE_TOTAL_THRESHOLD_CR,
                        (
                            f"2MIN PUT_SC TOT {put_sc_total:.2f}Cr >= "
                            f"{SC_BOTH_SIDE_TOTAL_THRESHOLD_CR:g}Cr, "
                            f"ITM/OTM >= {SC_BOTH_SIDE_LEG_THRESHOLD_CR:g}Cr"
                        ),
                    ))

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
                        trigger_label, trigger_value, trigger_threshold, trigger_reason = max(bullish_triggers, key=lambda item: item[1])
                        alert_side = "CALL"
                    elif bearish_triggers:
                        trigger_label, trigger_value, trigger_threshold, trigger_reason = max(bearish_triggers, key=lambda item: item[1])
                        alert_side = "PUT"

                if alert_side:
                    akey = f"{symbol}_{alert_side}_{trigger_label}_{now.strftime('%H:%M')}"
                    if akey not in instant_itm_alerts:
                        instant_itm_alerts[akey] = now
                        await handle_candidate_signal(
                            client,
                            target_entity,
                            symbol,
                            strike,
                            alert_side,
                            trigger_reason,
                            sl,
                            tg,
                            now,
                            created_pending_symbols,
                        )

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
                if other and other["type"] == sig_type and abs((now - other["time"]).total_seconds()) <= 30:
                    if ENABLE_2MIN_5MIN_DUAL_MATCH_ALERTS and ENABLE_MATCHED_IN_ALERTS:
                        await handle_candidate_signal(
                            client,
                            target_entity,
                            symbol,
                            strike,
                            sig_type,
                            f"Matched in {abs((now-other['time']).total_seconds()):.1f}s",
                            sl,
                            tg,
                            now,
                            created_pending_symbols,
                        )
                    last_signals_by_symbol[symbol] = {"2 MIN FLOW": None, "5 MIN FLOW": None}

            # BANKNIFTY OTM writer 2MIN + 5MIN matched logic
            otm_sig_type = None
            if symbol == "BANKNIFTY":
                if short_lbl == "2MIN":
                    if (
                        metrics["bull_t"] >= BANKNIFTY_OTM_WR_2MIN_TURN_CR
                        and metrics["put_otm"] >= BANKNIFTY_OTM_WR_2MIN_WRITER_CR
                        and metrics["bear_t"] < 1.0
                    ):
                        otm_sig_type = "CALL"
                    elif (
                        metrics["bear_t"] >= BANKNIFTY_OTM_WR_2MIN_TURN_CR
                        and metrics["call_otm"] >= BANKNIFTY_OTM_WR_2MIN_WRITER_CR
                        and metrics["bull_t"] < 1.0
                    ):
                        otm_sig_type = "PUT"
                else:
                    if (
                        metrics["bull_t"] >= BANKNIFTY_OTM_WR_5MIN_TURN_CR
                        and metrics["put_otm"] >= BANKNIFTY_OTM_WR_5MIN_WRITER_CR
                        and metrics["bear_t"] < 1.0
                    ):
                        otm_sig_type = "CALL"
                    elif (
                        metrics["bear_t"] >= BANKNIFTY_OTM_WR_5MIN_TURN_CR
                        and metrics["call_otm"] >= BANKNIFTY_OTM_WR_5MIN_WRITER_CR
                        and metrics["bull_t"] < 1.0
                    ):
                        otm_sig_type = "PUT"

            if otm_sig_type:
                if symbol not in last_otm_signals_by_symbol:
                    last_otm_signals_by_symbol[symbol] = {"2 MIN FLOW": None, "5 MIN FLOW": None}
                last_otm_signals_by_symbol[symbol][lbl] = {"type": otm_sig_type, "time": now}

                other_lbl = "5 MIN FLOW" if short_lbl == "2MIN" else "2 MIN FLOW"
                other = last_otm_signals_by_symbol[symbol].get(other_lbl)
                if other and other["type"] == otm_sig_type and abs((now - other["time"]).total_seconds()) <= 30:
                    if ENABLE_2MIN_5MIN_DUAL_MATCH_ALERTS and ENABLE_MATCHED_IN_ALERTS:
                        await handle_candidate_signal(
                            client,
                            target_entity,
                            symbol,
                            strike,
                            otm_sig_type,
                            f"OTM_WR Matched in {abs((now-other['time']).total_seconds()):.1f}s",
                            sl,
                            tg,
                            now,
                            created_pending_symbols,
                        )
                    last_otm_signals_by_symbol[symbol] = {"2 MIN FLOW": None, "5 MIN FLOW": None}

    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
