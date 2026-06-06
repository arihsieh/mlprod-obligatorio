#!/usr/bin/env pwsh
# Incremental Docker startup — run each step separately, wait for health before next.
# Usage: .\scripts\docker_up.ps1 [-Step all|mysql|api|portal|poller]

param(
    [ValidateSet("all", "mysql", "api", "portal", "poller")]
    [string]$Step = "all"
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

function Wait-Healthy($Service, $MaxSeconds = 120) {
    $deadline = (Get-Date).AddSeconds($MaxSeconds)
    while ((Get-Date) -lt $deadline) {
        $status = docker compose ps $Service --format "{{.Health}}" 2>$null
        if ($status -match "healthy") { return $true }
        if ($Service -eq "mysql" -and (docker compose ps $Service --format "{{.State}}" 2>$null) -match "running") {
            Start-Sleep 3
            $status = docker compose ps $Service --format "{{.Health}}" 2>$null
            if ($status -match "healthy") { return $true }
        }
        Start-Sleep 3
    }
    return $false
}

Write-Host "==> Checking Docker..."
docker info --format "{{.ServerVersion}}" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Docker daemon not running. Start Docker Desktop first." }

if ($Step -eq "all" -or $Step -eq "mysql") {
    Write-Host "==> Starting MySQL..."
    docker compose up -d mysql
    if (-not (Wait-Healthy "mysql" 60)) { throw "MySQL did not become healthy" }
    docker compose ps mysql
}

if ($Step -eq "all" -or $Step -eq "api") {
    Write-Host "==> Building + starting API (first build may take 10-15 min)..."
    docker compose up --build -d api
    Write-Host "    Waiting for /ready (up to 3 min)..."
    if (-not (Wait-Healthy "api" 180)) { throw "API did not become healthy — check: docker compose logs api" }
    docker compose ps api
    Write-Host "    API: http://localhost:8000/docs"
}

if ($Step -eq "all" -or $Step -eq "portal") {
    Write-Host "==> Building + starting portal..."
    docker compose up --build -d portal
    docker compose ps portal
    Write-Host "    Portal: http://localhost:8501"
}

if ($Step -eq "all" -or $Step -eq "poller") {
    Write-Host "==> Starting poller..."
    docker compose up --build -d poller
    docker compose ps poller
}

Write-Host "Done."
