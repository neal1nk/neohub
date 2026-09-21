# Push NeoHub to GitHub (run once after creating an empty repo on github.com)
# Usage:
#   .\scripts\push-github.ps1 -RepoUrl https://github.com/YOUR_LOGIN/neohub.git

param(
    [Parameter(Mandatory = $true)]
    [string]$RepoUrl
)

$ErrorActionPreference = "Stop"
$git = Join-Path $env:LOCALAPPDATA "Programs\git-portable\cmd\git.exe"
if (-not (Test-Path $git)) {
    $git = "git"
}

Set-Location (Split-Path $PSScriptRoot -Parent)

& $git remote remove origin 2>$null
& $git remote add origin $RepoUrl
& $git branch -M main
& $git push -u origin main

Write-Host "Pushed to $RepoUrl" -ForegroundColor Green
Write-Host "Next: open https://dashboard.render.com → New → Blueprint" -ForegroundColor Cyan
