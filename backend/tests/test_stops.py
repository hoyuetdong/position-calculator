"""用假券商測試，完全唔連線／落真單。"""
import copy
import importlib.util
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('broker_main', ROOT / 'main.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
spec2 = importlib.util.spec_from_file_location('maintenance', ROOT / 'maintenance.py')
maintenance = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(maintenance)


class Rows:
    def __init__(self, rows): self.rows = rows
    @property
    def empty(self): return not self.rows
    def iterrows(self): return enumerate(self.rows)


class Stops(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        m._PENDING_STOPS_FILE = Path(self.temp.name) / 'pending_stops.json'
        m._ORDER_HISTORY_FILE = Path(self.temp.name) / 'order_history.json'
        m._pending_stop_orders = {}
        m._order_snapshots = {}
        self.info = dict(symbol='AAPL', quantity=10, stop_loss_price=90, acc_id=42, trd_env='REAL', direction='LONG')
        m._add_pending_stop_order('entry', self.info.copy())
        self.query = patch.object(m, '_query_order_status_and_fill').start()
        self.query.return_value = dict(status='FILLED_ALL', fill_qty=10, order_qty=10, acc_id=42)
        self.place = patch.object(m, '_place_stop_order', return_value=dict(success=True, stop_order_id='stop-1')).start()
        self.reconcile = patch.object(m, '_reconcile_stop', return_value=None).start()
        self.capacity = patch.object(m, '_stop_capacity', return_value='available').start()

    def tearDown(self):
        patch.stopall()
        self.temp.cleanup()

    def tick(self):
        m._monitor_one('localhost', 11111, 'entry', m._get_pending_stop_orders()['entry'])

    def retry_now(self):
        m._pending_stop_orders['entry']['next_retry_at'] = 0

    def test_delayed_fill_after_query_failure_keeps_tracking(self):
        self.query.return_value = None
        self.tick()
        self.assertIn('entry', m._pending_stop_orders)
        m._init_pending_stops_from_file()
        self.retry_now()
        self.query.return_value = dict(status='FILLED_ALL', fill_qty=10)
        self.tick()
        self.assertEqual(self.place.call_args.args[3], 10)
        self.assertNotIn('entry', m._pending_stop_orders)

    def test_partial_fills_only_incremental_stop(self):
        self.query.return_value = dict(status='FILLED_PART', fill_qty=4)
        self.tick(); self.tick()
        self.assertEqual(self.place.call_count, 1)
        self.query.return_value = dict(status='FILLED_ALL', fill_qty=10)
        self.tick()
        self.assertEqual([c.args[3] for c in self.place.call_args_list], [4, 6])

    def test_partial_cancel_still_protects_filled_quantity(self):
        self.query.return_value = dict(status='CANCELLED_PART', fill_qty=3)
        self.tick()
        self.assertEqual(self.place.call_args.args[3], 3)
        self.assertNotIn('entry', m._pending_stop_orders)

    def test_restart_never_restores_completed(self):
        self.tick()
        self.assertTrue(json.loads(m._ORDER_HISTORY_FILE.read_text())[0]['completed'])
        m._restore_pending_stops_from_history('localhost', 1, 'REAL')
        self.assertEqual(m._pending_stop_orders, {})

    def test_restores_latest_partial_qty_from_history(self):
        self.query.return_value = dict(status='FILLED_PART', fill_qty=4)
        self.tick()
        m._pending_stop_orders = {}
        m._restore_pending_stops_from_history('localhost', 1, 'REAL')
        self.tick()
        self.assertEqual(self.place.call_count, 1)

    def test_uncertain_submission_is_not_retried(self):
        self.place.side_effect = TimeoutError('timeout')
        self.tick()
        m._init_pending_stops_from_file()
        self.retry_now(); self.tick()
        self.assertEqual(self.place.call_count, 1)
        self.assertEqual(m._pending_stop_orders['entry']['status'], 'SUBMISSION_UNKNOWN')

    def test_reconcile_after_crash_finds_stop_without_duplicate(self):
        self.place.side_effect = TimeoutError('timeout')
        self.tick()
        self.reconcile.return_value = {'stop_order_id': 'accepted-before-timeout'}
        self.retry_now(); self.tick(); self.tick()
        self.assertEqual(self.place.call_count, 1)
        self.assertNotIn('entry', m._pending_stop_orders)

    def test_persist_intent_before_broker_submission(self):
        def submit(*args):
            self.assertIsNotNone(json.loads(m._PENDING_STOPS_FILE.read_text())['entry']['stop_intent'])
            self.assertIsNotNone(json.loads(m._ORDER_HISTORY_FILE.read_text())[0]['stop_intent'])
            return {'success': True, 'stop_order_id': 'x'}
        self.place.side_effect = submit
        self.tick()

    def test_account_env_are_bound_to_entry(self):
        m._set_trade_env('SIMULATE')
        self.tick()
        self.assertEqual(self.query.call_args.args[3:5], (42, 'REAL'))
        self.assertEqual(self.place.call_args.args[5:7], (42, 'REAL'))

    def test_legacy_filled_requires_review(self):
        m._pending_stop_orders['entry'].pop('schema_version')
        self.tick()
        self.place.assert_not_called()
        self.assertEqual(m._pending_stop_orders['entry']['status'], 'LEGACY_NEED_MANUAL')

    def test_legacy_unfilled_is_migrated(self):
        m._pending_stop_orders['entry'].pop('schema_version')
        self.query.return_value = dict(status='SUBMITTED', fill_qty=0)
        self.tick()
        self.assertEqual(m._pending_stop_orders['entry']['schema_version'], 2)

    def test_known_pre_submission_failure_remains_visible(self):
        self.place.return_value = dict(success=False, error='unlock failed')
        for _ in range(5): self.retry_now(); self.tick()
        self.assertEqual(m._pending_stop_orders['entry']['status'], 'FAILED_NEED_MANUAL')
        self.tick()
        self.assertEqual(self.place.call_count, 5)
        response = m.get_pending_stop_orders()
        self.assertEqual(response.pending_orders[0].last_error, 'unlock failed')

    def test_atomic_write_failure_keeps_previous_file(self):
        before = m._PENDING_STOPS_FILE.read_text()
        with patch.object(m.os, 'replace', side_effect=OSError('disk')):
            with self.assertRaises(OSError): m._atomic_json(m._PENDING_STOPS_FILE, {'new': 1})
        self.assertEqual(m._PENDING_STOPS_FILE.read_text(), before)

    def test_corrupt_storage_is_not_silently_discarded(self):
        m._PENDING_STOPS_FILE.write_text('{')
        with self.assertRaises(RuntimeError): m._load_pending_stops_from_file()

    def test_cleanup_only_expired_cache_not_trading_data(self):
        root = Path(self.temp.name)
        cache = root / '.next/cache/fetch-cache'
        cache.mkdir(parents=True)
        old, fresh = cache / 'old', cache / 'fresh'
        old.write_text('old'); fresh.write_text('new')
        os.utime(old, (0, 0))
        self.assertEqual(maintenance.clean_cache(root), 1)
        self.assertTrue(fresh.exists())
        self.assertTrue(m._ORDER_HISTORY_FILE.exists())
        self.assertTrue(m._PENDING_STOPS_FILE.exists())

    def test_history_query_when_current_day_missing(self):
        # 暫時還原真實查詢函數，所有券商 context 仍然用假資料。
        patch.stopall()
        class Context:
            closed = 0
            def __init__(self, **kwargs): pass
            def order_list_query(self, **kwargs): return 0, Rows([])
            def history_order_list_query(self, **kwargs):
                return 0, Rows([dict(order_id='entry', order_status='FILLED_ALL', dealt_qty=10, qty=10)])
            def close(self): Context.closed += 1
        fake = types.SimpleNamespace(RET_OK=0, TrdMarket=types.SimpleNamespace(US='US', HK='HK'), OpenSecTradeContext=Context)
        with patch.dict(sys.modules, {'futu': fake}):
            result = m._query_order_status_and_fill('localhost', 1, 'entry', 42, 'REAL', '2026-09-01')
        self.assertEqual(result['fill_qty'], 10)
        self.assertEqual(Context.closed, 2)

    def test_cancelled_unfilled_archived_and_not_restored(self):
        self.query.return_value = dict(status='CANCELLED_ALL', fill_qty=0)
        self.tick()
        self.place.assert_not_called()
        self.assertFalse(m._pending_stop_orders)
        self.assertEqual(m.get_pending_stop_orders().completed_orders[0].status, 'CLOSED_UNFILLED')
        m._restore_pending_stops_from_history('localhost', 1, 'REAL')
        self.assertFalse(m._pending_stop_orders)

    def test_expired_partial_protects_filled_only(self):
        self.query.return_value = dict(status='DISABLED', fill_qty=2)
        self.tick()
        self.assertEqual(self.place.call_args.args[3], 2)
        self.assertEqual(m.get_pending_stop_orders().completed_orders[0].status, 'PROTECTED')

    def test_flat_requires_two_separated_checks(self):
        self.capacity.return_value = 'flat'
        self.tick()
        self.assertIn('entry', m._pending_stop_orders)
        m._pending_stop_orders['entry']['flat_seen_at'] -= 61
        self.retry_now(); self.tick()
        self.place.assert_not_called()
        self.assertNotIn('entry', m._pending_stop_orders)
        self.assertEqual(m.get_pending_stop_orders().completed_orders[0].status, 'NO_POSITION')

    def test_position_conflict_blocks_both_auto_and_manual(self):
        self.capacity.side_effect = RuntimeError('已有平倉單')
        self.tick()
        m.retry_pending_stop(m.StopRetryRequest(entry_order_id='entry'))
        self.tick()
        self.place.assert_not_called()
        self.assertEqual(m._pending_stop_orders['entry']['status'], 'POSITION_REVIEW')

    def test_double_manual_retry_sends_only_one_stop(self):
        for _ in range(2): m.retry_pending_stop(m.StopRetryRequest(entry_order_id='entry'))
        self.tick()
        m._monitor_one('localhost', 11111, 'entry', self.info)
        self.assertEqual(self.place.call_count, 1)

    def test_manual_unknown_only_reconciles_never_resends(self):
        self.place.side_effect = TimeoutError('timeout')
        self.tick()
        m.retry_pending_stop(m.StopRetryRequest(entry_order_id='entry'))
        self.tick()
        self.assertEqual(self.place.call_count, 1)

    def test_dismiss_requires_explicit_unfilled_confirmation(self):
        self.query.return_value = None
        with self.assertRaises(m.HTTPException):
            m.dismiss_deleted_stop(m.StopDismissRequest(entry_order_id='entry'))
        m.dismiss_deleted_stop(m.StopDismissRequest(entry_order_id='entry', confirmed_cancelled_unfilled=True))
        self.place.assert_not_called()
        self.assertFalse(m._pending_stop_orders)
        self.assertEqual(m.get_pending_stop_orders().completed_orders[0].status, 'CLOSED_BY_USER')

    def test_dismiss_refuses_broker_failure_or_known_order(self):
        for result in [dict(status='SUBMITTED', fill_qty=0), dict(status='FILLED_ALL', fill_qty=10)]:
            self.query.return_value = result
            with self.assertRaises(m.HTTPException):
                m.dismiss_deleted_stop(m.StopDismissRequest(entry_order_id='entry', confirmed_cancelled_unfilled=True))
        self.query.side_effect = RuntimeError('rate limit')
        with self.assertRaises(m.HTTPException):
            m.dismiss_deleted_stop(m.StopDismissRequest(entry_order_id='entry', confirmed_cancelled_unfilled=True))
        self.assertIn('entry', m._pending_stop_orders)

    def test_batch_queries_do_not_grow_with_order_count(self):
        patch.stopall()
        class Context:
            calls = 0
            def __init__(self, **kwargs): pass
            def order_list_query(self, **kwargs):
                Context.calls += 1
                return 0, Rows([dict(order_id=str(i), order_status='SUBMITTED', dealt_qty=0, qty=10) for i in range(50)])
            def close(self): pass
        with patch.dict(sys.modules, {'futu': types.SimpleNamespace(RET_OK=0, OpenSecTradeContext=Context)}):
            for i in range(50):
                self.assertEqual(m._query_order_status_and_fill('localhost', 1, str(i), 42, 'REAL')['fill_qty'], 0)
        self.assertEqual(Context.calls, 1)

    def test_query_failures_cached_and_not_treated_as_cancel(self):
        patch.stopall()
        class Context:
            calls = 0
            def __init__(self, **kwargs): pass
            def order_list_query(self, **kwargs):
                Context.calls += 1
                return -1, 'rate limit'
            history_order_list_query = order_list_query
            def close(self): pass
        with patch.dict(sys.modules, {'futu': types.SimpleNamespace(RET_OK=0, OpenSecTradeContext=Context)}):
            for i in range(12):
                with self.assertRaises(RuntimeError): m._query_order_status_and_fill('localhost', 1, str(i), 42, 'REAL')
        self.assertEqual(Context.calls, 2)

    def test_actual_capacity_checks_existing_exit_orders(self):
        patch.stopall()
        class Context:
            def __init__(self, **kwargs): pass
            def position_list_query(self, **kwargs):
                return 0, Rows([dict(code='US.AAPL', qty=10, position_side='LONG')])
            def close(self): pass
        existing = {'s': dict(code='US.AAPL', trd_side='SELL', order_status='SUBMITTED', qty=7, dealt_qty=0)}
        with patch.dict(sys.modules, {'futu': types.SimpleNamespace(RET_OK=0, OpenSecTradeContext=Context)}), patch.object(m, '_broker_order_snapshot', return_value=(existing, None)):
            self.assertEqual(m._stop_capacity('localhost', 1, self.info, 3), 'available')
            with self.assertRaises(RuntimeError): m._stop_capacity('localhost', 1, self.info, 4)

    def test_entry_limit_sessions_and_types(self):
        patch.stopall()
        class IndexedRows(Rows):
            @property
            def iloc(self): return self.rows
        class Context:
            calls = []
            def __init__(self, **kwargs): pass
            def get_acc_list(self):
                return 0, Rows([dict(acc_id=42, trd_env='REAL', acc_status='ACTIVE'), dict(acc_id=43, trd_env='SIMULATE', acc_status='ACTIVE')])
            def place_order(self, **kwargs):
                Context.calls.append(kwargs)
                return 0, IndexedRows([dict(order_id='new-entry')])
            def close(self): pass
        enum = lambda **kwargs: types.SimpleNamespace(**kwargs)
        fake = enum(RET_OK=0, OpenSecTradeContext=Context,
                    TrdMarket=enum(US='US', HK='HK'), TrdEnv=enum(REAL='REAL', SIMULATE='SIMULATE'),
                    OrderType=enum(NORMAL='NORMAL', MARKET='MARKET', STOP='STOP'),
                    TimeInForce=enum(DAY='DAY', GTC='GTC'), TrdSide=enum(BUY='BUY', SELL='SELL'),
                    Session=enum(ALL='ALL', RTH='RTH'))
        with patch.dict(sys.modules, {'futu': fake}), patch.object(m, '_unlock_trade', return_value=True):
            m._place_order('AAPL', 100, 10, 'LIMIT', 'BUY', 'localhost', 1, trd_env='REAL', time_in_force='GTC')
            self.assertEqual(Context.calls[-1]['session'], 'ALL')
            self.assertEqual(Context.calls[-1]['price'], 100)
            m._place_order('AAPL', 100, 10, 'LIMIT', 'BUY', 'localhost', 1, trd_env='SIMULATE')
            self.assertEqual(Context.calls[-1]['order_type'], 'NORMAL')
            self.assertNotIn('session', Context.calls[-1])
            m._place_order('AAPL', 100, 10, 'MARKET', 'BUY', 'localhost', 1, trd_env='REAL', trigger_price=100)
            self.assertEqual(Context.calls[-1]['order_type'], 'STOP')
            self.assertEqual(Context.calls[-1]['session'], 'RTH')



if __name__ == '__main__': unittest.main()
