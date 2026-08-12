# Start TheResearcher via Docker Compose on port 50080
Set-Location (Split-Path $PSScriptRoot -Parent)
docker compose up --build -d
Write-Host "TheResearcher should be available at http://localhost:50080"
