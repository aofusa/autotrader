from dataclasses import dataclass, field


from . import get_module_logger
from .exchange import ExchangeAdapter, ProductSpec
from .engine import TradingEngine


logger = get_module_logger()


@dataclass
class SimAccount:
    # シミュレーション用の口座
    cash: float = 0.0          # JPY残高（FXでは証拠金）
    size: float = 0.0          # ポジション数量（符号付き）
    entry_price: float = 0.0   # 平均取得単価
    fees_paid: float = 0.0
    swap_paid: float = 0.0
    trade_count: int = 0

    def equity(self, price):
        return self.cash + self.size * (price - self.entry_price)


class SimulatedExchange(ExchangeAdapter):
    # バックテスト用の取引所シミュレータ
    # bitFlyerの実際のコストを模擬する:
    #   - FX_BTC_JPY: 取引手数料0%、建玉のスワップ 0.04%/日
    #   - 現物: 取引手数料 0.15%（最大値で見積もる）
    #   - スリッページ: 成行注文は価格の0.05%不利に約定すると仮定

    # bitFlyerのFXは証拠金維持率50%を下回ると追証、さらに下回るとロスカット
    # ここでは要求証拠金（想定元本/レバレッジ2倍）の80%を下回ったら
    # マージンコールとして記録する（これが起きたら戦略は失格）
    EXCHANGE_LEVERAGE = 2.0
    MAINTENANCE_RATIO = 0.8

    def __init__(self, spec: ProductSpec, candles, initial_jpy,
                 fee_rate=None, slippage=0.0005, swap_rate_daily=0.0004):
        self.spec = spec
        self.candles = candles
        self.account = SimAccount(cash=initial_jpy)
        self.index = 0
        self.slippage = slippage
        self.swap_rate_daily = swap_rate_daily
        if fee_rate is None:
            fee_rate = 0.0015 if spec.spot else 0.0
        self.fee_rate = fee_rate
        self.margin_call_count = 0

    # --- バックテスト制御 ---

    def advance(self, index):
        # 時刻を進める。足の経過時間に応じてスワップコストを計上する
        prev_index = self.index
        self.index = index
        if not self.spec.spot and self.account.size != 0 and index > prev_index:
            bar_seconds = 0
            if index > 0:
                bar_seconds = self.candles[index].time - self.candles[prev_index].time
            notional = abs(self.account.size) * self.price()
            swap = notional * self.swap_rate_daily * (bar_seconds / 86400.0)
            self.account.cash -= swap
            self.account.swap_paid += swap

        # 証拠金維持率のチェック（FXのみ）
        if not self.spec.spot and self.account.size != 0:
            notional = abs(self.account.size) * self.price()
            required = notional / self.EXCHANGE_LEVERAGE
            if self.equity() < required * self.MAINTENANCE_RATIO:
                self.margin_call_count += 1
                logger.warning(f'MARGIN CALL at index {index}: equity={self.equity():.0f} '
                               f'required={required:.0f}')

    def price(self):
        return self.candles[self.index].close

    def equity(self):
        return self.account.equity(self.price())

    # --- ExchangeAdapter 実装 ---

    def get_candles(self, spec, limit):
        start = max(0, self.index + 1 - limit)
        return self.candles[start:self.index + 1]

    def get_price(self, spec):
        return self.price()

    def get_equity(self, spec):
        return self.equity()

    def get_position(self, spec):
        return self.account.size

    def market_order(self, spec, side, size):
        acc = self.account
        direction = 1 if side == 'BUY' else -1
        fill_price = self.price() * (1 + direction * self.slippage)

        if spec.spot:
            # 現物: 買いは現金の範囲内、売りは保有数量の範囲内
            if direction > 0:
                cost = size * fill_price * (1 + self.fee_rate)
                if cost > acc.cash:
                    size = acc.cash / (fill_price * (1 + self.fee_rate))
                    if size < spec.min_size:
                        return -1
            else:
                size = min(size, acc.size)
                if size < spec.min_size:
                    return -1

        fee = size * fill_price * self.fee_rate
        acc.fees_paid += fee
        acc.cash -= fee

        new_size = acc.size + direction * size
        if acc.size != 0 and (direction > 0) != (acc.size > 0):
            # 反対売買: 決済分の損益を現金に反映する
            closed = min(size, abs(acc.size))
            pnl = closed * (fill_price - acc.entry_price) * (1 if acc.size > 0 else -1)
            acc.cash += pnl
            if abs(new_size) > 1e-12 and (new_size > 0) != (acc.size > 0):
                # ドテン: 残りは新規建て
                acc.entry_price = fill_price
        elif acc.size == 0 or (direction > 0) == (acc.size > 0):
            # 新規または増し玉: 平均取得単価を更新する
            total = abs(acc.size) + size
            if total > 0:
                acc.entry_price = (abs(acc.size) * acc.entry_price + size * fill_price) / total

        if abs(new_size) < 1e-12:
            new_size = 0.0
            acc.entry_price = 0.0
        acc.size = new_size
        acc.trade_count += 1
        return 1


@dataclass
class BacktestResult:
    initial_equity: float
    final_equity: float
    max_drawdown: float
    trade_count: int
    fees_paid: float
    swap_paid: float
    margin_call_count: int
    years: float
    equity_curve: list = field(default_factory=list)

    @property
    def total_return(self):
        return self.final_equity / self.initial_equity - 1.0

    @property
    def cagr(self):
        if self.years <= 0 or self.final_equity <= 0:
            return -1.0
        return (self.final_equity / self.initial_equity) ** (1.0 / self.years) - 1.0

    def summary(self):
        return (f'initial={self.initial_equity:,.0f} final={self.final_equity:,.0f} '
                f'return={self.total_return:+.1%} cagr={self.cagr:+.1%}/y '
                f'maxDD={self.max_drawdown:.1%} trades={self.trade_count} '
                f'fees={self.fees_paid:,.0f} swap={self.swap_paid:,.0f} '
                f'margin_calls={self.margin_call_count}')


def run_backtest(spec: ProductSpec, candles, initial_jpy, config=None,
                 fee_rate=None, slippage=0.0005, swap_rate_daily=0.0004):
    # 過去データに対して戦略を実行し、資産推移を検証する
    sim = SimulatedExchange(spec, candles, initial_jpy,
                            fee_rate=fee_rate, slippage=slippage,
                            swap_rate_daily=swap_rate_daily)
    engine = TradingEngine(sim, spec, config=config)

    warmup = engine.strategy.min_history()
    if warmup >= len(candles):
        # データ不足の場合は取引なし（資産は初期値のまま）として返す
        logger.warning(f'not enough candles for backtest: {len(candles)} < {warmup}')
        return BacktestResult(initial_equity=initial_jpy, final_equity=initial_jpy,
                              max_drawdown=0.0, trade_count=0, fees_paid=0.0,
                              swap_paid=0.0, margin_call_count=0, years=0.0)
    equity_curve = []
    peak = initial_jpy
    max_dd = 0.0

    for i in range(warmup, len(candles)):
        sim.advance(i)
        engine.step()
        eq = sim.equity()
        equity_curve.append((candles[i].time, eq))
        peak = max(peak, eq)
        if peak > 0:
            max_dd = max(max_dd, 1.0 - eq / peak)

    years = (candles[-1].time - candles[warmup].time) / (365.25 * 86400)
    return BacktestResult(
        initial_equity=initial_jpy,
        final_equity=sim.equity(),
        max_drawdown=max_dd,
        trade_count=sim.account.trade_count,
        fees_paid=sim.account.fees_paid,
        swap_paid=sim.account.swap_paid,
        margin_call_count=sim.margin_call_count,
        years=years,
        equity_curve=equity_curve,
    )
