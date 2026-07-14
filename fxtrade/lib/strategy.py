from dataclasses import dataclass


from . import get_module_logger
from .indicators import ema, atr


logger = get_module_logger()


@dataclass
class Signal:
    # 戦略が出力する取引シグナル
    direction: int      # 1: ロング, -1: ショート, 0: ノーポジション
    strength: float     # シグナルの強さ 0.0〜1.0（ポジションサイズの係数）
    stop_price: float   # 損切り・トレーリングストップの価格（ポジションがない場合は0）
    atr: float          # 現在のATR（リスク計算用）
    price: float        # 直近終値


@dataclass
class PositionState:
    # 現在保有しているポジションの状態（トレーリングストップの計算に使う）
    direction: int = 0        # 1: ロング, -1: ショート, 0: なし
    entry_price: float = 0.0
    extreme_price: float = 0.0  # エントリー以降の最良値（ロングなら最高値、ショートなら最安値）

    def update_extreme(self, price):
        if self.direction > 0:
            self.extreme_price = max(self.extreme_price, price)
        elif self.direction < 0:
            self.extreme_price = min(self.extreme_price, price) if self.extreme_price > 0 else price


class TrendStrategy:
    # トレンドフォロー戦略
    #
    # エントリー:
    #   - EMA(fast) と EMA(slow) のクロスでトレンド方向を判断
    #   - ドンチャンチャネルのブレイクアウトで確認（だましの抑制）
    # 決済（固定値は持たず、毎回ATRから自動算出する）:
    #   - シャンデリアエグジット: エントリー後の最良値から ATR×係数 逆行したら決済
    #   - トレンド反転（EMAクロスの逆転）でも決済
    # 強さ:
    #   - EMAの乖離をATRで正規化した値。トレンドが強いほどポジションを大きくする

    def __init__(self, config=None):
        config = config or {}
        # デフォルト値はBTC/ETHの2017〜2026年のバックテストで選定した
        # 頑健なパラメータ（4時間足を想定）
        self.fast_span = int(config.get('fast-span', 20))
        self.slow_span = int(config.get('slow-span', 300))
        self.atr_span = int(config.get('atr-span', 14))
        self.donchian_span = int(config.get('donchian-span', 200))
        self.trail_atr_mult = float(config.get('trail-atr-mult', 2.5))
        self.allow_short = bool(config.get('allow-short', True))
        logger.debug(f'TrendStrategy params: fast={self.fast_span} slow={self.slow_span} '
                     f'atr={self.atr_span} donchian={self.donchian_span} '
                     f'trail={self.trail_atr_mult} allow_short={self.allow_short}')

    def min_history(self):
        # シグナル計算に必要な最低限のローソク足の本数
        return max(self.slow_span, self.donchian_span, self.atr_span) + 2

    def evaluate(self, candles, position: PositionState):
        # 確定済みローソク足からシグナルを計算する
        if len(candles) < self.min_history():
            logger.debug(f'not enough candles: {len(candles)} < {self.min_history()}')
            return Signal(direction=0, strength=0.0, stop_price=0.0, atr=0.0,
                          price=candles[-1].close if candles else 0.0)

        closes = [c.close for c in candles]
        price = closes[-1]

        fast = ema(closes, self.fast_span)
        slow = ema(closes, self.slow_span)
        atr_series = atr(candles, self.atr_span)
        current_atr = atr_series[-1]
        # ブレイクアウト判定は現在の足を除いた直近N本の終値で行う
        # （高値・安値ベースだと緩やかなトレンドを取りこぼすため終値を使う）
        window = closes[-(self.donchian_span + 1):-1]
        high_band = max(window)
        low_band = min(window)

        trend = 1 if fast[-1] > slow[-1] else -1

        # トレンドの強さ: EMAの乖離をATRで正規化（0.0〜1.0にクリップ）
        if current_atr > 0:
            strength = min(abs(fast[-1] - slow[-1]) / (current_atr * 2.0), 1.0)
        else:
            strength = 0.0

        # ポジションを持っている場合: トレーリングストップとトレンド反転をチェック
        if position.direction != 0:
            position.update_extreme(price)
            stop = self._trailing_stop(position, current_atr)
            flipped = (trend != position.direction)
            stopped = (position.direction > 0 and price <= stop) or \
                      (position.direction < 0 and price >= stop)
            if flipped or stopped:
                reason = 'trend flipped' if flipped else 'trailing stop hit'
                logger.debug(f'exit signal: {reason} (price={price}, stop={stop})')
                # 決済。反転シグナルが強ければ即ドテンする
                if flipped and self._breakout_confirmed(trend, price, high_band, low_band):
                    if trend < 0 and not self.allow_short:
                        return Signal(0, 0.0, 0.0, current_atr, price)
                    return Signal(trend, strength, self._initial_stop(trend, price, current_atr),
                                  current_atr, price)
                return Signal(0, 0.0, 0.0, current_atr, price)
            # 継続保有。ストップ水準を更新して返す
            return Signal(position.direction, strength, stop, current_atr, price)

        # ノーポジションの場合: 新規エントリーの判断
        if self._breakout_confirmed(trend, price, high_band, low_band):
            if trend < 0 and not self.allow_short:
                logger.debug('short signal but short is not allowed (spot market)')
                return Signal(0, 0.0, 0.0, current_atr, price)
            logger.debug(f'entry signal: direction={trend}, strength={strength:.3f}')
            return Signal(trend, strength,
                          self._initial_stop(trend, price, current_atr), current_atr, price)

        return Signal(0, 0.0, 0.0, current_atr, price)

    def _breakout_confirmed(self, trend, price, high_band, low_band):
        # ドンチャンチャネルのブレイクアウトでトレンドを確認する
        if trend > 0:
            return price > high_band
        else:
            return price < low_band

    def _initial_stop(self, direction, price, current_atr):
        # 新規エントリー時の損切り水準（ATRベースで自動算出）
        return price - direction * self.trail_atr_mult * current_atr

    def _trailing_stop(self, position: PositionState, current_atr):
        # シャンデリアエグジット: 最良値からATR×係数の逆行で決済
        return position.extreme_price - position.direction * self.trail_atr_mult * current_atr
