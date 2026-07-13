import json
import os
import time
from urllib import request, parse


from . import get_module_logger
from .candles import Candle, candles_to_csv, candles_from_csv


logger = get_module_logger()


BINANCE_KLINES_URL = 'https://api.binance.com/api/v3/klines'

# Binanceのintervalと秒数の対応
INTERVAL_SECONDS = {
    '1m': 60,
    '5m': 300,
    '15m': 900,
    '1h': 3600,
    '4h': 14400,
    '1d': 86400,
}


def fetch_binance_klines(symbol, interval, start_ms, end_ms=None, request_wait=0.2):
    # Binanceの公開APIからローソク足を取得する（認証不要）
    # start_ms から end_ms（省略時は現在）までページングしながら全件取得する
    candles = []
    cursor = start_ms
    if end_ms is None:
        end_ms = int(time.time() * 1000)

    while cursor < end_ms:
        params = parse.urlencode({
            'symbol': symbol,
            'interval': interval,
            'startTime': cursor,
            'endTime': end_ms,
            'limit': 1000,
        })
        url = f'{BINANCE_KLINES_URL}?{params}'
        logger.debug(f'call api: {url}')
        with request.urlopen(url, timeout=30) as response:
            rows = json.loads(response.read())
        if not rows:
            break
        for row in rows:
            candles.append(Candle(
                time=int(row[0] // 1000),
                open=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
                volume=float(row[5]),
            ))
        # 次のページへ（最後の足の次から）
        cursor = rows[-1][0] + 1
        if len(rows) < 1000:
            break
        time.sleep(request_wait)  # レート制限対策

    return candles


def load_or_fetch(symbol, interval, start_ms, cache_dir, refresh=False):
    # キャッシュがあればCSVから読み込み、なければBinanceから取得して保存する
    path = os.path.join(cache_dir, f'{symbol}_{interval}.csv')
    if not refresh and os.path.exists(path):
        logger.debug(f'load candles from cache: {path}')
        return candles_from_csv(path)

    logger.info(f'fetch candles from binance: {symbol} {interval}')
    candles = fetch_binance_klines(symbol, interval, start_ms)
    candles_to_csv(candles, path)
    logger.info(f'saved {len(candles)} candles to {path}')
    return candles


def fetch_recent_binance_klines(symbol, interval, limit=500):
    # 直近のローソク足を取得する（リアルタイムのシグナル計算用）
    # 最後の1本は未確定足なので注意
    params = parse.urlencode({
        'symbol': symbol,
        'interval': interval,
        'limit': limit,
    })
    url = f'{BINANCE_KLINES_URL}?{params}'
    logger.debug(f'call api: {url}')
    with request.urlopen(url, timeout=30) as response:
        rows = json.loads(response.read())
    return [Candle(
        time=int(row[0] // 1000),
        open=float(row[1]),
        high=float(row[2]),
        low=float(row[3]),
        close=float(row[4]),
        volume=float(row[5]),
    ) for row in rows]
