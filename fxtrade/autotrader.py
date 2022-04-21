import json
import time
import argparse
import logging


from lib import get_module_logger, update_transaction_id
from lib import Trader, MockStockMarket, BitFlyerMarket


logger = get_module_logger()


def main(config, use_bitflyer, threshold, wait_time, dryrun):
    logger.info('start trade program')
    logger.debug(f'config: {config}')

    # 取引を行うプログラムの準備を行う
    logger.debug('create Market instance')
    market = None
    if use_bitflyer:
        logger.info('use bitflyer market')
        market = BitFlyerMarket(config=config.get('bitflyer'), is_dryrun=dryrun)
    else:
        logger.info('use mock market')
        market = MockStockMarket(is_dryrun=dryrun)

    logger.debug('create Trader instance')
    trader = Trader(market, threshold)
    trader.initialize()

    # Event loop
    logger.info('start event loop')
    while True:
        # 予期せぬエラーで停止されると困るのでtryでくくる
        try:
            # 取引ごとにログを追えるようにトランザクションIDを更新する
            update_transaction_id()
            logger.debug('update transaction id')

            # 取引を行う
            logger.debug('start trade')
            trader.trade()
            logger.debug('end trade')

        except Exception as e:
            # 予期せぬエラーが発生したがそのままループを継続させる
            logger.warning(f'unhandled error occurred. but keep event loop. error: {e}')

        finally:
            # 1分間に100回までがAPIリクエストの上限なので注意する（処理を1秒ごとに限定して 1分60回に抑える）
            logger.debug(f'wait a {wait_time} sec')
            try:
                time.sleep(wait_time)
            except Exception as time_error:
                logger.warning(f'time.sleep() error occurred. error: {time_error}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Auto Trading System")
    parser.add_argument("config", help="Read config file")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--mock", help="use mock market (default)", action="store_true", default=True)
    group.add_argument("--bitflyer", help="use bitflyer market", action="store_true")
    parser.add_argument("-t", "--threshold", help="set threshold (default 0.1)", type=float, default=0.1)
    parser.add_argument("-w", "--wait", help="set sleep time (default 1 second)", type=int, default=1)
    parser.add_argument("-v", "--verbosity", help="increase output verbosity", action="store_true")
    parser.add_argument("--dryrun", help="Do only check. Do NOT execute any buy/sell functions", action="store_true")
    args = parser.parse_args()

    if not args.verbosity:
        logger.setLevel(logging.INFO)

    if args.dryrun:
        logger.info('dryrun mode')

    config = None
    with open(args.config, 'r') as f:
        config = json.load(f)

    main(config, args.bitflyer, args.threshold, args.wait, args.dryrun)

