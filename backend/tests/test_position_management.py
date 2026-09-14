import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from test_stops import m
from test_zero_cost import FakeBroker
from position_management import partial_plan, partial_tick, cost_price
from position_management_api import install
from zero_cost_api import Draft, Confirm


class Broker(FakeBroker):
    def __init__(self):
        super().__init__(); self.reference = 12
    def reference_price(self, job): return self.reference
    def modify(self, job, stop, qty):
        if self.raise_modify: raise self.raise_modify
        self.writes.append(('modify', stop['order_id'], qty, stop['aux_price']))
        row = self.orders[stop['order_id']]
        row.update(qty=qty, aux_price=stop['aux_price'], price=stop['price'])
        if not qty: row['order_status'] = 'CANCELLED_ALL'


class PartialExit(unittest.TestCase):
    def setUp(self):
        self.b = Broker()
        self.job = dict(code='US.AAPL', symbol='AAPL', phase='PREPARE', held_qty=100, principal=0, price=12,
            break_even=9, fraction=3, remark='partial-test', filled_qty=0, **partial_plan(self.b.orders, 'US.AAPL', 100, 3))
        self.saved = []
    def tick(self): partial_tick(self.job, self.b, lambda: self.saved.append(copy.deepcopy(self.job)))
    def until(self, phase):
        for _ in range(20):
            if self.job['phase'] == phase: return
            self.tick()
        self.fail(str(self.job))
    def fill(self, qty, status='FILLED_ALL'):
        self.b.orders['sell'].update(dealt_qty=qty, dealt_avg_price=12, order_status=status)
        self.b.held = 100 - qty
    def test_fraction_round_down_and_minimum(self):
        for denominator, quantity in [(2, 50), (3, 33), (4, 25)]:
            self.assertEqual(partial_plan(self.b.orders, 'US.AAPL', 100, denominator)['quantity'], quantity)
        with self.assertRaises(ValueError): partial_plan({}, 'US.AAPL', 1, 4)
    def test_fully_filled_promotes_only_after_fill(self):
        self.until('OPEN')
        self.assertEqual(self.b.stop['aux_price'], 8)
        self.assertEqual(self.b.stop['qty'], 67)
        self.fill(33); self.until('DONE')
        self.assertEqual(self.b.stop['aux_price'], 9)
        self.assertEqual(self.b.stop['qty'], 67)
        self.assertEqual(sum(w[0] == 'sell' for w in self.b.writes), 1)
    def test_cancel_unfilled_restores_all_shares_without_promoting(self):
        self.until('OPEN'); self.fill(0, 'CANCELLED_ALL'); self.until('DONE')
        self.assertEqual((self.b.stop['qty'], self.b.stop['aux_price']), (100, 8))
    def test_partial_fill_cancel_restores_remaining_and_promotes(self):
        self.until('OPEN'); self.fill(10, 'CANCELLED_PART'); self.until('DONE')
        self.assertEqual((self.b.stop['qty'], self.b.stop['aux_price']), (90, 9))
    def test_multiple_stops_keep_total_correct(self):
        self.b.stop['qty'] = 50
        self.b.orders['sl2'] = dict(self.b.stop, order_id='sl2', aux_price=9.5)
        self.job.update(partial_plan(self.b.orders, 'US.AAPL', 100, 2))
        self.job['fraction'] = 2
        self.until('OPEN'); self.fill(50); self.until('DONE')
        self.assertEqual(sum(r['qty'] for k,r in self.b.orders.items() if k != 'sell'), 50)
        self.assertEqual(self.b.orders['sl2']['aux_price'], 9.5)
    def test_unknown_sell_after_acceptance_never_resubmits(self):
        self.b.raise_sell = TimeoutError('unknown')
        with self.assertRaises(TimeoutError): self.until('OPEN')
        self.job = copy.deepcopy(self.saved[-1]); self.until('OPEN')
        self.assertEqual(sum(w[0] == 'sell' for w in self.b.writes), 1)
    def test_unknown_modification_is_not_replayed(self):
        self.b.raise_modify = TimeoutError('unknown')
        with self.assertRaises(TimeoutError): self.tick()
        self.job = copy.deepcopy(self.saved[-1]); self.b.raise_modify = None
        with self.assertRaises(ValueError): self.tick()
        self.assertEqual(self.b.writes, [])
    def test_below_cost_preserves_existing_stop_and_surfaces_problem(self):
        self.until('OPEN'); self.fill(33); self.tick(); self.b.reference = 8.5
        with self.assertRaisesRegex(ValueError, '現價不高於保本價'): self.tick()
        self.assertEqual((self.b.stop['qty'], self.b.stop['aux_price']), (67, 8))
    def test_average_cost_not_diluted_cost(self):
        self.assertEqual(cost_price({'average_cost': 9, 'diluted_cost': -2}), 9)
        with self.assertRaises(ValueError): cost_price({'cost_price': 9})
    def test_new_external_order_blocks_selling(self):
        self.b.orders['external'] = dict(self.b.stop, order_type='NORMAL')
        with self.assertRaises(ValueError): self.tick()
        self.assertFalse(self.b.writes)


class AutoStops(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.old = m._ORDER_HISTORY_FILE
        m._ORDER_HISTORY_FILE = Path(self.temp.name) / 'order_history.json'
        self.old_functions = {k: getattr(m, k) for k in ['_sync_position_stops','_position_stop_alerts','_position_stops_busy','_position_stop_records']}
        self.b = Broker(); install(m, lambda: self.b)
        self.held = 40
        self.records = [dict(symbol='AAPL', direction='LONG', stop_order_ids=['sl'])]
        self.patches = [patch.object(m, '_zero_cost_busy', return_value=False), patch.object(m, '_get_pending_stop_orders', return_value={}), patch('position_management_api.time.time', return_value=1000)]
        self.mocks = [p.start() for p in self.patches]
    def tearDown(self):
        for p in self.patches: p.stop()
        for k,v in self.old_functions.items(): setattr(m,k,v)
        m._ORDER_HISTORY_FILE = self.old; self.temp.cleanup()
    def sync(self):
        positions = [dict(code='US.AAPL', qty=self.held, position_side='LONG', average_cost=9, nominal_price=self.b.reference)] if self.held else []
        m._sync_position_stops(42,'REAL','US',positions,self.b.orders,self.records)
    def confirmed(self):
        self.sync(); self.assertFalse(self.b.writes)
        self.mocks[-1].return_value = 1060; self.sync()
    def test_full_exit_cancels_owned_stop_after_two_checks(self):
        self.held=0; self.confirmed()
        self.assertEqual(self.b.writes, [('modify','sl',0,8)])
        self.sync(); self.sync(); self.assertEqual(len(self.b.writes),1)
    def test_manual_partial_exit_reduces_then_promotes(self):
        self.confirmed()
        self.assertEqual((self.b.stop['qty'],self.b.stop['aux_price']), (40,8))
        for _ in range(4): self.sync()
        self.assertEqual((self.b.stop['qty'],self.b.stop['aux_price']), (40,9))
    def test_transient_empty_position_does_not_cancel(self):
        self.held=0; self.sync(); self.held=100
        self.mocks[-1].return_value=1060; self.sync()
        self.assertFalse(self.b.writes)
    def test_external_stop_is_not_cancelled(self):
        self.held=0; self.b.orders['manual']=dict(self.b.stop,order_id='manual')
        self.confirmed(); self.assertEqual(self.b.orders['manual']['order_status'],'WAITING_SUBMIT')
    def test_normal_stop_fill_does_not_trigger_breakeven(self):
        self.b.stop.update(qty=100,dealt_qty=60,order_status='FILLED_PART')
        self.sync(); self.mocks[-1].return_value=1060; self.sync()
        self.assertFalse(self.b.writes)
    def test_active_recovery_pauses_automatic_adjustment(self):
        self.mocks[0].return_value=True
        self.sync(); self.mocks[-1].return_value=1060; self.sync()
        self.assertFalse(self.b.writes)


class FractionApi(unittest.TestCase):
    def test_preview_and_confirmation_use_fraction_and_average_cost_once(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'order_history.json'
            broker = Broker()
            endpoint = lambda path: next(r.endpoint for r in m.app.routes if getattr(r, 'path', '') == path)
            with patch.object(m, '_ORDER_HISTORY_FILE', path), patch.object(m, '_get_trade_env', return_value='REAL'), \
                 patch.object(m, '_get_pending_stop_orders', return_value={}), patch.object(m, '_position_stops_busy', return_value=False), \
                 patch.object(m._ZeroCostBroker, 'position', return_value={'qty':100,'average_cost':9,'diluted_cost':-5,'cost_price_valid':True}), \
                 patch.object(m._ZeroCostBroker, 'orders', return_value=broker.orders), \
                 patch.object(m._ZeroCostBroker, 'bid', return_value={'bid':12,'bid_time':'','quote_read_at':''}):
                preview = endpoint('/api/zero-cost/preview')(Draft(symbol='AAPL',account_id='42',fraction=3))
                self.assertEqual((preview['quantity'],preview['keep_qty'],preview['break_even']), (33,67,9))
                confirm = endpoint('/api/zero-cost/confirm')
                first = confirm(Confirm(token=preview['token'],confirmed=True))
                second = confirm(Confirm(token=preview['token'],confirmed=True))
                self.assertEqual(first['id'], second['id'])
                self.assertEqual(first['kind'],'PARTIAL_EXIT')
                self.assertEqual(first['phase'],'PREPARE')
                self.assertEqual(len(json.loads(path.with_name('zero_cost_jobs.json').read_text())),1)
                self.assertFalse(broker.writes)
