import math
import random
import unittest


from fxtrade.lib.candles import Candle
from fxtrade.lib.exchange import PRODUCT_BTC_FX, PRODUCT_ETH_SPOT
from fxtrade.lib.backtest import SimulatedExchange, run_backtest


def make_candles(closes, bar_seconds=3600):
    return [Candle(time=i * bar_seconds, open=c, high=c * 1.005, low=c * 0.995,
                   close=c, volume=1.0)
            for i, c in enumerate(closes)]


def trending_market(n=600, seed=42):
    # 上昇と下降のトレンドを繰り返す合成相場
    random.seed(seed)
    closes = [1000000.0]
    direction = 1
    for i in range(n - 1):
        if i % 150 == 149:
            direction *= -1
        drift = direction * 0.003
        noise = random.gauss(0, 0.005)
        closes.append(max(closes[-1] * (1 + drift + noise), 1000.0))
    return closes


class TestSimulatedExchange(unittest.TestCase):

    def setUp(self):
        self.candles = make_candles([100.0] * 100)
        self.sim = SimulatedExchange(PRODUCT_BTC_FX, self.candles, 1000000,
                                     slippage=0.0, swap_rate_daily=0.0)

    def test_initial_state(self):
        self.assertEqual(self.sim.get_position(PRODUCT_BTC_FX), 0.0)
        self.assertEqual(self.sim.get_equity(PRODUCT_BTC_FX), 1000000)

    def test_buy_and_sell_roundtrip(self):
        # 同じ価格で買って売れば（コストゼロなら）資産は変わらない
        self.sim.market_order(PRODUCT_BTC_FX, 'BUY', 1.0)
        self.assertEqual(self.sim.get_position(PRODUCT_BTC_FX), 1.0)
        self.sim.market_order(PRODUCT_BTC_FX, 'SELL', 1.0)
        self.assertEqual(self.sim.get_position(PRODUCT_BTC_FX), 0.0)
        self.assertAlmostEqual(self.sim.get_equity(PRODUCT_BTC_FX), 1000000)

    def test_profit_on_price_rise(self):
        # 100で買って値上がりした後の資産は増えている
        self.sim.market_order(PRODUCT_BTC_FX, 'BUY', 10.0)
        candles = make_candles([100.0] * 50 + [110.0] * 50)
        self.sim.candles = candles
        self.sim.index = 99
        self.assertAlmostEqual(self.sim.get_equity(PRODUCT_BTC_FX), 1000000 + 10.0 * 10.0)

    def test_short_profit_on_price_fall(self):
        # ショートは値下がりで利益になる
        self.sim.market_order(PRODUCT_BTC_FX, 'SELL', 10.0)
        self.assertEqual(self.sim.get_position(PRODUCT_BTC_FX), -10.0)
        self.sim.candles = make_candles([100.0] * 50 + [90.0] * 50)
        self.sim.index = 99
        self.assertAlmostEqual(self.sim.get_equity(PRODUCT_BTC_FX), 1000000 + 10.0 * 10.0)

    def test_dohten(self):
        # ドテン（ロング→ショート）が正しく処理される
        self.sim.market_order(PRODUCT_BTC_FX, 'BUY', 1.0)
        self.sim.market_order(PRODUCT_BTC_FX, 'SELL', 3.0)
        self.assertEqual(self.sim.get_position(PRODUCT_BTC_FX), -2.0)

    def test_spot_cannot_oversell(self):
        # 現物は保有数量以上に売れない
        sim = SimulatedExchange(PRODUCT_ETH_SPOT, self.candles, 1000000,
                                slippage=0.0, fee_rate=0.0)
        sim.market_order(PRODUCT_ETH_SPOT, 'BUY', 5.0)
        sim.market_order(PRODUCT_ETH_SPOT, 'SELL', 100.0)
        self.assertAlmostEqual(sim.get_position(PRODUCT_ETH_SPOT), 0.0)

    def test_spot_cannot_overbuy(self):
        # 現物は現金の範囲内でしか買えない（自動的にサイズが縮小される）
        sim = SimulatedExchange(PRODUCT_ETH_SPOT, self.candles, 1000,
                                slippage=0.0, fee_rate=0.0)
        sim.market_order(PRODUCT_ETH_SPOT, 'BUY', 100.0)
        self.assertLessEqual(sim.get_position(PRODUCT_ETH_SPOT) * 100.0, 1000 + 1e-6)

    def test_fees_are_charged(self):
        sim = SimulatedExchange(PRODUCT_ETH_SPOT, self.candles, 1000000,
                                slippage=0.0, fee_rate=0.0015)
        sim.market_order(PRODUCT_ETH_SPOT, 'BUY', 10.0)
        self.assertGreater(sim.account.fees_paid, 0)

    def test_swap_is_charged_over_time(self):
        # FXの建玉を持ち越すとスワップコストがかかる
        candles = make_candles([100.0] * 100, bar_seconds=86400)
        sim = SimulatedExchange(PRODUCT_BTC_FX, candles, 1000000,
                                slippage=0.0, swap_rate_daily=0.0004)
        sim.market_order(PRODUCT_BTC_FX, 'BUY', 10.0)
        for i in range(1, 10):
            sim.advance(i)
        self.assertGreater(sim.account.swap_paid, 0)
        self.assertLess(sim.get_equity(PRODUCT_BTC_FX), 1000000)


class TestBacktest(unittest.TestCase):

    # テストは短い期間設定で行う（デフォルトは長期間の足が必要なため）
    CONFIG = {'strategy': {'fast-span': 10, 'slow-span': 30, 'donchian-span': 20}}

    def test_grows_on_trending_market(self):
        # トレンドの明確な合成相場では資産が増える
        candles = make_candles(trending_market())
        result = run_backtest(PRODUCT_BTC_FX, candles, 500000, config=self.CONFIG)
        self.assertGreater(result.final_equity, result.initial_equity)
        self.assertEqual(result.margin_call_count, 0)

    def test_no_margin_call_on_crash(self):
        # 暴落相場（毎バー-5%が続く）でもマージンコールにならない
        closes = [1000000.0]
        for _ in range(300):
            closes.append(closes[-1] * 0.95)
        candles = make_candles(closes)
        result = run_backtest(PRODUCT_BTC_FX, candles, 500000, config=self.CONFIG)
        self.assertEqual(result.margin_call_count, 0)
        # 資産がゼロやマイナスにならない
        self.assertGreater(result.final_equity, 0)

    def test_survives_flash_crash_and_spike(self):
        # 急騰と急落を繰り返す極端な相場でも資産がゼロにならない
        random.seed(7)
        closes = [1000000.0]
        for i in range(500):
            move = random.choice([0.90, 0.95, 1.0, 1.05, 1.10])
            closes.append(closes[-1] * move)
        candles = make_candles(closes)
        result = run_backtest(PRODUCT_BTC_FX, candles, 500000, config=self.CONFIG)
        self.assertGreater(result.final_equity, 0)
        self.assertEqual(result.margin_call_count, 0)

    def test_spot_never_negative(self):
        # 現物取引では資産がマイナスにならない
        closes = [1000000.0]
        for _ in range(300):
            closes.append(closes[-1] * 0.97)
        candles = make_candles(closes)
        result = run_backtest(PRODUCT_ETH_SPOT, candles, 500000, config=self.CONFIG)
        self.assertGreaterEqual(result.final_equity, 0)


if __name__ == '__main__':
    unittest.main()
