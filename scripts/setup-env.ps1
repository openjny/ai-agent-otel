#Requires -Version 5.1
<#
.SYNOPSIS
    Inject/remove OTel environment variables for AI agent telemetry collection (Windows).
.DESCRIPTION
    PowerShell equivalent of setup-env.sh. Manages environment variables in:
    - PowerShell profile ($PROFILE)
    - Windows User environment variables (for desktop apps like VS Code)
.PARAMETER Command
    install | uninstall | status
.EXAMPLE
    .\setup-env.ps1 install
    .\setup-env.ps1 status
    .\setup-env.ps1 uninstall
#>
param(
    [ValidateSet('install', 'uninstall', 'status')]
    [string]$Command = 'install'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$OtelEndpoint = if ($env:OTEL_EXPORTER_OTLP_ENDPOINT) { $env:OTEL_EXPORTER_OTLP_ENDPOINT } else { 'http://localhost:4318' }

$EnvVars = [ordered]@{
    COPILOT_OTEL_ENABLED                                = 'true'
    OTEL_EXPORTER_OTLP_ENDPOINT                         = $OtelEndpoint
    OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT   = 'true'
    CLAUDE_CODE_ENABLE_TELEMETRY                         = '1'
    CLAUDE_CODE_ENHANCED_TELEMETRY_BETA                  = '1'
    OTEL_METRICS_EXPORTER                                = 'otlp'
    OTEL_LOGS_EXPORTER                                   = 'otlp'
    OTEL_TRACES_EXPORTER                                 = 'otlp'
    OTEL_EXPORTER_OTLP_PROTOCOL                          = 'http/json'
    OTEL_LOG_USER_PROMPTS                                = '1'
    OTEL_LOG_TOOL_CONTENT                                = '1'
    OTEL_LOG_TOOL_DETAILS                                = '1'
}

$MarkerBegin = '# >>> ai-agent-otel >>>'
$MarkerEnd   = '# <<< ai-agent-otel <<<'

function New-ProfileBlock {
    $lines = @($MarkerBegin)
    foreach ($kv in $EnvVars.GetEnumerator()) {
        $lines += "`$env:$($kv.Key) = '$($kv.Value)'"
    }
    $lines += $MarkerEnd
    return $lines -join "`n"
}

function Install-ProfileBlock {
    $profilePath = $PROFILE.CurrentUserCurrentHost
    $profileDir = Split-Path $profilePath -Parent
    if (-not (Test-Path $profileDir)) {
        New-Item -ItemType Directory -Path $profileDir -Force | Out-Null
    }
    if (-not (Test-Path $profilePath)) {
        New-Item -ItemType File -Path $profilePath -Force | Out-Null
    }

    $content = Get-Content $profilePath -Raw -ErrorAction SilentlyContinue
    if (-not $content) { $content = '' }

    $block = New-ProfileBlock

    if ($content -match [regex]::Escape($MarkerBegin)) {
        # Replace existing block
        $pattern = "(?s)$([regex]::Escape($MarkerBegin)).*?$([regex]::Escape($MarkerEnd))"
        $content = [regex]::Replace($content, $pattern, $block)
        Write-Host "  Updated existing block in $profilePath"
    }
    else {
        $content = $content.TrimEnd() + "`n`n" + $block + "`n"
        Write-Host "  Added new block to $profilePath"
    }

    Set-Content -Path $profilePath -Value $content -NoNewline
}

function Uninstall-ProfileBlock {
    $profilePath = $PROFILE.CurrentUserCurrentHost
    if (-not (Test-Path $profilePath)) { return }

    $content = Get-Content $profilePath -Raw -ErrorAction SilentlyContinue
    if (-not $content) { return }

    if ($content -match [regex]::Escape($MarkerBegin)) {
        $pattern = "(?s)\r?\n?$([regex]::Escape($MarkerBegin)).*?$([regex]::Escape($MarkerEnd))\r?\n?"
        $content = [regex]::Replace($content, $pattern, "`n")
        $content = $content.TrimEnd() + "`n"
        Set-Content -Path $profilePath -Value $content -NoNewline
        Write-Host "  Removed block from $profilePath"
    }
}

function Install-UserEnvVars {
    foreach ($kv in $EnvVars.GetEnumerator()) {
        [Environment]::SetEnvironmentVariable($kv.Key, $kv.Value, 'User')
    }
    Write-Host "  Set $($EnvVars.Count) User environment variables"
    Write-Host "  (VS Code needs restart to pick up changes)"
}

function Uninstall-UserEnvVars {
    foreach ($kv in $EnvVars.GetEnumerator()) {
        [Environment]::SetEnvironmentVariable($kv.Key, $null, 'User')
    }
    Write-Host "  Removed $($EnvVars.Count) User environment variables"
}

function Show-Status {
    Write-Host '=== Current OTel Environment ==='
    Write-Host ''
    foreach ($kv in $EnvVars.GetEnumerator()) {
        $current = [Environment]::GetEnvironmentVariable($kv.Key, 'Process')
        if (-not $current) { $current = '<not set>' }
        $expected = $kv.Value
        if ($current -eq $expected) {
            Write-Host "  OK $($kv.Key)=$current" -ForegroundColor Green
        }
        else {
            Write-Host "  NG $($kv.Key)=$current (expected: $expected)" -ForegroundColor Yellow
        }
    }
}

switch ($Command) {
    'install' {
        Write-Host 'Installing OTel environment variables...'
        Write-Host ''
        Write-Host '[PowerShell profile]'
        Install-ProfileBlock
        Write-Host ''
        Write-Host '[User environment variables]'
        Install-UserEnvVars
        Write-Host ''
        Write-Host 'Done. To apply:'
        Write-Host "  - Terminal: . `$PROFILE"
        Write-Host '  - Desktop apps (VS Code): restart VS Code'
    }
    'uninstall' {
        Write-Host 'Removing OTel environment variables...'
        Write-Host ''
        Write-Host '[PowerShell profile]'
        Uninstall-ProfileBlock
        Write-Host ''
        Write-Host '[User environment variables]'
        Uninstall-UserEnvVars
        Write-Host ''
        Write-Host 'Done. Restart your terminal and VS Code to fully remove.'
    }
    'status' {
        Show-Status
    }
}
