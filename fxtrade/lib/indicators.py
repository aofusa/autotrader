import math


def ema(values, span):
    # 指数平滑移動平均線を計算する
    # 返り値は values と同じ長さのリスト（先頭から順に計算）
    if not values:
        return []
    alpha = 2.0 / (span + 1)
    result = [values[0]]
    for v in values[1:]:
        result.append(alpha * v + (1 - alpha) * result[-1])
    return result


def sma(values, span):
    # 単純移動平均線を計算する
    # 返り値は values と同じ長さのリスト（span本たまるまでは部分平均）
    result = []
    s = 0.0
    for i, v in enumerate(values):
        s += v
        if i >= span:
            s -= values[i - span]
            result.append(s / span)
        else:
            result.append(s / (i + 1))
    return result


def atr(candles, span=14):
    # ATR（Average True Range）を計算する
    # 返り値は candles と同じ長さのリスト
    if not candles:
        return []
    trs = [candles[0].high - candles[0].low]
    for i in range(1, len(candles)):
        c = candles[i]
        prev_close = candles[i - 1].close
        tr = max(c.high - c.low, abs(c.high - prev_close), abs(c.low - prev_close))
        trs.append(tr)
    return ema(trs, span)


def realized_volatility(closes, span=24):
    # 直近span本の対数リターンの標準偏差（1本あたりのボラティリティ）
    if len(closes) < 2:
        return 0.0
    returns = []
    start = max(1, len(closes) - span)
    for i in range(start, len(closes)):
        if closes[i - 1] > 0:
            returns.append(math.log(closes[i] / closes[i - 1]))
    if len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    var = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    return math.sqrt(var)


def donchian(candles, span):
    # ドンチャンチャネル（直近span本の最高値・最安値）を返す
    if not candles:
        return (0.0, 0.0)
    window = candles[-span:]
    return (max(c.high for c in window), min(c.low for c in window))
