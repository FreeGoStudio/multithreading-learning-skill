param(
  [string]$CodexHome = $env:CODEX_HOME,
  [switch]$NoBackup
)

$ErrorActionPreference = "Stop"

$skillName = "csharp-concurrency-coach"
$scriptPath = $MyInvocation.MyCommand.Path
$scriptDir = Split-Path -Parent $scriptPath
$repoRoot = Split-Path -Parent $scriptDir
$source = Join-Path $repoRoot $skillName

if (-not $CodexHome -or $CodexHome.Trim() -eq "") {
  $CodexHome = Join-Path $env:USERPROFILE ".codex"
}

$skillsRoot = Join-Path $CodexHome "skills"
$target = Join-Path $skillsRoot $skillName

function Assert-FileExists {
  param([string]$Path)

  if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
    throw "Required file not found: $Path"
  }
}

function Assert-DirectoryExists {
  param([string]$Path)

  if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
    throw "Required directory not found: $Path"
  }
}

Assert-DirectoryExists $source
Assert-FileExists (Join-Path $source "SKILL.md")

New-Item -ItemType Directory -Force -Path $skillsRoot | Out-Null

if (Test-Path -LiteralPath $target) {
  if ($NoBackup) {
    Remove-Item -LiteralPath $target -Recurse -Force
    Write-Host "Removed existing skill: $target"
  } else {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss-fff"
    $backup = Join-Path $skillsRoot "$skillName.backup-$stamp"
    Move-Item -LiteralPath $target -Destination $backup
    Write-Host "Backed up existing skill to: $backup"
  }
}

Copy-Item -LiteralPath $source -Destination $target -Recurse

Assert-FileExists (Join-Path $target "SKILL.md")
Assert-DirectoryExists (Join-Path $target "agents")
Assert-DirectoryExists (Join-Path $target "assets")
Assert-DirectoryExists (Join-Path $target "references")
Assert-DirectoryExists (Join-Path $target "scripts")

Write-Host ""
Write-Host "Installed Codex skill: $skillName"
Write-Host "Target: $target"
Write-Host ""
Write-Host "Open a new Codex task and test with:"
Write-Host "Use `$$skillName."
