"""全部使用假券商；測試不連線、不提交真實交易。"""
import copy
import unittest
from zero_cost import calculate, plan_stop, tick
from broker_io import Deferred


class FakeBroker:
    def __init__(self):
        self.held = 100
        self.stop = {'order_id':'sl', 'code':'US.AAPL', 'trd_side':'SELL', 'order_type':'STOP', 'order_status':'WAITING_SUBMIT', 'qty':100, 'dealt_qty':0, 'price':0, 'aux_price':8}
        self.orders = {'sl':self.stop}
        self.writes = []
        self.fee_value = 1
        self.raise_sell = None
        self.raise_modify = None
    def snapshot(self, job): return self.held, self.orders
    def lookup(self, job, order_id=None, remark=None):
        return self.orders.get(order_id) or next((r for r in self.orders.values() if remark and r.get('remark')==remark), None)
    def modify(self, job, stop, qty):
        if self.raise_modify: raise self.raise_modify
        self.writes.append(('modify',qty))
        self.stop['qty'] = qty
        if not qty: self.stop['order_status'] = 'CANCELLED_ALL'
    def sell(self, job):
        self.writes.append(('sell',job['quantity']))
        if isinstance(self.raise_sell, Deferred): self.writes.pop(); raise self.raise_sell
        self.orders['sell'] = {'order_id':'sell', 'code':'US.AAPL', 'trd_side':'SELL', 'order_type':'NORMAL', 'qty':job['quantity'], 'dealt_qty':0, 'dealt_avg_price':0, 'order_status':'SUBMITTED', 'remark':job['remark']}
        if self.raise_sell: raise self.raise_sell
        return 'sell'
    def fee(self, job): return self.fee_value


class ZeroCost(unittest.TestCase):
    def setUp(self):
        self.b = FakeBroker()
        self.job = dict(code='US.AAPL', symbol='AAPL', phase='PREPARE', held_qty=100, principal=300, price=10, fee_buffer=1, remark='test-zc', filled_qty=0,
                       stop=plan_stop(self.b.orders,'US.AAPL',100), **calculate(100,300,10,1))
        self.saved = []
    def tick(self): tick(self.job,self.b,lambda:self.saved.append(copy.deepcopy(self.job)))
    def opened(self):
        for _ in range(4): self.tick()
        self.assertEqual(self.job['phase'],'OPEN')
    def fill(self, qty, status='FILLED_ALL'):
        self.b.orders['sell'].update(dealt_qty=qty,dealt_avg_price=10,order_status=status)
        self.b.held=100-qty
    def test_round_up_and_keep_one_share(self):
        self.assertEqual(calculate(100,1000,30)['quantity'],34)
        self.assertEqual(calculate(100,1000,32)['quantity'],32)
        for args in [(100,1000,10),(100,0,10),(100,300,float('nan')),(100.5,300,10),(100,300,10,-1)]:
            with self.assertRaises(ValueError): calculate(*args)
    def test_existing_sell_or_multiple_stops_are_blocked(self):
        self.b.orders['other'] = dict(self.b.stop,order_type='NORMAL')
        with self.assertRaises(ValueError): plan_stop(self.b.orders,'US.AAPL',100)
        self.b.orders = {'sl':dict(self.b.stop,trd_side='BUY')}
        with self.assertRaises(ValueError): plan_stop(self.b.orders,'US.AAPL',100)
    def test_resize_is_persisted_and_confirmed_before_sell(self):
        self.opened()
        self.assertEqual(self.b.writes,[('modify',69),('sell',31)])
        self.assertTrue(any(j['phase']=='RESIZING' for j in self.saved))
        self.assertTrue(any(j['phase']=='SUBMITTING' and 'order_id' not in j for j in self.saved))
    def test_full_fill_and_fee(self):
        self.opened();self.fill(31)
        for _ in range(3): self.tick()
        self.assertEqual(self.job['phase'],'DONE')
        self.assertTrue(self.job['achieved'])
        self.assertEqual(self.job['net'],309)
        self.assertEqual(self.b.stop['qty'],69)
    def test_partial_fill_cancel_restores_only_unsold_stop_shares(self):
        self.opened();self.fill(10,'FILLED_PART');self.tick()
        self.assertEqual(self.job['filled_qty'],10)
        self.assertEqual(self.b.stop['qty'],69)
        self.b.orders['sell']['order_status']='CANCELLED_PART'
        for _ in range(5): self.tick()
        self.assertEqual(self.b.stop['qty'],90)
        self.assertEqual(self.job['remaining_principal'],201)
        self.assertFalse(self.job['achieved'])
        self.assertEqual(sum(x[0]=='sell' for x in self.b.writes),1)
    def test_cancel_unfilled_restores_original_stop(self):
        self.opened();self.fill(0,'CANCELLED_ALL')
        for _ in range(5): self.tick()
        self.assertEqual(self.b.stop['qty'],100)
        self.assertEqual(self.job['remaining_principal'],300)
    def test_timeout_after_accepted_sell_is_reconciled_never_replayed(self):
        self.b.raise_sell=TimeoutError('lost response')
        for _ in range(2): self.tick()
        with self.assertRaises(TimeoutError): self.tick()
        # 恢復自磁碟中的提交意圖。
        self.job=copy.deepcopy(self.saved[-1])
        for _ in range(3): self.tick()
        self.assertEqual(self.job['phase'],'OPEN')
        self.assertEqual(sum(x[0]=='sell' for x in self.b.writes),1)
    def test_unknown_sell_stays_unknown_when_missing(self):
        self.opened();self.job['phase']='SUBMITTING';del self.b.orders['sell'];self.job.pop('order_id')
        for _ in range(2):
            with self.assertRaises(ValueError): self.tick()
        self.assertEqual(sum(x[0]=='sell' for x in self.b.writes),1)
    def test_unconfirmed_modify_never_sends_sell(self):
        self.b.raise_modify=TimeoutError('unknown')
        with self.assertRaises(TimeoutError): self.tick()
        self.job=copy.deepcopy(self.saved[-1])
        with self.assertRaises(ValueError): self.tick()
        self.assertFalse(self.b.writes)
    def test_deferred_new_write_can_retry_but_query_deferred_cannot_rewind(self):
        self.b.raise_modify=Deferred('cooldown')
        with self.assertRaises(Deferred): self.tick()
        self.assertEqual(self.job['phase'],'PREPARE')
        self.b.raise_modify=None;self.tick()
        self.b.snapshot=lambda j: (_ for _ in ()).throw(Deferred('read cooldown'))
        with self.assertRaises(Deferred): self.tick()
        self.assertEqual(self.job['phase'],'RESIZING')
    def test_stop_fill_before_sell_aborts_sale(self):
        self.tick();self.tick()
        self.b.stop.update(order_status='FILLED_PART',dealt_qty=10)
        self.b.held=90
        self.tick();self.tick()
        self.assertEqual(self.b.stop['qty'],100)
        self.assertFalse(any(x[0]=='sell' for x in self.b.writes))
    def test_manual_stop_cancellation_does_not_recreate_stop(self):
        self.opened();self.fill(31);self.tick()
        self.b.stop['order_status']='CANCELLED_ALL'
        with self.assertRaises(ValueError): self.tick()
        self.assertEqual(self.b.writes,[('modify',69),('sell',31)])
    def test_missing_fee_never_marks_zero_cost(self):
        self.opened();self.fill(31);self.tick();self.tick();self.b.fee_value=None
        self.tick()
        self.assertEqual(self.job['phase'],'FEE_PENDING')
        self.assertNotIn('achieved',self.job)
    def test_new_external_order_blocks_submission(self):
        self.tick();self.tick();self.b.orders['external']=dict(self.b.stop,order_type='NORMAL')
        with self.assertRaises(ValueError): self.tick()
        self.assertFalse(any(x[0]=='sell' for x in self.b.writes))
    def test_no_original_stop_does_not_invent_stop(self):
        self.b.orders={};self.job['stop']=None
        self.tick();self.tick();self.fill(31)
        for _ in range(3):self.tick()
        self.assertEqual(self.b.writes,[('sell',31)])

    def test_preflight_failure_restores_stop_without_selling(self):
        from zero_cost import NotSent
        self.tick();self.tick()
        self.b.sell=lambda j: (_ for _ in ()).throw(NotSent('insufficient available qty'))
        with self.assertRaises(NotSent):self.tick()
        self.assertEqual(self.job['phase'],'SETTLE')
        for _ in range(4):self.tick()
        self.assertEqual(self.b.stop['qty'],100)
        self.assertFalse(any(x[0]=='sell' for x in self.b.writes))


class ZeroCostAPI(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from fastapi.testclient import TestClient
        from test_stops import m
        self.m = m
        self.temp = tempfile.TemporaryDirectory()
        self.fake = FakeBroker()
        self.patches = [patch.object(m, '_ORDER_HISTORY_FILE', Path(self.temp.name)/'history.json'),
            patch.object(m, '_get_trade_env', return_value='REAL'),
            patch.object(m, '_API_SECRET', 'unit-test'),
            patch.object(m, '_get_pending_stop_orders', return_value={}),
            patch.object(m._ZeroCostBroker, 'position', return_value={'qty':100,'cost_price_valid':True,'diluted_cost':3}),
            patch.object(m._ZeroCostBroker, 'orders', return_value=self.fake.orders),
            patch.object(m._ZeroCostBroker, 'bid', return_value={'bid':10,'bid_time':'','quote_read_at':'2026-09-14T00:00:00+00:00'}),
            patch.object(m._ZeroCostBroker, 'sell', side_effect=AssertionError('API preview and confirm must not trade')),
            patch.object(m._ZeroCostBroker, 'modify', side_effect=AssertionError('API preview and confirm must not modify'))]
        for p in self.patches:p.start()
        self.client = TestClient(m.app)
        self.headers={'X-API-Key':'unit-test'}
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.client.close();self.temp.cleanup()
    def post(self,path,body):return self.client.post('/api/zero-cost/'+path,json=body,headers=self.headers)
    def preview(self,**extra):return self.post('preview',{'symbol':'AAPL','account_id':'42',**extra})
    def test_preview_is_read_only_and_confirmation_is_idempotent(self):
        data=self.preview().json()
        self.assertEqual(data['price'],10)
        self.assertEqual(data['principal'],300)
        self.assertEqual(data['quantity'],30)
        for _ in range(2):
            r=self.post('confirm',{'token':data['token'],'confirmed':True})
            self.assertEqual(r.status_code,200)
        jobs=self.client.get('/api/zero-cost/jobs',headers=self.headers).json()['jobs']
        self.assertEqual(len(jobs),1)
        self.assertEqual(jobs[0]['phase'],'PREPARE')
        self.assertEqual(self.preview().status_code,409)
    def test_auth_confirmation_and_account_validation(self):
        self.assertEqual(self.client.get('/api/zero-cost/jobs').status_code,401)
        self.assertEqual(self.post('confirm',{'token':'unknown','confirmed':True}).status_code,409)
        self.assertEqual(self.preview(account_id='not-a-number').status_code,409)
        p=self.preview().json()
        self.assertEqual(self.post('confirm',{'token':p['token'],'confirmed':False}).status_code,409)
    def test_unprofitable_default_still_returns_editable_price_and_principal(self):
        from unittest.mock import patch
        with patch.object(self.m._ZeroCostBroker,'bid',return_value={'bid':2,'bid_time':'','quote_read_at':''}):
            r=self.preview()
        self.assertEqual(r.status_code,200)
        self.assertNotIn('token',r.json())
        self.assertEqual(r.json()['price'],2)
        self.assertEqual(self.preview(price=2,principal=300).status_code,409)
    def test_manual_price_when_bid_unavailable(self):
        from unittest.mock import patch
        with patch.object(self.m._ZeroCostBroker,'bid',side_effect=ValueError('no quote permission')):
            r=self.preview(price=12,principal=300)
        self.assertEqual(r.status_code,200)
        self.assertEqual(r.json()['quantity'],25)
        self.assertIsNone(r.json()['bid'])

    def test_environment_change_blocks_confirm(self):
        from unittest.mock import patch
        data=self.preview().json()
        with patch.object(self.m,'_get_trade_env',return_value='SIMULATE'):
            self.assertEqual(self.post('confirm',{'token':data['token'],'confirmed':True}).status_code,409)

    def test_cancel_preparation_without_trades(self):
        data=self.preview().json()
        self.post('confirm',{'token':data['token'],'confirmed':True})
        r=self.post('cancel',{'token':data['token'],'confirmed':True})
        self.assertEqual(r.status_code,200)
        self.assertEqual(r.json()['phase'],'DONE')
        self.assertFalse(r.json()['achieved'])
