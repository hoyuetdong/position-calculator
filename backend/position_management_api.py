"""沿用每分鐘持倉核對結果，不增加背景行情輪詢。"""
import json
import time
from zero_cost import ACTIVE, TERMINAL, remaining, finite, event
from position_management import cost_price, check_intent, adjust_stops


def install(m, Broker):
    def load():
        path = m._ORDER_HISTORY_FILE.with_name('position_stop_jobs.json')
        return json.loads(path.read_text()) if path.exists() else {}

    def sync(account, env, market, positions, orders, records):
        if env != 'REAL' or market != 'US':
            return
        jobs = load()
        def save():
            for job in jobs.values():
                job['events'] = job.get('events', [])[-100:]
            m._atomic_json(m._ORDER_HISTORY_FILE.with_name('position_stop_jobs.json'), jobs)
        codes = {m._to_futu_code(r['symbol']) for r in records if r.get('direction', 'LONG') == 'LONG'}
        for code in codes:
            if m._zero_cost_busy(account, code):
                continue
            if any(m._to_futu_code(p['symbol']) == code and p.get('acc_id') == account and p.get('trd_env') == env
                   for p in m._get_pending_stop_orders().values()):
                continue
            key = f'{account}:{env}:{code}'
            job = jobs.setdefault(key, {'id': key, 'code': code, 'symbol': code.split('.', 1)[-1],
                'account_id': str(account), 'env': env, 'phase': 'WATCHING', 'events': []})
            try:
                matches = [p for p in positions if p.get('code') == code and str(p.get('position_side')) != 'SHORT']
                if len(matches) > 1:
                    raise ValueError('持倉資料不唯一')
                position = matches[0] if matches else {'qty': 0}
                held = finite(position.get('qty', 0))
                if held < 0 or int(held) != held:
                    raise ValueError('自動止蝕調整只支援整股做多持倉')
                broker = Broker(); broker.last_position = position
                managed = {str(sid) for r in records if m._to_futu_code(r['symbol']) == code
                           for sid in r.get('stop_order_ids', [])}
                relevant = {sid: r for sid, r in orders.items() if sid in managed and r.get('code') == code
                            and str(r.get('trd_side')) == 'SELL' and str(r.get('order_type')) in {'STOP', 'STOP_LIMIT'}
                            and str(r.get('order_status')) not in TERMINAL}
                if job.get('stop_intent'):
                    sid = job['stop_intent']['order_id']
                    observed = dict(orders)
                    if sid not in observed:
                        row = broker.lookup(job, sid)
                        if row: observed[sid] = row
                    check_intent(job, observed, save)
                    job.pop('error', None)
                    save(); continue
                # External active orders must settle before partial-holding adjustments.
                others = [r for sid, r in orders.items() if r.get('code') == code and sid not in managed
                          and str(r.get('order_status')) not in TERMINAL]
                total = sum(remaining(r) for r in relevant.values())
                dealt = sum(finite(r.get('dealt_qty', 0)) for r in relevant.values())
                needs = bool(relevant) and (total > held or job.get('promote_pending'))
                if not needs:
                    job.update(last_held=held, last_stop_filled=dealt, phase='WATCHING', candidate=None)
                    job.pop('error', None); save(); continue
                if held and others:
                    raise ValueError('仍有其他未完成委託，完成後再核對剩餘止蝕')
                candidate = {'held': held, 'orders': {sid: [r.get('qty'), r.get('dealt_qty'), r.get('aux_price')] for sid, r in relevant.items()}}
                # Changes caused by our acknowledged edits do not restart the wait.
                if job.get('phase') != 'ADJUSTING':
                    if job.get('candidate') != candidate:
                        job.update(candidate=candidate, candidate_at=time.time(), phase='VERIFYING')
                        save(); continue
                    if time.time() - job.get('candidate_at', time.time()) < 55:
                        continue
                    job.update(phase='ADJUSTING', target_held=held, promote_pending=held > 0)
                    if held:
                        # Missing cost must not prevent cancellation of excess shares.
                        try: job['break_even'] = cost_price(position)
                        except ValueError: job['break_even'] = None
                    event(job, f'已連續核對持倉 {held:g} 股，準備調整止蝕')
                elif held != job.get('target_held'):
                    job.update(phase='WATCHING', candidate=None, promote_pending=False)
                    save(); continue
                job['stops'] = [{'order_id': sid, 'original_qty': finite(r.get('qty', 0))} for sid, r in sorted(relevant.items())]
                if adjust_stops(job, broker, orders, held, False, save):
                    if held and job.get('promote_pending'):
                        if not job.get('break_even'):
                            job['break_even'] = cost_price(position)
                        if not adjust_stops(job, broker, orders, held, True, save):
                            continue
                    event(job, '剩餘止蝕已撤銷' if held == 0 else '剩餘股數及保本止蝕已核對',
                          phase='WATCHING', promote_pending=False, candidate=None, last_held=held, last_stop_filled=dealt)
                job.pop('error', None)
            except Exception as exc:
                message = m.traditional(str(exc))
                if job.get('error') != message: event(job, message)
                job['error'] = message
            save()

    def alerts(state):
        for key, job in load().items():
            m.transition(state, 'position-stop:' + key, bool(job.get('error')),
                f"{job['symbol']} 止蝕調整：{job['error']}" if job.get('error') else f"{job['symbol']} 止蝕調整已恢復。", job['symbol'])

    m._sync_position_stops = sync
    m._position_stop_alerts = alerts
    m._position_stops_busy = lambda account, code: any((account is None or j['account_id'] == str(account)) and j['code'] == code
        and j.get('stop_intent') for j in load().values())
    m._position_stop_records = lambda: [{'symbol': j['symbol'], 'phase': j['phase'], 'error': j.get('error'),
        'events': j.get('events', [])[-10:]} for j in load().values() if j.get('events') or j.get('error')]
