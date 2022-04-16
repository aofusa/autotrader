import uuid
import time
import argparse


from market import get_module_logger, update_transaction_id
from market.trader import Trader
from market.mock import MockStockMarket


logger = get_module_logger(__name__)


def main(use_bitflyer, threshold, wait_time, dryrun):
    logger.info('start trade program')
    update_transaction_id(uuid.uuid4().hex)

    # 取引を行うプログラムの準備を行う
    logger.info('create Market instance')
    market = None
    if use_bitflyer:
        logger.info('use bitflyer market')
        market = MockStockMarket(is_dryrun=dryrun)  # TODO: 
    else:
        logger.info('use mock market')
        market = MockStockMarket(is_dryrun=dryrun)

    logger.info('create Trader instance')
    trader = Trader(market, threshold)
    trader.initialize()

    # Event loop
    logger.info('start event loop')
    while True:
        # 取引ごとにログを終えるようにトランザクションIDを更新する
        update_transaction_id(uuid.uuid4().hex)
        logger.info('update transaction id')

        # 取引を行う
        logger.info('start trade')
        trader.trade()
        logger.info('end trade')

        # 1分間に100回までがAPIリクエストの上限なので注意する（処理を1秒ごとに限定して 1分60回に抑える）
        logger.info(f'wait a {wait_time} sec')
        time.sleep(wait_time)
    

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Auto Trading System")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--mock", help="use mock market (default)", action="store_true", default=True)
    group.add_argument("--bitflyer", help="use bitflyer market", action="store_true")
    parser.add_argument("-t", "--threshold", help="set threshold (default 0.1)", type=float, default=0.1)
    parser.add_argument("-w", "--wait", help="set sleep time (default 1 second)", type=int, default=1)
    parser.add_argument("-v", "--verbosity", help="increase output verbosity", action="store_true")
    parser.add_argument("--dryrun", help="Do only check. Do NOT execute any buy/sell functions", action="store_true")
    args = parser.parse_args()

    if not args.verbosity:
        logger.setLevel(INFO)

    if args.dryrun:
        logger.info('dryrun mode')

    main(args.bitflyer, args.threshold, args.wait, args.dryrun)

