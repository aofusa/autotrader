import json
import time
import hmac
import hashlib
import random
from urllib import request


from .. import get_module_logger, calc_sma, calc_ema, calc_ma_slope, check_flip_slope
from ..base_market import BaseMarket


logger = get_module_logger()


class BitFlyerMarket(BaseMarket):

    is_dryrun = False  # dryrunモードフラグ
    cancel_order_id = None  # 未約定の取引があった場合、キャンセルするためにidを控える

    def __init__(self, config, is_dryrun=False):
        logger.debug(f'{type(self).__name__}.__init__()')

        self.is_dryrun = is_dryrun
        logger.debug(f'set is_dryrun: {self.is_dryrun}')

        self.config = config
        logger.debug(f'set config: {self.config}')

        self.key = self.config.get('key')
        self.secret = self.config.get('secret')

        self.strategy = self.config.get('strategy')

        self.url = self.config.get('endpoint').get('url')
        self.check_collateral_endpoint = self.config.get('endpoint').get('check-collateral')  # GET
        self.check_positions_endpoint = self.config.get('endpoint').get('check-positions')  # GET
        self.check_ticker_endpoint = self.config.get('endpoint').get('check-ticker')  # GET
        self.check_trade_endpoint = self.config.get('endpoint').get('check-trade')  # GET
        self.buy_endpoint = self.config.get('endpoint').get('buy')  # POST
        self.sell_endpoint = self.config.get('endpoint').get('sell')  # POST
        self.cancel_endpoint = self.config.get('endpoint').get('cancel')  # POST
        self.chart_endpoint = self.config.get('endpoint').get('chart')  # GET
        self.cryptwatch_data_type = self.config.get('type')
        self.span = self.config.get('span')
        self.minimum_trade_size = self.config.get('minimum-trade-size')

    def check_latest_trade(self):
        # 最後の取引履歴を確認する
        # 1: 最後に売却もしくはまだ取引を行っていないので、購入する
        # -1: 最後に購入したので、売却する
        # 0: なんらかの理由で確認できなかった
        logger.debug(f'{type(self).__name__}.check_latest_trade()')

        key = self.key
        secret = self.secret
        url = self.url

        timestamp = str(int(time.time()*1000))
        method = 'GET'
        path = self.check_trade_endpoint

        text = timestamp + method + path
        sign = hmac.new(secret.encode(), text.encode(), hashlib.sha256).hexdigest()

        headers = {
            'ACCESS-KEY': key,
            'ACCESS-TIMESTAMP': timestamp,
            'ACCESS-SIGN': sign,
        }

        logger.debug(f'call api: {url+path}')
        logger.debug(f'headers: {headers}')
        req = request.Request(url+path, b'', headers, method=method)
        
        try:
            with request.urlopen(req) as response:
                trade_results_raw = response.read()
            trade_results = json.loads(trade_results_raw)
        except Exception as e:
            # 取得に失敗したので確認できなかったことを返す
            logger.warning(e)
            return 0
        logger.debug(f'trade result list: {trade_results}')

        # レスポンスの内容を確認し次に購入/売却にするか決める
        # ACTIVEとCOMPLETEDのみに絞り込み、その中で最新の申込内容を確認する
        # COMPLETEDなら、次の行動はSELL/BUYのどちらかだったかで売却/購入を決める
        # ACTIVEなら、次の行動はCANCELになるので注意する

        trade_results_list = [x for x in trade_results if x.get('child_order_state') == 'ACTIVE' or x.get('child_order_state') == 'COMPLETED']  # ACTIVEとCOMPLETEDに絞り込む
        logger.debug(f'trade result list(filter): {trade_results_list}')
        if len(trade_results_list) == 0:  # 空なら初めての取引なので購入を返す
            self.cancel_order_id = None  # キャンセルしないので注文IDにNoneを入れておく
            logger.debug('this is first deal. I will buy.')
            return 1

        latest_trade_result = trade_results_list[0]  # 最新の取引内容
        logger.debug(f'latest trade result: {latest_trade_result}')
        if latest_trade_result.get('child_order_state') == 'COMPLETED':  # 最新の取引内容が約定済みだったら
            self.cancel_order_id = None  # キャンセルしないので注文IDにNoneを入れておく
            # 最後の取引内容が購入か売却か確認する
            if latest_trade_result.get('side') == 'SELL':
                # 最後の取引内容が売るだったので、次は買う
                logger.debug('latest trade result is SELL. I will buy.')
                return 1
            elif latest_trade_result.get('side') == 'BUY':
                # 最後の取引内容が買うだったので、次は売る
                logger.debug('latest trade result is BUY. I will sell.')
                return -1
            else:
                # それ以外の場合は正しい結果が返って規定なので何もしない
                logger.warning(f'unknown trade result: {latest_trade_result}')
                return 0
        elif latest_trade_result.get('child_order_state') == 'ACTIVE':
            self.cancel_order_id = latest_trade_result.get('child_order_id')  # キャンセル用に注文IDを控える
            logger.debug(f'set cancel child_order_id: {self.cancel_order_id}')
            # 最後の取引内容が購入か売却か確認する
            if latest_trade_result.get('side') == 'SELL':
                # 最後の取引内容が売るだったので、次は買う
                logger.debug(f'latest trade result is SELL(yet completed: {self.cancel_order_id}). I will buy(cancel).')
                return 1
            elif latest_trade_result.get('side') == 'BUY':
                # 最後の取引内容が買うだったので、次は売る
                logger.debug(f'latest trade result is BUY(yet completed: {self.cancel_order_id}). I will sell(cancel).')
                return -1
            else:
                # それ以外の場合は正しい結果が返ってきていないので何もしない
                logger.warning(f'unknown trade result(yet completed: {self.cancel_order_id}): {latest_trade_result}')
                return 0
        else:
            # 取引結果の内容が何かしらおかしいので何もしない
            self.cancel_order_id = None  # キャンセルしないので注文IDにNoneを入れておく
            logger.warning(f'unknown trade result: {latest_trade_result}')
            return 0

    def check_differential(self):
        # 現在の市場の動向を確認する
        logger.debug(f'{type(self).__name__}.check_differential()')

        if self.strategy == 'sma':
            logger.debug('using strategy: simple moving average')
            return self.check_simple_moving_average()
        elif self.strategy == 'ema':
            logger.debug('using strategy: exponentially smoothed moving average')
            return self.check_exponentially_smoothed_moving_average()
        elif self.strategy == 'ticker':
            logger.debug('using strategy: ticker')
            return self.check_ticker()
        elif self.strategy == 'hamster':
            logger.debug('using strategy: hamster')
            return self.hamster()
        else:
            logger.warning(f'unknown strategy: {self.strategy}. using default strategy (moving average)')
            return self.check_moving_average()

    def buy(self):
        # 購入取引を実施する
        # 1: 取引成功
        # -1: 取引失敗
        # 0: 取引を行わなかった
        logger.debug(f'{type(self).__name__}.buy()')

        if self.cancel_order_id:
            # キャンセルが指定されている場合はキャンセルを行う
            logger.debug('I will cancel instead buy.')
            return self.cancel_order()

        key = self.key
        secret = self.secret
        url = self.url

        timestamp = str(int(time.time()*1000))
        method = 'POST'
        path = self.buy_endpoint

        (collateral_jpy, _) = self.get_collateral()
        latest_ticker_price = self.get_ticker()
        deal_size = self.get_jpy_deal_size(latest_ticker_price, collateral_jpy, self.minimum_trade_size)
        logger.debug(f'latest ticker price: {latest_ticker_price}')
        logger.debug(f'collateral jpy: {collateral_jpy}')
        logger.debug(f'minimum trade size: {self.minimum_trade_size}')
        logger.debug(f'set deal size: {deal_size}')

        body = json.dumps(
            {
                "product_code": "FX_BTC_JPY",
                "child_order_type": "MARKET",
                "side": "BUY",
                "size": deal_size,
            }
        )

        text = timestamp + method + path + body
        sign = hmac.new(secret.encode(), text.encode(), hashlib.sha256).hexdigest()

        headers = {
            'ACCESS-KEY': key,
            'ACCESS-TIMESTAMP': timestamp,
            'ACCESS-SIGN': sign,
            'Content-Type': 'application/json'
        }

        logger.debug(f'call api: {url+path}')
        logger.debug(f'headers: {headers}')
        logger.debug(f'body: {body}')
        req = request.Request(url+path, body.encode('utf-8'), headers, method=method)

        if not self.is_dryrun:
            # dryrunが指定されていなければ実際に売買を行う
            try:
                with request.urlopen(req) as response:
                    child_order_acceptance_id_raw = response.read()
                child_order_acceptance_id = json.loads(child_order_acceptance_id_raw)
                logger.debug(f'child_order_acceptance_id: {child_order_acceptance_id}')
                # 売買に成功
                logger.info(f'trade: buy success, price: {latest_ticker_price} (JPY/BTC), size: {deal_size}, actual: {deal_size*latest_ticker_price}.')
                return 1
            except Exception as e:
                # 売買に失敗した
                logger.warning(e)
                logger.info(f'trade: buy failed, price: {latest_ticker_price} (JPY/BTC), size: {deal_size}, actual: {deal_size*latest_ticker_price}.')
                return -1
        else:
            # dryrunが指定されているので何もしない
            logger.debug('dryrun mode is enable. did not buy.')
            logger.info(f'trade: buy dryrun, price: {latest_ticker_price} (JPY/BTC), size: {deal_size}, actual: {deal_size*latest_ticker_price}.')
            return 0

    def sell(self):
        # 売却取引を実施する
        # 1: 取引成功
        # -1: 取引失敗
        # 0: 取引を行わなかった
        logger.debug(f'{type(self).__name__}.sell()')

        if self.cancel_order_id:
            # キャンセルが指定されている場合はキャンセルを行う
            logger.debug('I will cancel instead buy.')
            return self.cancel_order()

        key = self.key
        secret = self.secret
        url = self.url

        timestamp = str(int(time.time()*1000))
        method = 'POST'
        path = self.sell_endpoint

        collateral_btc = self.get_positions()
        latest_ticker_price = self.get_ticker()
        logger.debug(f'latest ticker price: {latest_ticker_price}')
        logger.debug(f'collateral btc: {collateral_btc}')
        logger.debug(f'set deal size: {collateral_btc}')

        body = json.dumps(
            {
                "product_code": "FX_BTC_JPY",
                "child_order_type": "MARKET",
                "side": "SELL",
                "size": collateral_btc,
            }
        )

        text = timestamp + method + path + body
        sign = hmac.new(secret.encode(), text.encode(), hashlib.sha256).hexdigest()

        headers = {
            'ACCESS-KEY': key,
            'ACCESS-TIMESTAMP': timestamp,
            'ACCESS-SIGN': sign,
            'Content-Type': 'application/json'
        }

        logger.debug(f'call api: {url+path}')
        logger.debug(f'headers: {headers}')
        logger.debug(f'body: {body}')
        req = request.Request(url+path, body.encode('utf-8'), headers, method=method)

        if not self.is_dryrun:
            # dryrunが指定されていなければ実際に売買を行う
            try:
                with request.urlopen(req) as response:
                    child_order_acceptance_id_raw = response.read()
                child_order_acceptance_id = json.loads(child_order_acceptance_id_raw)
                logger.debug(f'child_order_acceptance_id: {child_order_acceptance_id}')
                # 売買に成功
                logger.info(f'trade: sell success, price: {latest_ticker_price} (JPY/BTC), size: {collateral_btc}, actual: {collateral_btc*latest_ticker_price}.')
                return 1
            except Exception as e:
                # 売買に失敗した
                logger.warning(e)
                logger.info(f'trade: sell failed, price: {latest_ticker_price} (JPY/BTC), size: {collateral_btc}, actual: {collateral_btc*latest_ticker_price}.')
                return -1
        else:
            # dryrunが指定されているので何もしない
            logger.debug('dryrun mode is enable. did not buy.')
            logger.info(f'trade: sell dryrun, price: {latest_ticker_price} (JPY/BTC), size: {collateral_btc}, actual: {collateral_btc*latest_ticker_price}.')
            return 0

    def cancel(self):
        # 指定された注文をキャンセルする
        logger.debug(f'{type(self).__name__}.cancel()')

        key = self.key
        secret = self.secret
        url = self.url

        timestamp = str(int(time.time()*1000))
        method = 'POST'
        path = self.cancel_endpoint

        body = json.dumps(
            {
                "product_code": "FX_BTC_JPY",
                "child_order_id": self.cancel_order_id
            }
        )

        text = timestamp + method + path + body
        sign = hmac.new(secret.encode(), text.encode(), hashlib.sha256).hexdigest()

        headers = {
            'ACCESS-KEY': key,
            'ACCESS-TIMESTAMP': timestamp,
            'ACCESS-SIGN': sign,
            'Content-Type': 'application/json'
        }

        logger.debug(f'call api: {url+path}')
        logger.debug(f'headers: {headers}')
        logger.debug(f'body: {body}')
        req = request.Request(url+path, body.encode('utf-8'), headers, method=method)

        if not self.is_dryrun:
            # dryrunが指定されていなければ実際に売買を行う
            try:
                with request.urlopen(req) as response:
                    response.read()
                logger.debug(f'execute cancel. id: {self.cancel_order_id}')
                # キャンセルに成功
                logger.info(f'trade: cancel success, id: {self.cancel_order_id}.')
                return 1
            except Exception as e:
                # キャンセルに失敗
                logger.warning(f'failed to execute cancel. id: {self.cancel_order_id}. error: {e}')
                logger.info(f'trade: cancel failed, id: {self.cancel_order_id}.')
                return -1
        else:
            # dryrunが指定されているので何もしない
            logger.debug('dryrun mode is enable. did not buy.')
            logger.info(f'trade: cancel dryrun, id: {self.cancel_order_id}.')
            return 0

    def get_ticker(self):
        # 取引額を取得する
        logger.debug(f'{type(self).__name__}.get_board()')

        url = self.url
        path = self.check_ticker_endpoint

        logger.debug(f'call api: {url+path}')
        try:
            req = request.Request(url+path)
            with request.urlopen(req) as response:
                the_page = response.read()
            ticker_raw = json.loads(the_page)
            ticker = ticker_raw['ltp']
        except Exception as e:
            logger.warning(e)
            return 0
        logger.debug(f'latest trade price: {ticker}')

        return ticker

    def get_collateral(self):
        # 現在の証拠金を取得する
        logger.debug(f'{type(self).__name__}.get_collateral()')

        key = self.key
        secret = self.secret
        url = self.url

        timestamp = str(int(time.time()*1000))
        method = 'GET'
        path = self.check_collateral_endpoint

        text = timestamp + method + path
        sign = hmac.new(secret.encode(), text.encode(), hashlib.sha256).hexdigest()

        headers = {
            'ACCESS-KEY': key,
            'ACCESS-TIMESTAMP': timestamp,
            'ACCESS-SIGN': sign,
        }

        logger.debug(f'call api: {url+path}')
        logger.debug(f'headers: {headers}')
        req = request.Request(url+path, b'', headers, method=method)

        try:
            with request.urlopen(req) as response:
                the_page = response.read()
            collateral = json.loads(the_page)
        except Exception as e:
            # 取得に失敗したので0（証拠金なし）を返す
            logger.warning(e)
            logger.warning(f'collaterals: {0} (JPY), {0} (BTC). (failed to get collaterals)')
            return (0, 0)
        logger.debug(f'collateral: {collateral}')

        collateral_jpy = 0
        collateral_btc = 0
        for x in collateral:
            if x.get('currency_code') == 'JPY':
                collateral_jpy = x.get('amount')
            elif x.get('currency_code') == 'BTC':
                collateral_btc = x.get('amount')

        # 日本円, BTCの組を返す
        logger.debug(f'collaterals: {collateral_jpy} (JPY), {collateral_btc} (BTC)')
        return (collateral_jpy, collateral_btc)

    def get_jpy_deal_size(self, ticker, collateral, minimum):
        # 日本円で取引するときのBTCの数量を返す
        logger.debug(f'{type(self).__name__}.get_jpy_deal_size()')
        logger.debug(f'collateral(JPY): {collateral}')
        logger.debug(f'ticker: {ticker}')
        logger.debug(f'minimum: {minimum}')

        # 最小取引額を下回る場合は最小取引額になるように修正する
        size = float(f'{max(collateral / ticker, minimum):.7}')
        logger.debug(f'size: {size}')

        return size

    def get_positions(self):
        # 現在の建玉しているBTC額を取得する
        logger.debug(f'{type(self).__name__}.get_positions()')

        key = self.key
        secret = self.secret
        url = self.url

        timestamp = str(int(time.time()*1000))
        method = 'GET'
        path = self.check_positions_endpoint

        text = timestamp + method + path
        sign = hmac.new(secret.encode(), text.encode(), hashlib.sha256).hexdigest()

        headers = {
            'ACCESS-KEY': key,
            'ACCESS-TIMESTAMP': timestamp,
            'ACCESS-SIGN': sign,
        }

        logger.debug(f'call api: {url+path}')
        logger.debug(f'headers: {headers}')
        req = request.Request(url+path, b'', headers, method=method)

        try:
            with request.urlopen(req) as response:
                the_page = response.read()
            positions = json.loads(the_page)
        except Exception as e:
            # 取得に失敗したので0（所有BTC0）を返す
            logger.warning(e)
            return 0
        logger.debug(f'positions: {positions}')

        # 建玉しているBTC額の計算
        btc = float(f"{sum([x.get('size') for x in positions if x.get('side') == 'BUY']):.7}")
        logger.debug(f'btc: {btc}')

        return btc

    def check_simple_moving_average(self):
        # 移動平均線の変化を確認する
        logger.debug(f'{type(self).__name__}.check_simple_moving_average()')

        logger.debug('get market information')
        logger.debug(f'call api: {self.chart_endpoint}')
        try:
            with request.urlopen(self.chart_endpoint) as response:
                html = response.read()
            data_raw = json.loads(html)
        except Exception as e:
            logger.warning(e)
            return 0
        logger.debug(f'get response: {html}')
        # データ形式
        # [
        #     CloseTime,
        #     OpenPrice,
        #     HighPrice,
        #     LowPrice,
        #     ClosePrice,
        #     Volume,
        #     QuoteVolume
        # ]

        data = data_raw.get('result').get(self.cryptwatch_data_type)  # 3分足を取得
        data_closeprice = [x[4] for x in data]  # 終値の取得
        logger.debug(f'get close price list: {data_closeprice}')

        span = self.span  # 50件(3*50=150分)の移動平均線
        sma = calc_sma(data_closeprice, span)  # 単純移動平均線の作成
        ema = calc_ema(data_closeprice, span)  # 指数平滑移動平均線の作成
        logger.debug(f'span: {span}')
        logger.debug(f'simple moving average: {sma}')
        logger.debug(f'elastic moving average: {ema}')

        # 傾きを計算する
        slope_span = 1
        sma_slope = calc_ma_slope(sma, slope_span)
        ema_slope = calc_ma_slope(ema, slope_span)
        logger.debug(f'sma slope: {sma_slope}')
        logger.debug(f'ema slope: {ema_slope}')

        # 前回の確認から今回の確認までの間に急激な変化があったかどうかを確認する。あれば売買を行うようにレスポンスする

        # 傾きの反転をチェック
        reverse = check_flip_slope(sma_slope)
        logger.debug(f'reverse: {reverse}')

        latest_reverse_list = [x for x in reverse if x != 0]  # 傾きが急激に発生したもののみに絞り込む。その中での最新の情報を取得する
        logger.debug(f'latest_reverse_list: {latest_reverse_list}')

        # 急激な傾きが一度も起きてなければ最新の傾きを返却する
        if len(latest_reverse_list) == 0:
            if len(reverse) > 0:
                return reverse[-1]
            else:
                # 傾きの情報がなければ傾きはなかったとして返す
                return 0

        # 最新の傾きの情報のみをレスポンスする
        latest_reverse = latest_reverse_list[-1]
        logger.debug(f'latest_reverse: {latest_reverse}')

        return latest_reverse

    def check_exponentially_smoothed_moving_average(self):
        # 移動平均線の変化を確認する
        logger.debug(f'{type(self).__name__}.check_exponentially_smoothed_moving_average()')

        logger.debug('get market information')
        logger.debug(f'call api: {self.chart_endpoint}')
        try:
            with request.urlopen(self.chart_endpoint) as response:
                html = response.read()
            data_raw = json.loads(html)
        except Exception as e:
            logger.warning(e)
            return 0
        logger.debug(f'get response: {html}')
        # データ形式
        # [
        #     CloseTime,
        #     OpenPrice,
        #     HighPrice,
        #     LowPrice,
        #     ClosePrice,
        #     Volume,
        #     QuoteVolume
        # ]

        data = data_raw.get('result').get(self.cryptwatch_data_type)  # 3分足を取得
        data_closeprice = [x[4] for x in data]  # 終値の取得
        logger.debug(f'get close price list: {data_closeprice}')

        span = self.span  # 50件(3*50=150分)の移動平均線
        sma = calc_sma(data_closeprice, span)  # 単純移動平均線の作成
        ema = calc_ema(data_closeprice, span)  # 指数平滑移動平均線の作成
        logger.debug(f'span: {span}')
        logger.debug(f'simple moving average: {sma}')
        logger.debug(f'elastic moving average: {ema}')

        # 傾きを計算する
        slope_span = 1
        sma_slope = calc_ma_slope(sma, slope_span)
        ema_slope = calc_ma_slope(ema, slope_span)
        logger.debug(f'sma slope: {sma_slope}')
        logger.debug(f'ema slope: {ema_slope}')

        # 前回の確認から今回の確認までの間に急激な変化があったかどうかを確認する。あれば売買を行うようにレスポンスする

        # 傾きの反転をチェック
        reverse = check_flip_slope(ema_slope)
        logger.debug(f'reverse: {reverse}')

        latest_reverse_list = [x for x in reverse if x != 0]  # 傾きが急激に発生したもののみに絞り込む。その中での最新の情報を取得する
        logger.debug(f'latest_reverse_list: {latest_reverse_list}')

        # 急激な傾きが一度も起きてなければ最新の傾きを返却する
        if len(latest_reverse_list) == 0:
            if len(reverse) > 0:
                return reverse[-1]
            else:
                # 傾きの情報がなければ傾きはなかったとして返す
                return 0

        # 最新の傾きの情報のみをレスポンスする
        latest_reverse = latest_reverse_list[-1]
        logger.debug(f'latest_reverse: {latest_reverse}')

        return latest_reverse

    def check_ticker(self):
        # 売りと買いの気配を調べる
        logger.debug(f'{type(self).__name__}.check_ticker()')

        url = self.url
        path = self.check_ticker_endpoint

        logger.debug(f'call api: {url+path}')
        try:
            req = request.Request(url+path)
            with request.urlopen(req) as response:
                the_page = response.read()
            ticker_raw = json.loads(the_page)
            ticker = ticker_raw
        except Exception as e:
            logger.warning(e)
            return 0
        logger.debug(f'ticker: {ticker}')

        # 気配の有意な方に合わせる
        try:
            bid = ticker.get('total_bid_depth')
            ask = ticker.get('total_ask_depth')
            logger.debug(f'total_bid_depth: {bid}')
            logger.debug(f'total_ask_depth: {ask}')
            logger.debug(f'difference: {bid-ask}')
            # 買い気配の方が売り気配よりも高ければ自動的に購入になる。逆なら売却になる
            return bid - ask
        except Exception as e:
            # 予期しないエラーが発生したので何もしない
            logger.warning(e)
            return 0

    def hamster(self):
        # ランダムに売買を決定する(-1, 0, 1を返す)
        logger.debug(f'{type(self).__name__}.hamster()')
        t = random.randint(-1,1)
        logger.debug(f'hamster: {t}')
        return t

