#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Write App Insights connection string to .env for docker compose
$connStr = azd env get-value APPLICATIONINSIGHTS_CONNECTION_STRING
if ($LASTEXITCODE -ne 0) { throw "Failed to get connection string from azd env" }

Set-Content -Path (Join-Path $PSScriptRoot '..\..\.env') -Value "APPLICATIONINSIGHTS_CONNECTION_STRING=$connStr" -NoNewline
Write-Host "Wrote connection string to .env"
