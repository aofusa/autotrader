import json
import time
import argparse
import logging


from lib import get_module_logger, update_transaction_id
from lib import TradingEngine, PaperExchange, BitFlyerExchange, products_from_config


logger = get_module_logger()


def main(config, use_bitflyer, threshold, wait_time, dryrun):
    logger.info('start trade program')

    trading_config = config.get('trading') or {}

    # 取引を行う取引所アダプタの準備を行う
    if use_bitflyer:
        logger.info('use bitflyer market (real trading)')
        exchange = BitFlyerExchange(config=config.get('bitflyer'), is_dryrun=dryrun)
    else:
        logger.info('use paper trading market (no real trade will be executed)')
        exchange = PaperExchange(config=trading_config.get('paper'), is_dryrun=dryrun)

    # threshold は旧実装の互換のために受け付けるが、
    # 現在は決済水準を相場のボラティリティ（ATR）から自動算出するため使用しない
    if threshold is not None:
        logger.info(f'note: --threshold ({threshold}) is accepted for compatibility '
                    'but exit levels are now auto-derived from market volatility')

    # 設定された銘柄ごとに取引エンジンを作成する（btc / eth / both）
    products = products_from_config(trading_config.get('products', 'btc'))
    engines = [TradingEngine(exchange, spec, config=trading_config) for spec in products]
    logger.info(f'trading products: {[spec.name for spec in products]}')

    # Event loop
    logger.info('start event loop')
    while True:
        # 予期せぬエラーで停止されると困るのでtryでくくる
        try:
            # 取引ごとにログを追えるようにトランザクションIDを更新する
            update_transaction_id()

            for engine in engines:
                logger.debug(f'start trade cycle: {engine.spec.name}')
                engine.step()
                logger.debug(f'end trade cycle: {engine.spec.name}')

        except Exception as e:
            # 予期せぬエラーが発生したがそのままループを継続させる
            logger.warning(f'unhandled error occurred. but keep event loop. error: {e}')

        finally:
            # APIリクエストの上限に注意して待機する
            logger.debug(f'wait a {wait_time} sec')
            try:
                time.sleep(wait_time)
            except Exception as time_error:
                logger.warning(f'time.sleep() error occurred. error: {time_error}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Auto Trading System")
    parser.add_argument("config", help="Read config file")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--mock", help="use paper trading market (default)", action="store_true", default=True)
    group.add_argument("--bitflyer", help="use bitflyer market (real trading)", action="store_true")
    parser.add_argument("-t", "--threshold", help="(deprecated) kept for compatibility", type=float, default=None)
    parser.add_argument("-w", "--wait", help="set sleep time (default 60 seconds)", type=int, default=60)
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
