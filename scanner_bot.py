kimport os
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

STRATEGY_SYMBOLS = [
    s.strip().upper()
    for s in os.getenv("STRATEGY_SYMBOLS", "BANKNIFTY,NIFTY").split(",")
    if s.strip()
]
TURN_MIN_WINDOW = int(os.getenv("TURN_MIN_WINDOW", "3"))
TURN_MAX_WINDOW = int(os.getenv("TURN_MAX_WINDOW", "5"))
FULL_TURN_MIN_CR = float(os.getenv("FULL_TURN_MIN_CR", "15"))
FULL_OPPOSITE_MAX_CR = float(os.getenv("FULL_OPPOSITE_MAX_CR", "1"))
FULL_COMPONENT_MIN_CR = float(os.getenv("FULL_COMPONENT_MIN_CR", "15"))
FULL_COMPONENT_OTHER_MIN_CR = float(os.getenv("FULL_COMPONENT_OTHER_MIN_CR", "2"))
FULL_ITM_WRITING_MIN_CR = float(os.getenv("FULL_ITM_WRITING_MIN_CR", "15"))
WATCH_TURN_MIN_CR = float(os.getenv("WATCH_TURN_MIN_CR", "7"))
WATCH_OPPOSITE_MAX_CR = float(os.getenv("WATCH_OPPOSITE_MAX_CR", "1.5"))
WATCH_COMPONENT_MIN_CR = float(os.getenv("WATCH_COMPONENT_MIN_CR", "7"))
FUTURE_OPPOSITE_BLOCK_CR = float(os.getenv("FUTURE_OPPOSITE_BLOCK_CR", "5"))
FULL_DUP_MIN = int(os.getenv("FULL_DUP_MIN", "10"))
WATCH_DUP_MIN = int(os.getenv("WATCH_DUP_MIN", "5"))

FULL_FUT_MOVE_POINTS = {
    "BANKNIFTY": float(os.getenv("BANKNIFTY_FULL_FUT_MOVE_POINTS", "20")),
    "NIFTY": float(os.getenv("NIFTY_FULL_FUT_MOVE_POINTS", "5")),
}
WATCH_FUT_MOVE_POINTS = {
    "BANKNIFTY": float(os.getenv("BANKNIFTY_WATCH_FUT_MOVE_POINTS", "20")),
    "NIFTY": float(os.getenv("NIFTY_WATCH_FUT_MOVE_POINTS", "5")),
}
REVERSE_FULL_FUT_MOVE_POINTS = {
    "BANKNIFTY": float(os.getenv("BANKNIFTY_REVERSE_FULL_FUT_MOVE_POINTS", "20")),
    "NIFTY": float(os.getenv("NIFTY_REVERSE_FULL_FUT_MOVE_POINTS", "7")),
}
REVERSE_ITM_WRITING_MIN_CR = {
    "BANKNIFTY": float(os.getenv("BANKNIFTY_REVERSE_ITM_WRITING_MIN_CR", "10")),
    "NIFTY": float(os.getenv("NIFTY_REVERSE_ITM_WRITING_MIN_CR", "10")),
}

BULLISH_COMPONENTS = ("CALL_SC", "PUT_WR", "CALL_BUY", "PUT_UNW")
BEARISH_COMPONENTS = ("CALL_WR", "CALL_UNW", "PUT_BUY", "PUT_SC")

# State Tracking
last_index_signals = {}
last_fut_signals = {}
last_signals_by_symbol = {}
last_otm_signals_by_symbol = {}
active_signals_by_symbol = {}
pending_reverses_by_symbol = {}
instant_itm_alerts = {}
flow_rows_by_symbol = {}
last_strategy_alerts = {}

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

def get_component_totals(label, text):
    itm, otm = get_writing_values(label, text)
    return {"itm": itm, "otm": otm, "total": itm + otm}

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
    components = {
        label: get_component_totals(label, opt_part)
        for label in (
            "CALL_WR", "PUT_WR", "CALL_SC", "PUT_SC",
            "CALL_BUY", "PUT_BUY", "CALL_UNW", "PUT_UNW",
        )
    }
    fut_flow = re.search(
        r"(FUT_BUY|FUT_SELL|FUT_UNW)\s*:\s*(\d+)\s+lots\s*\(([\d.]+)(Cr|L|)\)",
        fut_part,
        re.IGNORECASE,
    )
    fut_flow_type = fut_flow.group(1).upper() if fut_flow else ""
    fut_flow_lots = int(fut_flow.group(2)) if fut_flow else 0
    fut_flow_cr = (
        _normalize_cr(fut_flow.group(3), fut_flow.group(4))
        if fut_flow else 0.0
    )
    c_itm, c_otm = components["CALL_WR"]["itm"], components["CALL_WR"]["otm"]
    p_itm, p_otm = components["PUT_WR"]["itm"], components["PUT_WR"]["otm"]
    cs_itm, cs_otm = components["CALL_SC"]["itm"], components["CALL_SC"]["otm"]
    ps_itm, ps_otm = components["PUT_SC"]["itm"], components["PUT_SC"]["otm"]
    return {
        "option_bias": get_bias("Option Bias", opt_part),
        "bull_t": get_value("Bullish Turn", opt_part),
        "bear_t": get_value("Bearish Turn", opt_part),
        "future_bias": get_bias("Future Bias", fut_part),
        "future_bull_t": get_value("Bullish Turn", fut_part),
        "future_bear_t": get_value("Bearish Turn", fut_part),
        "future_flow_type": fut_flow_type,
        "future_flow_lots": fut_flow_lots,
        "future_flow_cr": fut_flow_cr,
        "components": components,
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

def side_from_bias(bias):
    up = str(bias or "").upper()
    if "BULLISH" in up and "BEARISH" not in up:
        return "CALL"
    if "BEARISH" in up and "BULLISH" not in up:
        return "PUT"
    return None

def side_from_future_flow(flow_type):
    up = str(flow_type or "").upper()
    if up == "FUT_BUY":
        return "CALL"
    if up == "FUT_SELL":
        return "PUT"
    return None

def side_turn_values(metrics, side):
    if side == "CALL":
        return metrics.get("bull_t", 0.0), metrics.get("bear_t", 0.0)
    return metrics.get("bear_t", 0.0), metrics.get("bull_t", 0.0)

def side_future_turn_values(metrics, side):
    if side == "CALL":
        return metrics.get("future_bull_t", 0.0), metrics.get("future_bear_t", 0.0)
    return metrics.get("future_bear_t", 0.0), metrics.get("future_bull_t", 0.0)

def component_labels_for(side):
    return BULLISH_COMPONENTS if side == "CALL" else BEARISH_COMPONENTS

def component_support(rows, side):
    totals = {}
    for row in rows:
        components = row["metrics"].get("components", {})
        for label in component_labels_for(side):
            totals[label] = totals.get(label, 0.0) + components.get(label, {}).get("total", 0.0)
    total = sum(totals.values())
    biggest = max(totals.values()) if totals else 0.0
    other = total - biggest
    top = sorted(totals.items(), key=lambda item: item[1], reverse=True)
    return total, other, top

def itm_writing_support(rows, side):
    label = "PUT_WR" if side == "CALL" else "CALL_WR"
    total = 0.0
    for row in rows:
        total += row["metrics"].get("components", {}).get(label, {}).get("itm", 0.0)
    return total, label

def future_price_move(rows, side):
    prices = [row.get("price") for row in rows]
    if any(price is None for price in prices):
        return None, None
    raw_move = prices[-1] - prices[0]
    side_move = raw_move if side == "CALL" else -raw_move
    return side_move, raw_move

def future_side_check(rows, side):
    latest = rows[-1]["metrics"]
    latest_bias = latest.get("future_bias", "")
    latest_bias_side = side_from_bias(latest_bias)
    strong_opp_bias = is_strong_opposite_future(latest, side)

    align_turn_sum = 0.0
    opp_turn_sum = 0.0
    align_flow_sum = 0.0
    opp_flow_sum = 0.0

    for row in rows:
        metrics = row["metrics"]
        align_turn, opp_turn = side_future_turn_values(metrics, side)
        align_turn_sum += align_turn
        opp_turn_sum += opp_turn

        flow_side = side_from_future_flow(metrics.get("future_flow_type", ""))
        flow_cr = metrics.get("future_flow_cr", 0.0)
        if flow_side == side:
            align_flow_sum += flow_cr
        elif flow_side:
            opp_flow_sum += flow_cr

    _, latest_opp_turn = side_future_turn_values(latest, side)
    blocked = (
        strong_opp_bias
        or latest_opp_turn >= FUTURE_OPPOSITE_BLOCK_CR
        or opp_flow_sum >= FUTURE_OPPOSITE_BLOCK_CR
    )
    confirmed = (
        latest_bias_side == side
        or align_turn_sum >= FUTURE_OPPOSITE_BLOCK_CR
        or align_flow_sum >= FUTURE_OPPOSITE_BLOCK_CR
    )
    warning = bool(latest_bias_side and latest_bias_side != side and not strong_opp_bias)

    return {
        "blocked": blocked,
        "confirmed": confirmed,
        "warning": warning,
        "future_bias": latest_bias or "NA",
        "align_turn_sum": align_turn_sum,
        "opp_turn_sum": opp_turn_sum,
        "latest_opp_turn": latest_opp_turn,
        "align_flow_sum": align_flow_sum,
        "opp_flow_sum": opp_flow_sum,
    }

def build_flow_row(now, price, metrics):
    return {
        "time": now,
        "price": price,
        "metrics": metrics,
    }

def fmt_cr(value):
    return f"{value:.2f}Cr"

def fmt_points(value):
    if value is None:
        return "NA"
    return f"{value:+.1f}"

def fmt_window(rows):
    return f"{rows[0]['time'].strftime('%H:%M')}-{rows[-1]['time'].strftime('%H:%M')} ({len(rows)} rows)"

def fmt_components(top):
    return ", ".join(f"{label} {fmt_cr(value)}" for label, value in top[:3])

def evaluate_window_signal(symbol, rows, side, mode, reverse_active=False):
    latest_metrics = rows[-1]["metrics"]
    if side_from_bias(latest_metrics.get("option_bias", "")) != side:
        return None

    turn_sum = 0.0
    opposite_sum = 0.0
    for row in rows:
        turn, opposite = side_turn_values(row["metrics"], side)
        turn_sum += turn
        opposite_sum += opposite

    if mode == "FULL":
        turn_min = FULL_TURN_MIN_CR
        opposite_max = FULL_OPPOSITE_MAX_CR
        component_min = FULL_COMPONENT_MIN_CR
        component_other_min = FULL_COMPONENT_OTHER_MIN_CR
        move_min = FULL_FUT_MOVE_POINTS.get(symbol, FULL_FUT_MOVE_POINTS["BANKNIFTY"])
    else:
        turn_min = WATCH_TURN_MIN_CR
        opposite_max = WATCH_OPPOSITE_MAX_CR
        component_min = WATCH_COMPONENT_MIN_CR
        component_other_min = 0.0
        move_min = WATCH_FUT_MOVE_POINTS.get(symbol, WATCH_FUT_MOVE_POINTS["BANKNIFTY"])

    if turn_sum < turn_min or opposite_sum > opposite_max:
        return None

    component_total, component_other, top_components = component_support(rows, side)
    if component_total < component_min or component_other < component_other_min:
        return None

    base_move_min = move_min
    reverse_relaxed = False
    itm_writing_total, itm_writing_label = itm_writing_support(rows, side)
    itm_writing_min = REVERSE_ITM_WRITING_MIN_CR.get(
        symbol,
        REVERSE_ITM_WRITING_MIN_CR["BANKNIFTY"],
    )
    if reverse_active and mode == "FULL" and itm_writing_total >= itm_writing_min:
        reverse_move_min = REVERSE_FULL_FUT_MOVE_POINTS.get(
            symbol,
            REVERSE_FULL_FUT_MOVE_POINTS["BANKNIFTY"],
        )
        if reverse_move_min < move_min:
            move_min = reverse_move_min
            reverse_relaxed = True

    side_move, raw_move = future_price_move(rows, side)
    if side_move is None or side_move < move_min:
        return None

    future_check = future_side_check(rows, side)
    if future_check["blocked"]:
        return None

    return {
        "mode": mode,
        "symbol": symbol,
        "side": side,
        "rows": rows,
        "turn_sum": turn_sum,
        "opposite_sum": opposite_sum,
        "turn_min": turn_min,
        "opposite_max": opposite_max,
        "component_total": component_total,
        "component_other": component_other,
        "component_min": component_min,
        "component_other_min": component_other_min,
        "top_components": top_components,
        "side_move": side_move,
        "raw_move": raw_move,
        "move_min": move_min,
        "base_move_min": base_move_min,
        "reverse_relaxed": reverse_relaxed,
        "itm_writing_total": itm_writing_total,
        "itm_writing_label": itm_writing_label,
        "itm_writing_min": itm_writing_min,
        "option_bias": latest_metrics.get("option_bias", "NA"),
        "future": future_check,
        "latest_price": rows[-1].get("price"),
    }

def evaluate_fast_itm_writing_signal(symbol, rows, side):
    latest_metrics = rows[-1]["metrics"]
    if side_from_bias(latest_metrics.get("option_bias", "")) != side:
        return None

    turn_sum = 0.0
    opposite_sum = 0.0
    for row in rows:
        turn, opposite = side_turn_values(row["metrics"], side)
        turn_sum += turn
        opposite_sum += opposite

    if opposite_sum > FULL_OPPOSITE_MAX_CR:
        return None

    itm_writing_total, itm_writing_label = itm_writing_support(rows, side)
    if itm_writing_total < FULL_ITM_WRITING_MIN_CR:
        return None

    component_total, component_other, top_components = component_support(rows, side)
    future_check = future_side_check(rows, side)
    if future_check["blocked"]:
        return None

    return {
        "mode": "FULL",
        "symbol": symbol,
        "side": side,
        "rows": rows,
        "turn_sum": turn_sum,
        "opposite_sum": opposite_sum,
        "turn_min": FULL_ITM_WRITING_MIN_CR,
        "opposite_max": FULL_OPPOSITE_MAX_CR,
        "component_total": component_total,
        "component_other": component_other,
        "component_min": FULL_ITM_WRITING_MIN_CR,
        "component_other_min": 0.0,
        "top_components": top_components,
        "side_move": None,
        "raw_move": None,
        "move_min": 0.0,
        "base_move_min": 0.0,
        "reverse_relaxed": False,
        "itm_writing_total": itm_writing_total,
        "itm_writing_label": itm_writing_label,
        "itm_writing_min": FULL_ITM_WRITING_MIN_CR,
        "option_bias": latest_metrics.get("option_bias", "NA"),
        "future": future_check,
        "latest_price": rows[-1].get("price"),
        "signal_label": "FULL 2MIN ITM WRITING",
        "skip_future_move": True,
    }

def evaluate_full_signal(symbol, active=None):
    rows = flow_rows_by_symbol.get(symbol, [])
    for window in (1, 2):
        if len(rows) < window:
            continue
        recent = rows[-window:]
        candidates = [
            candidate
            for candidate in (
                evaluate_fast_itm_writing_signal(symbol, recent, "CALL"),
                evaluate_fast_itm_writing_signal(symbol, recent, "PUT"),
            )
            if candidate
        ]
        if candidates:
            return max(candidates, key=lambda item: item["itm_writing_total"])

    min_window = max(1, TURN_MIN_WINDOW)
    max_window = max(min_window, TURN_MAX_WINDOW)
    for window in range(min_window, max_window + 1):
        if len(rows) < window:
            continue
        recent = rows[-window:]
        candidates = [
            candidate
            for candidate in (
                evaluate_window_signal(
                    symbol,
                    recent,
                    "CALL",
                    "FULL",
                    reverse_active=bool(active and active["side"] != "CALL"),
                ),
                evaluate_window_signal(
                    symbol,
                    recent,
                    "PUT",
                    "FULL",
                    reverse_active=bool(active and active["side"] != "PUT"),
                ),
            )
            if candidate
        ]
        if candidates:
            return max(candidates, key=lambda item: item["turn_sum"])
    return None

def evaluate_watch_signal(symbol):
    rows = flow_rows_by_symbol.get(symbol, [])
    if len(rows) < 2:
        return None
    recent = rows[-2:]
    candidates = [
        candidate
        for candidate in (
            evaluate_window_signal(symbol, recent, "CALL", "WATCH"),
            evaluate_window_signal(symbol, recent, "PUT", "WATCH"),
        )
        if candidate
    ]
    if candidates:
        return max(candidates, key=lambda item: item["turn_sum"])
    return None

def strategy_duplicate(symbol, mode, side, now, minutes):
    key = (symbol, mode, side)
    last = last_strategy_alerts.get(key)
    if last and now - last < datetime.timedelta(minutes=minutes):
        return True
    last_strategy_alerts[key] = now
    return False

def build_full_alert(symbol, strike, signal, sl, tg, reverse_confirmed):
    side = signal["side"]
    emoji = emoji_for_side(side)
    future = signal["future"]
    signal_label = signal.get("signal_label", "FULL 2MIN OPTION+FUTURE")
    reverse_line = "\n**REVERSE CONFIRMED FULL OPPOSITE**" if reverse_confirmed else ""
    relaxed_line = ""
    if signal.get("reverse_relaxed"):
        relaxed_line = (
            f"\nREVERSE FILTER: FUT MOVE RELAXED "
            f"{signal['base_move_min']:.0f}->{signal['move_min']:.0f} pts, "
            f"{signal['itm_writing_label']} ITM {fmt_cr(signal['itm_writing_total'])} "
            f">= {fmt_cr(signal['itm_writing_min'])}"
        )
    fast_itm_line = ""
    if signal.get("skip_future_move"):
        fast_itm_line = (
            f"\nITM WRITING: {signal['itm_writing_label']} ITM "
            f"{fmt_cr(signal['itm_writing_total'])} >= "
            f"{fmt_cr(signal['itm_writing_min'])}; FUTURE MOVE SKIPPED"
        )
    confidence = "CONFIRMED" if future["confirmed"] else "NEUTRAL FUTURE"
    if future["warning"]:
        confidence = "OPTION STRONG, FUTURE WARNING"
    if signal.get("skip_future_move"):
        future_line = (
            f"FUTURE: move skipped for ITM writing, "
            f"bias {future['future_bias']} ({confidence})\n"
        )
    else:
        future_line = (
            f"FUTURE: move {fmt_points(signal['side_move'])} pts >= {signal['move_min']:.0f}, "
            f"bias {future['future_bias']} ({confidence})\n"
        )

    return (
        f"{emoji} **INSTITUTIONAL DUAL MATCH** {emoji}\n\n"
        f"**ACTION: BUY {symbol} {strike} {option_type_for_side(side)}**\n"
        f"**SIGNAL: {side} ({signal_label})**"
        f"{reverse_line}\n"
        f"WINDOW: {fmt_window(signal['rows'])}\n"
        f"OPTION: {fmt_cr(signal['turn_sum'])} >= {fmt_cr(signal['turn_min'])}, "
        f"opposite {fmt_cr(signal['opposite_sum'])} <= {fmt_cr(signal['opposite_max'])}\n"
        f"BIAS: {signal['option_bias']}\n"
        f"COMPONENT: {fmt_cr(signal['component_total'])} >= {fmt_cr(signal['component_min'])}, "
        f"other {fmt_cr(signal['component_other'])} >= {fmt_cr(signal['component_other_min'])}\n"
        f"TOP: {fmt_components(signal['top_components'])}\n"
        f"{future_line}"
        f"FUT TURN/FLOW: same {fmt_cr(future['align_turn_sum'])}/{fmt_cr(future['align_flow_sum'])}, "
        f"opp {fmt_cr(future['opp_turn_sum'])}/{fmt_cr(future['opp_flow_sum'])}"
        f"{relaxed_line}"
        f"{fast_itm_line}\n"
        f"🛡️ **SL: {sl} pts | 🎯 TARGET: {tg} pts**"
    )

def build_watch_alert(symbol, signal, active=None):
    side = signal["side"]
    future = signal["future"]
    action = f"**ACTION: EXIT {symbol}**\n" if active else "**ACTION: WATCH ONLY**\n"
    active_line = ""
    if active:
        active_line = f"OLD: {symbol} {active['strike']} {option_type_for_side(active['side'])}\n"

    return (
        f"⚠️ **2MIN WATCH {'EXIT' if active else 'ONLY'}**\n\n"
        f"{action}"
        f"{active_line}"
        f"SIDE: {side} {option_type_for_side(side)}\n"
        f"WINDOW: {fmt_window(signal['rows'])}\n"
        f"OPTION: {fmt_cr(signal['turn_sum'])} >= {fmt_cr(signal['turn_min'])}, "
        f"opposite {fmt_cr(signal['opposite_sum'])} <= {fmt_cr(signal['opposite_max'])}\n"
        f"COMPONENT: {fmt_cr(signal['component_total'])} >= {fmt_cr(signal['component_min'])}\n"
        f"FUTURE: move {fmt_points(signal['side_move'])} pts >= {signal['move_min']:.0f}, "
        f"bias {future['future_bias']}\n"
        f"TOP: {fmt_components(signal['top_components'])}"
    )

async def send_full_signal(client, target_id, symbol, signal, now):
    side = signal["side"]
    active = active_signal_for(symbol, now)
    reverse_confirmed = bool(active and active["side"] != side)

    if not reverse_confirmed and strategy_duplicate(symbol, "FULL", side, now, FULL_DUP_MIN):
        return False

    strike = get_atm(signal["latest_price"], symbol) if signal["latest_price"] else "ATM"
    sl, tg = risk_points_for(symbol)
    await safe_send(
        client,
        target_id,
        build_full_alert(symbol, strike, signal, sl, tg, reverse_confirmed),
    )
    active_signals_by_symbol[symbol] = {
        "side": side,
        "strike": strike,
        "time": now,
        "reverse": reverse_confirmed,
    }
    last_strategy_alerts[(symbol, "FULL", side)] = now
    pending_reverses_by_symbol.pop(symbol, None)
    return True

async def send_watch_signal(client, target_id, symbol, signal, now):
    side = signal["side"]
    active = active_signal_for(symbol, now)
    exit_active = active and active["side"] != side
    mode = "WATCH_EXIT" if exit_active else "WATCH"

    if strategy_duplicate(symbol, mode, side, now, WATCH_DUP_MIN):
        return False

    await safe_send(
        client,
        target_id,
        build_watch_alert(symbol, signal, active if exit_active else None),
    )
    if exit_active:
        active_signals_by_symbol.pop(symbol, None)
        pending_reverses_by_symbol.pop(symbol, None)
    return True

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
    print("🚀 SCANNER ACTIVE: 2MIN option+future strategy for BANKNIFTY/NIFTY")

    @client.on(events.NewMessage(chats=SOURCE_IDS))
    async def handler(event):
        text = event.message.text
        if not text: return
        now = datetime.datetime.now(IST)
        
        if "2 MIN" not in text.upper():
            return

        max_keep_rows = max(TURN_MAX_WINDOW + 3, 8)
        for symbol in STRATEGY_SYMBOLS:
            if symbol not in WATCH_SYMBOLS:
                continue

            section = extract_instrument_section(text, symbol)
            metrics = parse_flow_metrics(section)
            if not metrics:
                continue

            price = get_future_price(section, symbol)
            rows = flow_rows_by_symbol.setdefault(symbol, [])
            rows.append(build_flow_row(now, price, metrics))
            if len(rows) > max_keep_rows:
                del rows[:-max_keep_rows]

            active = active_signal_for(symbol, now)
            full_signal = evaluate_full_signal(symbol, active)
            if full_signal:
                await send_full_signal(client, target_entity, symbol, full_signal, now)
                continue

            watch_signal = evaluate_watch_signal(symbol)
            if watch_signal:
                await send_watch_signal(client, target_entity, symbol, watch_signal, now)

    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
