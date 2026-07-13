import json
import os
import time
from urllib import request


from .. import get_module_logger
from ..exchange import ExchangeAdapter, ProductSpec
from ..history import fetch_recent_binance_klines
from ..candles import Candle


logger = get_module_logger()


DEFAULT_STATE_PATH = 'docs/artifacts/paper_state.json'
BITFLYER_URL = 'https://api.bitflyer.com'


class PaperExchange(ExchangeAdapter):
    # ペーパートレード（モック）用の取引所
    #
    # - シグナル計算用のローソク足はBinanceの公開APIから取得し、
    #   bitFlyerの現在価格との比率でJPY相当にスケーリングする
    #   （戦略はスケール不変なので方向・ATR比率は保たれる）
    # - 注文は実行せず、仮想口座に約定を記録する
    #   （実際に取引を行っていたらどうなっていたかを確認できる）
    # - 口座状態はファイルに永続化され、再起動しても継続する

    def __init__(self, config=None, is_dryrun=False, state_path=None):
        config = config or {}
        self.is_dryrun = is_dryrun  # ペーパートレードは元々取引しないためdryrunでも動作は同じ
        self.initial_jpy = float(config.get('initial-jpy', 500000))
        self.slippage = float(config.get('slippage', 0.0005))
        self.swap_rate_daily = float(config.get('swap-rate-daily', 0.0004))
        self.spot_fee_rate = float(config.get('spot-fee-rate', 0.0015))
        self.candle_interval = config.get('candle-interval', '1h')
        self.state_path = state_path or config.get('state-path', DEFAULT_STATE_PATH)
        self.state = self._load_state()
        self._price_cache = {}

    # --- 口座状態の永続化 ---

    def _load_state(self):
        if os.path.exists(self.state_path):
            try:
                with open(self.state_path) as f:
                    state = json.load(f)
                logger.info(f'loaded paper trading state from {self.state_path}')
                return state
            except Exception as e:
                logger.warning(f'failed to load paper state: {e}. start fresh')
        return {}

    def _save_state(self):
        try:
            os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
            with open(self.state_path, 'w') as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            logger.warning(f'failed to save paper state: {e}')

    def _account(self, spec: ProductSpec):
        # 銘柄ごとの仮想口座を取得する（なければ初期資金で作成）
        if spec.code not in self.state:
            self.state[spec.code] = {
                'cash': self.initial_jpy,
                'size': 0.0,
                'entry_price': 0.0,
                'fees_paid': 0.0,
                'swap_paid': 0.0,
                'trade_count': 0,
                'last_swap_time': time.time(),
            }
            self._save_state()
        return self.state[spec.code]

    # --- 市場データ ---

    def get_candles(self, spec, limit):
        try:
            candles = fetch_recent_binance_klines(spec.symbol, self.candle_interval,
                                                  limit=min(limit + 1, 1000))
        except Exception as e:
            logger.warning(f'failed to fetch candles: {e}')
            return []
        if not candles:
            return []
        candles = candles[:-1]  # 最後の1本は未確定足なので除外する

        # bitFlyerの現在価格との比率でJPY相当にスケーリングする
        bf_price = self._bitflyer_ticker(spec)
        if bf_price > 0 and candles[-1].close > 0:
            rate = bf_price / candles[-1].close
        else:
            rate = 1.0
        return [Candle(time=c.time, open=c.open * rate, high=c.high * rate,
                       low=c.low * rate, close=c.close * rate,
                       volume=c.volume) for c in candles]

    def _bitflyer_ticker(self, spec):
        try:
            url = f'{BITFLYER_URL}/v1/getticker?product_code={spec.code}'
            logger.debug(f'call api: {url}')
            with request.urlopen(url, timeout=15) as response:
                ticker = json.loads(response.read())
            price = float(ticker.get('ltp', 0))
            if price > 0:
                self._price_cache[spec.code] = price
            return price
        except Exception as e:
            logger.warning(f'failed to get bitflyer ticker: {e}')
            return self._price_cache.get(spec.code, 0)

    def get_price(self, spec):
        price = self._bitflyer_ticker(spec)
        if price <= 0:
            price = self._price_cache.get(spec.code, 0)
        return price

    # --- 仮想口座 ---

    def get_equity(self, spec):
        acc = self._account(spec)
        self._apply_swap(spec, acc)
        price = self.get_price(spec)
        if price <= 0:
            price = acc['entry_price']
        equity = acc['cash'] + acc['size'] * (price - acc['entry_price'])
        logger.info(f'paper equity [{spec.name}]: {equity:,.0f} JPY '
                    f'(cash={acc["cash"]:,.0f}, size={acc["size"]}, '
                    f'entry={acc["entry_price"]:,.0f}, price={price:,.0f})')
        return equity

    def get_position(self, spec):
        return self._account(spec)['size']

    def _apply_swap(self, spec, acc):
        # FXの建玉に対して経過時間分のスワップコストを計上する
        now = time.time()
        last = acc.get('last_swap_time', now)
        acc['last_swap_time'] = now
        if spec.spot or acc['size'] == 0:
            return
        price = self._price_cache.get(spec.code) or acc['entry_price']
        notional = abs(acc['size']) * price
        swap = notional * self.swap_rate_daily * ((now - last) / 86400.0)
        if swap > 0:
            acc['cash'] -= swap
            acc['swap_paid'] += swap
            self._save_state()

    def market_order(self, spec, side, size):
        # 仮想約定を記録する（実際の注文は行わない）
        acc = self._account(spec)
        price = self.get_price(spec)
        if price <= 0:
            logger.warning(f'[{spec.name}] no price available. order skipped')
            return -1

        direction = 1 if side == 'BUY' else -1
        fill_price = price * (1 + direction * self.slippage)
        fee_rate = self.spot_fee_rate if spec.spot else 0.0

        if spec.spot:
            if direction > 0:
                cost = size * fill_price * (1 + fee_rate)
                if cost > acc['cash']:
                    size = acc['cash'] / (fill_price * (1 + fee_rate))
                    if size < spec.min_size:
                        return -1
            else:
                size = min(size, acc['size'])
                if size < spec.min_size:
                    return -1

        fee = size * fill_price * fee_rate
        acc['cash'] -= fee
        acc['fees_paid'] += fee

        old_size = acc['size']
        new_size = old_size + direction * size
        if old_size != 0 and (direction > 0) != (old_size > 0):
            closed = min(size, abs(old_size))
            pnl = closed * (fill_price - acc['entry_price']) * (1 if old_size > 0 else -1)
            acc['cash'] += pnl
            if abs(new_size) > 1e-12 and (new_size > 0) != (old_size > 0):
                acc['entry_price'] = fill_price
        else:
            total = abs(old_size) + size
            if total > 0:
                acc['entry_price'] = (abs(old_size) * acc['entry_price'] + size * fill_price) / total

        if abs(new_size) < 1e-12:
            new_size = 0.0
            acc['entry_price'] = 0.0
        acc['size'] = new_size
        acc['trade_count'] += 1
        self._save_state()

        logger.info(f'paper trade [{spec.name}]: {side} {size} at {fill_price:,.0f} '
                    f'(fee={fee:,.0f}, position={new_size}, cash={acc["cash"]:,.0f})')
        return 1
