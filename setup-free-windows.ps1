# Free local GTAClipper setup for Windows 11 / 16 GB RAM
# Run this file in PowerShell from the extracted repository folder.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker Desktop is not installed. Install Docker Desktop with WSL2 first."
}
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Docker Desktop is not running. Open it and wait for Engine running."
}

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
}
$envPath = Join-Path $PSScriptRoot ".env"
$config = [System.IO.File]::ReadAllText($envPath)

# Generate local auth secrets, never commit this .env file.
foreach ($key in @("BETTER_AUTH_SECRET", "BACKEND_AUTH_SECRET", "APP_SETTINGS_ENCRYPTION_KEY")) {
    $pattern = "(?m)^" + [regex]::Escape($key) + "=(.*)$"
    $match = [regex]::Match($config, $pattern)
    $existing = if ($match.Success) { $match.Groups[1].Value.Trim() } else { "" }
    if ($existing.Length -lt 32 -or $existing -match "^(change|make-|your_|gtaclipper_dev_)") {
        $bytes = New-Object byte[] 32
        $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
        try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
        $secret = [BitConverter]::ToString($bytes).Replace("-", "").ToLowerInvariant()
        if ($match.Success) {
            $config = [regex]::Replace($config, $pattern, ($key + "=" + $secret))
        } else {
            $config += [Environment]::NewLine + $key + "=" + $secret + [Environment]::NewLine
        }
    }
}

[System.IO.File]::WriteAllText($envPath, $config, (New-Object System.Text.UTF8Encoding($false)))
Write-Host "Starting GTAClipper with local Whisper and Ollama..." -ForegroundColor Cyan
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build
if ($LASTEXITCODE -ne 0) {
    throw "Docker setup failed. Read the Docker logs for details."
}
Write-Host "Open http://localhost:3107 once containers are healthy." -ForegroundColor Green
