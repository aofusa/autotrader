# AGENTS.md

AIエージェント（および開発者）向けのプロジェクトガイド。

## プロジェクト概要

bitFlyer Lightning API を使用して暗号資産（BTC / ETH）の自動取引を行う Python プログラム。
ユーザは入金してアプリケーションを起動するだけで、あとは全自動で取引が行われ、長期的に資産が増えることを目標とする。

- 言語: Python 3.12+（標準ライブラリのみ。外部パッケージへの依存は追加しない）
- 取引所: bitFlyer Lightning
  - BTC: `FX_BTC_JPY`（証拠金取引・レバレッジ可。bitFlyer の FX 対応銘柄は BTC のみ）
  - ETH: `ETH_JPY`（現物取引のみ。レバレッジ不可）
- チャートデータ: bitFlyer 公開APIから取得（旧実装が使っていた cryptowat.ch は2023年にサービス終了済み）

## 実行方法

```sh
# モック（ペーパートレード）実行。実際の取引は行わず、実相場での仮想損益を記録する
python3 fxtrade/autotrader.py ~/unleash/credentials/autotrader/production.json -v --mock --wait 180 --threshold 0.1 --dryrun 2>&1 | tee -a ./docs/logs/$(date '+%y%m%d%H%M%S%Z').log

# 本番実行（実際に取引を行う）
python3 fxtrade/autotrader.py ~/unleash/credentials/autotrader/production.json -v --bitflyer --wait 180

# テスト実行
python3 -m unittest discover tests

# バックテスト実行（過去データで資産推移を検証）
python3 fxtrade/backtest_runner.py --help
```

## ディレクトリ構成

- `fxtrade/autotrader.py` — エントリポイント（イベントループ）
- `fxtrade/lib/` — ライブラリ本体
  - `trader.py` — 取引の意思決定（戦略・リスク管理を統合）
  - `strategy.py` — 売買シグナル生成（トレンドフォロー + 動的な決済判断）
  - `risk.py` — リスク管理（ポジションサイズ、レバレッジ上限、証拠金保護）
  - `candles.py` — ローソク足データの取得・構築
  - `backtest.py` — バックテストエンジン
  - `market/bitflyer.py` — bitFlyer API アダプタ（本番取引）
  - `market/mock.py` — モック市場（ペーパートレード / テスト用）
- `tests/` — ユニットテスト（unittest）
- `docs/sample.json` — 設定ファイルのサンプル
- `docs/artifacts/` — AI生成の一時ファイル置き場（**gitignore済み**。一時的な生成物は必ずここに置く）
- `docs/logs/` — 実行ログ置き場（gitignore済み）

## 設定ファイル

実体は `~/unleash/credentials/autotrader/production.json`（APIキーを含むためリポジトリ外）。
形式は `docs/sample.json` を参照。主な設定:

- `trading.products`: `"btc"` / `"eth"` / `"both"` — 取引対象の銘柄
- `trading.max-leverage`: レバレッジ上限（デフォルト 2.0、**絶対上限 3.0**。bitFlyer の規制上の上限は 2 倍である点に注意）
- `trading.risk-per-trade` などのリスクパラメータ

## 重要な制約・方針

1. **証拠金を枯渇させない**: 証拠金が 0 や不足になると処理が停止するため、リスク管理で必ず余力を残す。ポジションサイズはボラティリティと証拠金残高から動的に算出する。
2. **レバレッジ上限は 3 倍**（設定ファイルで変更可能だが 3 を超えない）。
3. **決済タイミングは固定にしない**: ATR等の指標から相場状況を見て自動で損切り・利確・トレーリングの水準を決める。
4. **一時的なマイナスは許容**するが、長期的に資産が増えることを目標とする。
5. 変更時は**必ずテストを実装・実行**し、バックテストで過去データに対して資産が増えることを確認する。
6. APIキー・シークレットを**ログに出力しない**（設定のログ出力時はマスクする）。
7. 一時的なAI生成物は `docs/artifacts/` に保存する（git管理外）。
8. 作業は適宜コミットしながら進める。

## API リファレンス

- bitFlyer Lightning API: https://lightning.bitflyer.com/docs
  - 公開API: `/v1/getticker`, `/v1/getexecutions`, `/v1/getboard`, `/v1/markets`
  - プライベートAPI（HMAC-SHA256署名）: `/v1/me/getcollateral`, `/v1/me/getpositions`, `/v1/me/sendchildorder`, `/v1/me/getchildorders`, `/v1/me/cancelchildorder`, `/v1/me/getbalance`
- APIレート制限: プライベートAPIは5分で500回、注文系は1分で100回程度。ポーリング間隔（`--wait`）で調整する。

## 過去データ（バックテスト用）

- Binance 公開API（`https://api.binance.com/api/v3/klines`）等から BTC/ETH の日足・時間足を取得し `docs/artifacts/data/` にキャッシュする。
- テスト用の小さなfixtureは `tests/fixtures/` に格納する（決定的なテストのため）。
