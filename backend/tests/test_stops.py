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
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location('broker_main', ROOT / 'main.py')
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
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
        m._broker_io = m.BrokerIO()
        m._push_inbox = m.PushInbox()
        m._push_fresh = set()
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

    def crossed_fill(self):
        m._update_pending_stop_order('entry', {'entry_price': 957, 'stop_loss_price': 941.36})
        self.query.return_value = dict(status='FILLED_ALL', fill_qty=10, fill_price=939.26)

    def test_crossed_fill_preserves_distance_and_audit(self):
        self.crossed_fill(); self.tick()
        self.assertEqual(self.place.call_args.args[4], 923.62)
        record = json.loads(m._ORDER_HISTORY_FILE.read_text())[0]
        self.assertEqual(record['original_stop_loss_price'], 941.36)
        self.assertEqual(record['stop_price_adjustment']['distance'], 15.64)
        self.assertEqual(record['stop_price_adjustment']['fill_price'], 939.26)
        self.assertTrue(any('stop_price_adjustment' in e['changes'] for e in record['events']))
        self.assertEqual(m.get_pending_stop_orders().completed_orders[0].stop_loss_price, 923.62)

    def test_prepared_repair_requires_user_submission(self):
        self.crossed_fill()
        m._update_pending_stop_order('entry', {'status': 'STOP_REPAIR_READY'})
        self.tick()
        self.place.assert_not_called()
        m.retry_pending_stop(m.StopRetryRequest(entry_order_id='entry'))
        self.tick()
        self.assertEqual(self.place.call_args.args[4], 923.62)

    def test_normal_fill_never_rebases_even_if_submission_price_rejected(self):
        self.crossed_fill()
        self.query.return_value['fill_price'] = 950
        self.place.return_value = dict(success=False, price_rejected=True, error='市價已下跌')
        self.tick()
        self.assertEqual(self.place.call_args.args[4], 941.36)
        self.assertNotIn('stop_price_adjustment', m._pending_stop_orders['entry'])

    def test_crossed_fill_short_and_equal_boundary(self):
        for fill in [110, 115]:
            result = m._crossed_fill_stop_adjustment(
                dict(direction='SHORT', entry_price=100, stop_loss_price=110), {'fill_price': fill})
            self.assertEqual(result['stop_loss_price'], fill + 10)
        self.assertEqual(m._crossed_fill_stop_adjustment(
            dict(entry_price=100, stop_loss_price=90), {'fill_price': 90})['stop_loss_price'], 80)

    def test_crossed_fill_missing_original_entry_requires_review(self):
        self.query.return_value['fill_price'] = 80
        self.tick()
        self.place.assert_not_called()
        self.assertEqual(m._pending_stop_orders['entry']['status'], 'FAILED_NEED_MANUAL')

    def test_existing_stop_never_rebases(self):
        for extra in [{'stop_loss_placed_qty': 3}, {'stop_order_ids': ['existing']}]:
            self.assertEqual(m._crossed_fill_stop_adjustment(
                dict(entry_price=100, stop_loss_price=90, **extra), {'fill_price': 80}), {})

    def test_adjustment_is_frozen_after_restart_and_preflight_defer(self):
        self.crossed_fill()
        self.place.return_value = dict(success=False, deferred=True, error='cooldown')
        self.tick()
        m._init_pending_stops_from_file(); self.retry_now()
        self.query.return_value['fill_price'] = 910
        self.place.return_value = dict(success=True, stop_order_id='retry-stop')
        self.tick()
        self.assertEqual([c.args[4] for c in self.place.call_args_list], [923.62, 923.62])

    def test_crossed_fill_unknown_does_not_resubmit(self):
        self.crossed_fill()
        self.place.side_effect = TimeoutError('timeout')
        self.tick(); self.retry_now(); self.tick()
        self.assertEqual(self.place.call_count, 1)
        self.assertEqual(m._pending_stop_orders['entry']['stop_loss_price'], 923.62)

    def test_partial_fill_stop_not_moved_for_later_fills(self):
        self.crossed_fill()
        self.query.return_value.update(status='FILLED_PART', fill_qty=4)
        self.tick()
        self.query.return_value.update(status='FILLED_ALL', fill_qty=10, fill_price=920)
        self.tick()
        self.assertEqual([c.args[3:5] for c in self.place.call_args_list], [(4, 923.62), (6, 923.62)])

    def test_invalid_fill_data_never_guesses_adjustment(self):
        for price in [None, 'N/A', float('nan'), 0, -1]:
            self.assertEqual(m._crossed_fill_stop_adjustment(
                dict(entry_price=100, stop_loss_price=90), {'fill_price': price}), {})
        with self.assertRaises(ValueError):
            m._crossed_fill_stop_adjustment(dict(entry_price=100, stop_loss_price=90), {'fill_price': 5})

    def test_explicit_price_rejection_waits_for_user_and_keeps_price(self):
        self.place.return_value = dict(success=False, price_rejected=True, error='價格被拒絕')
        self.tick()
        self.tick()
        self.assertEqual(self.place.call_count, 1)
        record = m._pending_stop_orders['entry']
        self.assertEqual(record['status'], 'STOP_PRICE_REJECTED')
        self.assertIsNone(record['stop_intent'])
        self.assertEqual(record['stop_loss_price'], 90)
        m.retry_pending_stop(m.StopRetryRequest(entry_order_id='entry'))
        self.place.return_value = dict(success=True, stop_order_id='retry-stop')
        self.tick()
        self.assertEqual(self.place.call_count, 2)
        self.assertEqual(self.place.call_args.args[4], 90)
        self.assertEqual(self.capacity.call_count, 2)

    def legacy_rejection(self):
        self.place.return_value = dict(success=False, ambiguous=True,
            error='下单失败。触发价输入需低于市价，请修改后重新提交。')
        self.tick()
        # The old monitor overwrote the broker response on its next reconciliation.
        m._update_pending_stop_order('entry', {'last_error': '止蝕提交結果未確認'})
        self.retry_now()

    def test_legacy_explicit_rejection_recovers_without_resubmission(self):
        self.legacy_rejection()
        m._init_pending_stops_from_file()
        self.retry_now()
        self.tick()
        record = m._pending_stop_orders['entry']
        self.assertEqual(record['status'], 'STOP_PRICE_REJECTED')
        self.assertIsNone(record['stop_intent'])
        self.assertIn('低於市價', record['last_error'])
        self.assertEqual(self.place.call_count, 1)

    def test_legacy_rejection_does_not_override_broker_matching_order(self):
        self.legacy_rejection()
        self.reconcile.return_value = {'stop_order_id': 'found'}
        self.tick()
        self.assertEqual(m._pending_stop_orders['entry']['stop_order_ids'], ['found'])
        self.assertEqual(self.place.call_count, 1)

    def test_legacy_rejection_does_not_clear_intent_when_query_fails(self):
        self.legacy_rejection()
        self.reconcile.return_value = {'query_error': 'NN_ProtoRet_TimeOut'}
        self.tick()
        record = m._pending_stop_orders['entry']
        self.assertEqual(record['status'], 'SUBMISSION_UNKNOWN')
        self.assertIsNotNone(record['stop_intent'])
        self.assertIn('NN_ProtoRet_TimeOut', record['last_error'])

    def test_older_rejection_cannot_clear_later_unknown_submission(self):
        self.legacy_rejection()
        m._update_pending_stop_order('entry', {'status': 'SUBMITTING_STOP'})
        m._update_pending_stop_order('entry', {'status': 'SUBMISSION_UNKNOWN', 'last_error': 'timeout'})
        self.tick()
        self.assertEqual(m._pending_stop_orders['entry']['status'], 'SUBMISSION_UNKNOWN')
        self.assertIsNotNone(m._pending_stop_orders['entry']['stop_intent'])

    def test_manual_price_retry_still_checks_existing_closing_orders(self):
        self.place.return_value = dict(success=False, price_rejected=True, error='價格被拒絕')
        self.tick()
        m.retry_pending_stop(m.StopRetryRequest(entry_order_id='entry'))
        self.capacity.side_effect = RuntimeError('已有平倉單')
        self.tick()
        self.assertEqual(self.place.call_count, 1)
        self.assertEqual(m._pending_stop_orders['entry']['status'], 'POSITION_REVIEW')

    def test_price_rejection_classifier_is_narrow(self):
        self.assertIn('低於', m._stop_price_rejection('下单失败。触发价输入需低于市价，请修改后重新提交。'))
        self.assertIn('高於', m._stop_price_rejection('下单失败。触发价输入需高于市价，请修改后重新提交。'))
        for error in ['timeout', 'NN_ProtoRet_TimeOut', '下单失败', '连接断开', '未知错误']:
            self.assertIsNone(m._stop_price_rejection(error))

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

    def test_push_wakes_tracking_but_never_trusts_fill_amount(self):
        m._pending_stop_orders['entry']['next_retry_at'] = 9999999999
        for _ in range(100): m._push_inbox.put('entry')
        self.assertEqual(m._drain_trade_push('localhost', 1), {'entry'})
        self.assertEqual(m._pending_stop_orders['entry']['filled_qty'], 0)
        self.assertEqual(m._pending_stop_orders['entry']['next_retry_at'], 0)
        self.place.assert_not_called()
        self.tick()
        self.assertEqual(self.place.call_count, 1)

    def test_reconnect_wakes_all_accounts_without_placing(self):
        m._push_inbox.put()
        self.assertEqual(m._drain_trade_push('localhost', 1), {'entry'})
        self.assertIn((42, 'REAL'), m._push_fresh)
        self.place.assert_not_called()

    def test_local_rate_deferral_keeps_automatic_retry_enabled(self):
        self.place.return_value = dict(success=False, deferred=True, error='cooldown')
        for _ in range(10):
            self.retry_now(); self.tick()
        info = m._pending_stop_orders['entry']
        self.assertEqual(info['status'], 'RETRY')
        self.assertIsNone(info['stop_intent'])
        self.assertEqual(info['stop_loss_retry_count'], 0)
        self.place.return_value = dict(success=True, stop_order_id='confirmed')
        self.retry_now(); self.tick()
        self.assertFalse(m._pending_stop_orders)

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
        with patch.dict(sys.modules, {'futu': fake}), patch.object(m, '_unlock_trade', return_value=True), patch.object(m, '_duplicate_entry_warning', return_value=None) as duplicate:
            m._place_order('AAPL', 100, 10, 'LIMIT', 'BUY', 'localhost', 1, trd_env='REAL', time_in_force='GTC')
            self.assertEqual(Context.calls[-1]['session'], 'ALL')
            self.assertEqual(Context.calls[-1]['price'], 100)
            m._place_order('AAPL', 100, 10, 'LIMIT', 'BUY', 'localhost', 1, trd_env='SIMULATE')
            self.assertEqual(Context.calls[-1]['order_type'], 'NORMAL')
            self.assertNotIn('session', Context.calls[-1])
            m._place_order('AAPL', 100, 10, 'MARKET', 'BUY', 'localhost', 1, trd_env='REAL', trigger_price=100)
            self.assertEqual(Context.calls[-1]['order_type'], 'STOP')
            self.assertEqual(Context.calls[-1]['session'], 'RTH')
            with patch.object(m, '_entry_quote', return_value={'tradingQuoteValid':True,'lastPrice':1608.5,'priceSessionLabel':'夜盤'}):
                m._place_order('ASML', 1596, 10, 'LIMIT', 'BUY', 'localhost', 1, trd_env='REAL', auto_entry=True)
                self.assertEqual(Context.calls[-1]['order_type'], 'NORMAL')
                self.assertEqual(Context.calls[-1]['session'], 'ALL')
                self.assertEqual(Context.calls[-1]['price'], 1596)
                self.assertNotIn('aux_price', Context.calls[-1])
                m._place_order('ASML', 1620, 10, 'LIMIT', 'SELL', 'localhost', 1, trd_env='REAL', auto_entry=True)
                self.assertEqual(Context.calls[-1]['order_type'], 'NORMAL')
            duplicate.return_value = {'success': False, 'status': 'duplicate_confirmation_required', 'duplicate_orders': [{'order_id': 'old'}]}
            before = len(Context.calls)
            result = m._place_order('AAPL', 100, 10, 'LIMIT', 'BUY', 'localhost', 1, trd_env='REAL')
            self.assertFalse(result['success'])
            self.assertEqual(len(Context.calls), before)

    def duplicate_check(self, rows, confirmed=None, error=None, records=None):
        with patch.object(m, '_broker_order_snapshot', return_value=(rows, error)), patch.object(m, '_load_order_history_from_file', return_value=records or []):
            return m._duplicate_entry_warning('localhost', 1, 'US', 42, 'REAL', 'US.SNDK', 'BUY', confirmed)

    def test_duplicate_partial_and_waiting_orders_require_confirmation(self):
        rows = {'one': dict(code='US.SNDK', trd_side='BUY', order_status='FILLED_PART', qty=9, dealt_qty=2, price=1585, order_type='NORMAL'),
            'two': dict(code='US.SNDK', trd_side='BUY', order_status='WAITING_SUBMIT', qty=9, dealt_qty=0, price=1586, order_type='NORMAL')}
        warning = self.duplicate_check(rows)
        self.assertEqual([r['remaining_qty'] for r in warning['duplicate_orders']], [7, 9])
        self.assertIsNone(self.duplicate_check(rows, ['one', 'two']))
        self.assertIsNotNone(self.duplicate_check(rows, ['one']))

    def test_duplicate_excludes_completed_cancelled_opposite_side_and_other_stock(self):
        base = dict(code='US.SNDK', trd_side='BUY', order_status='SUBMITTED', qty=9, dealt_qty=0)
        for change in [{'order_status': 'FILLED_ALL'}, {'order_status': 'CANCELLED_ALL'}, {'trd_side': 'SELL'}, {'code': 'US.MU'}]:
            self.assertIsNone(self.duplicate_check({'one': {**base, **change}}))

    def test_duplicate_local_record_covers_broker_cache_delay_and_account_scope(self):
        record = dict(entry_order_id='new', symbol='SNDK', acc_id=42, trd_env='REAL', quantity=9, filled_qty=0, status='SUBMITTED', direction='LONG')
        self.assertIsNotNone(self.duplicate_check({}, records=[record]))
        for change in [{'acc_id': 43}, {'trd_env': 'SIMULATE'}, {'completed': True}]:
            self.assertIsNone(self.duplicate_check({}, records=[{**record, **change}]))
        self.assertIsNone(self.duplicate_check({'new': {'order_status': 'CANCELLED_ALL'}}, records=[record]))

    def test_duplicate_query_failure_does_not_allow_submission(self):
        with self.assertRaisesRegex(ValueError, '尚未提交新單'):
            self.duplicate_check({}, error='timeout')

    def test_duplicate_response_is_forwarded_without_success(self):
        result = {'success': False, 'status': 'duplicate_confirmation_required', 'message': '請確認', 'duplicate_orders': [{'order_id': 'old'}]}
        with patch.object(m, '_place_order', return_value=result) as submit:
            response = m.place_order(m.OrderRequest(symbol='SNDK', price=100, quantity=9, confirmed_duplicate_ids=['old']))
        self.assertFalse(response.success)
        self.assertEqual(response.duplicate_orders, result['duplicate_orders'])
        self.assertEqual(submit.call_args.kwargs['confirmed_duplicate_ids'], ['old'])



if __name__ == '__main__': unittest.main()
