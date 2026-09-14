"""持倉減少後的止蝕調整；先保存改單意圖，結果不明時不重送。"""
from decimal import Decimal, ROUND_HALF_UP
from zero_cost import ACTIVE, TERMINAL, STOPS, finite, remaining, active_orders, event, NotSent
from broker_io import Deferred


def cost_price(position):
    try:
        value = finite(position.get('average_cost'))
    except (ValueError, TypeError):
        raise ValueError('未能取得平均買入成本，暫不設定保本價')
    if value <= 0:
        raise ValueError('平均買入成本無效，暫不設定保本價')
    return float(Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


def partial_plan(orders, code, held, denominator):
    if denominator not in (2, 3, 4) or held <= 0 or int(held) != held:
        raise ValueError('請選擇 1/2、1/3 或 1/4 的整股持倉')
    quantity = int(held) // denominator
    if quantity < 1:
        raise ValueError('持股不足以按此比例賣出至少一股')
    stops = []
    for sid, row in sorted(active_orders(orders, code).items()):
        if (str(row.get('trd_side')) != 'SELL' or str(row.get('order_type')) not in {'STOP', 'STOP_LIMIT'}
                or str(row.get('order_status')) not in {'SUBMITTED', 'WAITING_SUBMIT'} or finite(row.get('dealt_qty', 0))):
            raise ValueError('已有其他委託或止蝕正在成交，請先核對')
        stop = {'order_id': sid, 'order_type': str(row['order_type']), 'price': finite(row.get('price', 0)),
                'aux_price': finite(row.get('aux_price', 0)), 'original_qty': remaining(row)}
        if stop['aux_price'] <= 0:
            raise ValueError('止蝕觸發價無效')
        stops.append(stop)
    if not stops or sum(s['original_qty'] for s in stops) != held:
        raise ValueError('請先補齊與持倉股數一致的止蝕單，再使用分批賣出')
    keep = int(held) - quantity
    if keep < len(stops):
        raise ValueError('剩餘股數少於現有止蝕單數目，請先合併止蝕單')
    return {'quantity': quantity, 'keep_qty': keep, 'stops': stops}


def check_intent(job, orders, save):
    intent = job.get('stop_intent')
    if not intent:
        return False
    row = orders.get(intent['order_id'])
    if row is None:
        raise ValueError('止蝕改單结果待核對，暫停重送')
    status = str(row.get('order_status'))
    confirmed = (status in {'CANCELLED_ALL', 'CANCELLED_PART', 'FILLED_ALL'} if intent['qty'] == 0 else
        status in {'SUBMITTED', 'WAITING_SUBMIT', 'FILLED_PART'} and finite(row.get('qty', 0)) == intent['qty']
        and finite(row.get('aux_price', 0)) == intent['aux_price'] and finite(row.get('price', 0)) == intent['price'])
    if not confirmed:
        raise ValueError('止蝕改單結果尚未確認，不會重複提交')
    event(job, '止蝕改單已確認', stop_intent=None)
    save()
    return True


def modify_once(job, broker, row, sid, qty, aux, save):
    old_aux = finite(row.get('aux_price', 0))
    price = finite(row.get('price', 0))
    if str(row.get('order_type')) == 'STOP_LIMIT' and aux != old_aux:
        price = round(price + aux - old_aux, 3)
        if price <= 0:
            raise ValueError('調整後止蝕限價無效')
    intent = {'order_id': sid, 'qty': qty, 'aux_price': aux, 'price': price}
    event(job, '準備撤銷止蝕' if qty == 0 else f'準備調整止蝕：{qty:g} 股，觸發價 ${aux:g}', stop_intent=intent)
    save()
    try:
        broker.modify(job, intent, qty)
    except (Deferred, NotSent):
        job['stop_intent'] = None
        save()
        raise


def adjust_stops(job, broker, orders, held_target, promote, save, preserve=False):
    """一次最多一張改單，先改股數，再改價；不會下調做多止蝕。"""
    stops = job['stops']
    left = held_target
    live = []
    for index, stop in enumerate(stops):
        sid = stop['order_id']; row = orders.get(sid)
        if row is None:
            raise ValueError('未能核對原止蝕，暫停操作')
        status = str(row.get('order_status'))
        dealt = finite(row.get('dealt_qty', 0))
        capacity = max(0, stop['original_qty'] - dealt)
        reserve = len(stops) - index - 1 if preserve else 0
        allocation = min(capacity, max(0, left - reserve))
        left -= allocation
        if status in TERMINAL:
            if allocation:
                raise ValueError('原止蝕已取消或結束，請先核對，程式不會自行重建')
            continue
        if status not in {'SUBMITTED', 'WAITING_SUBMIT', 'FILLED_PART'}:
            raise ValueError('止蝕正在變更，等待確認')
        live.append((sid, row, allocation))
        if remaining(row) != allocation:
            modify_once(job, broker, row, sid, allocation + dealt if allocation else 0,
                        finite(row.get('aux_price', 0)), save)
            return False
    if left:
        raise ValueError('可調整的止蝕股數不足')
    if promote:
        for sid, row, allocation in live:
            target = max(finite(row.get('aux_price', 0)), job['break_even'])
            if allocation and target > finite(row.get('aux_price', 0)):
                if target >= broker.reference_price(job):
                    raise ValueError('股數已核對；現價不高於保本價，暫不能將止蝕推至保本，保留原止蝕價')
                modify_once(job, broker, row, sid, finite(row['qty']), target, save)
                return False
    return True


def partial_tick(job, broker, save):
    if job['phase'] == 'DONE':
        return
    held, orders = broker.snapshot(job)
    for stop in job['stops']:
        if stop['order_id'] not in orders:
            found = broker.lookup(job, stop['order_id'])
            if found: orders[stop['order_id']] = found
    if check_intent(job, orders, save):
        return
    others = active_orders(orders, job['code'])
    for sid in [s['order_id'] for s in job['stops']] + [job.get('order_id')]:
        others.pop(sid, None)
    if any(r.get('remark') != job['remark'] for r in others.values()):
        raise ValueError('發現其他未完成委託，已暫停分批賣出')
    phase = job['phase']
    if phase in {'PREPARE', 'READY'}:
        if not job.get('preparation_checked'):
            if partial_plan(orders, job['code'], held, job['fraction'])['stops'] != job['stops']:
                raise ValueError('預覽後原止蝕已變更，尚未提交賣單，請取消準備後重新預覽')
            job['preparation_checked'] = True; save()
        if held != job['held_qty']:
            event(job, '持倉已變更，放棄提交賣單並核對止蝕', phase='SETTLE'); save(); return
        if not adjust_stops(job, broker, orders, job['keep_qty'], False, save, preserve=True):
            return
        if phase == 'PREPARE':
            event(job, '待保留股數的止蝕已核對', phase='READY'); save(); return
        event(job, '已記錄分批賣出意圖', phase='SUBMITTING'); save()
        try: sid = broker.sell(job)
        except Deferred:
            job['phase'] = 'READY'; save(); raise
        except NotSent:
            job['phase'] = 'SETTLE'; save(); raise
        if sid:
            event(job, '分批賣單已提交', phase='OPEN', order_id=str(sid)); save()
        return
    if phase in {'SUBMITTING', 'OPEN'}:
        row = broker.lookup(job, job.get('order_id'), job['remark'])
        if not row:
            raise ValueError('分批賣單結果未確認，只查詢、不重送')
        if str(row.get('code')) != job['code'] or str(row.get('trd_side')) != 'SELL' or finite(row.get('qty', 0)) != job['quantity']:
            raise ValueError('分批賣單資料已變更，請核對')
        filled = finite(row.get('dealt_qty', 0))
        gross = filled * finite(row.get('dealt_avg_price', 0))
        if filled and gross <= 0:
            raise ValueError('成交價資料未完整')
        next_phase = 'SETTLE' if str(row.get('order_status')) in TERMINAL else 'OPEN'
        if filled != job.get('filled_qty', 0) or phase != next_phase or job.get('order_id') != str(row['order_id']):
            event(job, f'累計賣出 {filled:g} 股', filled_qty=filled, gross=gross, order_id=str(row['order_id']), phase=next_phase)
            save()
        return
    if phase == 'SETTLE':
        stop_filled = sum(finite(orders.get(s['order_id'], {}).get('dealt_qty', 0)) for s in job['stops'])
        if held != job['held_qty'] - job.get('filled_qty', 0) - stop_filled:
            raise ValueError('持倉與已知成交不一致，暫停調整止蝕')
        if adjust_stops(job, broker, orders, held, job.get('filled_qty', 0) > 0, save):
            event(job, '剩餘股數與止蝕已核對', phase='DONE', remaining_qty=held, achieved=False); save()
