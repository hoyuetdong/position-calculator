"""全部平倉：撤單確認後才賣出；未知提交只核對，不重送。"""
from zero_cost import active_orders, finite, remaining, event, TERMINAL, NotSent
from broker_io import Deferred
from position_management import check_intent, modify_once


def close_plan(orders, code, held):
    if held <= 0 or int(held) != held:
        raise ValueError('沒有可平倉的整股做多持倉')
    stops = []
    for sid, row in sorted(active_orders(orders, code).items()):
        if (row.get('trd_side') != 'SELL' or row.get('order_type') not in {'STOP', 'STOP_LIMIT'}
                or row.get('order_status') not in {'SUBMITTED', 'WAITING_SUBMIT'}
                or finite(row.get('dealt_qty', 0))):
            raise ValueError('已有其他委託或正在成交的止蝕，請先處理後再全部平倉')
        stop = dict(order_id=sid, order_type=row['order_type'], price=finite(row.get('price', 0)),
                    aux_price=finite(row.get('aux_price', 0)), original_qty=remaining(row),
                    time_in_force=str(row.get('time_in_force', 'GTC')))
        if stop['aux_price'] <= 0 or stop['original_qty'] <= 0 or stop['time_in_force'] not in {'DAY', 'GTC'}:
            raise ValueError('原止蝕資料無效，暫不平倉')
        stops.append(stop)
    return dict(quantity=int(held), keep_qty=0, stops=stops)


def close_tick(job, broker, save):
    if job['phase'] == 'DONE': return
    held, orders = broker.snapshot(job)
    if held < 0 or int(held) != held: raise ValueError('持倉資料異常，暫停平倉')
    for stop in job['stops']:
        if stop['order_id'] not in orders:
            row = broker.lookup(job, stop['order_id'])
            if row: orders[stop['order_id']] = row
        if stop['order_id'] not in orders:
            raise ValueError('未能確認原止蝕狀態，不會提交平倉單')
    if check_intent(job, orders, save): return
    others = active_orders(orders, job['code'])
    for sid in [s['order_id'] for s in job['stops']] + [job.get('order_id')] + job.get('restored_stop_ids', []):
        others.pop(sid, None)
    known_remarks = {job['remark'], job.get('restore_intent', {}).get('remark')}
    if any(not r.get('remark') or r.get('remark') not in known_remarks for r in others.values()):
        raise ValueError('發現其他未完成委託，暫停平倉，請核對富途訂單')
    phase = job['phase']
    if phase in {'PREPARE', 'READY'}:
        if not job.get('preparation_checked'):
            if held != job['held_qty'] or close_plan(orders, job['code'], held)['stops'] != job['stops']:
                raise ValueError('預覽後持倉或止蝕已變更，請取消準備並重新預覽')
            job['preparation_checked'] = True; save()
        if held != job['held_qty']:
            event(job, '持倉已變更，不提交平倉單，核對剩餘止蝕', phase='SETTLE'); save(); return
        for stop in job['stops']:
            row = orders[stop['order_id']]
            if row['order_status'] in TERMINAL: continue
            if row['order_status'] not in {'SUBMITTED', 'WAITING_SUBMIT'} or finite(row.get('dealt_qty', 0)):
                raise ValueError('原止蝕正在成交或變更，暫不提交平倉單')
            modify_once(job, broker, row, stop['order_id'], 0, finite(row['aux_price']), save); return
        if phase == 'PREPARE':
            event(job, '原止蝕已撤銷，準備提交全部平倉限價單', phase='READY'); save(); return
        event(job, '已記錄全部平倉意圖', phase='SUBMITTING'); save()
        try: sid = broker.sell(job)
        except Deferred:
            job['phase'] = 'READY'; save(); raise
        except NotSent:
            job['phase'] = 'SETTLE'; save(); raise
        if sid: event(job, '全部平倉限價單已提交', phase='OPEN', order_id=str(sid)); save()
        return
    if phase in {'SUBMITTING', 'OPEN'}:
        row = broker.lookup(job, job.get('order_id'), job['remark'])
        if not row: raise ValueError('平倉提交結果未確認，只查詢、不重送')
        if row.get('code') != job['code'] or row.get('trd_side') != 'SELL' or finite(row.get('qty', 0)) != job['quantity']:
            raise ValueError('平倉委託資料不符，請核對')
        filled = finite(row.get('dealt_qty', 0))
        gross = filled * finite(row.get('dealt_avg_price', 0))
        if filled < 0 or filled > job['quantity'] or filled and gross <= 0: raise ValueError('成交資料尚未完整')
        next_phase = 'SETTLE' if row['order_status'] in TERMINAL else 'OPEN'
        if filled != job.get('filled_qty', 0) or phase != next_phase or job.get('order_id') != str(row['order_id']):
            event(job, f'累計平倉 {filled:g} 股', filled_qty=filled, gross=gross, phase=next_phase, order_id=str(row['order_id'])); save()
        return
    if phase not in {'SETTLE', 'RESTORING_CLOSE'}: raise ValueError('未知平倉狀態，請核對')
    intent = job.get('restore_intent')
    if intent:
        row = broker.lookup(job, intent.get('order_id'), intent['remark'])
        if not row: raise ValueError('恢復止蝕結果未確認，不會重複提交')
        if (row.get('code') != job['code'] or row.get('trd_side') != 'SELL' or row.get('order_type') != intent['order_type']
                or finite(row.get('qty', 0)) != intent['qty'] or finite(row.get('aux_price', 0)) != intent['aux_price']
                or (intent['order_type'] == 'STOP_LIMIT' and finite(row.get('price', 0)) != intent['price'])
                or row['order_status'] not in {'SUBMITTED', 'WAITING_SUBMIT', 'FILLED_PART', 'FILLED_ALL'}):
            raise ValueError('恢復止蝕未獲確認，請核對富途訂單及原定止蝕價')
        job.setdefault('restored_stop_ids', []).append(str(row['order_id']))
        job.setdefault('restored_by_original', {})[intent['original_id']] = str(row['order_id'])
        job.pop('restore_intent', None)
        event(job, '剩餘止蝕已恢復', phase='SETTLE'); save(); return
    restored = {}
    for sid in job.get('restored_stop_ids', []):
        row = orders.get(sid) or broker.lookup(job, sid)
        if not row: raise ValueError('未能核對已恢復的止蝕')
        restored[sid] = row
    stop_filled = sum(finite(r.get('dealt_qty', 0)) for r in [orders[s['order_id']] for s in job['stops']] + list(restored.values()))
    if held != job['held_qty'] - job.get('filled_qty', 0) - stop_filled:
        raise ValueError('持倉與已知成交不一致，暫不調整止蝕')
    left = held
    for stop in job['stops']:
        sid = job.get('restored_by_original', {}).get(stop['order_id'], stop['order_id'])
        row = restored.get(sid, orders.get(sid))
        capacity = max(0, stop['original_qty'] - finite(orders[stop['order_id']].get('dealt_qty', 0))
                       - (finite(row.get('dealt_qty', 0)) if sid in restored else 0))
        allocation = min(left, capacity); left -= allocation
        if row['order_status'] not in TERMINAL:
            if row['order_status'] not in {'SUBMITTED', 'WAITING_SUBMIT', 'FILLED_PART'}: raise ValueError('剩餘止蝕正在變更')
            if remaining(row) != allocation:
                modify_once(job, broker, row, sid, allocation + finite(row.get('dealt_qty', 0)) if allocation else 0,
                            finite(row['aux_price']), save); return
        elif allocation:
            if sid in restored: raise ValueError('恢復後的止蝕已結束，請核對剩餘持倉')
            intent = dict(stop, qty=allocation, original_id=stop['order_id'], remark='vcp-cl-'+job['id'][:16]+'-'+str(job['stops'].index(stop)))
            intent.pop('order_id')
            event(job, '準備按原價恢復剩餘止蝕', restore_intent=intent, phase='RESTORING_CLOSE'); save()
            try: result = broker.restore_stop(job, intent)
            except (Deferred, NotSent):
                job.pop('restore_intent', None); job['phase'] = 'SETTLE'; save(); raise
            if result: intent['order_id'] = str(result); save()
            return
    event(job, '已全部平倉' if held == 0 else ('平倉單已結束，剩餘持倉及原止蝕已核對' if job['stops'] else '平倉單已結束，仍有剩餘持倉；原本未設定止蝕'),
          phase='DONE', remaining_qty=held, closed=held == 0, achieved=False)
    save()
