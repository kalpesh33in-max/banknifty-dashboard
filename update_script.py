import sys

with open("C:\\Users\\kalpe\\gdfl data\\banknifty-dashboard\\scanner_bot.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

start_idx = -1
end_idx = -1

for i, line in enumerate(lines):
    if line.startswith("def evaluate_window_signal("):
        start_idx = i
    if line.startswith("def build_reverse_exit_alert("):
        end_idx = i
        break

if start_idx == -1 or end_idx == -1:
    print("Could not find boundaries")
    sys.exit(1)

new_code = """
def get_side_components(rows, side):
    wr_label = "PUT_WR" if side == "CALL" else "CALL_WR"
    sc_label = "CALL_SC" if side == "CALL" else "PUT_SC"

    itm_wr = sum(r["metrics"].get("components", {}).get(wr_label, {}).get("itm", 0.0) for r in rows)
    otm_wr = sum(r["metrics"].get("components", {}).get(wr_label, {}).get("otm", 0.0) for r in rows)

    itm_sc = sum(r["metrics"].get("components", {}).get(sc_label, {}).get("itm", 0.0) for r in rows)
    otm_sc = sum(r["metrics"].get("components", {}).get(sc_label, {}).get("otm", 0.0) for r in rows)

    return wr_label, sc_label, itm_wr, otm_wr, itm_sc, otm_sc

def evaluate_direct_signals(symbol, rows, side):
    latest_metrics = rows[-1]["metrics"]
    if side_from_bias(latest_metrics.get("option_bias", "")) != side:
        return None

    turn_sum = 0.0
    opposite_sum = 0.0
    for row in rows:
        turn, opposite = side_turn_values(row["metrics"], side)
        turn_sum += turn
        opposite_sum += opposite

    if opposite_sum > 1.0:
        return None

    wr_label, sc_label, itm_wr, otm_wr, itm_sc, otm_sc = get_side_components(rows, side)

    signal_type = None
    trigger_line = ""

    if otm_wr >= 15.0:
        signal_type = "DIRECT: AGGRESSIVE OTM WRITER"
        trigger_line = f"{wr_label} OTM {fmt_cr(otm_wr)} >= 15.00Cr"
    elif itm_wr >= 8.0:
        signal_type = "DIRECT: AGGRESSIVE ITM WRITER"
        trigger_line = f"{wr_label} ITM {fmt_cr(itm_wr)} >= 8.00Cr"
    elif itm_sc >= 10.0:
        signal_type = "DIRECT: AGGRESSIVE ITM SHORT COVERING"
        trigger_line = f"{sc_label} ITM {fmt_cr(itm_sc)} >= 10.00Cr"

    if not signal_type:
        return None

    future_check = future_side_check(rows, side)
    _, _, top_components = component_support(rows, side)

    return {
        "mode": "FULL",
        "symbol": symbol,
        "side": side,
        "rows": rows,
        "turn_sum": turn_sum,
        "opposite_sum": opposite_sum,
        "signal_label": signal_type,
        "trigger_line": trigger_line,
        "option_bias": latest_metrics.get("option_bias", "NA"),
        "future": future_check,
        "latest_price": rows[-1].get("price"),
        "is_direct": True,
        "top_components": top_components
    }

def evaluate_standard_signal(symbol, rows, side):
    latest_metrics = rows[-1]["metrics"]
    if side_from_bias(latest_metrics.get("option_bias", "")) != side:
        return None

    turn_sum = 0.0
    opposite_sum = 0.0
    for row in rows:
        turn, opposite = side_turn_values(row["metrics"], side)
        turn_sum += turn
        opposite_sum += opposite

    if turn_sum < 10.0 or opposite_sum > 1.0:
        return None

    wr_label, sc_label, itm_wr, otm_wr, itm_sc, otm_sc = get_side_components(rows, side)

    itm_condition = (itm_wr >= 5.0) or (itm_sc >= 5.0)
    otm_condition = (otm_wr + otm_sc) >= 5.0

    if not (itm_condition and otm_condition):
        return None

    move_min = FULL_FUT_MOVE_POINTS.get(symbol, FULL_FUT_MOVE_POINTS["BANKNIFTY"])
    side_move, raw_move = future_price_move(rows, side)
    
    if side_move is None or side_move < move_min:
        return None

    future_check = future_side_check(rows, side)
    if future_check["blocked"]:
        return None
        
    _, _, top_components = component_support(rows, side)

    itm_trigger_str = f"{wr_label} ITM {fmt_cr(itm_wr)}" if itm_wr >= 5.0 else f"{sc_label} ITM {fmt_cr(itm_sc)}"
    
    return {
        "mode": "FULL",
        "symbol": symbol,
        "side": side,
        "rows": rows,
        "turn_sum": turn_sum,
        "opposite_sum": opposite_sum,
        "signal_label": "STANDARD BALANCED FLOW",
        "option_bias": latest_metrics.get("option_bias", "NA"),
        "future": future_check,
        "latest_price": rows[-1].get("price"),
        "is_direct": False,
        "itm_trigger_str": f"{itm_trigger_str} >= 5.00Cr",
        "otm_total_str": f"{fmt_cr(otm_wr + otm_sc)} >= 5.00Cr",
        "top_components": top_components,
        "side_move": side_move,
        "move_min": move_min
    }

def evaluate_full_signal(symbol, active=None):
    rows = flow_rows_by_symbol.get(symbol, [])
    
    for window in (1, 2):
        if len(rows) < window:
            continue
        recent = rows[-window:]
        candidates = [
            candidate for candidate in (
                evaluate_direct_signals(symbol, recent, "CALL"),
                evaluate_direct_signals(symbol, recent, "PUT"),
            ) if candidate
        ]
        if candidates:
            return max(candidates, key=lambda item: item["turn_sum"])

    min_window = max(1, TURN_MIN_WINDOW)
    max_window = max(min_window, TURN_MAX_WINDOW)
    for window in range(min_window, max_window + 1):
        if len(rows) < window:
            continue
        recent = rows[-window:]
        candidates = [
            candidate for candidate in (
                evaluate_standard_signal(symbol, recent, "CALL"),
                evaluate_standard_signal(symbol, recent, "PUT"),
            ) if candidate
        ]
        if candidates:
            return max(candidates, key=lambda item: item["turn_sum"])
            
    return None

def evaluate_watch_signal(symbol):
    rows = flow_rows_by_symbol.get(symbol, [])
    if len(rows) < 2:
        return None
    recent = rows[-2:]
    
    for side in ("CALL", "PUT"):
        latest_metrics = recent[-1]["metrics"]
        if side_from_bias(latest_metrics.get("option_bias", "")) != side:
            continue
            
        turn_sum = 0.0
        opposite_sum = 0.0
        for row in recent:
            turn, opposite = side_turn_values(row["metrics"], side)
            turn_sum += turn
            opposite_sum += opposite
            
        if turn_sum >= WATCH_TURN_MIN_CR and opposite_sum <= WATCH_OPPOSITE_MAX_CR:
            component_total, _, top_components = component_support(recent, side)
            if component_total >= WATCH_COMPONENT_MIN_CR:
                side_move, raw_move = future_price_move(recent, side)
                move_min = WATCH_FUT_MOVE_POINTS.get(symbol, WATCH_FUT_MOVE_POINTS["BANKNIFTY"])
                if side_move is not None and side_move >= move_min:
                    return {
                        "side": side,
                        "rows": recent,
                        "turn_sum": turn_sum,
                        "turn_min": WATCH_TURN_MIN_CR,
                        "opposite_sum": opposite_sum,
                        "opposite_max": WATCH_OPPOSITE_MAX_CR,
                        "component_total": component_total,
                        "component_min": WATCH_COMPONENT_MIN_CR,
                        "side_move": side_move,
                        "move_min": move_min,
                        "top_components": top_components,
                        "future": future_side_check(recent, side)
                    }
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
    reverse_line = "\\n**REVERSE CONFIRMED FULL OPPOSITE**" if reverse_confirmed else ""
    
    confidence = "CONFIRMED" if future["confirmed"] else "NEUTRAL FUTURE"
    if future["warning"]:
        confidence = "OPTION STRONG, FUTURE WARNING"
        
    if signal.get("is_direct"):
        middle_section = (
            f"OPTION: {fmt_cr(signal['turn_sum'])} Turn, opposite {fmt_cr(signal['opposite_sum'])} <= 1.00Cr\\n"
            f"BIAS: {signal['option_bias']}\\n"
            f"DIRECT TRIGGER:\\n"
            f" • {signal['trigger_line']}\\n"
            f"FUTURE: move skipped for Direct Trigger, bias {future['future_bias']} ({confidence})\\n"
        )
    else:
        middle_section = (
            f"OPTION: {fmt_cr(signal['turn_sum'])} >= 10.00Cr, opposite {fmt_cr(signal['opposite_sum'])} <= 1.00Cr\\n"
            f"BIAS: {signal['option_bias']}\\n"
            f"COMPONENT SPLIT:\\n"
            f" • ITM WR/SC: {signal['itm_trigger_str']}\\n"
            f" • OTM WR+SC: {signal['otm_total_str']}\\n"
            f"TOP: {fmt_components(signal.get('top_components', []))}\\n"
            f"FUTURE: move {fmt_points(signal.get('side_move'))} pts >= {signal.get('move_min', 0):.0f}, "
            f"bias {future['future_bias']} ({confidence})\\n"
        )

    return (
        f"{emoji} **INSTITUTIONAL DUAL MATCH** {emoji}\\n\\n"
        f"**ACTION: BUY {symbol} {strike} {option_type_for_side(side)}**\\n"
        f"**SIGNAL: {side} ({signal_label})**"
        f"{reverse_line}\\n"
        f"WINDOW: {fmt_window(signal['rows'])}\\n"
        f"{middle_section}"
        f"🛡️ **SL: {sl} pts | 🎯 TARGET: {tg} pts**"
    )

def build_watch_alert(symbol, signal, active=None):
    side = signal["side"]
    future = signal["future"]
    action = f"**ACTION: EXIT {symbol}**\\n" if active else "**ACTION: WATCH ONLY**\\n"
    active_line = ""
    if active:
        active_line = f"OLD: {symbol} {active['strike']} {option_type_for_side(active['side'])}\\n"

    return (
        f"⚠️ **2MIN WATCH {'EXIT' if active else 'ONLY'}**\\n\\n"
        f"{action}"
        f"{active_line}"
        f"SIDE: {side} {option_type_for_side(side)}\\n"
        f"WINDOW: {fmt_window(signal['rows'])}\\n"
        f"OPTION: {fmt_cr(signal['turn_sum'])} >= {fmt_cr(signal['turn_min'])}, "
        f"opposite {fmt_cr(signal['opposite_sum'])} <= {fmt_cr(signal['opposite_max'])}\\n"
        f"COMPONENT: {fmt_cr(signal['component_total'])} >= {fmt_cr(signal['component_min'])}\\n"
        f"FUTURE: move {fmt_points(signal['side_move'])} pts >= {signal['move_min']:.0f}, "
        f"bias {future['future_bias']}\\n"
        f"TOP: {fmt_components(signal['top_components'])}"
    )

"""

final_lines = lines[:start_idx] + [new_code] + lines[end_idx:]

with open("C:\\Users\\kalpe\\gdfl data\\banknifty-dashboard\\scanner_bot.py", "w", encoding="utf-8") as f:
    f.writelines(final_lines)

print("Updated scanner_bot.py successfully.")
