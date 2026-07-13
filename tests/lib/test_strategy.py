import unittest


from fxtrade.lib.candles import Candle
from fxtrade.lib.strategy import TrendStrategy, PositionState


def make_candles(closes):
    return [Candle(time=i * 3600, open=c, high=c * 1.005, low=c * 0.995, close=c, volume=1.0)
            for i, c in enumerate(closes)]


def uptrend(n=200, start=100.0, step=1.0):
    return [start + i * step for i in range(n)]


def downtrend(n=200, start=300.0, step=1.0):
    return [start - i * step for i in range(n)]


class TestTrendStrategy(unittest.TestCase):

    def setUp(self):
        self.strategy = TrendStrategy({
            'fast-span': 10, 'slow-span': 30,
            'donchian-span': 20, 'trail-atr-mult': 3.0,
        })

    def test_not_enough_history(self):
        # データ不足のときはシグナルを出さない
        candles = make_candles([100.0] * 5)
        signal = self.strategy.evaluate(candles, PositionState())
        self.assertEqual(signal.direction, 0)

    def test_uptrend_entry(self):
        # 明確な上昇トレンドではロングのシグナルが出る
        candles = make_candles(uptrend())
        signal = self.strategy.evaluate(candles, PositionState())
        self.assertEqual(signal.direction, 1)
        self.assertGreater(signal.strength, 0)
        # 損切りは現在価格より下に自動設定される
        self.assertLess(signal.stop_price, signal.price)

    def test_downtrend_entry_short(self):
        # 明確な下降トレンドではショートのシグナルが出る
        candles = make_candles(downtrend())
        signal = self.strategy.evaluate(candles, PositionState())
        self.assertEqual(signal.direction, -1)
        # ショートの損切りは現在価格より上
        self.assertGreater(signal.stop_price, signal.price)

    def test_downtrend_no_short_for_spot(self):
        # 現物（ショート不可）では下降トレンドでもポジションを取らない
        strategy = TrendStrategy({
            'fast-span': 10, 'slow-span': 30,
            'donchian-span': 20, 'allow-short': False,
        })
        candles = make_candles(downtrend())
        signal = strategy.evaluate(candles, PositionState())
        self.assertEqual(signal.direction, 0)

    def test_ranging_market_no_entry(self):
        # 一定の値動きのないレンジ相場ではエントリーしない
        candles = make_candles([100.0, 101.0] * 100)
        signal = self.strategy.evaluate(candles, PositionState())
        self.assertEqual(signal.direction, 0)

    def test_trailing_stop_exit(self):
        # ロング保有中に価格が最高値からATR×係数以上下落したら決済する
        closes = uptrend(150) + [250.0 - i * 8.0 for i in range(1, 15)]
        candles = make_candles(closes)
        position = PositionState(direction=1, entry_price=200.0, extreme_price=249.0)
        signal = self.strategy.evaluate(candles, position)
        # 急落によりトレンド反転またはトレーリングストップで手仕舞われる
        self.assertIn(signal.direction, (0, -1))

    def test_hold_position_in_trend(self):
        # 上昇トレンド継続中はロングを維持する
        candles = make_candles(uptrend())
        price = candles[-1].close
        position = PositionState(direction=1, entry_price=price * 0.9,
                                 extreme_price=price)
        signal = self.strategy.evaluate(candles, position)
        self.assertEqual(signal.direction, 1)
        # トレーリングストップの水準が返される
        self.assertGreater(signal.stop_price, 0)
        self.assertLess(signal.stop_price, price)

    def test_stop_is_adaptive_to_volatility(self):
        # ボラティリティが大きいほど損切り幅（ATRベース）も広くなる
        calm = make_candles(uptrend(step=0.5))
        wild_closes = [c + (10.0 if i % 2 == 0 else -10.0) for i, c in enumerate(uptrend(step=2.0))]
        wild = make_candles(wild_closes)
        calm_signal = self.strategy.evaluate(calm, PositionState())
        wild_signal = self.strategy.evaluate(wild, PositionState())
        self.assertGreater(wild_signal.atr, calm_signal.atr)


class TestPositionState(unittest.TestCase):

    def test_update_extreme_long(self):
        state = PositionState(direction=1, entry_price=100.0, extreme_price=100.0)
        state.update_extreme(110.0)
        self.assertEqual(state.extreme_price, 110.0)
        state.update_extreme(105.0)  # 下がっても最高値は維持
        self.assertEqual(state.extreme_price, 110.0)

    def test_update_extreme_short(self):
        state = PositionState(direction=-1, entry_price=100.0, extreme_price=100.0)
        state.update_extreme(90.0)
        self.assertEqual(state.extreme_price, 90.0)
        state.update_extreme(95.0)  # 上がっても最安値は維持
        self.assertEqual(state.extreme_price, 90.0)


if __name__ == '__main__':
    unittest.main()
