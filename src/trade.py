import json
import uuid
import time
from urllib import request
from logging import getLogger, StreamHandler, DEBUG, Formatter
import random


class JsonFormatter(Formatter):

    def _str2json(self, msg):
        if type(msg) is str or \
            type(msg) is dict or \
            type(msg) is list:
            return json.dumps(msg)
        return msg

    def format(self, record):
        record.msg = self._str2json(record.msg)
        return super().format(record)


def anonymization(x):
    data = str(x)
    if len(data) < 1:
        return data
    elif len(data) == 1:
        return '*'
    elif len(data) <= 4:
        return data[0] + '*'*(len(data)-1)
    else:
        return data[0] + data[1] + '*'*(len(data)-3) + data[-1]


def update_transaction_id(handler, transaction_id=uuid.uuid4().hex):
    formatter = JsonFormatter('{"timestamp": "%(asctime)-15s", "transaction-id": ' + f'"{transaction_id}"' + ', "level": "%(levelname)s", "message": %(message)s}')
    handler.setFormatter(formatter)


formatter = JsonFormatter('{"timestamp": "%(asctime)-15s", "transaction-id": ' + f'"{uuid.uuid4().hex}"' + ', "level": "%(levelname)s", "message": %(message)s}')
logger = getLogger(__name__)
handler = StreamHandler()
handler.setLevel(DEBUG)
handler.setFormatter(formatter)
logger.setLevel(DEBUG)
logger.addHandler(handler)
logger.propagate = False


class Trader():

    threshold_differential = 0.1  # 売買を行うかどうかの判断基準。直近取引の傾きがこの値を超えていれば売買を行う

    def __init__(self, threshold_differential=0.1):
        # クラスの初期パラメータを設定する
        logger.debug('Trader.__init__()')
        self.threshold_differential = threshold_differential
        logger.info(f'set threshold differential: {self.threshold_differential}')

    def initialize(self):
        # 初期化を行う
        logger.debug('Trader.initialize()')

    def trade(self):
        # 売買を行う
        logger.debug('Trader.trade()')

        # 買う -> 売る の順番で必ず売買を行う
        # 最新の取引履歴を確認し、買っていれば売る、売っていれば買うのみを行う
        # まだ一度も売買を行っていなければ、売った後として処理する
        logger.info('check latest trade')
        latest_trade_log = self.check_latest_trade()
        logger.info(f'latest trade: {latest_trade_log}  (1: buy, -1: sell, 0: nothing)')

        # 移動平均の変化を確認し、傾きが急激であれば売買を行う
        # 傾きには下がる傾きと上がる傾きがある
        # 上がる傾きの時には買い、下がる傾きの時は売る
        # 直前の売る・買うの判断と合わせて、不一致の場合は購入しない
        logger.info('check differential')
        differential = self.check_differential()
        logger.info(f'differential: {differential}')

        # 取引を行うかどうか確認し取引を実行する
        logger.info('check should deal or not')
        is_deal = self.decision_deal(self.threshold_differential, differential, latest_trade_log)
        logger.info(f'dealing: {is_deal}  (1: buy, -1: sell, 0: no deal)')

        is_success = None
        if is_deal == 1:
            # 購入取引する判断をしたので購入を行う
            logger.info('execute buy deal')
            is_success = self.buy()
        elif is_deal == -1:
            # 売却取引する判断をしたので売却を行う
            logger.info('execute sell deal')
            is_success = self.sell()
        else:
            # 取引しない判断をしたので何もしない
            logger.info('no deal')
            is_success = None

        # 取引の実行結果成功したかどうかを返却する
        # 1: 成功した
        # -1: 失敗した
        # 0: 取引を行わなかった
        logger.info(f'deal result: {is_success}  (1: buy, -1: sell, 0: no deal)')
        return is_success

    def decision_deal(self, threshold, differential, trade_log):
        # 売買を行うべきか判断する
        logger.debug('Trader.is_deal()')

        # 移動平均の変化を確認し、傾きが急激であれば売買を行う
        # 傾きには下がる傾きと上がる傾きがある
        # 上がる傾きの時には買い、下がる傾きの時は売る
        # 直前の売る・買うの判断と合わせて、不一致の場合は購入しない

        # 符号の確認と絶対値で比較を行う
        # trade_log: 1で購入、-1で売却
        # differential: 0以上で購入、0未満で売却
        # differentialの絶対値がthreshold未満なら購入も売却もしない
        # trade_logとdifferentialの値が一致していなければ購入も売却もしない

        # 購入なら1、売却なら-1、何もしないなら0を返す
        logger.info(f'threshold: {threshold}')
        logger.info(f'differential: {differential}')
        logger.info(f'trade log: {trade_log}  (1: buy, -1: sell, 0: nothing)')

        # thresholdとdifferentialの絶対値を比較する
        logger.info('check differential and threshold')
        if max(differential, differential*-1) < threshold:
            # differentialの絶対値がthreshold未満なので何もしない
            logger.info('|differential| < threshold. no deal')
            return 0

        # 取引履歴と傾きの一致を確認する
        logger.info('check trade_log and differential')
        if trade_log == 1 and differential >= 0:
            # 傾きが+で最後の購入履歴が売却だったなら、購入する
            logger.info('trade log == buy(1) and differential >= 0. will execute buy')
            return 1
        elif trade_log == -1 and differential < 0:
            # 傾きが-で最後の購入履歴が購入だったなら、売却する
            logger.info('trade log == sell(-1) and differential < 0. will execute sell')
            return -1
        else:
            # 符号が不一致なら何もしない
            logger.info('trade log and differential is mismatch. no deal')
            return 0

    def check_latest_trade(self):
        # 最後の取引履歴を確認する
        # 1: 最後に売却もしくはまだ取引を行っていないので、購入する
        # -1: 最後に購入したので、売却する
        # 0: なんらかの理由で確認できなかった
        logger.debug('Trader.check_latest_trade()')
        return random.randint(-1,1)  # TODO: 

    def check_differential(self):
        # 現在の市場の動向を確認する
        logger.debug('Trader.check_differential()')
        return random.uniform(-1,1)  # TODO:

    def buy(self):
        # 購入取引を実施する
        # 1: 取引成功
        # -1: 取引失敗
        # 0: 取引を行わなかった
        logger.debug('Trader.buy()')
        return random.randint(-1,1)  # TODO: 

    def sell(self):
        # 売却取引を実施する
        # 1: 取引成功
        # -1: 取引失敗
        # 0: 取引を行わなかった
        logger.debug('Trader.sell()')
        return random.randint(-1,1)  # TODO: 


def main():
    logger.info('start trade program')
    update_transaction_id(handler)

    # 取引を行うプログラムの準備を行う
    logger.info('create Trader instance')
    trader = Trader()
    trader.initialize()

    # Event loop
    logger.info('start event loop')
    while True:
        # 取引ごとにログを終えるようにトランザクションIDを更新する
        update_transaction_id(handler)
        logger.info('update transaction id')

        # 取引を行う
        logger.info('start trade')
        trader.trade()
        logger.info('end trade')

        # 1分間に100回までがAPIリクエストの上限なので注意する（処理を1秒ごとに限定して 1分60回に抑える）
        logger.info('wait a 1 sec')
        time.sleep(1)
    

if __name__ == '__main__':
    main()

