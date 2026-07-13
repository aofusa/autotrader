import csv
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Candle:
    # 1本のローソク足
    # time はエポック秒（足の開始時刻）
    time: int
    open: float
    high: float
    low: float
    close: float
    volume: float


def candles_to_csv(candles, path):
    # ローソク足のリストをCSVに保存する
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['time', 'open', 'high', 'low', 'close', 'volume'])
        for c in candles:
            writer.writerow([c.time, c.open, c.high, c.low, c.close, c.volume])


def candles_from_csv(path):
    # CSVからローソク足のリストを読み込む
    candles = []
    with open(path, newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            candles.append(Candle(
                time=int(row['time']),
                open=float(row['open']),
                high=float(row['high']),
                low=float(row['low']),
                close=float(row['close']),
                volume=float(row['volume']),
            ))
    return candles
