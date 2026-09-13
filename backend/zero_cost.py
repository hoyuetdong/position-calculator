"""收回本金：持久化狀態機；所有券商寫入均先記錄意圖，結果不明時只查詢。"""
from decimal import Decimal, ROUND_CEILING
from datetime import datetime, timezone
import math
from broker_io import Deferred

ACTIVE = {'WAITING_SUBMIT', 'SUBMITTING', 'SUBMITTED', 'FILLED_PART', 'CANCELLING_PART', 'CANCELLING_ALL'}
TERMINAL = {'FILLED_ALL', 'CANCELLED_ALL', 'CANCELLED_PART', 'DISABLED', 'FAILED', 'DELETED'}
class NotSent(RuntimeError):
    """已確認未呼叫券商交易接口，可安全撤回準備。"""


STOPS = {'STOP', 'STOP_LIMIT', 'TRAILING_STOP', 'TRAILING_STOP_LIMIT'}


def now():
    return datetime.now(timezone.utc).isoformat()


def finite(value):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError('數值無效')
    return value


def calculate(held, principal, price, fee_buffer=0):
    held, principal, price, fee_buffer = map(finite, (held, principal, price, fee_buffer))
    if held <= 0 or int(held) != held or principal <= 0 or price <= 0 or fee_buffer < 0:
        raise ValueError('請輸入有效的整股持倉、本金及限價')
    quantity = int(((Decimal(str(principal)) + Decimal(str(fee_buffer))) / Decimal(str(price))).to_integral_value(rounding=ROUND_CEILING))
    if quantity >= held:
        raise ValueError('此價格不足以在收回本金後保留至少一股；請提高限價或核實本金')
    return {'quantity': quantity, 'keep_qty': int(held) - quantity,
            'expected_gross': round(quantity * price, 4), 'estimated_remaining_principal': max(0, round(principal - quantity * price + fee_buffer, 4))}


def remaining(row):
    return max(0, finite(row.get('qty', 0)) - finite(row.get('dealt_qty', 0)))


def active_orders(orders, code):
    # 未知／過渡狀態也不得視為已撤銷。
    return {str(k): r for k, r in orders.items() if str(r.get('code')) == code and str(r.get('order_status')) not in TERMINAL}


def plan_stop(orders, code, held):
    live = active_orders(orders, code)
    if not live:
        return None
    if len(live) != 1:
        raise ValueError('已有多張未完成訂單，請先處理後再收回本金')
    sid, row = next(iter(live.items()))
    if (str(row.get('trd_side')) != 'SELL' or str(row.get('order_type')) not in {'STOP', 'STOP_LIMIT'}
            or str(row.get('order_status')) not in {'WAITING_SUBMIT', 'SUBMITTED'}
            or finite(row.get('dealt_qty', 0)) != 0 or remaining(row) != held):
        raise ValueError('已有賣單或不能安全調整的止蝕單，請先核對；系統不會重複提交')
    if finite(row.get('aux_price', 0)) <= 0:
        raise ValueError('無法確認原止蝕觸發價')
    return {'order_id': sid, 'order_type': str(row['order_type']), 'price': finite(row.get('price', 0)),
            'aux_price': finite(row['aux_price']), 'original_qty': held}


def event(job, message, **changes):
    job.update(changes)
    job.setdefault('events', []).append({'timestamp': now(), 'message': message})


def tick(job, broker, save):
    """每輪最多一次交易寫入。broker.snapshot() 必須查詢原帳戶及環境。"""
    if job['phase'] == 'DONE':
        return
    held, orders = broker.snapshot(job)
    held = finite(held)
    code, stop = job['code'], job.get('stop')
    phase = job['phase']
    sid = stop['order_id'] if stop else None
    stop_row = orders.get(sid) if sid else None
    if sid and stop_row is None:
        stop_row = broker.lookup(job, sid)
    others = active_orders(orders, code)
    for key in (sid, job.get('order_id')):
        others.pop(key, None)
    # 尚未找到自己賣單 ID 時，容許以唯一 remark 辨認。
    others = {k:r for k,r in others.items() if r.get('remark') != job['remark']}
    if others:
        raise ValueError('發現其他未完成訂單，已暫停自動操作，請核對')
    if phase == 'PREPARE':
        if held != job['held_qty'] or plan_stop(orders, code, held) != stop:
            raise ValueError('持倉或原止蝕已變更，未提交賣單；請核對')
        if stop:
            event(job, '準備調整原止蝕股數', phase='RESIZING', stop_target=job['keep_qty'])
            save()
            try: broker.modify(job, stop, job['keep_qty'])
            except (Deferred, NotSent):
                job['phase'] = 'PREPARE'; save(); raise
        else:
            event(job, '持倉核對完成', phase='READY'); save()
        return
    if phase == 'RESIZING':
        if not stop_row or str(stop_row.get('order_status')) not in {'WAITING_SUBMIT', 'SUBMITTED'}:
            raise ValueError('止蝕調整結果待核對；不會提交賣單')
        if finite(stop_row.get('qty', 0)) != job['stop_target'] or finite(stop_row.get('aux_price', 0)) != stop['aux_price']:
            raise ValueError('尚未確認止蝕股數已調整；不會重送指令')
        event(job, '止蝕股數調整已確認', phase='READY'); save(); return
    if phase == 'READY':
        if held != job['held_qty']:
            # 原止蝕可能已成交；放棄賣出並恢復剩餘保護。
            event(job, '持倉已變更，取消本次賣出準備', phase='SETTLE'); save(); return
        if stop and (not stop_row or str(stop_row.get('order_status')) not in {'WAITING_SUBMIT', 'SUBMITTED'}
                     or remaining(stop_row) != job['keep_qty'] or finite(stop_row.get('aux_price', 0)) != stop['aux_price']):
            raise ValueError('原止蝕狀態已變更，未提交賣單')
        event(job, '已記錄限價賣出意圖', phase='SUBMITTING')
        save()
        # 此階段即使逾時或程序中止也永不自行重送。
        try: order_id = broker.sell(job)
        except Deferred:
            job['phase'] = 'READY'; save(); raise
        except NotSent:
            job['phase'] = 'SETTLE'; save(); raise
        if order_id:
            event(job, '限價賣單已提交', order_id=str(order_id), phase='OPEN'); save()
        return
    if phase in {'SUBMITTING', 'OPEN'}:
        row = broker.lookup(job, job.get('order_id'), job['remark'])
        if not row:
            raise ValueError('賣單提交結果尚未確認，已保留追蹤，不會重複下單')
        if str(row.get('code')) != code or str(row.get('trd_side')) != 'SELL' or finite(row.get('qty', 0)) != job['quantity']:
            raise ValueError('賣單資料已變更，需人工核對')
        dealt = finite(row.get('dealt_qty', 0))
        gross = round(dealt * finite(row.get('dealt_avg_price', 0)), 4)
        if dealt and gross <= 0:
            raise ValueError('成交價資料未齊全')
        if dealt != job.get('filled_qty', 0) or job.get('phase') != 'OPEN':
            event(job, f'累計賣出 {dealt:g} 股', phase='OPEN', filled_qty=dealt, gross=gross, order_id=str(row['order_id']))
        job['gross'] = gross
        if str(row.get('order_status')) in TERMINAL:
            event(job, '賣單已結束，核對剩餘止蝕', phase='SETTLE')
        save(); return
    if phase == 'SETTLE':
        if stop:
            if not stop_row:
                raise ValueError('找不到原止蝕單，請核對剩餘持倉')
            stop_filled = finite(stop_row.get('dealt_qty', 0))
            if held != job['held_qty'] - job.get('filled_qty', 0) - stop_filled:
                raise ValueError('持倉與已知成交不一致，暫停調整止蝕')
            if str(stop_row.get('order_status')) in TERMINAL:
                if held:
                    raise ValueError('原止蝕已取消或結束，請手動核對剩餘持倉的止蝕')
            elif str(stop_row.get('order_status')) in {'WAITING_SUBMIT', 'SUBMITTED', 'FILLED_PART'}:
                if finite(stop_row.get('aux_price', 0)) != stop['aux_price']:
                    raise ValueError('原止蝕價格已變更，暫停自動調整')
                if remaining(stop_row) != held:
                    target = held + stop_filled if held else 0
                    event(job, '準備核對後調整剩餘止蝕', phase='RESTORING', stop_target=target)
                    save()
                    try: broker.modify(job, stop, target)
                    except (Deferred, NotSent):
                        job['phase'] = 'SETTLE'; save(); raise
                    return
            else:
                raise ValueError('原止蝕正在變更，等待確認')
        event(job, '剩餘持倉核對完成', phase='FEE_PENDING', remaining_qty=held); save(); return
    if phase == 'RESTORING':
        if not stop_row:
            raise ValueError('止蝕調整結果尚未確認')
        matches = (str(stop_row.get('order_status')) in TERMINAL if job['stop_target'] == 0
                   else str(stop_row.get('order_status')) in {'WAITING_SUBMIT', 'SUBMITTED', 'FILLED_PART'}
                   and finite(stop_row.get('qty', 0)) == job['stop_target'])
        if not matches:
            raise ValueError('止蝕調整結果待確認，不會重送指令')
        event(job, '止蝕調整已確認', phase='SETTLE'); save(); return
    if phase == 'FEE_PENDING':
        fee = broker.fee(job) if job.get('filled_qty', 0) else 0
        if fee is None:
            # 正常等待券商費用資料，不誤報為需要人工處理。
            return
        fee = finite(fee)
        if fee < 0:
            raise ValueError('費用資料無效')
        net = round(job.get('gross', 0) - fee, 4)
        unrecovered = max(0, round(job['principal'] - net, 4))
        event(job, '本次成交及費用已核對', phase='DONE', fee=fee, net=net,
              remaining_principal=unrecovered, achieved=unrecovered == 0 and job.get('remaining_qty', 0) > 0)
        save()
