"""按券商回報的交易時段選價；缺少時段報價時不可拿收市價作下單判斷。"""
import math
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

SESSIONS = {
    'OVERNIGHT': ('OVERNIGHT', '夜盤', 'overnight'),
    'PRE_MARKET_BEGIN': ('PRE', '盤前', 'pre'),
    'AFTER_HOURS_BEGIN': ('POST', '盤後', 'after'),
    'MORNING': ('RTH', '盤中', ''), 'AFTERNOON': ('RTH', '盤中', ''),
}


def number(value):
    try:
        value=float(value)
        return value if math.isfinite(value) else None
    except (ValueError, TypeError): return None


def select_quote(row, state, now=None):
    now=now or datetime.now(timezone.utc)
    session,label,prefix=SESSIONS.get(str(state), ('CLOSED','非交易時段',''))
    regular=number(row.get('last_price'))
    selected=number(row.get(prefix+'_price' if prefix else 'last_price'))
    timestamp=str(row.get('update_time') or '')
    recent=False
    try:
        updated=datetime.fromisoformat(timestamp).replace(tzinfo=ZoneInfo('America/New_York'))
        recent=-30 <= (now-updated).total_seconds() <= 180
    except (ValueError,TypeError): pass
    valid=session!='CLOSED' and selected is not None and selected>0 and recent
    change=number(row.get(prefix+'_change_val')) if prefix else None
    if not prefix and regular:
        previous=number(row.get('prev_close_price'))
        change=regular-previous if previous and previous>0 else None
    change_percent=number(row.get(prefix+'_change_rate')) if prefix else None
    if not prefix and change is not None:
        base=regular-change
        change_percent=change/base*100 if base>0 else None
    warning='' if valid else ('目前不在可核對的交易時段' if session=='CLOSED' else f'未取得有效的{label}報價，請稍後重新核對')
    return dict(lastPrice=selected if valid else regular, regularPrice=regular,
        change=change if valid else None, changePercent=change_percent if valid else None,
        priceSession=session, priceSessionLabel=label if valid else '參考價',
        priceTime=timestamp, priceTimezone='America/New_York', priceCheckedAt=now.isoformat(),
        priceSource='futu', tradingQuoteValid=valid, priceWarning=warning)


def install(m):
    def read(symbol):
        import futu
        code=m._to_futu_code(symbol)
        if not code.startswith('US.'): raise ValueError('此報價核對僅適用於美股')
        host=m._get_futu_host();port=int(m.os.getenv('FUTU_PORT','11111'))
        ctx=m._ManagedContext(futu.OpenQuoteContext(host=host,port=port),host,port,'QUOTE',priority=True)
        try:
            ret,states=ctx.get_market_state(code_list=[code])
            if ret!=futu.RET_OK: raise ValueError('未能核對交易時段：'+str(states))
            matching=[r for _,r in states.iterrows() if str(r.get('code'))==code]
            if len(matching)!=1: raise ValueError('交易時段資料不完整')
            ret,rows=ctx.get_market_snapshot(code_list=[code])
            if ret!=futu.RET_OK: raise ValueError('未能核對即時報價：'+str(rows))
            quotes=[r for _,r in rows.iterrows() if str(r.get('code'))==code]
            if len(quotes)!=1: raise ValueError('報價資料不完整')
            return dict(select_quote(quotes[0],matching[0]['market_state']),symbol=code[3:])
        finally: ctx.close()
    m._entry_quote=read
