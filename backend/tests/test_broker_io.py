"""限速、合併、斷線及重複推送全部使用假 API，唔連券商。"""
import sys
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from broker_io import BrokerIO, Deferred, PushInbox


class BrokerTests(unittest.TestCase):
    def setUp(self):
        self.now = 1000.0
        self.io = BrokerIO(clock=lambda: self.now)
        self.ctx = Mock()
        self.ctx.order_list_query.return_value = (0, [{'order_id': 'one'}])

    def read(self, **kwargs):
        return self.io.read(self.ctx, 'order_list_query', 'host', 1, 'US', acc_id=42, trd_env='REAL', **kwargs)

    def test_fifty_simultaneous_readers_make_one_request(self):
        with ThreadPoolExecutor(max_workers=10) as pool:
            results = list(pool.map(lambda _: self.read(), range(50)))
        self.assertEqual(self.ctx.order_list_query.call_count, 1)
        results[0][1][0]['order_id'] = 'changed'
        self.assertEqual(self.read()[1][0]['order_id'], 'one')

    def test_cached_opend_reads_and_periodic_server_refresh(self):
        self.read()
        self.now += 10
        self.read()
        self.now += 51
        self.read()
        self.assertEqual([call.kwargs['refresh_cache'] for call in self.ctx.order_list_query.call_args_list], [True, False, True])

    def test_safety_check_forces_fresh_but_coalesces_burst(self):
        self.read()
        self.now += 4
        self.read(priority=True, fresh=True)
        self.read(priority=True, fresh=True)
        self.assertEqual(self.ctx.order_list_query.call_count, 2)
        self.assertTrue(self.ctx.order_list_query.call_args.kwargs['refresh_cache'])

    def test_priority_reserve_is_shared_across_markets(self):
        self.ctx.place_order.return_value = (0, {})
        for _ in range(8):
            self.io.command(self.ctx, 'place_order', 'host', 1, acc_id=42)
        with self.assertRaises(Deferred):
            self.io.command(self.ctx, 'place_order', 'host', 1, acc_id=42)
        for _ in range(2):
            self.io.command(self.ctx, 'place_order', 'host', 1, acc_id=42, priority=True)
        with self.assertRaises(Deferred):
            self.io.command(self.ctx, 'place_order', 'host', 1, acc_id=42, priority=True)
        self.assertEqual(self.ctx.place_order.call_count, 10)
        self.now += 30
        self.io.command(self.ctx, 'place_order', 'host', 1, acc_id=42)

    def test_rate_limit_cooldown_increases_and_blocks_repeated_calls(self):
        self.ctx.order_list_query.return_value = (-1, '查询频率太高')
        self.read()
        for _ in range(20):
            with self.assertRaises(Deferred): self.read(priority=True, fresh=True)
        self.assertEqual(self.ctx.order_list_query.call_count, 1)
        self.now += 30
        self.read(priority=True, fresh=True)
        self.now += 31
        with self.assertRaises(Deferred): self.read(priority=True, fresh=True)
        self.now += 30
        self.ctx.order_list_query.return_value = (0, [])
        self.read(priority=True, fresh=True)
        self.assertEqual(self.io.stats()['cooling_interfaces'], 0)

    def test_failed_fresh_query_cannot_return_old_success(self):
        self.read()
        self.now += 4
        self.ctx.order_list_query.return_value = (-1, 'disconnected')
        self.assertEqual(self.read(priority=True, fresh=True)[0], -1)
        with self.assertRaises(Deferred): self.read(priority=True, fresh=True)

    def test_submission_timeout_is_never_automatically_replayed(self):
        self.ctx.place_order.side_effect = TimeoutError('unknown')
        with self.assertRaises(TimeoutError):
            self.io.command(self.ctx, 'place_order', 'host', 1, acc_id=42, priority=True)
        self.assertEqual(self.ctx.place_order.call_count, 1)

    def test_quote_lists_share_result(self):
        self.ctx.get_market_snapshot.return_value = (0, [])
        for _ in range(10):
            self.io.read(self.ctx, 'get_market_snapshot', 'host', 1, 'QUOTE', code_list=['US.AAPL'])
        self.assertEqual(self.ctx.get_market_snapshot.call_count, 1)

    def test_duplicate_pushes_coalesce_and_overflow_triggers_full_reconcile(self):
        inbox = PushInbox()
        for _ in range(100): inbox.put('same')
        self.assertEqual(inbox.drain(), ({'same'}, False))
        self.assertFalse(inbox.event.is_set())
        for i in range(2000): inbox.put(str(i))
        ids, full = inbox.drain()
        self.assertLessEqual(len(ids), 1024)
        self.assertTrue(full)
        inbox.put()
        self.assertEqual(inbox.drain(), (set(), True))


if __name__ == '__main__': unittest.main()
