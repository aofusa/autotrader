

def calc_sma(data, span):
    # 単純移動平均線の作成
    sma = []
    for index in range(len(data)-span):
        s = sum(data[index:index+span])
        m = s / span
        sma.append(m)
    
    return sma


def calc_ema(data, span):
    # 指数平滑移動平均線の作成
    ema = []
    for index in range(len(data)-span):
        s = sum(data[index:index+span])
        es = s + data[index+span]
        em = es / (span+1)
        ema.append(em)

    return ema


def calc_ma_slope(ma, span):
    # 傾きを計算する
    slope = []
    for index in range(len(ma)):
        s = (ma[index] - ma[index-span]) / (index - (index - span))
        slope.append(s)

    return slope


def check_flip_slope(slope):
    # 傾きの反転をチェック
    flip = []
    for index in range(len(slope)-1):
        if slope[index+1] > 0 and slope[index] < 0:
            # +に反転している
            flip.append(1)
        elif slope[index+1] < 0 and slope[index] > 0:
            # -に反転している
            flip.append(-1)
        else:
            # 反転は起きていない
            flip.append(0)

    return flip


def check_latest_differential(data, span, calc_ma=calc_sma):
    # 前回の確認から今回の確認までの間に急激な変化があったかどうかを確認する
    ma = calc_ma(data, span)  # 移動平均線の作成

    # 傾きを計算する
    slope_span = 1
    ma_slope = calc_ma_slope(ma, slope_span)

    # 傾きの反転をチェック
    flip = check_flip_slope(ma_slope)

    latest_flip_list = [x for x in flip if x != 0]  # 傾きが急激に発生したもののみに絞り込む。その中での最新の情報を取得

    # 急激な傾きが一度も起きてなければ最新の傾きを返却する
    if len(latest_flip_list) == 0:
        if len(flip) > 0:
            return flip[-1]
        else:
            # 傾きの情報がなければ傾きはなかったとして返す
            return 0

    # 最新の傾きの情報のみをレスポンスする
    return latest_flip_list[-1]

