from . import get_module_logger
from .strategy import TrendStrategy, PositionState
from .risk import RiskManager
from .exchange import ProductSpec, ExchangeAdapter


logger = get_module_logger()


class TradingEngine:
    # 1銘柄の取引を管理するエンジン
    # 毎サイクル step() を呼ぶと、シグナル計算 → 目標ポジション算出 → 発注 を行う

    def __init__(self, exchange: ExchangeAdapter, spec: ProductSpec,
                 strategy: TrendStrategy = None, risk: RiskManager = None,
                 config=None):
        config = config or {}
        self.exchange = exchange
        self.spec = spec
        self.strategy = strategy or TrendStrategy(config.get('strategy'))
        if spec.spot:
            # 現物はショートできないため設定に関わらず禁止する
            self.strategy.allow_short = False
        self.risk = risk or RiskManager(config.get('risk'))
        # ポジションの入れ替えを行う閾値（小さな乖離では発注せず手数料と滑りを節約する）
        self.rebalance_threshold = float(config.get('rebalance-threshold', 0.3))
        self.candle_limit = max(self.strategy.min_history() + 10,
                                int(config.get('candle-limit', 200)))
        self.position_state = PositionState()

    def step(self):
        # 1サイクル分の取引判断と執行を行う
        # 戻り値: (発注したかどうか, シグナル) のタプル
        spec = self.spec
        logger.debug(f'[{spec.name}] engine step')

        candles = self.exchange.get_candles(spec, self.candle_limit)
        if not candles:
            logger.warning(f'[{spec.name}] no candle data. skip this cycle')
            return (False, None)

        current = self.exchange.get_position(spec)
        equity = self.exchange.get_equity(spec)
        logger.debug(f'[{spec.name}] current position: {current}, equity: {equity}')

        if equity <= 0:
            logger.warning(f'[{spec.name}] no equity available. skip this cycle')
            return (False, None)

        # 実際のポジションと内部状態を同期する
        # （手動決済や強制決済などで外部からポジションが変わった場合に追従する）
        self._sync_position_state(current, candles[-1].close)

        signal = self.strategy.evaluate(candles, self.position_state)
        logger.debug(f'[{spec.name}] signal: direction={signal.direction} '
                     f'strength={signal.strength:.3f} stop={signal.stop_price:.1f} '
                     f'price={signal.price:.1f}')

        target = self.risk.position_size(equity, signal.price, signal,
                                         spot=spec.spot, min_size=spec.min_size)
        logger.debug(f'[{spec.name}] target position: {target}')

        traded = self._execute(current, target, signal)
        return (traded, signal)

    def _sync_position_state(self, current, price):
        state = self.position_state
        if abs(current) < self.spec.min_size / 2:
            # 実ポジションがない
            if state.direction != 0:
                logger.debug(f'[{self.spec.name}] position closed externally. reset state')
                self.position_state = PositionState()
        else:
            direction = 1 if current > 0 else -1
            if state.direction != direction:
                # 外部でポジションが変わった（または再起動でメモリ上の状態が消えた）
                logger.debug(f'[{self.spec.name}] adopt external position: direction={direction}')
                self.position_state = PositionState(direction=direction,
                                                    entry_price=price,
                                                    extreme_price=price)

    def _execute(self, current, target, signal):
        # 現在ポジションと目標ポジションの差分を発注する
        spec = self.spec
        delta = target - current

        if abs(delta) < spec.min_size:
            logger.debug(f'[{spec.name}] delta {delta} below min size. no order')
            return False

        # 方向転換・決済以外の単なるサイズ調整は、乖離が大きいときだけ行う（取引コスト節約）
        same_direction = (current > 0 and target > 0) or (current < 0 and target < 0)
        if same_direction:
            base = max(abs(current), abs(target))
            if base > 0 and abs(delta) / base < self.rebalance_threshold:
                logger.debug(f'[{spec.name}] rebalance too small '
                             f'({abs(delta)/base:.2%} < {self.rebalance_threshold:.0%}). no order')
                return False

        side = 'BUY' if delta > 0 else 'SELL'
        size = round(abs(delta), 8)
        logger.info(f'[{spec.name}] order: {side} {size} '
                    f'(current={current}, target={target}, price={signal.price})')
        result = self.exchange.market_order(spec, side, size)

        if result >= 0:
            # 成功（またはdryrun）。新規・決済・ドテンのとき内部状態を作り直す
            # （同方向のサイズ調整ではエントリー情報を維持する）
            if not same_direction:
                if abs(target) < spec.min_size / 2:
                    self.position_state = PositionState()
                else:
                    direction = 1 if target > 0 else -1
                    self.position_state = PositionState(direction=direction,
                                                        entry_price=signal.price,
                                                        extreme_price=signal.price)
            return True
        else:
            logger.warning(f'[{spec.name}] order failed')
            return False
