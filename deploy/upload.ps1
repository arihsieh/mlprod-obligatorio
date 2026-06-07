#!/usr/bin/env pwsh
# Upload code + models to EC2 and start the stack.
$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
$DeployDir = Join-Path $Root "deploy"
$InstanceEnv = Join-Path $DeployDir "instance.env"

if (-not (Test-Path $InstanceEnv)) { throw "Run deploy/provision.ps1 first" }
Get-Content $InstanceEnv | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "env:$($Matches[1])" -Value $Matches[2] }
}

$Ip = $env:EC2_PUBLIC_IP
$Key = $env:EC2_SSH_KEY
$Remote = "ubuntu@$Ip"
$SshOpts = @("-i", $Key, "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=30")

Write-Host "==> Packing models..."
& (Join-Path $Root "scripts\pack_models.ps1")

Write-Host "==> Preparing remote directory..."
ssh @SshOpts $Remote "mkdir -p ~/mlprod-obligatorio/models ~/mlprod-obligatorio/mindful_news ~/mlprod-obligatorio/portal ~/mlprod-obligatorio/data/splits ~/mlprod-obligatorio/scripts ~/mlprod-obligatorio/deploy"

$Files = @(
    "config.yml",
    "docker-compose.prod.yml",
    "Dockerfile",
    "Dockerfile.poller",
    "requirements.txt",
    "requirements-ml.txt",
    "requirements-api.txt",
    "requirements-poller.txt"
)
foreach ($f in $Files) {
    scp @SshOpts (Join-Path $Root $f) "${Remote}:~/mlprod-obligatorio/"
}

scp @SshOpts -r (Join-Path $Root "mindful_news") "${Remote}:~/mlprod-obligatorio/"
scp @SshOpts (Join-Path $Root "portal\index.html") "${Remote}:~/mlprod-obligatorio/portal/"
scp @SshOpts -r (Join-Path $Root "data\splits") "${Remote}:~/mlprod-obligatorio/data/"
scp @SshOpts (Join-Path $Root "scripts\run_api.py") "${Remote}:~/mlprod-obligatorio/scripts/"
scp @SshOpts (Join-Path $Root "scripts\run_poller.py") "${Remote}:~/mlprod-obligatorio/scripts/"
scp @SshOpts (Join-Path $Root "deploy\start-remote.sh") "${Remote}:~/mlprod-obligatorio/deploy/"

Write-Host "==> Uploading models (~500MB, may take several minutes)..."
scp @SshOpts (Join-Path $Root "models-deploy.tar.gz") "${Remote}:~/"

Write-Host "==> Starting stack on EC2..."
ssh @SshOpts $Remote "bash ~/mlprod-obligatorio/deploy/start-remote.sh"

Write-Host ""
Write-Host "Upload complete. Portal: $env:PORTAL_URL"
Write-Host "Run: .\deploy\smoke_test.ps1"
