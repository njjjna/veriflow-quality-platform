# VeriFlow: Windows local Docker launcher. PostgreSQL is default; -UseSQLite is optional.
param(
  [string]$AdminEmail = 'admin@demo.invalid',
  [switch]$NoBootstrap,
  [switch]$UseSQLite
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw '未找到Docker。请先安装并启动 Docker Desktop，然后重新运行本脚本。'
    }
    docker info *> $null
    if ($LASTEXITCODE -ne 0) {throw 'Docker Engine未启动。请先启动Docker Desktop。'}
    $files = @('-f', 'compose.yml')
    if (-not $UseSQLite) {
        $files += @('-f', 'compose.postgres.yml')
        $envFile = Join-Path $root '.env'
        $existing = if (Test-Path $envFile) { Get-Content $envFile -Raw } else { '' }
        if ($existing -notmatch '(?m)^POSTGRES_PASSWORD=\S+') {
            $bytes = New-Object byte[] 32
            $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
            try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
            $secret = [BitConverter]::ToString($bytes).Replace('-', '').ToLowerInvariant()
            if ($existing -and -not $existing.EndsWith("`n")) { Add-Content -Path $envFile -Value '' }
            Add-Content -Path $envFile -Value "POSTGRES_PASSWORD=$secret"
            Write-Host '已生成本机PostgreSQL密码并保存到 .env （已在.gitignore中忽略，勿上传）。'
        }
    }
    docker compose @files up --build -d
    if ($LASTEXITCODE -ne 0) {throw 'Docker Compose启动失败；请检查终端输出。'}
    Write-Host 'VeriFlow 已在 http://localhost:8000 启动；存储：' $(if ($UseSQLite) {'SQLite'} else {'PostgreSQL'})
    if (-not $NoBootstrap) {
        Write-Host '首次运行，请设置管理员密码两遍（至少12位）；已有管理员时可忽略初始化提示。'
        docker compose @files exec web python -m app.bootstrap --email $AdminEmail
        if ($LASTEXITCODE -ne 0) {Write-Warning '管理员初始化未执行；若已有管理员可直接登录，否则查看上方报错。'}
    }
    Start-Process 'http://localhost:8000'
    Write-Host '停止服务：./scripts/stop_local.ps1 ；SQLite部署请使用 ./scripts/stop_local.ps1 -UseSQLite'
} finally {Pop-Location}
