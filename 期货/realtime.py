# -*- coding: utf-8 -*-
"""商品期货盘中报价：独立于 EOD 决策管道的一条只读旁路。

只做一件事：按新浪 nf_ 接口取内盘期货最新价与买卖一档。
不写 MySQL、不写快照、不参与评分，避免污染收盘口径的 data_hash。
新浪是公开网页接口，非官方、无 SLA，失败一律降级为空报价而不是抛错。
"""
import threading
import time
from datetime import datetime

import requests

SINA_URL = 'https://hq.sinajs.cn/list='
HEADERS = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
           'Referer': 'https://finance.sina.com.cn'}
CHUNK_SIZE = 30
CACHE_SECONDS = 5.0
REQUEST_TIMEOUT = 10.0

# 新浪内盘期货字段位次；已用东财同一时刻数据交叉验证（开高低/最新/昨结/买卖一档/持仓成交）
POSITIONS = {0: 'name', 1: 'time', 2: 'open', 3: 'high', 4: 'low', 6: 'bid', 7: 'ask',
             8: 'last', 10: 'pre_settle', 11: 'bid_volume', 12: 'ask_volume',
             13: 'oi', 14: 'volume', 15: 'exchange', 16: 'product', 17: 'date'}
NUMERIC = {'open', 'high', 'low', 'bid', 'ask', 'last', 'pre_settle',
           'bid_volume', 'ask_volume', 'oi', 'volume'}
MIN_FIELDS = 18

_CACHE = {}
_CACHE_LOCK = threading.Lock()


def _number(raw):
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _clock(raw):
    text = str(raw or '').strip()
    if len(text) == 6 and text.isdigit():
        return '%s:%s:%s' % (text[:2], text[2:4], text[4:6])
    return None


def age_seconds(quote, now=None):
    """报价时间距现在多少秒，供前端判断这条报价是否已经过期。"""
    stamp = '%s %s' % (quote.get('date') or '', quote.get('time') or '')
    try:
        taken = datetime.strptime(stamp, '%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError):
        return None
    return max(0.0, ((now or datetime.now()) - taken).total_seconds())


def parse_quote(symbol, payload):
    """解析 `var hq_str_nf_CU2610="..."` 引号内的内容；字段不足或没有任何价格时返回 None。"""
    parts = str(payload or '').split(',')
    if len(parts) < MIN_FIELDS:
        return None
    quote = {'ts_code': symbol}
    for index, key in POSITIONS.items():
        raw = parts[index].strip()
        quote[key] = _number(raw) if key in NUMERIC else raw
    if quote['last'] is None and quote['bid'] is None:
        return None
    quote['time'] = _clock(quote['time'])
    pre_settle = quote['pre_settle']
    quote['change_pct'] = ((quote['last'] / pre_settle - 1) * 100
                           if quote['last'] is not None and pre_settle else None)
    quote['spread'] = (quote['ask'] - quote['bid']
                       if quote['ask'] is not None and quote['bid'] is not None else None)
    quote['age_seconds'] = age_seconds(quote)
    return quote


def _lines(text):
    """从新浪返回的 `var hq_str_nf_xxx="...";` 文本里取出 (symbol, payload)。"""
    for chunk in str(text or '').split(';'):
        if 'hq_str_nf_' not in chunk or '="' not in chunk:
            continue
        symbol = chunk.split('hq_str_nf_', 1)[1].split('=', 1)[0].strip().upper()
        payload = chunk.split('="', 1)[1]
        if symbol:
            yield symbol, payload


def fetch_quotes(codes, timeout=REQUEST_TIMEOUT, get=None):
    """按 ts_code 列表取报价，返回 (quotes, error)；网络与解析失败都不抛异常。"""
    wanted = {str(code).split('.')[0].upper(): code for code in codes if code}
    if not wanted:
        return {}, None
    requester = get or requests.get
    quotes, failures = {}, []
    symbols = sorted(wanted)
    for start in range(0, len(symbols), CHUNK_SIZE):
        batch = symbols[start:start + CHUNK_SIZE]
        try:
            response = requester(SINA_URL + ','.join('nf_' + item for item in batch),
                                 headers=HEADERS, timeout=timeout)
            response.raise_for_status()
            text = response.text
        except Exception as exc:
            failures.append(type(exc).__name__)
            continue
        for symbol, payload in _lines(text):
            code = wanted.get(symbol)
            quote = parse_quote(code, payload) if code else None
            if quote:
                quotes[code] = quote
    if failures:
        return quotes, '新浪行情请求失败（%s）' % '、'.join(sorted(set(failures)))
    if not quotes:
        return quotes, '新浪行情没有返回可用报价'
    return quotes, None


def snapshot(codes, timeout=REQUEST_TIMEOUT, ttl=CACHE_SECONDS, get=None, now=None):
    """带短 TTL 缓存的报价快照；同一批合约在 TTL 内只打一次上游，失败结果同样缓存以免反复重试。"""
    key = tuple(sorted(str(code) for code in codes if code))
    if not key:
        return dict(quotes={}, error=None, cached=False)
    moment = time.monotonic() if now is None else now
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
        if hit is not None and moment - hit['at'] < ttl:
            return dict(hit['value'], cached=True)
    quotes, error = fetch_quotes(key, timeout=timeout, get=get)
    value = dict(quotes=quotes, error=error)
    with _CACHE_LOCK:
        _CACHE[key] = dict(at=moment, value=value)
    return dict(value, cached=False)


def clear_cache():
    with _CACHE_LOCK:
        _CACHE.clear()
