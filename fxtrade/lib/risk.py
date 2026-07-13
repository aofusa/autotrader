from . import get_module_logger


logger = get_module_logger()


# レバレッジの絶対上限（設定ファイルでもこれを超えることはできない）
HARD_MAX_LEVERAGE = 3.0


class RiskManager:
    # ポジションサイズの決定と資金保護を行う
    #
    # 資金保護の考え方（証拠金を絶対に枯渇させない）:
    #   1. 1回の取引で失ってよい額は資産の一定割合（risk-per-trade）まで。
    #      損切り幅（ATRベース）から逆算してサイズを決める
    #   2. ボラティリティが高い相場では自動的にサイズを縮小する
    #   3. レバレッジ上限（設定可能・絶対上限3倍）を超えない
    #   4. 証拠金維持率に余裕を残す（margin-usage-limit）
    #   5. ドローダウン中はサイズをさらに縮小し、資産の回復を優先する

    def __init__(self, config=None):
        config = config or {}
        self.max_leverage = min(float(config.get('max-leverage', 2.0)), HARD_MAX_LEVERAGE)
        if float(config.get('max-leverage', 2.0)) > HARD_MAX_LEVERAGE:
            logger.warning(f'max-leverage exceeds hard limit. clamped to {HARD_MAX_LEVERAGE}')
        self.risk_per_trade = float(config.get('risk-per-trade', 0.02))
        self.margin_usage_limit = float(config.get('margin-usage-limit', 0.7))
        self.drawdown_soft = float(config.get('drawdown-soft', 0.10))
        self.drawdown_hard = float(config.get('drawdown-hard', 0.35))
        self.drawdown_min_scale = float(config.get('drawdown-min-scale', 0.25))
        self.equity_peak = 0.0
        logger.debug(f'RiskManager params: max_leverage={self.max_leverage} '
                     f'risk_per_trade={self.risk_per_trade} '
                     f'margin_usage_limit={self.margin_usage_limit}')

    def drawdown_scale(self, equity):
        # ドローダウンに応じたサイズ縮小係数を返す（1.0〜drawdown_min_scale）
        # 資産のピークからの下落率が drawdown_soft を超えると縮小を始め、
        # drawdown_hard で最小係数まで縮小する。ゼロにはしない（取引を止めない）
        self.equity_peak = max(self.equity_peak, equity)
        if self.equity_peak <= 0:
            return 1.0
        dd = 1.0 - equity / self.equity_peak
        if dd <= self.drawdown_soft:
            return 1.0
        if dd >= self.drawdown_hard:
            return self.drawdown_min_scale
        # softとhardの間は線形に縮小する
        ratio = (dd - self.drawdown_soft) / (self.drawdown_hard - self.drawdown_soft)
        return 1.0 - ratio * (1.0 - self.drawdown_min_scale)

    def position_size(self, equity, price, signal, spot=False, min_size=0.0):
        # 目標ポジションサイズ（通貨数量、符号付き）を計算する
        # equity: 現在の資産（証拠金評価額 or 現物口座評価額、JPY）
        # price: 現在価格
        # signal: strategy.Signal
        if equity <= 0 or price <= 0 or signal.direction == 0:
            return 0.0

        # 1. 損切り幅から逆算したサイズ（1回の損失を資産のrisk_per_trade以内に）
        stop_distance = abs(signal.price - signal.stop_price)
        if stop_distance <= 0:
            return 0.0
        size_by_risk = (equity * self.risk_per_trade) / stop_distance

        # 2. シグナルの強さで加重（弱いトレンドには小さく張る。下限0.25）
        strength_scale = 0.25 + 0.75 * signal.strength

        # 3. ドローダウン中はさらに縮小
        dd_scale = self.drawdown_scale(equity)

        size = size_by_risk * strength_scale * dd_scale

        # 4. レバレッジ上限（現物はレバレッジ1倍まで）
        leverage_cap = 1.0 if spot else self.max_leverage
        # 証拠金取引では証拠金使用率の上限も掛ける（維持率に余裕を残す）
        if not spot:
            leverage_cap = min(leverage_cap, self.max_leverage * self.margin_usage_limit)
        max_size = equity * leverage_cap / price
        size = min(size, max_size)

        # 最小取引数量未満なら取引しない（無理に張らない）
        if size < min_size:
            logger.debug(f'size {size} below minimum {min_size}. no position')
            return 0.0

        return signal.direction * size
