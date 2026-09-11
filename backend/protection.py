"""唯讀止蝕覆蓋核對及通知去重，不提交或修改券商訂單。"""
from datetime import datetime, timezone

ACTIVE = {'SUBMITTED', 'FILLED_PART', 'WAITING_SUBMIT', 'SUBMITTING'}
STOPS = {'STOP', 'STOP_LIMIT', 'TRAILING_STOP', 'TRAILING_STOP_LIMIT'}
TERMINAL = {'FILLED_ALL', 'CANCELLED_ALL', 'CANCELLED_PART', 'DISABLED', 'FAILED', 'DELETED'}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def coverage(code, direction, positions, orders):
    short = direction == 'SHORT'
    held = sum(abs(float(p.get('qty', 0))) for p in positions if str(p.get('code')) == code
        and (str(p.get('position_side')) == 'SHORT' or float(p.get('qty', 0)) < 0) == short)
    sides = {'BUY', 'BUY_BACK'} if short else {'SELL', 'SELL_SHORT'}
    relevant = [o for o in orders if str(o.get('code')) == code and str(o.get('trd_side')) in sides
        and str(o.get('order_type')) in STOPS and str(o.get('order_status')) in ACTIVE]
    confirmed = [o for o in relevant if str(o.get('order_status')) in {'SUBMITTED', 'FILLED_PART'}]
    protected = sum(max(0, float(o.get('qty', 0)) - float(o.get('dealt_qty', 0))) for o in confirmed)
    if held == 0:
        status = 'EXCESS_STOP' if protected else 'NO_POSITION'
    elif protected < held:
        status = 'UNDER_PROTECTED'
    elif protected > held:
        status = 'EXCESS_STOP'
    else:
        status = 'COVERED'
    return {'code': code, 'direction': direction, 'held_qty': held, 'protected_qty': protected,
        'status': status, 'checked_at': now_iso()}


def transition(state, key, active, message, symbol=''):
    """只有首次異常及已確認恢復產生通知；未知不應傳入 active=False。"""
    conditions = state.setdefault('conditions', {})
    previous = conditions.get(key, {})
    if previous.get('active', False) == active:
        if previous:
            previous['message'] = message
        return
    timestamp = now_iso()
    conditions[key] = {'active': active, 'message': message, 'symbol': symbol, 'updated_at': timestamp}
    notices = state.setdefault('notifications', [])
    notices.append({'id': f'{key}:{timestamp}', 'symbol': symbol, 'message': message,
        'kind': 'warning' if active else 'recovered', 'timestamp': timestamp})
    state['notifications'] = notices[-200:]


def timeline_event(previous, current, timestamp=None):
    fields = ('status', 'filled_qty', 'stop_loss_placed_qty', 'stop_order_ids', 'stop_loss_price', 'last_error', 'completed', 'entry_price', 'quantity', 'direction', 'order_type', 'time_in_force')
    changes = {key: current.get(key) for key in fields if previous.get(key) != current.get(key)}
    if not previous:
        changes = {key: current.get(key) for key in fields if key in current}
    if not changes:
        return None
    return {'timestamp': timestamp or now_iso(), 'kind': 'UPDATE' if previous else 'REGISTERED', 'changes': changes}
