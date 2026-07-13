from abc import ABCMeta, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class ProductSpec:
    # 取引対象の銘柄の定義
    name: str           # 表示名（例: 'BTC-FX'）
    code: str           # bitFlyerのproduct_code（例: 'FX_BTC_JPY'）
    symbol: str         # チャートデータ取得用のシンボル（例: 'BTCUSDT'）
    spot: bool          # True: 現物（ロングのみ・レバレッジなし）, False: 証拠金取引
    min_size: float     # 最小取引数量


# bitFlyerで取引可能な銘柄
# bitFlyerのレバレッジ取引（FX）はBTCのみ対応。ETHは現物のみ
PRODUCT_BTC_FX = ProductSpec(name='BTC-FX', code='FX_BTC_JPY', symbol='BTCUSDT',
                             spot=False, min_size=0.01)
PRODUCT_ETH_SPOT = ProductSpec(name='ETH', code='ETH_JPY', symbol='ETHUSDT',
                               spot=True, min_size=0.01)


def products_from_config(products_setting):
    # 設定値（'btc' / 'eth' / 'both'）から取引対象のリストを返す
    setting = (products_setting or 'btc').lower()
    if setting == 'btc':
        return [PRODUCT_BTC_FX]
    elif setting == 'eth':
        return [PRODUCT_ETH_SPOT]
    elif setting == 'both':
        return [PRODUCT_BTC_FX, PRODUCT_ETH_SPOT]
    else:
        raise ValueError(f'unknown products setting: {products_setting} (use btc / eth / both)')


class ExchangeAdapter(metaclass=ABCMeta):
    # 取引所へのアクセスを抽象化するインタフェース
    # 本番（bitFlyer）・ペーパートレード・バックテストで共通

    @abstractmethod
    def get_candles(self, spec: ProductSpec, limit: int):
        # 確定済みローソク足を古い順に返す
        pass

    @abstractmethod
    def get_price(self, spec: ProductSpec):
        # 現在価格を返す（取得できなければ0）
        pass

    @abstractmethod
    def get_equity(self, spec: ProductSpec):
        # この銘柄の取引に使える資産評価額（JPY）を返す
        # FX: 証拠金 + 評価損益、現物: 日本円残高 + 保有数量の評価額
        pass

    @abstractmethod
    def get_position(self, spec: ProductSpec):
        # 現在のポジション数量（符号付き。現物は保有数量）を返す
        pass

    @abstractmethod
    def market_order(self, spec: ProductSpec, side: str, size: float):
        # 成行注文を出す。side: 'BUY' or 'SELL'
        # 1: 成功, -1: 失敗, 0: 実行しなかった（dryrun等）
        pass
