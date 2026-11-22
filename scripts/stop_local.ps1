param([switch]$UseSQLite)
$ErrorActionPreference = 'Stop'
Push-Location (Split-Path -Parent $PSScriptRoot)
try {
  $files = @('-f', 'compose.yml')
  if (-not $UseSQLite) { $files += @('-f', 'compose.postgres.yml') }
  docker compose @files down
  if ($LASTEXITCODE -ne 0) {throw '停止服务失败，请检查Docker Desktop。'}
  Write-Host '已停止VeriFlow，数据库卷保留，下次启动仍有原始数据。'
} finally {Pop-Location}
