import unittest


from fxtrade.lib.risk import RiskManager, HARD_MAX_LEVERAGE
from fxtrade.lib.strategy import Signal


def make_signal(direction=1, strength=1.0, price=100.0, stop=95.0):
    return Signal(direction=direction, strength=strength, stop_price=stop,
                  atr=2.0, price=price)


class TestRiskManager(unittest.TestCase):

    def test_leverage_hard_limit(self):
        # 設定でレバレッジ上限に3を超える値を指定しても3にクランプされる
        risk = RiskManager({'max-leverage': 10.0})
        self.assertEqual(risk.max_leverage, HARD_MAX_LEVERAGE)

    def test_leverage_configurable(self):
        risk = RiskManager({'max-leverage': 1.5})
        self.assertEqual(risk.max_leverage, 1.5)

    def test_no_position_without_signal(self):
        risk = RiskManager()
        size = risk.position_size(1000000, 100.0, make_signal(direction=0))
        self.assertEqual(size, 0.0)

    def test_no_position_without_equity(self):
        risk = RiskManager()
        size = risk.position_size(0, 100.0, make_signal())
        self.assertEqual(size, 0.0)

    def test_size_respects_leverage_cap(self):
        # どんなに損切り幅が狭くても、想定元本が資産×レバレッジ上限を超えない
        risk = RiskManager({'max-leverage': 2.0, 'risk-per-trade': 0.5,
                            'margin-usage-limit': 0.7})
        equity = 1000000
        price = 100.0
        signal = make_signal(stop=99.9)  # 極端に狭い損切り
        size = risk.position_size(equity, price, signal)
        self.assertLessEqual(abs(size) * price, equity * 2.0 * 0.7 + 1e-6)

    def test_spot_no_leverage(self):
        # 現物はレバレッジ1倍まで（資産以上のポジションを持たない）
        risk = RiskManager({'max-leverage': 3.0, 'risk-per-trade': 0.5})
        equity = 1000000
        price = 100.0
        signal = make_signal(stop=99.9)
        size = risk.position_size(equity, price, signal, spot=True)
        self.assertLessEqual(abs(size) * price, equity + 1e-6)

    def test_risk_per_trade_limits_loss(self):
        # 損切りにかかった場合の損失が資産のrisk-per-trade以内になるサイズ
        risk = RiskManager({'risk-per-trade': 0.02})
        equity = 1000000
        signal = make_signal(price=100.0, stop=95.0)
        size = risk.position_size(equity, 100.0, signal)
        max_loss = abs(size) * (100.0 - 95.0)
        self.assertLessEqual(max_loss, equity * 0.02 + 1e-6)

    def test_short_size_negative(self):
        risk = RiskManager()
        signal = make_signal(direction=-1, price=100.0, stop=105.0)
        size = risk.position_size(1000000, 100.0, signal)
        self.assertLess(size, 0)

    def test_min_size(self):
        # 最小取引数量未満ならポジションを取らない
        risk = RiskManager({'risk-per-trade': 0.0001})
        signal = make_signal(price=10000000.0, stop=9000000.0)
        size = risk.position_size(100000, 10000000.0, signal, min_size=0.01)
        self.assertEqual(size, 0.0)

    def test_drawdown_scale(self):
        risk = RiskManager({'drawdown-soft': 0.1, 'drawdown-hard': 0.3,
                            'drawdown-min-scale': 0.25})
        # ピーク更新
        self.assertEqual(risk.drawdown_scale(1000000), 1.0)
        # 小さいドローダウンでは縮小しない
        self.assertEqual(risk.drawdown_scale(950000), 1.0)
        # 大きいドローダウンでは縮小するがゼロにはならない（取引を止めない）
        scale = risk.drawdown_scale(600000)
        self.assertEqual(scale, 0.25)
        self.assertGreater(scale, 0)
        # 中間は線形に縮小
        scale_mid = risk.drawdown_scale(800000)
        self.assertLess(scale_mid, 1.0)
        self.assertGreater(scale_mid, 0.25)


if __name__ == '__main__':
    unittest.main()
