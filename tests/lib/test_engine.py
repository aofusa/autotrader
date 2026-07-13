import unittest


from fxtrade.lib.candles import Candle
from fxtrade.lib.exchange import ExchangeAdapter, PRODUCT_BTC_FX, PRODUCT_ETH_SPOT, \
    products_from_config
from fxtrade.lib.engine import TradingEngine


def make_candles(closes):
    return [Candle(time=i * 3600, open=c, high=c * 1.005, low=c * 0.995, close=c, volume=1.0)
            for i, c in enumerate(closes)]


class FakeExchange(ExchangeAdapter):
    # テスト用の取引所。注文を記録するだけで状態は手動で設定する

    def __init__(self, candles, equity=1000000, position=0.0):
        self.candles = candles
        self.equity = equity
        self.position = position
        self.orders = []
        self.order_result = 1

    def get_candles(self, spec, limit):
        return self.candles[-limit:]

    def get_price(self, spec):
        return self.candles[-1].close if self.candles else 0

    def get_equity(self, spec):
        return self.equity

    def get_position(self, spec):
        return self.position

    def market_order(self, spec, side, size):
        self.orders.append((side, size))
        return self.order_result


class TestProductsFromConfig(unittest.TestCase):

    def test_btc(self):
        products = products_from_config('btc')
        self.assertEqual([p.code for p in products], ['FX_BTC_JPY'])

    def test_eth(self):
        products = products_from_config('eth')
        self.assertEqual([p.code for p in products], ['ETH_JPY'])
        self.assertTrue(products[0].spot)

    def test_both(self):
        products = products_from_config('both')
        self.assertEqual([p.code for p in products], ['FX_BTC_JPY', 'ETH_JPY'])

    def test_default_is_btc(self):
        products = products_from_config(None)
        self.assertEqual([p.code for p in products], ['FX_BTC_JPY'])

    def test_unknown_raises(self):
        with self.assertRaises(ValueError):
            products_from_config('doge')


class TestTradingEngine(unittest.TestCase):

    def uptrend_candles(self):
        return make_candles([100000.0 + i * 1000 for i in range(300)])

    def test_enters_long_on_uptrend(self):
        # 上昇トレンドでノーポジションなら買い注文が出る
        exchange = FakeExchange(self.uptrend_candles())
        engine = TradingEngine(exchange, PRODUCT_BTC_FX)
        traded, signal = engine.step()
        self.assertTrue(traded)
        self.assertEqual(exchange.orders[0][0], 'BUY')

    def test_no_trade_without_data(self):
        exchange = FakeExchange([])
        engine = TradingEngine(exchange, PRODUCT_BTC_FX)
        traded, signal = engine.step()
        self.assertFalse(traded)
        self.assertEqual(exchange.orders, [])

    def test_no_trade_without_equity(self):
        exchange = FakeExchange(self.uptrend_candles(), equity=0)
        engine = TradingEngine(exchange, PRODUCT_BTC_FX)
        traded, signal = engine.step()
        self.assertFalse(traded)

    def test_no_rebalance_for_small_delta(self):
        # 目標と現在の差が小さいときは発注しない（コスト節約）
        exchange = FakeExchange(self.uptrend_candles())
        engine = TradingEngine(exchange, PRODUCT_BTC_FX)
        # 一度発注させて目標サイズを得る
        engine.step()
        target = exchange.orders[0][1]
        # ほぼ目標どおりのポジションを持っている状態にする
        exchange.position = target * 0.95
        exchange.orders = []
        engine.step()
        self.assertEqual(exchange.orders, [])

    def test_adopts_external_position(self):
        # 再起動などで内部状態がなくても実ポジションに追従する
        exchange = FakeExchange(self.uptrend_candles(), position=0.5)
        engine = TradingEngine(exchange, PRODUCT_BTC_FX)
        engine.step()
        self.assertEqual(engine.position_state.direction, 1)

    def test_spot_engine_never_sells_short(self):
        # 現物のエンジンは下降トレンドでも売り建てしない
        downtrend = make_candles([300000.0 - i * 500 for i in range(300)])
        exchange = FakeExchange(downtrend)
        engine = TradingEngine(exchange, PRODUCT_ETH_SPOT,
                               config={'strategy': {'allow-short': False}})
        traded, signal = engine.step()
        self.assertFalse(traded)
        self.assertEqual(exchange.orders, [])


if __name__ == '__main__':
    unittest.main()
