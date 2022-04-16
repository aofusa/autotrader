import unittest


from fxtrade.market import Trader, MockStockMarket
from fxtrade.market import get_module_logger, update_transaction_id


logger = get_module_logger()


class TestTrader(unittest.TestCase):

    def setUp(self):
        self.market = MockStockMarket(is_dryrun=True)

    def test_decision_deal(self):
        # 売買を行うべきかどうかの判断が正しいかどうかテスト
        logger.debug('start test_decision_deal')

        # 符号の確認と絶対値で比較を行う
        # trade_log: 1で購入、-1で売却
        # differential: 0以上で購入、0未満で売却
        # differentialの絶対値がthreshold未満なら購入も売却もしない
        # trade_logとdifferentialの符号が一致していなければ購入も売却もしない
        patterns = [
            # (threshold, differential, trade_log, expected)
            (0.2, 0.1, None, 0),  # differentialの絶対値がthreshold未満なら何もしない
            (0.2, -0.1, None, 0),  # differentialの絶対値がthreshold未満なら何もしない

            # differentialの絶対値がthreshold以上なら、differentialとtrade_logの符号を確認する
            (0.1, 0.1, 1, 1),  # differentialの値が正かつtrade_logの結果が次に購入(1)なら、購入(1)
            (0.1, -0.1, -1, -1),  # differentialの値が負かつtrade_logの結果が次に売却(-1)なら、売却(-1)
            (0.1, 0.2, -1, 0),  # differentialの値が正かつtrade_logの結果が次に売却(-1)なら、何もしない(0)
            (0.1, -0.2, 1, 0),  # differentialの値が負かつtrade_logの結果が次に購入(1)なら、何もしない(0)

            # trade_logがなんらかの理由でうまく取れなければ、何もしない
            (0.1, 0.2, 0, 0),
        ]

        for idx, parameter in enumerate(patterns):
            update_transaction_id()
            logger.debug(f'parameter[{idx}]: {parameter}')

            trader = Trader(self.market, parameter[0])
            is_deal = trader.decision_deal(
                parameter[0],  # threshold
                parameter[1],  # differential
                parameter[2]   # trade_log
            )

            logger.debug(f'parameter[{idx}]: {parameter}, expected: {parameter[3]}, actual: {is_deal}')
            self.assertEqual(is_deal, parameter[3])

        logger.debug('end test_decision_deal')


if __name__ == '__main__':
    unittest.main()

