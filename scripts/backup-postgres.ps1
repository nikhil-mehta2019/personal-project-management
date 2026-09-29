param([string]$OutputDirectory = "./backups")
$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$file = Join-Path $OutputDirectory "workos-$stamp.dump"
docker compose exec -T db pg_dump -U workos -d workos -Fc > $file
if ((Get-Item $file).Length -lt 100) { throw "Backup appears empty: $file" }
Write-Host "Created $file"
