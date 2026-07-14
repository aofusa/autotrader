Auto Trader
=====

bitFlyer Lightning API を利用して暗号資産（BTC / ETH）の自動トレードを行う。

- BTC: `FX_BTC_JPY`（証拠金取引。レバレッジ上限は設定可能、絶対上限3倍）
- ETH: `ETH_JPY`（現物取引。bitFlyerのレバレッジ取引はBTCのみ対応のため）
- 戦略: トレンドフォロー（EMAクロス + ドンチャンブレイクアウト）
- 決済: 固定値ではなく、ATR（ボラティリティ）から自動算出されるトレーリングストップとトレンド反転で決定
- リスク管理: ボラティリティに応じたポジションサイズ、証拠金保護、ドローダウン時の自動縮小

実行方法
-----

config.json は docs/sample.json の内容を参照

- モック（ペーパートレード）実行。実際の取引は行わず、実相場で「取引していたらどうなっていたか」を記録する
```sh
python3 fxtrade/autotrader.py ./config.json -v --mock --wait 180 2>&1 | tee -a ./docs/logs/$(date '+%y%m%d%H%M%S%Z').log
```

- 本番実行（実際に取引を行う）
```sh
python3 fxtrade/autotrader.py ./config.json --bitflyer --wait 180 2>&1 | tee -a ./docs/logs/$(date '+%y%m%d%H%M%S%Z').log
```

- テストの実行
```sh
python3 -m unittest discover tests
```

- バックテストの実行（過去データで資産推移を検証）
```sh
python3 fxtrade/backtest_runner.py --product btc --interval 1d --initial 500000
python3 fxtrade/backtest_runner.py --product eth --interval 1d --initial 500000
```

設定
-----

`trading` セクションの主な設定（詳細は docs/sample.json）:

| 設定 | 説明 |
|---|---|
| `products` | 取引対象。`btc` / `eth` / `both` |
| `risk.max-leverage` | レバレッジ上限（デフォルト2.0、絶対上限3.0。現物は常に1倍） |
| `risk.risk-per-trade` | 1回の取引で許容する損失（資産比。デフォルト2%） |
| `strategy.trail-atr-mult` | トレーリングストップの幅（ATRの倍数） |
| `bitflyer.candle-interval` | シグナル計算に使う足の間隔（例: `4h`） |
| `bitflyer.spot-reserves` | 運用対象外にする現物残高（例: `{"ETH": 0.6875}`。この数量には一切手を触れない） |

API
-----
[trade](https://lightning.bitflyer.com/trade)

[bitFlyer Lightning API](https://lightning.bitflyer.com/docs)

チャートデータ（ローソク足）は Binance の公開APIから取得し、bitFlyer の現在価格でスケーリングして使用する
（bitFlyer にはOHLCの公開APIがなく、旧実装で使用していた cryptowat.ch は2023年にサービスを終了したため）。
