import hashlib
import hmac
import json
import time
from urllib import request


from .. import get_module_logger, anonymization
from ..exchange import ExchangeAdapter, ProductSpec
from ..history import fetch_recent_binance_klines
from ..candles import Candle


logger = get_module_logger()


class BitFlyerExchange(ExchangeAdapter):
    # bitFlyer Lightning API を使用する本番用の取引所アダプタ
    # APIドキュメント: https://lightning.bitflyer.com/docs
    #
    # - シグナル計算用のローソク足はBinanceの公開APIから取得し、
    #   bitFlyerの現在価格との比率でJPY相当にスケーリングする
    #   （bitFlyerにはOHLCの公開APIがないため）
    # - FX_BTC_JPY: 証拠金口座（getcollateral）とポジション（getpositions）を使用
    # - 現物（ETH_JPY）: 資産残高（getbalance）を使用

    def __init__(self, config, is_dryrun=False):
        self.config = config or {}
        self.is_dryrun = is_dryrun
        self.key = self.config.get('key')
        self.secret = self.config.get('secret')
        self.url = (self.config.get('endpoint') or {}).get('url', 'https://api.bitflyer.com')
        self.candle_interval = self.config.get('candle-interval', '1h')
        # 予約残高: ここで指定した数量はボットの運用対象外として一切売買しない
        # 例: {"ETH": 0.6875} → 既存保有の0.6875 ETHには手を触れない
        self.spot_reserves = self.config.get('spot-reserves') or {}
        self._price_cache = {}
        logger.debug(f'BitFlyerExchange initialized. key={anonymization(self.key)} '
                     f'dryrun={self.is_dryrun}')

    # --- APIリクエスト共通処理 ---

    def _private_request(self, method, path, body=None):
        # 署名付きのプライベートAPIリクエストを行う
        timestamp = str(int(time.time() * 1000))
        body_str = json.dumps(body) if body is not None else ''
        text = timestamp + method + path + body_str
        sign = hmac.new(self.secret.encode(), text.encode(), hashlib.sha256).hexdigest()
        headers = {
            'ACCESS-KEY': self.key,
            'ACCESS-TIMESTAMP': timestamp,
            'ACCESS-SIGN': sign,
        }
        if body is not None:
            headers['Content-Type'] = 'application/json'
        data = body_str.encode() if body is not None else b''
        logger.debug(f'call api: {method} {self.url + path}')
        req = request.Request(self.url + path, data, headers, method=method)
        with request.urlopen(req, timeout=30) as response:
            return json.loads(response.read())

    def _public_request(self, path):
        logger.debug(f'call api: GET {self.url + path}')
        with request.urlopen(self.url + path, timeout=30) as response:
            return json.loads(response.read())

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

        bf_price = self.get_price(spec)
        if bf_price > 0 and candles[-1].close > 0:
            rate = bf_price / candles[-1].close
        else:
            rate = 1.0
        return [Candle(time=c.time, open=c.open * rate, high=c.high * rate,
                       low=c.low * rate, close=c.close * rate,
                       volume=c.volume) for c in candles]

    def get_price(self, spec):
        try:
            ticker = self._public_request(f'/v1/getticker?product_code={spec.code}')
            price = float(ticker.get('ltp', 0))
            if price > 0:
                self._price_cache[spec.code] = price
            return price
        except Exception as e:
            logger.warning(f'failed to get ticker: {e}')
            return self._price_cache.get(spec.code, 0)

    # --- 口座情報 ---

    def get_equity(self, spec):
        try:
            if spec.spot:
                # 現物: 日本円残高 + 運用対象の保有数量（予約残高を除く）の評価額
                balances = self._private_request('GET', '/v1/me/getbalance')
                jpy = 0.0
                coin = 0.0
                currency = spec.code.split('_')[0]  # 'ETH_JPY' -> 'ETH'
                for b in balances:
                    if b.get('currency_code') == 'JPY':
                        jpy = float(b.get('amount', 0))
                    elif b.get('currency_code') == currency:
                        coin = float(b.get('amount', 0))
                reserve = float(self.spot_reserves.get(currency, 0))
                tradable = max(coin - reserve, 0.0)
                price = self.get_price(spec)
                equity = jpy + tradable * price
                logger.info(f'equity [{spec.name}]: {equity:,.0f} JPY '
                            f'(JPY={jpy:,.0f}, {currency}={coin}, '
                            f'reserved={reserve}, tradable={tradable})')
                return equity
            else:
                # FX: 証拠金 + 評価損益
                collateral = self._private_request('GET', '/v1/me/getcollateral')
                equity = float(collateral.get('collateral', 0)) + \
                    float(collateral.get('open_position_pnl', 0))
                logger.info(f'equity [{spec.name}]: {equity:,.0f} JPY '
                            f'(collateral={collateral.get("collateral")}, '
                            f'pnl={collateral.get("open_position_pnl")}, '
                            f'keep_rate={collateral.get("keep_rate")})')
                return equity
        except Exception as e:
            logger.warning(f'failed to get equity: {e}')
            return 0

    def get_position(self, spec):
        try:
            if spec.spot:
                balances = self._private_request('GET', '/v1/me/getbalance')
                currency = spec.code.split('_')[0]
                for b in balances:
                    if b.get('currency_code') == currency:
                        # 予約残高はボットのポジションとして扱わない（売買対象外）
                        reserve = float(self.spot_reserves.get(currency, 0))
                        return max(float(b.get('amount', 0)) - reserve, 0.0)
                return 0.0
            else:
                positions = self._private_request(
                    'GET', f'/v1/me/getpositions?product_code={spec.code}')
                size = 0.0
                for p in positions:
                    if p.get('side') == 'BUY':
                        size += float(p.get('size', 0))
                    elif p.get('side') == 'SELL':
                        size -= float(p.get('size', 0))
                return size
        except Exception as e:
            logger.warning(f'failed to get position: {e}')
            return 0.0

    # --- 発注 ---

    def market_order(self, spec, side, size):
        if spec.spot and side == 'SELL':
            # 安全装置: 現物の売却は運用対象数量（予約残高を除く）を超えない
            tradable = self.get_position(spec)
            if size > tradable:
                logger.warning(f'[{spec.name}] sell size {size} exceeds tradable {tradable}. clamped')
                size = tradable
            if size < spec.min_size:
                logger.warning(f'[{spec.name}] sell size below minimum. order skipped')
                return -1
        size = float(f'{size:.8f}')
        body = {
            'product_code': spec.code,
            'child_order_type': 'MARKET',
            'side': side,
            'size': size,
        }

        if self.is_dryrun:
            logger.info(f'trade [{spec.name}]: {side} {size} dryrun (order not sent)')
            return 0

        try:
            result = self._private_request('POST', '/v1/me/sendchildorder', body)
            logger.info(f'trade [{spec.name}]: {side} {size} success. '
                        f'acceptance_id={result.get("child_order_acceptance_id")}')
            return 1
        except Exception as e:
            logger.warning(f'trade [{spec.name}]: {side} {size} failed. error: {e}')
            return -1
