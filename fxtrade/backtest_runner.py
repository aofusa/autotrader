import argparse
import json
import logging


from lib import get_module_logger
from lib.history import load_or_fetch, INTERVAL_SECONDS
from lib.exchange import PRODUCT_BTC_FX, PRODUCT_ETH_SPOT
from lib.backtest import run_backtest


logger = get_module_logger()


# Binanceの上場日（これより前のデータはない）
DEFAULT_START_MS = 1502928000000  # 2017-08-17


def main():
    parser = argparse.ArgumentParser(description='Backtest Runner')
    parser.add_argument('--product', choices=['btc', 'eth'], default='btc')
    parser.add_argument('--interval', choices=list(INTERVAL_SECONDS), default='1h')
    parser.add_argument('--initial', type=float, default=500000, help='initial JPY')
    parser.add_argument('--cache-dir', default='docs/artifacts/data')
    parser.add_argument('--config', help='trading config json file (optional)')
    parser.add_argument('--start-ms', type=int, default=DEFAULT_START_MS)
    parser.add_argument('-v', '--verbosity', action='store_true')
    args = parser.parse_args()

    if not args.verbosity:
        logger.setLevel(logging.INFO)

    config = None
    if args.config:
        with open(args.config) as f:
            config = json.load(f).get('trading')

    spec = PRODUCT_BTC_FX if args.product == 'btc' else PRODUCT_ETH_SPOT
    candles = load_or_fetch(spec.symbol, args.interval, args.start_ms, args.cache_dir)
    logger.info(f'loaded {len(candles)} candles for {spec.symbol} {args.interval}')

    result = run_backtest(spec, candles, args.initial, config=config)
    logger.info(f'[{spec.name}] {result.summary()}')
    print(result.summary())


if __name__ == '__main__':
    main()
