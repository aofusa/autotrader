import unittest


from fxtrade.lib.market.bitflyer import BitFlyerExchange
from fxtrade.lib.exchange import PRODUCT_ETH_SPOT, PRODUCT_BTC_FX


class FakeBitFlyerExchange(BitFlyerExchange):
    # ネットワークを使わないテスト用のスタブ

    def __init__(self, config, balances=None, price=300000.0):
        super().__init__(config=config, is_dryrun=True)
        self.balances = balances or []
        self.price = price
        self.sent_orders = []

    def _private_request(self, method, path, body=None):
        if '/v1/me/getbalance' in path:
            return self.balances
        if '/v1/me/sendchildorder' in path:
            self.sent_orders.append(body)
            return {'child_order_acceptance_id': 'TEST'}
        raise AssertionError(f'unexpected api call: {path}')

    def get_price(self, spec):
        return self.price


def config_with_reserve(reserve):
    return {
        'key': 'k', 'secret': 's',
        'spot-reserves': {'ETH': reserve},
    }


class TestSpotReserves(unittest.TestCase):

    BALANCES = [
        {'currency_code': 'JPY', 'amount': 100000.0},
        {'currency_code': 'ETH', 'amount': 0.6875},
    ]

    def test_position_excludes_reserve(self):
        # 予約残高はポジションとして扱われない
        ex = FakeBitFlyerExchange(config_with_reserve(0.6875), balances=self.BALANCES)
        self.assertAlmostEqual(ex.get_position(PRODUCT_ETH_SPOT), 0.0)

    def test_position_includes_tradable_portion(self):
        # 予約を超える分だけが運用対象になる
        ex = FakeBitFlyerExchange(config_with_reserve(0.5), balances=self.BALANCES)
        self.assertAlmostEqual(ex.get_position(PRODUCT_ETH_SPOT), 0.1875)

    def test_equity_excludes_reserve(self):
        # 資産評価額にも予約残高は含まれない（日本円+運用対象分のみ）
        ex = FakeBitFlyerExchange(config_with_reserve(0.6875), balances=self.BALANCES,
                                  price=300000.0)
        self.assertAlmostEqual(ex.get_equity(PRODUCT_ETH_SPOT), 100000.0)

    def test_no_reserve_config(self):
        # 予約設定がなければ全量が運用対象
        ex = FakeBitFlyerExchange({'key': 'k', 'secret': 's'}, balances=self.BALANCES)
        self.assertAlmostEqual(ex.get_position(PRODUCT_ETH_SPOT), 0.6875)

    def test_sell_clamped_to_tradable(self):
        # 予約残高を超える売り注文は運用対象分にクランプされる
        ex = FakeBitFlyerExchange(config_with_reserve(0.5), balances=self.BALANCES)
        ex.is_dryrun = False
        result = ex.market_order(PRODUCT_ETH_SPOT, 'SELL', 0.6875)
        self.assertEqual(result, 1)
        self.assertEqual(len(ex.sent_orders), 1)
        self.assertAlmostEqual(ex.sent_orders[0]['size'], 0.1875)

    def test_sell_fully_reserved_is_rejected(self):
        # 全量が予約されている場合、売り注文は発注されない
        ex = FakeBitFlyerExchange(config_with_reserve(0.6875), balances=self.BALANCES)
        ex.is_dryrun = False
        result = ex.market_order(PRODUCT_ETH_SPOT, 'SELL', 0.5)
        self.assertEqual(result, -1)
        self.assertEqual(ex.sent_orders, [])

    def test_fx_position_not_affected_by_reserve(self):
        # 予約残高は現物のみの概念で、FXのポジションには影響しない
        ex = FakeBitFlyerExchange(config_with_reserve(0.6875))

        def fake_private(method, path, body=None):
            assert 'getpositions' in path
            return [{'side': 'BUY', 'size': 0.05}]
        ex._private_request = fake_private
        self.assertAlmostEqual(ex.get_position(PRODUCT_BTC_FX), 0.05)


if __name__ == '__main__':
    unittest.main()
