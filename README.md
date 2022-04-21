FX Trade
=====

FX Trade

BitFlyer API を利用して自動トレードを行う


基本戦略
-----

資産の20% or 最低購入額の 0.01BTC を使う
短期移動平均線の傾きの変化が一定以上の時に売買を行う


実行方法
-----

- プログラムの実行
```sh
python3 fxtrade/autotrader.py ./config.json -v --mock --wait 180 --threshold 0.1 --dryrun 2>&1 | tee -a ./$(date '+%y%m%d%H%M%S%Z').log
```

- テストの実行
```sh
python3 -m unittest discover tests
```

API
-----
[trade](https://lightning.bitflyer.com/trade)

[API](https://lightning.bitflyer.com/docs?lang=ja&_gl=1*1xpgy5d*_ga*MTAwNzY1MDEzNS4xNjI3NDUxODQ5*_ga_3VYMQNCVSM*MTY0Njc5NjcxNi4xMS4xLjE2NDY3OTY5MTguNjA.)
細かい必要な権限は docs/sample.json を参照

チャートの取得はcryptwatchのapiを使用する
[cryptwatch](https://docs.cryptowat.ch/rest-api/markets/ohlc)

