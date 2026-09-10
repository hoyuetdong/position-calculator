"""富途共用查詢、限速及退避；唔會自行重送任何交易指令。"""
import copy
import threading
import time
from collections import deque


class Deferred(RuntimeError):
    pass


class BrokerIO:
    # 留餘量俾其他程式；普通查詢再預留兩個名額俾止蝕核對。
    LIMITS = {'order_list_query': 6, 'position_list_query': 6, 'accinfo_query': 6,
              'history_order_list_query': 4, 'place_order': 10,
              'get_market_snapshot': 30, 'request_history_kline': 20,
              'subscribe': 10, 'unlock_trade': 8, 'get_acc_list': 6}
    TTL = {'order_list_query': 3, 'position_list_query': 5, 'accinfo_query': 30,
           'history_order_list_query': 300, 'get_acc_list': 30,
           'get_market_snapshot': 2, 'request_history_kline': 300}
    REFRESHABLE = {'order_list_query', 'position_list_query', 'accinfo_query'}

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.lock = threading.RLock()
        self.read_locks = {}
        self.windows = {}
        self.cooldowns = {}
        self.failures = {}
        self.cache = {}
        self.forced_at = {}
        self.metrics = {'server_requests': 0, 'cache_hits': 0, 'deferred': 0, 'rate_limits': 0}

    def _bucket(self, host, port, name, kwargs):
        # 同帳戶唔同市場／視窗共用額度。
        return (host, port, name, kwargs.get('acc_id', 0))

    def _reserve(self, bucket, priority):
        now = self.clock()
        window = self.windows.setdefault(bucket, deque())
        while window and now - window[0] >= 30:
            window.popleft()
        cap = self.LIMITS.get(bucket[2], 4)
        allowance = cap if priority else max(1, cap - 2)
        if now < self.cooldowns.get(bucket, 0) or len(window) >= allowance:
            self.metrics['deferred'] += 1
            raise Deferred('API 正在限速／冷卻，已延後處理，唔會密集重試')
        window.append(now)
        self.metrics['server_requests'] += 1

    def _outcome(self, bucket, result):
        if result[0] == 0:
            self.failures.pop(bucket, None)
            self.cooldowns.pop(bucket, None)
            return
        message = str(result[1]).lower()
        rate_limited = any(word in message for word in ('频率', '頻率', 'frequency', 'rate limit', 'too frequent'))
        count = min(self.failures.get(bucket, 0) + 1, 5)
        self.failures[bucket] = count
        self.cooldowns[bucket] = self.clock() + min(300, (30 if rate_limited else 5) * 2 ** (count - 1))
        if rate_limited:
            self.metrics['rate_limits'] += 1

    def read(self, ctx, name, host, port, market, *, priority=False, fresh=False, **kwargs):
        def freeze(value):
            if isinstance(value, (list, tuple)):
                return tuple(freeze(item) for item in value)
            if isinstance(value, dict):
                return tuple(sorted((k, freeze(v)) for k, v in value.items()))
            return value
        key = (host, port, market, name, freeze(kwargs))
        bucket = self._bucket(host, port, name, kwargs)
        with self.lock:
            singleflight = self.read_locks.setdefault(bucket, threading.Lock())
        # 慢行情查詢唔可以阻塞另一個接口嘅止蝕核對。
        with singleflight:
            with self.lock:
                now = self.clock()
                last_force = self.forced_at.get(key, float('-inf'))
                force = name in self.REFRESHABLE and (now - last_force >= 60 or (fresh and now - last_force >= 2))
                cached = self.cache.get(key)
                if cached and now - cached[0] < self.TTL.get(name, 5) and not force:
                    self.metrics['cache_hits'] += 1
                    return copy.deepcopy(cached[1])
                if now < self.cooldowns.get(bucket, 0):
                    self.metrics['deferred'] += 1
                    raise Deferred('券商 API 冷卻中，稍後自動再核對')
                params = dict(kwargs)
                if name in self.REFRESHABLE:
                    params['refresh_cache'] = force
                if force or name not in self.REFRESHABLE:
                    self._reserve(bucket, priority)
            try:
                result = getattr(ctx, name)(**params)
            except Exception:
                with self.lock:
                    self._outcome(bucket, (-1, 'connection error'))
                raise
            with self.lock:
                if force or name not in self.REFRESHABLE or result[0] != 0:
                    self._outcome(bucket, result)
                if result[0] == 0:
                    if force:
                        self.forced_at[key] = self.clock()
                    self.cache[key] = (self.clock(), copy.deepcopy(result))
                self._prune()
            return result

    def command(self, ctx, name, host, port, *, priority=False, **kwargs):
        bucket = self._bucket(host, port, name, kwargs)
        with self.lock:
            self._reserve(bucket, priority)
        # 寫入操作不快取、不自動重播，逾時由持久化意圖核對。
        try:
            result = getattr(ctx, name)(**kwargs)
        except Exception:
            with self.lock:
                self._outcome(bucket, (-1, 'connection error'))
            raise
        with self.lock:
            self._outcome(bucket, result)
        return result

    def invalidate(self, host, port, account=None, history=False):
        with self.lock:
            for key in list(self.cache):
                params = dict(key[4])
                eligible = key[3] in self.REFRESHABLE or (history and key[3] == 'history_order_list_query')
                if eligible and key[:2] == (host, port) and (account is None or params.get('acc_id') == account):
                    self.cache.pop(key, None)
            # 保留 last_force，推送風暴亦唔會繞過兩秒合併與額度。

    def _prune(self):
        now = self.clock()
        for key, item in list(self.cache.items()):
            if now - item[0] > 600:
                self.cache.pop(key, None)
                self.forced_at.pop(key, None)
        for key, stamp in list(self.forced_at.items()):
            if key not in self.cache and now - stamp > 600:
                self.forced_at.pop(key, None)

    def stats(self):
        with self.lock:
            return {**self.metrics, 'cooling_interfaces': sum(self.clock() < t for t in self.cooldowns.values())}


class PushInbox:
    """推送只記低要核對嘅 ID；唔喺 SDK callback 入面查詢或落單。"""
    def __init__(self):
        self.lock = threading.Lock()
        self.event = threading.Event()
        self.ids = set()
        self.reconnect = False
        self.received = 0

    def put(self, order_id=None):
        with self.lock:
            self.received += 1
            if order_id and len(self.ids) < 1024:
                self.ids.add(str(order_id))
            else:
                self.reconnect = True
            self.event.set()

    def drain(self):
        with self.lock:
            result = (self.ids, self.reconnect)
            self.ids, self.reconnect = set(), False
            self.event.clear()
            return result
