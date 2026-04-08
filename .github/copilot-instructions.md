# Project Guidelines

## Overview

AI コーディングエージェント (Copilot Chat, Copilot CLI, Claude Code) の OTel テレメトリをローカル + Azure に集約・分析する環境。

## Build & Run

```bash
azd up                                    # Azure リソースデプロイ + .env 自動生成
docker compose up -d                      # OTel Collector 起動
./scripts/setup-env.sh install            # エージェント用 OTel 環境変数を注入
uv run scripts/analyze.py <command>       # DuckDB 分析 (summary|tools|cost|security|direction)
uv run scripts/score.py [--trace-id ID]   # LLM-as-a-Judge スコアリング
```

既存環境を別マシンで使う: `azd env refresh && bash infra/hooks/postprovision.sh`

## Conventions

### Python スクリプト

- PEP 723 inline script metadata を使用。`uv run` で依存解決される
- `DATA_DIR = Path(__file__).parent.parent / "data"` でデータディレクトリを参照
- DuckDB で `read_json()` → `unnest()` で OTel JSON Lines をクエリ
- 結果は `.fetchdf()` で pandas DataFrame に変換して表示

### OTel データ

- `data/traces.jsonl` が正本。OTLP JSON 形式 (`resourceSpans[].scopeSpans[].spans[]`)
- 主要属性: `gen_ai.request.model`, `gen_ai.usage.input_tokens`, `gen_ai.tool.name`, `gen_ai.operation.name`
- `service.name` でエージェント識別: `copilot-chat`, `github-copilot`, `claude-code`

### モデル単価

`scripts/analyze.py` の `MODEL_PRICING` dict に `(input_per_1M, output_per_1M)` USD で定義。新モデル追加時は更新が必要。

### pre-commit (prek)

gitleaks (シークレットスキャン), ruff (lint + format), shellcheck, check-yaml/json。`prek run --all-files` で全チェック。

## Docs

詳細は `docs/` を参照。README に重複させない。

- [docs/otel-collector.md](docs/otel-collector.md) — パイプライン設定、コンテンツ分離、バックエンド追加方法
- [docs/cost.md](docs/cost.md) — コスト計算の仕組み、MODEL_PRICING の管理、注意事項
- [docs/infrastructure.md](docs/infrastructure.md) — Bicep テンプレート、作成されるリソース
