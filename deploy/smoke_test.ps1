#!/usr/bin/env pwsh
# Smoke test against deployed portal.
$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
$InstanceEnv = Join-Path $PSScriptRoot "instance.env"
if (-not (Test-Path $InstanceEnv)) { throw "Run deploy/provision.ps1 first" }
Get-Content $InstanceEnv | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "env:$($Matches[1])" -Value $Matches[2] }
}

$Base = "http://$($env:EC2_PUBLIC_IP):8000"
Write-Host "Testing $Base ..."

function Test-Endpoint($path, $desc) {
    $url = "$Base$path"
    try {
        $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 30
        Write-Host "[OK] $desc ($($r.StatusCode))"
        return $r
    } catch {
        Write-Host "[FAIL] $desc — $($_.Exception.Message)"
        throw
    }
}

Test-Endpoint "/ready" "API ready"
$portal = Test-Endpoint "/portal" "Portal HTML"
if ($portal.Content -notmatch "Mindful News") { throw "Portal missing title" }

$headlines = Invoke-RestMethod -Uri "$Base/api/headlines?limit=5" -TimeoutSec 30
$count = if ($headlines.items) { $headlines.items.Count } else { $headlines.Count }
Write-Host "[OK] Headlines API returned $count items"

Write-Host ""
Write-Host "All checks passed!"
Write-Host "Portal: $env:PORTAL_URL"
