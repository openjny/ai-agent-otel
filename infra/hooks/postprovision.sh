#!/bin/bash
set -euo pipefail

# Write App Insights connection string to .env for docker compose
conn_str=$(azd env get-value APPLICATIONINSIGHTS_CONNECTION_STRING)
echo "APPLICATIONINSIGHTS_CONNECTION_STRING=${conn_str}" > .env
echo "Wrote connection string to .env"
