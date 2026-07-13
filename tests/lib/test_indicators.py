import unittest


from fxtrade.lib.candles import Candle
from fxtrade.lib.indicators import ema, sma, atr, realized_volatility, donchian


def make_candles(closes):
    return [Candle(time=i * 3600, open=c, high=c * 1.01, low=c * 0.99, close=c, volume=1.0)
            for i, c in enumerate(closes)]


class TestIndicators(unittest.TestCase):

    def test_sma_constant(self):
        # 一定の値ならSMAも同じ値になる
        values = [100.0] * 10
        result = sma(values, 5)
        self.assertEqual(len(result), 10)
        for v in result:
            self.assertAlmostEqual(v, 100.0)

    def test_sma_window(self):
        values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
        result = sma(values, 3)
        # 最後の値は直近3本の平均
        self.assertAlmostEqual(result[-1], (4 + 5 + 6) / 3)

    def test_ema_constant(self):
        values = [100.0] * 10
        result = ema(values, 5)
        for v in result:
            self.assertAlmostEqual(v, 100.0)

    def test_ema_follows_trend(self):
        # 上昇トレンドならEMAは上昇し、直近の値に近づく
        values = list(range(1, 101))
        result = ema([float(v) for v in values], 10)
        self.assertGreater(result[-1], result[-10])
        self.assertLess(result[-1], values[-1])  # EMAは遅行する

    def test_ema_empty(self):
        self.assertEqual(ema([], 5), [])

    def test_atr_positive(self):
        candles = make_candles([100.0, 102.0, 101.0, 103.0, 105.0] * 5)
        result = atr(candles, 14)
        self.assertEqual(len(result), len(candles))
        self.assertGreater(result[-1], 0)

    def test_atr_zero_range(self):
        # 値動きがなければATRは0
        candles = [Candle(time=i, open=100, high=100, low=100, close=100, volume=1)
                   for i in range(20)]
        result = atr(candles, 14)
        self.assertAlmostEqual(result[-1], 0.0)

    def test_realized_volatility(self):
        # 値動きがなければボラティリティは0
        self.assertAlmostEqual(realized_volatility([100.0] * 30), 0.0)
        # 変動があれば正の値
        closes = [100.0, 110.0, 95.0, 105.0, 90.0] * 6
        self.assertGreater(realized_volatility(closes), 0)

    def test_donchian(self):
        candles = make_candles([100.0, 110.0, 105.0, 95.0, 100.0])
        high_band, low_band = donchian(candles, 5)
        self.assertAlmostEqual(high_band, 110.0 * 1.01)
        self.assertAlmostEqual(low_band, 95.0 * 0.99)


if __name__ == '__main__':
    unittest.main()
