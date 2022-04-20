import random
from .. import get_module_logger
from ..base_market import BaseMarket


logger = get_module_logger()


class MockStockMarket(BaseMarket):

    is_dryrun = False
    trade_log = None
    differential = None
    trade_result = None

    def __init__(self, trade_log=None, differential=None, trade_result=None, is_dryrun=False):
        self.set_mock_parameter(trade_log, differential, trade_result, is_dryrun)

    def set_mock_parameter(self, trade_log=None, differential=None, trade_result=None, is_dryrun=False):
        # モックとして返す値を設定する
        # Noneが指定されていた場合は乱数を返すようにする
        logger.debug('MockStockMarket.set_mock_parameter()')
        self.trade_log = trade_log
        self.differential = differential
        self.trade_result = trade_result
        self.is_dryrun = is_dryrun
        logger.debug(f'set trade_log: {trade_log}')
        logger.debug(f'set differential: {differential}')
        logger.debug(f'set trade_result: {trade_result}')
        logger.debug(f'set dryrun: {is_dryrun}')

    def check_latest_trade(self):
        # 最後の取引履歴を確認する
        # 1: 最後に売却もしくはまだ取引を行っていないので、購入する
        # -1: 最後に購入したので、売却する
        # 0: なんらかの理由で確認できなかった

        # モックの値が指定されていればその値を返却する
        # 指定されていなければ乱数を返す
        logger.debug('MockStockMarket.check_latest_trade()')
        logger.debug(f'mock trade log: {self.trade_log}')
        if self.trade_log:
            logger.debug(f'response trade log: {self.trade_log}')
            return self.trade_log
        else:
            t = random.randint(-1,1)
            logger.debug(f'using random value: {t}')
            return t

    def check_differential(self):
        # 現在の市場の動向を確認する

        # モックの値が指定されていればその値を返却する
        # 指定されていなければ乱数を返す
        logger.debug('MockStockMarket.check_differential()')
        logger.debug(f'mock differential: {self.differential}')
        if self.differential:
            logger.debug(f'response differential: {self.differential}')
            return self.differential
        else:
            t = random.uniform(-1,1)
            logger.debug(f'using random value: {t}')
            return t

    def buy(self):
        # 購入取引を実施する
        # 1: 取引成功
        # -1: 取引失敗
        # 0: 取引を行わなかった

        # モックの値が指定されていればその値を返却する
        # 指定されていなければ乱数を返す
        logger.debug('MockStockMarket.buy()')
        logger.debug(f'mock trade result: {self.trade_result}')
        if self.trade_result:
            logger.debug(f'response trade result: {self.trade_result}')
            return self.trade_result
        else:
            t = random.randint(-1,1)
            logger.debug(f'using random value: {t}')
            return t

    def sell(self):
        # 売却取引を実施する
        # 1: 取引成功
        # -1: 取引失敗
        # 0: 取引を行わなかった

        # モックの値が指定されていればその値を返却する
        # 指定されていなければ乱数を返す
        logger.debug('MockStockMarket.sell()')
        logger.debug(f'mock trade result: {self.trade_result}')
        if self.trade_result:
            logger.debug(f'response trade result: {self.trade_result}')
            return self.trade_result
        else:
            t = random.randint(-1,1)
            logger.debug(f'using random value: {t}')
            return t

