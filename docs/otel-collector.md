# OTel Collector

[otel-collector/config.yaml](../otel-collector/config.yaml) で 2 系統のパイプラインを構成しています。

## パイプライン構成

| パイプライン | データ | 宛先 | processor |
|---|---|---|---|
| `traces/file`, `metrics/file`, `logs/file` | フルデータ (コンテンツ込み) | `data/*.jsonl` | なし |
| `traces/cloud`, `metrics/cloud`, `logs/cloud` | メタデータのみ | App Insights | `transform/strip-content` |

## コンテンツ分離

`transform/strip-content` processor は以下の属性をクラウド送信前に削除します:

| 属性 | 内容 |
|---|---|
| `gen_ai.input.messages` | プロンプト全文 |
| `gen_ai.output.messages` | レスポンス全文 |
| `gen_ai.tool.definitions` | ツール定義 |
| `tool_input` / `tool_output` | ツールの入出力 |
| `prompt` | ユーザープロンプト |
| `tool_parameters` | ツールパラメータ |

コンテンツ込みフルデータはローカルの `data/*.jsonl` にのみ保存されます。

## バックエンド追加

exporter + pipeline を追加するだけで他のバックエンドに送信可能:

```yaml
# 例: Grafana Cloud を追加
exporters:
  otlphttp/grafana:
    endpoint: "https://otlp-gateway-prod-ap-southeast-1.grafana.net/otlp"
    headers:
      Authorization: "Basic <token>"

service:
  pipelines:
    traces/grafana:
      receivers: [otlp]
      processors: [transform/strip-content, batch]
      exporters: [otlphttp/grafana]
```

## ファイルローテーション

`file` exporter はローテーション設定済み:

- traces: 100MB × 30 世代
- metrics: 50MB × 10 世代
- logs: 100MB × 30 世代

想定ストレージ: ~200MB/月
