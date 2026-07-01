# Runs the bot with the Python launcher (py). Usage:  .\run.ps1
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    Write-Error "Python launcher 'py' not found. Install Python 3.9+ from https://python.org (check 'Add to PATH')."
    exit 1
}

if (-not (Test-Path ".env")) {
    Write-Warning "No .env file found. Copy .env.example to .env and fill it in:"
    Write-Host "    Copy-Item .env.example .env"
    exit 1
}

Write-Host "Installing dependencies..."
py -m pip install -q -r requirements.txt

Write-Host "Starting bot..."
py bot.py
