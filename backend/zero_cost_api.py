"""收回本金的服務整合；安裝時注入主程式，共用鎖、快取及 API 限頻。"""
import math
import re
import time
import uuid
from datetime import datetime, timezone
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from zero_cost import calculate, plan_stop, tick, event, finite, NotSent
from position_management import partial_plan, partial_tick, cost_price
from full_exit import close_plan, close_tick


class Draft(BaseModel):
    symbol: str
    account_id: str
    price: float | None = None
    principal: float | None = None
    fee_buffer: float = Field(default=0, ge=0)
    fraction: int | None = None
    close_all: bool = False


class Confirm(BaseModel):
    token: str
    confirmed: bool = False


def install(m):
    path = lambda: m._ORDER_HISTORY_FILE.with_name('zero_cost_jobs.json')
    def load():
        import json
        return json.loads(path().read_text()) if path().exists() else {}
    def save(jobs):
        m._atomic_json(path(), jobs)
    def is_busy(account, code):
        return any((account is None or j['account_id'] == str(account)) and j['code'] == code and j['phase'] != 'DONE' for j in load().values())
    m._zero_cost_busy = lambda account, code: any((account is None or j['account_id'] == str(account)) and j['code'] == code and j['phase'] not in {'DONE','FEE_PENDING'} for j in load().values())
    drafts = {}

    class Broker:
        def __init__(self):
            self.host = m._get_futu_host()
            self.port = int(m.os.getenv('FUTU_PORT', '11111'))
        def context(self):
            import futu
            return m._ManagedContext(futu.OpenSecTradeContext(filter_trdmarket=futu.TrdMarket.US, host=self.host, port=self.port), self.host, self.port, 'US', priority=True)
        def position(self, job):
            import futu
            ctx = self.context()
            try:
                ret, data = ctx.position_list_query(acc_id=int(job['account_id']), trd_env=job['env'], refresh_cache=True)
                if ret != futu.RET_OK:
                    raise ValueError('持倉查詢失敗：' + str(data))
                rows = [dict(r) for _, r in data.iterrows() if str(r.get('code')) == job['code']]
                if any(str(r.get('position_side')) == 'SHORT' or float(r.get('qty',0)) < 0 for r in rows):
                    raise ValueError('收回本金功能只支援做多持倉')
                if len(rows) > 1:
                    raise ValueError('持倉資料不唯一')
                return rows[0] if rows else {'qty': 0}
            finally:
                ctx.close()
        def orders(self, job, history=False):
            rows, error = m._broker_order_snapshot(self.host, self.port, 'US', int(job['account_id']), job['env'], history)
            if error:
                raise ValueError('訂單查詢失敗：' + str(error))
            return rows
        def snapshot(self, job):
            self.last_position = self.position(job)
            return finite(self.last_position.get('qty', 0)), self.orders(job)
        def reference_price(self, job):
            value = finite(getattr(self, 'last_position', {}).get('nominal_price', 0))
            if value <= 0: raise ValueError('現價資料無效，保留現有止蝕價')
            return value
        def create_stop(self, job):
            try:
                return m._place_stop_order(self.host, self.port, job['symbol'], int(job['be_qty']), job['break_even'],
                    int(job['account_id']), job['env'], m.os.getenv('FUTU_TRADE_PWD', ''), 'LONG', job['be_remark'])
            finally:
                self.invalidate(job)
        def lookup(self, job, order_id=None, remark=None):
            for history in (False, True):
                rows = self.orders(job, history)
                if order_id and order_id in rows:
                    return rows[order_id]
                matches = [r for r in rows.values() if remark and r.get('remark') == remark and str(r.get('code')) == job['code']]
                if len(matches) > 1:
                    raise ValueError('找到多張相同標記的訂單，請人工核對')
                if matches:
                    return matches[0]
            return None
        def invalidate(self, job):
            m._broker_io.invalidate(self.host, self.port, int(job['account_id']))
            for k in list(m._order_snapshots):
                if k[3] == int(job['account_id']):
                    m._order_snapshots.pop(k, None)
            m._push_fresh.add((int(job['account_id']), job['env']))
        def modify(self, job, stop, qty):
            import futu
            ctx = self.context()
            try:
                if not m._unlock_trade(ctx, m.os.getenv('FUTU_TRADE_PWD', '')):
                    raise NotSent('交易解鎖失敗，尚未調整止蝕')
                ret, data = ctx.modify_order(modify_order_op=futu.ModifyOrderOp.NORMAL if qty else futu.ModifyOrderOp.CANCEL,
                    order_id=stop['order_id'], qty=qty, price=stop['price'], aux_price=stop['aux_price'],
                    acc_id=int(job['account_id']), trd_env=job['env'])
                if ret != futu.RET_OK:
                    raise ValueError('止蝕調整結果待核對：' + str(data))
            finally:
                self.invalidate(job); ctx.close()
        def restore_stop(self, job, stop):
            import futu
            ctx = self.context()
            try:
                if not m._unlock_trade(ctx, m.os.getenv('FUTU_TRADE_PWD', '')):
                    raise NotSent('交易解鎖失敗，尚未恢復止蝕')
                ret, data = ctx.place_order(price=stop['price'], qty=stop['qty'], code=job['code'],
                    trd_side=futu.TrdSide.SELL, order_type=getattr(futu.OrderType, stop['order_type']),
                    aux_price=stop['aux_price'], trd_env=job['env'], acc_id=int(job['account_id']),
                    time_in_force=getattr(futu.TimeInForce, stop['time_in_force']), remark=stop['remark'])
                if ret != futu.RET_OK:
                    raise ValueError('恢復原止蝕未獲確認：' + str(data))
                return str(data.iloc[0]['order_id']) if data is not None and not data.empty else None
            finally:
                self.invalidate(job); ctx.close()
        def sell(self, job):
            import futu
            try:
                position = self.position(job)
                if job.get('kind') == 'FULL_EXIT' and finite(position.get('qty', 0)) != job['quantity']:
                    raise ValueError('持倉股數已變更，請重新核對平倉股數')
                if finite(position.get('can_sell_qty', position.get('qty', 0))) < job['quantity']:
                    raise ValueError('可賣股數不足')
            except Exception as exc:
                raise NotSent('提交前持倉核對未通過，未提交賣單：' + str(exc))
            ctx = self.context()
            try:
                if not m._unlock_trade(ctx, m.os.getenv('FUTU_TRADE_PWD', '')):
                    raise NotSent('交易解鎖失敗，未提交賣單，將核對原止蝕')
                ret, data = ctx.place_order(price=job['price'], qty=job['quantity'], code=job['code'],
                    trd_side=futu.TrdSide.SELL, order_type=futu.OrderType.NORMAL,
                    trd_env=job['env'], acc_id=int(job['account_id']), time_in_force=futu.TimeInForce.DAY,
                    session=futu.Session.ALL, fill_outside_rth=True, remark=job['remark'])
                if ret != futu.RET_OK:
                    raise ValueError('賣單結果待核對：' + str(data))
                return str(data.iloc[0]['order_id']) if data is not None and not data.empty else None
            finally:
                self.invalidate(job); ctx.close()
        def fee(self, job):
            import futu
            ctx = self.context()
            try:
                ret, data = ctx.order_fee_query(order_id_list=[job['order_id']], acc_id=int(job['account_id']), trd_env=job['env'])
                if ret != futu.RET_OK:
                    return None
                rows = [r for _,r in data.iterrows() if str(r.get('order_id')) == job['order_id']]
                return finite(rows[0]['fee_amount']) if len(rows) == 1 else None
            finally:
                ctx.close()
        def bid(self, code):
            import futu
            ctx = m._ManagedContext(futu.OpenQuoteContext(host=self.host, port=self.port), self.host, self.port, 'US')
            try:
                ret, data = ctx.subscribe(code_list=[code], subtype_list=[futu.SubType.ORDER_BOOK], subscribe_push=False)
                if ret != futu.RET_OK:
                    raise ValueError('未能訂閱買一價：' + str(data)[:160])
                ret, data = ctx.get_order_book(code=code, num=1)
                if ret != futu.RET_OK:
                    raise ValueError('買一價查詢失敗：' + str(data)[:160])
                if not data.get('Bid') or finite(data['Bid'][0][0]) <= 0:
                    raise ValueError('富途目前沒有有效買一價，請自行輸入限價，或稍後重新開啟預覽')
                return {'bid': finite(data['Bid'][0][0]), 'bid_time': str(data.get('svr_recv_time_bid', '')), 'quote_read_at': datetime.now(timezone.utc).isoformat()}
            finally:
                ctx.close()

    def public(job):
        allowed = {'id','symbol','account_id','env','phase','price','principal','fee_buffer','quantity','held_qty','keep_qty',
                   'filled_qty','remaining_qty','gross','fee','net','remaining_principal','achieved','error','created_at','events','order_id','stop','expected_gross',
                   'kind','fraction','break_even','stops','be_stop_id','closed','restored_stop_ids'}
        return m.traditional({k:v for k,v in job.items() if k in allowed})

    @m.app.get('/api/zero-cost/jobs', dependencies=[Depends(m.verify_api_key)])
    def jobs_list():
        with m._stop_execution_lock:
            jobs = sorted(load().values(), key=lambda j:j['created_at'], reverse=True)
            return {'jobs': [public(j) for j in jobs[:100]]}

    @m.app.post('/api/zero-cost/preview', dependencies=[Depends(m.verify_api_key)])
    def preview(body: Draft):
        try:
            with m._stop_execution_lock:
                if m._get_trade_env() != 'REAL':
                    raise ValueError('此頁顯示真實持倉；請先切換至真實交易環境')
                symbol = body.symbol.upper().strip()
                if not re.fullmatch(r'[A-Z][A-Z0-9]{0,5}(?:[.\-][A-Z])?', symbol) or symbol.endswith('.HK') or not body.account_id.isdigit():
                    raise ValueError('股票或帳戶資料無效，請重新同步持倉')
                job = {'code':'US.'+symbol, 'symbol':symbol, 'account_id':body.account_id, 'env':'REAL'}
                if is_busy(body.account_id, job['code']):
                    raise ValueError('此持倉已有賣出流程，請查看處理紀錄')
                if m._position_stops_busy(body.account_id, job['code']):
                    raise ValueError('此持倉的止蝕正在調整，請稍後再試')
                if any(m._to_futu_code(p['symbol']) == job['code'] and str(p.get('acc_id')) == body.account_id for p in m._get_pending_stop_orders().values()):
                    raise ValueError('此股票仍有入場／補止蝕追蹤，請待處理完成')
                b = Broker(); position = b.position(job); held = finite(position.get('qty', 0))
                if held <= 0 or int(held) != held:
                    raise ValueError('沒有可處理的整股做多持倉')
                orders = b.orders(job)
                if body.close_all and body.fraction is not None: raise ValueError('不能同時選擇全部平倉及分批賣出')
                closing = close_plan(orders, job['code'], held) if body.close_all else None
                partial = partial_plan(orders, job['code'], held, body.fraction) if body.fraction is not None else None
                stop = None if partial or closing else plan_stop(orders, job['code'], held)
                break_even = cost_price(position) if partial else None
                quote = {'bid': None, 'bid_time': '', 'quote_read_at': ''}
                warning = ''
                try: quote = b.bid(job['code'])
                except Exception as exc: warning = str(exc)
                principal = body.principal
                if principal is None and bool(position.get('cost_price_valid', False)):
                    raw = position.get('diluted_cost', position.get('cost_price'))
                    try: principal = max(0, round(finite(raw) * held, 4))
                    except (ValueError, TypeError): principal = None
                price = body.price if body.price is not None else quote['bid']
                result = {**quote, 'warning': warning, 'principal': principal, 'price': price, 'held_qty':held,
                          'stop':stop, 'env':'REAL', 'account_id':body.account_id, 'symbol':symbol}
                if closing:
                    result.update(**closing, kind='FULL_EXIT')
                    if price is None: return m.traditional(result)
                    price = finite(price)
                    if price <= 0: raise ValueError('請輸入有效的平倉限價')
                    token = uuid.uuid4().hex
                    for k,v in list(drafts.items()):
                        if time.time() - v['at'] > 120: drafts.pop(k, None)
                    if len(drafts) >= 100: raise ValueError('預覽過多，請稍後再試')
                    numbers = {**closing, 'expected_gross': round(held * price, 4)}
                    result.update(numbers, token=token)
                    drafts[token] = {'at':time.time(), 'job': {**job, **numbers, 'kind':'FULL_EXIT',
                        'held_qty':held, 'stop':None, 'price':price, 'principal':0, 'fee_buffer':0}}
                    return m.traditional(result)
                if partial:
                    result.update(**partial, break_even=break_even, fraction=body.fraction, kind='PARTIAL_EXIT')
                    if price is None: return m.traditional(result)
                    price = finite(price)
                    if price <= max([break_even] + [s['aux_price'] for s in partial['stops']]):
                        message = '分批賣出限價須高於保本價及原止蝕價'
                        if body.price is not None: raise ValueError(message)
                        result['warning'] = message; return m.traditional(result)
                    token = uuid.uuid4().hex
                    for k,v in list(drafts.items()):
                        if time.time() - v['at'] > 120: drafts.pop(k, None)
                    if len(drafts) >= 100: raise ValueError('預覽過多，請稍後再試')
                    numbers = {**partial, 'expected_gross': round(partial['quantity'] * price, 4)}
                    result.update(numbers, token=token)
                    drafts[token] = {'at':time.time(), 'job': {**job, **numbers, 'kind':'PARTIAL_EXIT', 'fraction':body.fraction,
                        'break_even':break_even, 'held_qty':held, 'stop':None, 'price':price, 'principal':0, 'fee_buffer':0}}
                    return m.traditional(result)
                if principal is not None and principal <= 0:
                    result['warning'] = '券商成本顯示本金已收回；如不符，請核實並修改尚未收回本金'
                if price is not None and principal is not None and principal > 0:
                    try: numbers = calculate(held, principal, price, body.fee_buffer)
                    except ValueError as exc:
                        if body.price is not None: raise
                        result['warning'] = str(exc)
                        return m.traditional(result)
                    if stop and price <= stop['aux_price']:
                        if body.price is not None: raise ValueError('賣出限價必須高於原止蝕觸發價')
                        result['warning'] = '買一價低於原止蝕觸發價，請核實限價'
                        return m.traditional(result)
                    token = uuid.uuid4().hex
                    result.update(numbers, token=token)
                    for k,v in list(drafts.items()):
                        if time.time() - v['at'] > 120: drafts.pop(k, None)
                    if len(drafts) >= 100: raise ValueError('預覽過多，請稍後再試')
                    drafts[token] = {'at':time.time(), 'job':{**job, **numbers, 'held_qty':held, 'stop':stop,
                        'price':finite(price), 'principal':finite(principal), 'fee_buffer':finite(body.fee_buffer)}}
                return m.traditional(result)
        except Exception as exc:
            raise HTTPException(409, m.traditional(str(exc)))

    @m.app.post('/api/zero-cost/confirm', dependencies=[Depends(m.verify_api_key)])
    def confirm(body: Confirm):
        with m._stop_execution_lock:
            jobs = load()
            if body.token in jobs: return public(jobs[body.token])
            draft = drafts.get(body.token)
            if not body.confirmed or not draft or time.time() - draft['at'] > 120:
                raise HTTPException(409, '預覽已過期或尚未確認，請重新預覽')
            if m._get_trade_env() != 'REAL': raise HTTPException(409, '交易環境已變更，請重新確認')
            job = dict(draft['job'])
            if is_busy(job['account_id'], job['code']): raise HTTPException(409, '已有處理中的賣出流程')
            if m._position_stops_busy(job['account_id'], job['code']): raise HTTPException(409, '止蝕正在調整，請重新預覽')
            job.update(id=body.token, remark='vcp-zc-'+body.token[:24], phase='PREPARE', created_at=datetime.now(timezone.utc).isoformat(), filled_qty=0)
            event(job, '使用者確認全部平倉及撤銷原止蝕' if job.get('kind') == 'FULL_EXIT' else '使用者確認分批賣出及保本止蝕' if job.get('kind') == 'PARTIAL_EXIT' else '使用者確認收回本金、本金金額及止蝕調整')
            jobs[body.token] = job; save(jobs)
            return public(job)

    @m.app.post('/api/zero-cost/cancel', dependencies=[Depends(m.verify_api_key)])
    def cancel_preparation(body: Confirm):
        with m._stop_execution_lock:
            jobs = load(); job = jobs.get(body.token)
            if not body.confirmed or not job or job['phase'] not in {'PREPARE','READY'}:
                raise HTTPException(409, '已開始提交或正在核對，不能取消準備；請查看紀錄及富途訂單')
            if job.get('kind') in {'PARTIAL_EXIT', 'FULL_EXIT'}:
                if job.get('stop_intent'): raise HTTPException(409, '止蝕調整待確認，請稍後再試')
                event(job, '使用者取消賣出準備，將恢復剩餘止蝕', phase='SETTLE')
            elif job['phase'] == 'PREPARE' or not job.get('stop'):
                event(job, '使用者取消準備，沒有提交賣單', phase='DONE', achieved=False, remaining_principal=job['principal'])
            else:
                event(job, '使用者取消準備，將核對及恢復原止蝕', phase='SETTLE')
            job.pop('error', None);job['next_at'] = 0;save(jobs)
            return public(job)

    def monitor():
        with m._stop_execution_lock:
            jobs = load()
            for job in jobs.values():
                if job['phase'] == 'DONE' or time.time() < job.get('next_at', 0): continue
                try:
                    (close_tick if job.get('kind') == 'FULL_EXIT' else partial_tick if job.get('kind') == 'PARTIAL_EXIT' else tick)(job, Broker(), lambda: save(jobs))
                    job.pop('error', None)
                except Exception as exc:
                    message = m.traditional(str(exc))
                    if job.get('error') != message: event(job, message)
                    job['error'] = message
                job['next_at'] = time.time() + (300 if job['phase'] == 'FEE_PENDING' else 30)
                if job.get('kind') in {'PARTIAL_EXIT', 'FULL_EXIT'}: job['events'] = job.get('events', [])[-200:]
                save(jobs)
    def adjust_coverage(result, account, env, orders):
        for j in load().values():
            if j['phase'] == 'DONE' or j.get('error') or not (j.get('stop') or j.get('stops')) or j['account_id'] != str(account) or j['env'] != env or j['code'] != result['code']: continue
            configured = result['protected_qty'] + result.get('waiting_qty', 0)
            if configured != j['keep_qty'] or result['held_qty'] < configured: continue
            row = orders.get(j.get('order_id'))
            reserved = max(0, float(row.get('qty',0))-float(row.get('dealt_qty',0))) if row and str(row.get('order_status')) in {'SUBMITTED','WAITING_SUBMIT','FILLED_PART'} else 0
            preparing = j['phase'] in {'PREPARE','RESIZING','READY','SUBMITTING'} and result['held_qty'] == j['held_qty']
            if preparing or reserved and configured + reserved == result['held_qty']:
                result['status'] = 'FULL_EXIT' if j.get('kind') == 'FULL_EXIT' else 'PARTIAL_EXIT' if j.get('kind') == 'PARTIAL_EXIT' else 'RECOVERING_PRINCIPAL'
                result['recovery_reserved_qty'] = result['held_qty'] - configured
        return result
    def alerts(state):
        for j in load().values():
            name = '全部平倉' if j.get('kind') == 'FULL_EXIT' else '分批賣出' if j.get('kind') == 'PARTIAL_EXIT' else '收回本金'
            m.transition(state, 'zero-cost:' + j['id'], bool(j.get('error')) and j['phase'] != 'DONE',
                f"{j['symbol']} {name}：{j['error']}" if j.get('error') else f"{j['symbol']} {name}流程已恢復。", j['symbol'])
    def history():
        return [{'entry_order_id':j.get('order_id', j['id']), 'symbol':j['symbol'], 'quantity':j['quantity'],
                 'entry_price':j['price'], 'stop_loss_price':j['stop']['aux_price'] if j.get('stop') else None,
                 'filled_qty':j.get('filled_qty',0), 'created_at':j['created_at'], 'status':('FULL_EXIT_' if j.get('kind') == 'FULL_EXIT' else 'RECOVERY_')+j['phase'],
                 'events':[{'timestamp':e['timestamp'],'kind':'RECOVERY','changes':{'message':e['message']}} for e in j['events']]} for j in load().values()]
    m._zero_cost_history = history
    m._zero_cost_protection_records = lambda: [dict(entry_order_id='exit:'+j['id'], symbol=j['symbol'],
        acc_id=int(j['account_id']), trd_env=j['env'], direction='LONG', completed=True,
        stop_order_ids=([s['order_id'] for s in j.get('stops', [])] + ([j['be_stop_id']] if j.get('be_stop_id') else []) + j.get('restored_stop_ids', [])))
        for j in load().values() if j.get('kind') in {'PARTIAL_EXIT', 'FULL_EXIT'} and (j.get('stops') or j.get('be_stop_id') or j.get('restored_stop_ids'))]
    m._zero_cost_coverage = adjust_coverage
    m._zero_cost_alerts = alerts
    m._monitor_zero_cost = monitor
    return Broker
