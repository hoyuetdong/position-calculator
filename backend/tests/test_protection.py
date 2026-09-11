"""持續核對測試只使用假券商，不連線或下單。"""
import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch
from test_stops import m, Rows
from protection import coverage, transition, timeline_event


class Protection(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_path = m._ORDER_HISTORY_FILE
        m._ORDER_HISTORY_FILE = Path(self.temp.name) / 'order_history.json'
        self.record = {'entry_order_id': 'entry', 'symbol': 'AAPL', 'acc_id': 42, 'trd_env': 'REAL',
            'direction': 'LONG', 'quantity': 10, 'stop_loss_price': 90, 'completed': True, 'stop_order_ids': ['stop']}
        m._atomic_json(m._ORDER_HISTORY_FILE, [self.record])
        self.positions = [{'code': 'US.AAPL', 'qty': 10, 'position_side': 'LONG'}]
        self.stop = {'code': 'US.AAPL', 'qty': 10, 'dealt_qty': 0, 'trd_side': 'SELL',
            'order_type': 'STOP', 'order_status': 'SUBMITTED', 'aux_price': 90}
        self.orders = {'stop': self.stop}
        self.error = None
        self.context = types.SimpleNamespace(position_list_query=lambda **kw: (0, Rows(self.positions)), close=lambda: None)
        self.patches = [patch.dict('sys.modules', {'futu': types.SimpleNamespace(RET_OK=0, OpenSecTradeContext=lambda **kw: self.context)}),
            patch.object(m, '_ManagedContext', side_effect=lambda ctx, *a, **kw: ctx),
            patch.object(m, '_broker_order_snapshot', side_effect=lambda *a: (self.orders, self.error)),
            patch.object(m, '_get_pending_stop_orders', return_value={}),
            patch.object(m, '_test_opend_connection', return_value=True),
            patch.object(m, '_broker_io', m.BrokerIO()),
            patch.object(m, '_place_stop_order', side_effect=AssertionError('audit must never trade'))]
        for p in self.patches: p.start()

    def tearDown(self):
        for p in reversed(self.patches): p.stop()
        m._ORDER_HISTORY_FILE = self.old_path
        self.temp.cleanup()

    def audit(self):
        m._audit_protection('fake', 0)
        return m._load_protection()

    def test_cancel_dedup_restart_recovery_and_no_trades(self):
        self.assertEqual(self.audit()['notifications'], [])
        self.stop['order_status'] = 'CANCELLED_ALL'
        state = self.audit()
        self.assertEqual(len(state['notifications']), 1)
        self.assertEqual(next(iter(state['checks'].values()))['status'], 'UNDER_PROTECTED')
        # 每次核對均從磁碟重新載入，重啟後亦不重複通知。
        self.assertEqual(len(self.audit()['notifications']), 1)
        self.stop['order_status'] = 'SUBMITTED'
        state = self.audit()
        self.assertEqual([n['kind'] for n in state['notifications']], ['warning', 'recovered'])
        events = m._load_order_history_from_file()[0]['events']
        self.assertEqual(len(events), 3)

    def test_query_failure_keeps_existing_alert_and_last_success(self):
        self.stop['order_status'] = 'DISABLED'
        before = self.audit()
        self.error = 'API cooldown'
        after = self.audit()
        self.assertEqual(after['last_success_at'], before['last_success_at'])
        self.assertEqual(after['system_status'], 'DEGRADED')
        self.assertTrue(after['conditions']['coverage:42:REAL:US.AAPL:LONG']['active'])
        self.assertFalse(any(n['kind'] == 'recovered' for n in after['notifications']))

    def test_fill_and_manual_position_close(self):
        self.stop['order_status'] = 'FILLED_PART'
        self.stop['dealt_qty'] = 4
        self.positions[0]['qty'] = 6
        self.assertEqual(next(iter(self.audit()['checks'].values()))['status'], 'COVERED')
        self.positions[0]['qty'] = 0
        self.assertEqual(next(iter(self.audit()['checks'].values()))['status'], 'EXCESS_STOP')
        self.stop['order_status'] = 'FILLED_ALL'
        self.stop['dealt_qty'] = 10
        self.assertEqual(next(iter(self.audit()['checks'].values()))['status'], 'NO_POSITION')

    def test_short_and_unconfirmed_or_wrong_side_order(self):
        positions = [{'code': 'US.AAPL', 'qty': -10, 'position_side': 'SHORT'}]
        self.assertEqual(coverage('US.AAPL', 'SHORT', positions, [self.stop])['protected_qty'], 0)
        self.stop['trd_side'] = 'BUY_BACK'
        self.assertEqual(coverage('US.AAPL', 'SHORT', positions, [self.stop])['status'], 'COVERED')
        self.stop['order_status'] = 'SUBMITTING'
        self.assertEqual(coverage('US.AAPL', 'SHORT', positions, [self.stop])['status'], 'UNDER_PROTECTED')

    def test_unknown_link_recorded_and_not_mistaken_for_active_stop(self):
        self.orders = {}
        state = self.audit()
        self.assertEqual(state['linked_stops']['entry']['statuses']['stop'], 'UNKNOWN')
        self.assertEqual(next(iter(state['checks'].values()))['protected_qty'], 0)

    def test_timeline_merge_search_and_traditional_warning(self):
        m._sync_history('entry', {'status': 'RETRY', 'last_error': '订单失败，请检查账户'})
        m._sync_history('entry', {'status': 'RETRY', 'last_error': '订单失败，请检查账户'})
        result = m.order_history('aap')
        record = result['orders'][0]
        self.assertEqual(len(record['events']), 1)
        self.assertEqual(record['stop_loss_price'], 90)
        self.assertNotIn('acc_id', record)
        self.assertEqual(record['events'][0]['changes']['last_error'], '訂單失敗，請檢查賬戶')
        self.assertEqual(m.order_history('TSLA')['total'], 0)
        self.assertIsNone(timeline_event({'status': 'x'}, {'status': 'x'}))

    def test_stale_status_and_notification_bound(self):
        state = self.audit()
        state['last_attempt_at'] = '2020-01-01T00:00:00+00:00'
        m._atomic_json(m._ORDER_HISTORY_FILE.with_name('protection_state.json'), state)
        self.assertEqual(m.protection_status()['system_status'], 'STALE')
        for i in range(250): transition(state, str(i), True, '异常')
        self.assertEqual(len(state['notifications']), 200)

    def test_entry_fill_timeline(self):
        self.orders['entry'] = {'order_status': 'FILLED_ALL', 'dealt_qty': 10}
        self.audit(); self.audit()
        events = m._load_order_history_from_file()[0]['events']
        entry_events = [e for e in events if e['kind'] == 'ENTRY_CHECK']
        self.assertEqual(len(entry_events), 1)
        self.assertEqual(entry_events[0]['changes']['filled_qty'], 10)

    def test_disconnection_and_recovery_are_deduplicated(self):
        with patch.object(m, '_test_opend_connection', return_value=False):
            self.assertEqual(self.audit()['system_status'], 'DISCONNECTED')
            self.assertEqual(len(self.audit()['notifications']), 1)
        state = self.audit()
        self.assertEqual([n['kind'] for n in state['notifications']], ['warning', 'recovered'])

    def test_unknown_submission_only_alerts_after_five_minutes(self):
        pending = {'uncertain': {'symbol': 'AAPL', 'status': 'SUBMISSION_UNKNOWN'}}
        with patch.object(m, '_get_pending_stop_orders', return_value=pending), patch.object(m.time, 'time', return_value=1000):
            self.assertEqual(self.audit()['notifications'], [])
        with patch.object(m, '_get_pending_stop_orders', return_value=pending), patch.object(m.time, 'time', return_value=1301):
            self.assertEqual(len(self.audit()['notifications']), 1)
            self.assertEqual(len(self.audit()['notifications']), 1)
        pending['uncertain']['status'] = 'pending'
        with patch.object(m, '_get_pending_stop_orders', return_value=pending):
            self.assertEqual(self.audit()['notifications'][-1]['kind'], 'recovered')
