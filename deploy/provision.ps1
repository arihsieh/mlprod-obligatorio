#!/usr/bin/env pwsh
# Provision EC2 + security group + Elastic IP for Mindful News.
# Reads AWS credentials from .env in repo root.
$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
$DeployDir = Join-Path $Root "deploy"
$EnvFile = Join-Path $Root ".env"
$InstanceEnv = Join-Path $DeployDir "instance.env"

function Load-DotEnv($path) {
    if (-not (Test-Path $path)) { throw "Missing $path" }
    Get-Content $path | ForEach-Object {
        if ($_ -match '^\s*#' -or $_ -match '^\s*$') { return }
        $parts = $_ -split '=', 2
        if ($parts.Count -eq 2) {
            $key = $parts[0].Trim()
            $val = $parts[1].Trim().Trim('"')
            Set-Item -Path "env:$key" -Value $val
        }
    }
    # Normalize common AWS env var names
    if ($env:aws_access_key_id -and -not $env:AWS_ACCESS_KEY_ID) { $env:AWS_ACCESS_KEY_ID = $env:aws_access_key_id }
    if ($env:aws_secret_access_key -and -not $env:AWS_SECRET_ACCESS_KEY) { $env:AWS_SECRET_ACCESS_KEY = $env:aws_secret_access_key }
    if ($env:aws_session_token -and -not $env:AWS_SESSION_TOKEN) { $env:AWS_SESSION_TOKEN = $env:aws_session_token }
}

Load-DotEnv $EnvFile
if (-not $env:AWS_ACCESS_KEY_ID) { throw "AWS_ACCESS_KEY_ID not found in .env" }

$Region = if ($env:AWS_REGION) { $env:AWS_REGION } else { "us-east-1" }
$env:AWS_DEFAULT_REGION = $Region
$KeyName = "mindful-news-deploy"
$KeyPath = Join-Path $DeployDir "$KeyName.pem"
$SgName = "mindful-news-sg"
$InstanceType = if ($env:EC2_INSTANCE_TYPE) { $env:EC2_INSTANCE_TYPE } else { "t3.large" }

Write-Host "==> Region: $Region | Instance: $InstanceType"

# Get Ubuntu 22.04 AMI
$AmiId = aws ec2 describe-images `
    --owners 099720109477 `
    --filters "Name=name,Values=ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*" "Name=state,Values=available" `
    --query "sort_by(Images, &CreationDate)[-1].ImageId" `
    --output text
Write-Host "AMI: $AmiId"

# Key pair
if (-not (Test-Path $KeyPath)) {
    Write-Host "==> Creating key pair $KeyName"
    aws ec2 create-key-pair --key-name $KeyName --query KeyMaterial --output text | Out-File -FilePath $KeyPath -Encoding ascii
    icacls $KeyPath /inheritance:r /grant:r "$($env:USERNAME):(R)" | Out-Null
} else {
    Write-Host "==> Reusing key $KeyPath"
}

# Security group
$VpcId = aws ec2 describe-vpcs --filters "Name=is-default,Values=true" --query "Vpcs[0].VpcId" --output text
$SgId = aws ec2 describe-security-groups --filters "Name=group-name,Values=$SgName" --query "SecurityGroups[0].GroupId" --output text 2>$null
if ($SgId -eq "None" -or -not $SgId) {
    $SgId = aws ec2 create-security-group --group-name $SgName --description "Mindful News" --vpc-id $VpcId --query GroupId --output text
    $MyIp = (Invoke-RestMethod -Uri "https://checkip.amazonaws.com").Trim()
    aws ec2 authorize-security-group-ingress --group-id $SgId --protocol tcp --port 22 --cidr "$MyIp/32" | Out-Null
    aws ec2 authorize-security-group-ingress --group-id $SgId --protocol tcp --port 8000 --cidr "0.0.0.0/0" | Out-Null
    Write-Host "Security group created: $SgId (SSH from $MyIp, 8000 public)"
} else {
    Write-Host "Security group exists: $SgId"
}

# Check for existing running instance with tag
$Existing = aws ec2 describe-instances `
    --filters "Name=tag:Project,Values=mindful-news" "Name=instance-state-name,Values=running,pending" `
    --query "Reservations[0].Instances[0].InstanceId" --output text

if ($Existing -and $Existing -ne "None") {
    $InstanceId = $Existing
    Write-Host "==> Reusing instance $InstanceId"
} else {
    Write-Host "==> Launching EC2..."
    $UserData = @"
#!/bin/bash
set -e
apt-get update
apt-get install -y ca-certificates curl git
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=`$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu `$(. /etc/os-release && echo `$VERSION_CODENAME) stable" > /etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
usermod -aG docker ubuntu
mkdir -p /home/ubuntu/mlprod-obligatorio/models
chown -R ubuntu:ubuntu /home/ubuntu/mlprod-obligatorio
"@
    $UserDataFile = Join-Path $env:TEMP "mindful-userdata.sh"
    $UserData | Out-File -FilePath $UserDataFile -Encoding ascii -NoNewline

    $InstanceId = aws ec2 run-instances `
        --image-id $AmiId `
        --instance-type $InstanceType `
        --key-name $KeyName `
        --security-group-ids $SgId `
        --block-device-mappings "DeviceName=/dev/sda1,Ebs={VolumeSize=40,VolumeType=gp3}" `
        --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=mindful-news},{Key=Project,Value=mindful-news}]" `
        --user-data "file://$UserDataFile" `
        --query "Instances[0].InstanceId" --output text
    Write-Host "Instance launched: $InstanceId"
    aws ec2 wait instance-running --instance-ids $InstanceId
}

# Elastic IP
$Allocation = aws ec2 describe-addresses --filters "Name=tag:Project,Values=mindful-news" --query "Addresses[0].AllocationId" --output text
if ($Allocation -eq "None" -or -not $Allocation) {
    $Allocation = aws ec2 allocate-address --domain vpc --tag-specifications "ResourceType=elastic-ip,Tags=[{Key=Project,Value=mindful-news}]" --query AllocationId --output text
    aws ec2 associate-address --instance-id $InstanceId --allocation-id $Allocation | Out-Null
} else {
    $CurrentInstance = aws ec2 describe-addresses --allocation-ids $Allocation --query "Addresses[0].InstanceId" --output text
    if ($CurrentInstance -ne $InstanceId) {
        aws ec2 associate-address --instance-id $InstanceId --allocation-id $Allocation | Out-Null
    }
}

$PublicIp = aws ec2 describe-addresses --allocation-ids $Allocation --query "Addresses[0].PublicIp" --output text
Write-Host "Waiting for instance status checks..."
aws ec2 wait instance-status-ok --instance-ids $InstanceId

$PortalUrl = "http://${PublicIp}:8000/portal"
@"
EC2_INSTANCE_ID=$InstanceId
EC2_PUBLIC_IP=$PublicIp
EC2_SSH_KEY=$KeyPath
EC2_REGION=$Region
PORTAL_URL=$PortalUrl
"@ | Out-File -FilePath $InstanceEnv -Encoding utf8

Write-Host ""
Write-Host "Provisioned successfully!"
Write-Host "  Instance: $InstanceId"
Write-Host "  Public IP: $PublicIp"
Write-Host "  Portal URL: $PortalUrl"
Write-Host "  SSH: ssh -i `"$KeyPath`" ubuntu@$PublicIp"
Write-Host ""
Write-Host "Next: .\deploy\upload.ps1"
