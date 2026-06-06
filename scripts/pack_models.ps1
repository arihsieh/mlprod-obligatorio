#!/usr/bin/env pwsh
# Pack production model files for upload to EC2 (excludes trial checkpoints).
$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
$Out = Join-Path $Root "models-deploy.tar.gz"

$staging = Join-Path $env:TEMP "mindful-models-deploy"
if (Test-Path $staging) { Remove-Item $staging -Recurse -Force }
New-Item -ItemType Directory -Path "$staging/temas-phase4", "$staging/carga-phase3" | Out-Null

$include = @("config.json", "model.safetensors", "tokenizer.json", "tokenizer_config.json", "metrics.json")
foreach ($task in @("temas-phase4", "carga-phase3")) {
    $src = Join-Path $Root "models/$task"
    if (-not (Test-Path $src)) { throw "Missing $src" }
    foreach ($name in $include) {
        $file = Join-Path $src $name
        if (Test-Path $file) {
            Copy-Item $file (Join-Path $staging $task)
        }
    }
}

if (Test-Path $Out) { Remove-Item $Out -Force }
tar -czf $Out -C $staging .
Remove-Item $staging -Recurse -Force
$size = [math]::Round((Get-Item $Out).Length / 1MB, 1)
Write-Host "Created $Out ($size MB)"
