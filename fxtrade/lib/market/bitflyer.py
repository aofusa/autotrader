import json
import time
import hmac
import hashlib
from urllib import request


from .. import get_module_logger
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

        self.url = self.config.get('endpoint').get('url')
        self.check_collateral_endpoint = self.config.get('endpoint').get('check-collateral')  # GET
        self.check_board_endpoint = self.config.get('endpoint').get('check-board')  # GET
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

        logger.info(f'call api: {url+path}')
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
            logger.info('this is first deal. I will buy.')
            return 1

        latest_trade_result = trade_results_list[0]  # 最新の取引内容
        logger.debug(f'latest trade result: {latest_trade_result}')
        if latest_trade_result.get('child_order_state') == 'COMPLETED':  # 最新の取引内容が約定済みだったら
            self.cancel_order_id = None  # キャンセルしないので注文IDにNoneを入れておく
            # 最後の取引内容が購入か売却か確認する
            if latest_trade_result.get('side') == 'SELL':
                # 最後の取引内容が売るだったので、次は買う
                logger.info('latest trade result is SELL. I will buy.')
                return 1
            elif latest_trade_result.get('side') == 'BUY':
                # 最後の取引内容が買うだったので、次は売る
                logger.info('latest trade result is BUY. I will sell.')
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
                logger.info(f'latest trade result is SELL(yet completed: {self.cancel_order_id}). I will buy(cancel).')
                return 1
            elif latest_trade_result.get('side') == 'BUY':
                # 最後の取引内容が買うだったので、次は売る
                logger.info(f'latest trade result is BUY(yet completed: {self.cancel_order_id}). I will sell(cancel).')
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

        logger.info('get market information')
        logger.info(f'call api: {self.chart_endpoint}')
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
        sma = []  # 単純移動平均線の作成
        ema = []  # 指数平滑移動平均線の作成
        for index in range(len(data_closeprice)-span):
            s = sum(data_closeprice[index:index+span])
            m = s / span
            sma.append(m)

            es = s + data_closeprice[index+span]
            em = es / (span+1)
            ema.append(em)
        logger.debug(f'span: {span}')
        logger.debug(f'simple moving average: {sma}')
        logger.debug(f'elastic moving average: {ema}')

        # 傾きを計算する
        sma_slope = []
        ema_slope = []
        slope_span = 1
        for index in range(len(sma)):
            s_slope = (sma[index] - sma[index-slope_span]) / (index - (index - span))
            sma_slope.append(s_slope)

            es_slope = (ema[index] - ema[index-slope_span]) / (index - (index - span))
            ema_slope.append(es_slope)
        logger.debug(f'sma slope: {sma_slope}')
        logger.debug(f'ema slope: {ema_slope}')

        # 前回の確認から今回の確認までの間に急激な変化があったかどうかを確認する。あれば売買を行うようにレスポンスする

        # 傾きの反転をチェック
        reverse = []
        for index in range(len(sma_slope)-1):
            if sma_slope[index+1] > 0 and sma_slope[index] < 0:
                # +に反転している
                reverse.append(1)
            elif sma_slope[index+1] < 0 and sma_slope[index] > 0:
                # -に反転している
                reverse.append(-1)
            else:
                # 反転は起きていない
                reverse.append(0)
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

    def buy(self):
        # 購入取引を実施する
        # 1: 取引成功
        # -1: 取引失敗
        # 0: 取引を行わなかった
        logger.debug(f'{type(self).__name__}.buy()')

        if self.cancel_order_id:
            # キャンセルが指定されている場合はキャンセルを行う
            logger.info('I will cancel instead buy.')
            return self.cancel_order()

        key = self.key
        secret = self.secret
        url = self.url

        timestamp = str(int(time.time()*1000))
        method = 'POST'
        path = self.buy_endpoint

        mid_board = self.get_mid_board()
        (collateral_jpy, _) = self.get_collateral()
        deal_size = self.get_jpy_deal_size(mid_board, collateral_jpy, self.minimum_trade_size)
        logger.debug(f'mid board: {mid_board}')
        logger.debug(f'collateral jpy: {collateral_jpy}')
        logger.debug(f'minimum trade size: {self.minimum_trade_size}')
        logger.info(f'set deal size: {deal_size}')

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

        logger.info(f'call api: {url+path}')
        logger.debug(f'headers: {headers}')
        logger.debug(f'body: {body}')
        req = request.Request(url+path, body.encode('utf-8'), headers, method=method)

        if not self.is_dryrun:
            # dryrunが指定されていなければ実際に売買を行う
            try:
                with request.urlopen(req) as response:
                    child_order_acceptance_id_raw = response.read()
                child_order_acceptance_id = json.loads(child_order_acceptance_id_raw)
                logger.info(f'child_order_acceptance_id: {child_order_acceptance_id}')
                # 売買に成功
                return 1
            except Exception as e:
                # 売買に失敗した
                logger.warning(e)
                return -1
        else:
            # dryrunが指定されているので何もしない
            logger.info('dryrun mode is enable. did not buy.')
            return 0

    def sell(self):
        # 売却取引を実施する
        # 1: 取引成功
        # -1: 取引失敗
        # 0: 取引を行わなかった
        logger.debug(f'{type(self).__name__}.sell()')

        if self.cancel_order_id:
            # キャンセルが指定されている場合はキャンセルを行う
            logger.info('I will cancel instead buy.')
            return self.cancel_order()

        key = self.key
        secret = self.secret
        url = self.url

        timestamp = str(int(time.time()*1000))
        method = 'POST'
        path = self.sell_endpoint

        (_, collateral_btc) = self.get_collateral()
        logger.debug(f'collateral btc: {collateral_btc}')
        logger.info(f'set deal size: {collateral_btc}')

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

        logger.info(f'call api: {url+path}')
        logger.debug(f'headers: {headers}')
        logger.debug(f'body: {body}')
        req = request.Request(url+path, body.encode('utf-8'), headers, method=method)

        if not self.is_dryrun:
            # dryrunが指定されていなければ実際に売買を行う
            try:
                with request.urlopen(req) as response:
                    child_order_acceptance_id_raw = response.read()
                child_order_acceptance_id = json.loads(child_order_acceptance_id_raw)
                logger.info(f'child_order_acceptance_id: {child_order_acceptance_id}')
                # 売買に成功
                return 1
            except Exception as e:
                # 売買に失敗した
                logger.warning(e)
                return -1
        else:
            # dryrunが指定されているので何もしない
            logger.info('dryrun mode is enable. did not buy.')
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

        logger.info(f'call api: {url+path}')
        logger.debug(f'headers: {headers}')
        logger.debug(f'body: {body}')
        req = request.Request(url+path, body.encode('utf-8'), headers, method=method)

        if not self.is_dryrun:
            # dryrunが指定されていなければ実際に売買を行う
            try:
                with request.urlopen(req) as response:
                    response.read()
                logger.info(f'execute cancel. id: {self.cancel_order_id}')
                # キャンセルに成功
                return 1
            except Exception as e:
                # キャンセルに失敗
                logger.warning(f'failed to execute cancel. id: {self.cancel_order_id}. error: {e}')
                return -1
        else:
            # dryrunが指定されているので何もしない
            logger.info('dryrun mode is enable. did not buy.')
            return 0

    def get_mid_board(self):
        # 取引額を取得する
        logger.debug(f'{type(self).__name__}.get_board()')

        url = self.url
        path = self.check_board_endpoint
        query = '?product_code=FX_BTC_JPY'

        logger.debug(f'call api: {url+path+query}')
        try:
            req = request.Request(url+path+query)
            with request.urlopen(req) as response:
                the_page = response.read()
            board_raw = json.loads(the_page)
            board = board_raw['mid_price']
        except Exception as e:
            logger.warning(e)
            return 0
        logger.debug(f'mid board data: {board}')

        return board

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

        logger.info(f'call api: {url+path}')
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
        logger.info(f'collaterals: {collateral_jpy} (JPY), {collateral_btc} (BTC)')
        return (collateral_jpy, collateral_btc)

    def get_jpy_deal_size(self, board, collateral, minimum):
        # 日本円で取引するときのBTCの数量を返す
        logger.debug(f'{type(self).__name__}.get_jpy_deal_size()')
        logger.debug(f'collateral(JPY): {collateral}')
        logger.debug(f'board: {board}')
        logger.debug(f'minimum: {minimum}')

        # 最小取引額を下回る場合は最小取引額になるように修正する
        size = max(collateral / board, minimum)
        logger.debug(f'size: {size}')

        return size

