param(
  [string]$RepoUrl = "https://github.com/FreeGoStudio/multithreading-learning-skill.git",
  [string]$Branch = "main",
  [string]$CodexHome = $env:CODEX_HOME,
  [string]$InstallRoot = (Join-Path $env:TEMP "multithreading-learning-skill"),
  [switch]$NoBackup
)

$ErrorActionPreference = "Stop"

function Assert-CommandExists {
  param([string]$Name)

  if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
    throw "Required command not found: $Name. Please install Git and try again."
  }
}

function Invoke-Git {
  param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)

  & git @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "Git command failed with exit code ${LASTEXITCODE}: git $($Arguments -join ' ')"
  }
}

Assert-CommandExists "git"

if (-not $CodexHome -or $CodexHome.Trim() -eq "") {
  $CodexHome = Join-Path $env:USERPROFILE ".codex"
}

$repoDir = Join-Path $InstallRoot "repo"
New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null

if (Test-Path -LiteralPath (Join-Path $repoDir ".git") -PathType Container) {
  Write-Host "Updating existing checkout: $repoDir"
  Invoke-Git -C $repoDir remote set-url origin $RepoUrl
  Invoke-Git -C $repoDir fetch origin $Branch --prune
  Invoke-Git -C $repoDir checkout $Branch
  Invoke-Git -C $repoDir reset --hard "origin/$Branch"
} else {
  if (Test-Path -LiteralPath $repoDir) {
    Remove-Item -LiteralPath $repoDir -Recurse -Force
  }

  Write-Host "Cloning $RepoUrl ($Branch) to: $repoDir"
  Invoke-Git clone --depth 1 --branch $Branch $RepoUrl $repoDir
}

$installer = Join-Path $repoDir "scripts\install-skill.ps1"
if (-not (Test-Path -LiteralPath $installer -PathType Leaf)) {
  throw "Installer not found after clone: $installer"
}

$installerArguments = @(
  "-NoProfile",
  "-ExecutionPolicy", "Bypass",
  "-File", $installer,
  "-CodexHome", $CodexHome
)

if ($NoBackup) {
  $installerArguments += "-NoBackup"
}

Write-Host ""
Write-Host "Running local installer..."
& powershell @installerArguments

if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}

Write-Host ""
Write-Host "Done."
