import sys
import types
import unittest
from datetime import datetime,timezone
from unittest.mock import patch,Mock
from session_quote import select_quote
from test_stops import m


class SessionQuotes(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,9,15,7,11,20,tzinfo=timezone.utc)
        self.row=dict(last_price=1575.15,prev_close_price=1698.3,update_time='2026-09-15 03:11:15.635',
            overnight_price=1608.5,overnight_change_val=33.35,overnight_change_rate=2.12,
            pre_price=1594.07,pre_change_val=-104.23,pre_change_rate=-6.14,
            after_price=1589.97,after_change_val=14.82,after_change_rate=.94)
    def quote(self,state):return select_quote(self.row,state,self.now)
    def test_overnight_uses_overnight_not_regular_or_old_premarket(self):
        q=self.quote('OVERNIGHT')
        self.assertEqual(q['lastPrice'],1608.5)
        self.assertEqual(q['regularPrice'],1575.15)
        self.assertTrue(q['tradingQuoteValid'])
        self.assertEqual(q['change'],33.35)
    def test_premarket_and_afterhours_use_matching_fields(self):
        self.assertEqual(self.quote('PRE_MARKET_BEGIN')['lastPrice'],1594.07)
        self.assertEqual(self.quote('AFTER_HOURS_BEGIN')['lastPrice'],1589.97)
    def test_rth_ignores_old_extended_prices(self):
        q=self.quote('MORNING')
        self.assertEqual(q['lastPrice'],1575.15)
        self.assertAlmostEqual(q['change'],-123.15)
    def test_unknown_or_closed_state_cannot_authorize_auto_order(self):
        for state in ['CLOSED','NONE','AFTER_HOURS_END','NIGHT_OPEN']:
            self.assertFalse(self.quote(state)['tradingQuoteValid'])
    def test_missing_zero_nan_extended_price_never_uses_regular_for_order(self):
        for value in [None,0,float('nan')]:
            self.row['overnight_price']=value
            q=self.quote('OVERNIGHT');self.assertFalse(q['tradingQuoteValid'])
            self.assertEqual(q['priceSessionLabel'],'參考價')
    def test_stale_snapshot_blocks_auto_selection(self):
        self.row['update_time']='2026-09-14 16:00:00'
        self.assertFalse(self.quote('OVERNIGHT')['tradingQuoteValid'])
    def test_future_timestamp_blocks_auto_selection(self):
        self.row['update_time']='2026-09-15 04:00:00'
        self.assertFalse(self.quote('OVERNIGHT')['tradingQuoteValid'])
    def test_standard_time_uses_new_york_dst_rules(self):
        self.row['update_time']='2026-12-15 03:11:15'
        q=select_quote(self.row,'OVERNIGHT',datetime(2026,12,15,8,11,20,tzinfo=timezone.utc))
        self.assertTrue(q['tradingQuoteValid'])
    def test_guard_rejects_wrong_auto_stop_without_opening_trade_context(self):
        ctx=Mock()
        fake=types.SimpleNamespace(TrdMarket=types.SimpleNamespace(US='US',HK='HK'),OpenSecTradeContext=ctx)
        with patch.dict(sys.modules,{'futu':fake}),patch.object(m,'_entry_quote',return_value=self.quote('OVERNIGHT')):
            with self.assertRaisesRegex(ValueError,'訂單類型需要重新確認'):
                m._place_order('ASML',1596,10,'MARKET','BUY','localhost',11111,trigger_price=1596,auto_entry=True)
            ctx.assert_not_called()
    def test_guard_rejects_stale_data_before_trade_context(self):
        self.row['update_time']='2026-09-14 16:00:00'
        ctx=Mock();fake=types.SimpleNamespace(TrdMarket=types.SimpleNamespace(US='US',HK='HK'),OpenSecTradeContext=ctx)
        with patch.dict(sys.modules,{'futu':fake}),patch.object(m,'_entry_quote',return_value=self.quote('OVERNIGHT')):
            with self.assertRaisesRegex(ValueError,'尚未提交訂單'):
                m._place_order('ASML',1596,10,'LIMIT','BUY','localhost',11111,auto_entry=True)
            ctx.assert_not_called()
