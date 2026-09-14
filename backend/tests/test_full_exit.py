import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from test_position_management import Broker
from test_stops import m
from full_exit import close_plan, close_tick
from zero_cost_api import Draft, Confirm


class CloseBroker(Broker):
    def restore_stop(self, job, stop):
        sid = 'restored-' + str(len(self.writes))
        self.writes.append(('restore', sid, stop['qty']))
        self.orders[sid] = dict(order_id=sid, code=job['code'], trd_side='SELL', order_type=stop['order_type'],
            price=stop['price'], aux_price=stop['aux_price'], qty=stop['qty'], dealt_qty=0,
            order_status='SUBMITTED', remark=stop['remark'])
        return sid


class FullExit(unittest.TestCase):
    def setUp(self):
        self.b = CloseBroker()
        self.job = dict(id='close-test', code='US.AAPL', symbol='AAPL', kind='FULL_EXIT', phase='PREPARE',
            held_qty=100, price=7, remark='close-test', filled_qty=0, **close_plan(self.b.orders,'US.AAPL',100))
        self.saved=[]
    def tick(self): close_tick(self.job,self.b,lambda:self.saved.append(copy.deepcopy(self.job)))
    def until(self, phase):
        for _ in range(30):
            if self.job['phase']==phase:return
            self.tick()
        self.fail(str(self.job))
    def fill(self, qty, status):
        self.b.orders['sell'].update(dealt_qty=qty,dealt_avg_price=7,order_status=status)
        self.b.held=100-qty
    def test_full_fill_cancels_first_and_finishes_only_when_flat(self):
        self.until('OPEN')
        self.assertEqual(self.b.writes[0][0:3],('modify','sl',0))
        self.fill(100,'FILLED_ALL');self.until('DONE')
        self.assertTrue(self.job['closed']);self.assertEqual(self.job['remaining_qty'],0)
        self.assertFalse(any(w[0]=='restore' for w in self.b.writes))
    def test_partial_then_expiry_restores_original_price_and_remaining_qty(self):
        self.until('OPEN');self.fill(30,'FILLED_PART');self.tick()
        self.assertEqual(self.job['phase'],'OPEN')
        self.fill(30,'CANCELLED_PART');self.until('DONE')
        row=self.b.orders[self.job['restored_stop_ids'][0]]
        self.assertEqual((row['qty'],row['aux_price']),(70,8))
        self.assertFalse(self.job['closed'])
    def test_cancel_unfilled_restores_all(self):
        self.until('OPEN');self.fill(0,'CANCELLED_ALL');self.until('DONE')
        self.assertEqual(self.b.orders[self.job['restored_stop_ids'][0]]['qty'],100)
    def test_cancel_preparation_before_any_write_does_not_recreate_stop(self):
        self.job['phase']='SETTLE';self.until('DONE');self.assertFalse(self.b.writes)
    def test_cancel_preparation_after_cancel_restores(self):
        self.until('READY');self.job['phase']='SETTLE';self.until('DONE')
        self.assertFalse(any(w[0]=='sell' for w in self.b.writes))
        self.assertEqual(self.b.orders[self.job['restored_stop_ids'][0]]['qty'],100)
    def test_unknown_sell_is_not_resent_after_restart(self):
        self.b.raise_sell=TimeoutError('unknown')
        with self.assertRaises(TimeoutError):self.until('OPEN')
        self.job=copy.deepcopy(self.saved[-1]);self.until('OPEN')
        self.assertEqual(sum(w[0]=='sell' for w in self.b.writes),1)
    def test_unknown_cancel_blocks_sale(self):
        self.b.raise_modify=TimeoutError('unknown')
        with self.assertRaises(TimeoutError):self.tick()
        self.b.raise_modify=None;self.job=copy.deepcopy(self.saved[-1])
        with self.assertRaises(ValueError):self.tick()
        self.assertFalse(self.b.writes)
    def test_unknown_restore_reconciles_without_resending(self):
        self.until('OPEN');self.fill(50,'CANCELLED_PART');self.tick()
        original=self.b.restore_stop
        def unknown(job, stop): original(job,stop);raise TimeoutError('unknown')
        self.b.restore_stop=unknown
        with self.assertRaises(TimeoutError):self.tick()
        self.job=copy.deepcopy(self.saved[-1]);self.until('DONE')
        self.assertEqual(sum(w[0]=='restore' for w in self.b.writes),1)
    def test_multiple_stop_limit_prices_preserved(self):
        self.b.stop.update(qty=50,order_type='STOP_LIMIT',price=7.8)
        self.b.orders['sl2']=dict(self.b.stop,order_id='sl2',aux_price=9,price=8.8)
        self.job.update(close_plan(self.b.orders,'US.AAPL',100))
        self.until('OPEN');self.fill(20,'CANCELLED_PART');self.until('DONE')
        rows=[self.b.orders[s] for s in self.job['restored_stop_ids']]
        self.assertEqual([(r['qty'],r['aux_price'],r['price']) for r in rows],[(50,8,7.8),(30,9,8.8)])
    def test_no_stops_and_single_share_supported(self):
        self.b.orders={};self.b.held=1;self.job.update(held_qty=1,**close_plan({},'US.AAPL',1))
        self.until('OPEN');self.b.orders['sell'].update(dealt_qty=1,dealt_avg_price=7,order_status='FILLED_ALL');self.b.held=0
        self.until('DONE');self.assertTrue(self.job['closed'])
    def test_changed_holdings_before_preview_execution_blocks_all_writes(self):
        self.b.held=90
        with self.assertRaises(ValueError):self.tick()
        self.assertFalse(self.b.writes)
    def test_other_orders_block_close(self):
        self.b.orders['other']=dict(self.b.stop,order_type='NORMAL')
        with self.assertRaises(ValueError):close_plan(self.b.orders,'US.AAPL',100)
    def test_stale_zero_position_does_not_report_closed(self):
        self.until('OPEN');self.fill(50,'CANCELLED_PART');self.tick();self.b.held=0
        with self.assertRaises(ValueError):self.tick()
        self.assertNotEqual(self.job['phase'],'DONE')
    def test_api_accepts_loss_and_no_average_cost_with_idempotent_confirm(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'order_history.json'
            endpoint=lambda path:next(r.endpoint for r in m.app.routes if getattr(r,'path','')==path)
            with patch.object(m,'_ORDER_HISTORY_FILE',path),patch.object(m,'_get_trade_env',return_value='REAL'), \
                 patch.object(m,'_get_pending_stop_orders',return_value={}),patch.object(m,'_position_stops_busy',return_value=False), \
                 patch.object(m._ZeroCostBroker,'position',return_value={'qty':100}), \
                 patch.object(m._ZeroCostBroker,'orders',return_value=self.b.orders), \
                 patch.object(m._ZeroCostBroker,'bid',return_value={'bid':7,'bid_time':'','quote_read_at':''}):
                draft=endpoint('/api/zero-cost/preview')(Draft(symbol='AAPL',account_id='42',close_all=True))
                self.assertEqual((draft['quantity'],draft['keep_qty']),(100,0))
                confirm=endpoint('/api/zero-cost/confirm');a=confirm(Confirm(token=draft['token'],confirmed=True));b=confirm(Confirm(token=draft['token'],confirmed=True))
                self.assertEqual(a['id'],b['id']);self.assertEqual(a['kind'],'FULL_EXIT')
                self.assertEqual(len(json.loads(path.with_name('zero_cost_jobs.json').read_text())),1)
