#!/usr/bin/env bash
set -euo pipefail

# Inject OTel environment variables for AI agent telemetry collection.
# Covers both terminal shells and desktop-launched VS Code.

OTEL_ENDPOINT="${OTEL_EXPORTER_OTLP_ENDPOINT:-http://localhost:4318}"

ENV_VARS=(
  "COPILOT_OTEL_ENABLED=true"
  "OTEL_EXPORTER_OTLP_ENDPOINT=${OTEL_ENDPOINT}"
  "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true"
  "CLAUDE_CODE_ENABLE_TELEMETRY=1"
  "CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1"
  "OTEL_METRICS_EXPORTER=otlp"
  "OTEL_LOGS_EXPORTER=otlp"
  "OTEL_TRACES_EXPORTER=otlp"
  "OTEL_EXPORTER_OTLP_PROTOCOL=http/json"
  "OTEL_LOG_USER_PROMPTS=1"
  "OTEL_LOG_TOOL_CONTENT=1"
  "OTEL_LOG_TOOL_DETAILS=1"
)

MARKER_BEGIN="# >>> ai-agent-otel >>>"
MARKER_END="# <<< ai-agent-otel <<<"

generate_shell_block() {
  echo "$MARKER_BEGIN"
  for var in "${ENV_VARS[@]}"; do
    echo "export ${var}"
  done
  echo "$MARKER_END"
}

generate_envd_block() {
  for var in "${ENV_VARS[@]}"; do
    echo "${var}"
  done
}

inject_shell_profile() {
  local profile="$1"

  if [[ ! -f "$profile" ]]; then
    touch "$profile"
  fi

  # Remove existing block if present
  if grep -qF "$MARKER_BEGIN" "$profile" 2>/dev/null; then
    sed -i "/${MARKER_BEGIN//\//\\/}/,/${MARKER_END//\//\\/}/d" "$profile"
    echo "  Updated existing block in $profile"
  else
    echo "  Added new block to $profile"
  fi

  echo "" >> "$profile"
  generate_shell_block >> "$profile"
}

inject_environment_d() {
  local dir="$HOME/.config/environment.d"
  local file="${dir}/ai-agent-otel.conf"
  mkdir -p "$dir"
  generate_envd_block > "$file"
  echo "  Wrote $file"
}

remove_shell_profile() {
  local profile="$1"
  if [[ -f "$profile" ]] && grep -qF "$MARKER_BEGIN" "$profile" 2>/dev/null; then
    sed -i "/${MARKER_BEGIN//\//\\/}/,/${MARKER_END//\//\\/}/d" "$profile"
    # Remove trailing blank lines
    sed -i -e :a -e '/^\n*$/{$d;N;ba' -e '}' "$profile"
    echo "  Removed block from $profile"
  fi
}

remove_environment_d() {
  local file="$HOME/.config/environment.d/ai-agent-otel.conf"
  if [[ -f "$file" ]]; then
    rm "$file"
    echo "  Removed $file"
  fi
}

detect_shell_profile() {
  local shell_name
  shell_name=$(basename "${SHELL:-/bin/bash}")
  case "$shell_name" in
    zsh)  echo "$HOME/.zshrc" ;;
    bash) echo "$HOME/.bashrc" ;;
    fish) echo "$HOME/.config/fish/config.fish" ;;
    *)    echo "$HOME/.profile" ;;
  esac
}

cmd_install() {
  local profile
  profile=$(detect_shell_profile)

  echo "Installing OTel environment variables..."
  echo ""
  echo "[Shell profile]"
  inject_shell_profile "$profile"
  echo ""
  echo "[Desktop session (systemd environment.d)]"
  inject_environment_d
  echo ""
  echo "Done. To apply:"
  echo "  - Terminal: source $profile"
  echo "  - Desktop apps (VS Code): log out and back in, or run: systemctl --user import-environment"
}

cmd_uninstall() {
  local profile
  profile=$(detect_shell_profile)

  echo "Removing OTel environment variables..."
  echo ""
  echo "[Shell profile]"
  remove_shell_profile "$profile"
  echo ""
  echo "[Desktop session]"
  remove_environment_d
  echo ""
  echo "Done. Restart your terminal and re-login to fully remove."
}

cmd_status() {
  echo "=== Current OTel Environment ==="
  echo ""
  for var in "${ENV_VARS[@]}"; do
    local key="${var%%=*}"
    local current="${!key:-<not set>}"
    local expected="${var#*=}"
    if [[ "$current" == "$expected" ]]; then
      echo "  ✓ $key=$current"
    else
      echo "  ✗ $key=$current (expected: $expected)"
    fi
  done
}

case "${1:-install}" in
  install)   cmd_install ;;
  uninstall) cmd_uninstall ;;
  status)    cmd_status ;;
  *)
    echo "Usage: $0 {install|uninstall|status}"
    exit 1
    ;;
esac
