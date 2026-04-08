## File Structure

```
.
├── azure.yaml                    # azd プロジェクト定義 (postprovision hook)
├── docker-compose.yml            # OTel Collector (常時) + Jaeger (on-demand)
├── .env                          # App Insights connection string (自動生成)
├── .env.example
├── infra/
│   ├── main.bicep                # サブスクリプションスコープ
│   ├── main.parameters.json
│   ├── monitoring.bicep          # App Insights + Log Analytics
│   └── hooks/
│       └── postprovision.sh      # .env 自動書き込み
├── otel-collector/
│   └── config.yaml               # 2 系統パイプライン (file + azuremonitor)
├── data/                          # テレメトリファイル (gitignored)
│   ├── traces.jsonl
│   ├── metrics.jsonl
│   └── logs.jsonl
├── scripts/
│   ├── analyze.py                # DuckDB 分析 CLI (summary/tools/cost/security/direction)
│   ├── score.py                  # LLM-as-a-Judge (Copilot SDK, 4 軸スコアリング)
│   ├── push_to_jaeger.py         # ファイル → Jaeger トレース再生
│   └── setup-env.sh              # 環境変数注入 (install/uninstall/status)
├── docs/
│   ├── otel-collector.md         # OTel Collector パイプライン設定の詳細
│   ├── cost.md                   # コスト計算の仕組みと注意事項
│   └── infrastructure.md         # Azure インフラ (Bicep)
└── blog/                          # (参考) 関連ブログ記事の原稿
```
