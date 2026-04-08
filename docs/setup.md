# Setup

## Prerequisites

- Docker
- [Azure Developer CLI (azd)](https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd)
- Azure サブスクリプション (App Insights 無料枠: 5GB/月)
- GitHub Copilot サブスクリプション
- Claude Code (optional)
- [uv](https://docs.astral.sh/uv/) (Python スクリプト実行用)

## Azure リソースをデプロイ (共通)

App Insights + Log Analytics をデプロイ。postprovision hook が `.env` に connection string を自動書き込み:

```bash
azd init    # 環境名とリージョンを設定
azd up      # デプロイ → .env 自動生成
```

### 既存環境を別マシンで使う場合

`azd up` の代わりに `azd env refresh` + postprovision hook を手動実行する:

```bash
azd init                # 同じ環境名を指定
azd env refresh         # Azure から既存デプロイの output を取得（再デプロイ不要）
                        # .env に Connection String を追加
# Windows 
pwsh infra/hooks/postprovision.ps1

# Linux
bash infra/hooks/postprovision.sh
```

## Windows

### 1. OTel Collector を起動

```powershell
New-Item -ItemType Directory -Path data -Force
docker compose up -d
```

### 2. エージェントを設定

OTel 環境変数を PowerShell プロファイル + Windows User 環境変数にセット:

```powershell
.\scripts\setup-env.ps1 install
. $PROFILE   # 現在のターミナルに反映
```

VS Code はユーザー環境変数の変更を再起動するまで反映しないため、VS Code を再起動する。

設定状況の確認 / 削除:

```powershell
.\scripts\setup-env.ps1 status
.\scripts\setup-env.ps1 uninstall
```

### 3. 動作確認

```powershell
Get-ChildItem data/                    # jsonl ファイルが生成されているか
uv run scripts/analyze.py summary      # DuckDB でクエリできるか
```

## Linux

systemd がある環境を前提とする。macOS は TBD。

### 1. OTel Collector を起動

```bash
mkdir -p data
docker compose up -d
```

### 2. エージェントを設定

OTel 環境変数をシェルプロファイル + systemd `environment.d` にセット:

```bash
./scripts/setup-env.sh install
source "$SHELL_PROFILE"   # スクリプトが出力したプロファイルパスを source
```

> `setup-env.sh` は `$SHELL` からプロファイルを自動検出し、実行結果にパスを表示します。

デスクトップランチャーから VS Code を起動する場合は、ログアウト→再ログインで `environment.d` を反映。または:

```bash
systemctl --user import-environment $(cut -d= -f1 ~/.config/environment.d/ai-agent-otel.conf | tr '\n' ' ')
# → VS Code の再起動が必要
```

設定状況の確認 / 削除:

```bash
./scripts/setup-env.sh status
./scripts/setup-env.sh uninstall
```

### 3. 動作確認

```bash
ls -la data/                           # jsonl ファイルが生成されているか
uv run scripts/analyze.py summary      # DuckDB でクエリできるか
```

## 補足: Claude Code の settings.json

Claude Code は `~/.claude/settings.json` の `env` ブロックでも設定できます。
シェル環境変数と重複しますが、`settings.json` 側が優先されます。
