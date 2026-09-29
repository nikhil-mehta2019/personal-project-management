param([Parameter(Mandatory=$true)][string]$BackupFile)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $BackupFile)) { throw "Backup not found: $BackupFile" }
Write-Host "This replaces the current database. Stop the backend before continuing."
$answer = Read-Host "Type RESTORE to continue"
if ($answer -ne 'RESTORE') { throw 'Restore cancelled' }
docker compose stop backend
Get-Content -LiteralPath $BackupFile -AsByteStream | docker compose exec -T db pg_restore -U workos -d workos --clean --if-exists --no-owner
docker compose start backend
docker compose exec -T backend alembic -c alembic.ini upgrade head
Write-Host "Restore completed and migrations applied."
