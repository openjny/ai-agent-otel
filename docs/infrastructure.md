# Azure インフラ

## Bicep (azd)

`infra/` に Bicep テンプレート:

| ファイル | 内容 |
|---|---|
| `main.bicep` | サブスクリプションスコープ。RG 作成 + monitoring モジュール呼び出し |
| `main.parameters.json` | azd 環境変数からパラメータ注入 |
| `monitoring.bicep` | Application Insights + Log Analytics Workspace |
| `hooks/postprovision.sh` | `azd up` 後に connection string を `.env` に書き込み |

### デプロイ

```bash
azd init    # 環境名・リージョン設定
azd up      # デプロイ + .env 自動生成
```

### 作成されるリソース

| リソース | 種類 | 備考 |
|---|---|---|
| `rg-<環境名>` | Resource Group | |
| `log-<token>` | Log Analytics Workspace | PerGB2018 SKU, 90 日保持 |
| `appi-<token>` | Application Insights | workspace-based |
