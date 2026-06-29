<#
.SYNOPSIS
  Export a finished FunscriptForge scene to a current-format `.forge` bundle
  (a zip containing manifest.ffmeta + motion.funscript + stations/<id>/...),
  for use as a forgeassembler `.forge`-import test fixture.

.DESCRIPTION
  Wraps `funscriptforge/cli.py export --mode forge`. Export is a PACKAGER: it
  gathers the effective main funscript, any Polish-stamped device stations,
  events.yml, the authoring sidecars (chapters/phrases/characters json), and
  writes a manifest.ffmeta describing it all into a `.forge` zip.

  NOTE: the bundle's channel richness depends on what's in the source project's
  working `.forge/` sidecar dir (polish stations, characters.json). A sparse
  working folder yields a thinner bundle (motion-only). Inspect the printed
  manifest's `artifacts`/`stations` after running.

.PARAMETER SrcFunscript
  Path to the scene's main .funscript (owns the stem + working forge dir).

.PARAMETER OutDir
  Where to drop the bundle. Defaults to forgeassembler/test_media/forge_bundles.

.PARAMETER Stem
  Bundle stem (default: source filename without extension).

.PARAMETER IncludeMedia
  Embed the source video in the bundle (big — standalone handoff). Default off
  (lean bundle + manifest relink key).

.PARAMETER FromLooseChannels
  Instead of running FSF's export (which rebuilds channels from a live working
  folder), repackage the LOOSE channel funscripts already on disk next to the
  motion funscript (`<stem>.funscript` + `<stem>.<channel>.funscript`) into a
  multi-channel `.forge` bundle via scripts/build_forge_from_loose.py. Use this
  when a scene exists only as exported output files. Output stem gets `.full`.

.EXAMPLE
  .\make_forge_fixture.ps1 -SrcFunscript `
    "C:\Users\bruce\Projects\_lqr\funscriptforge\assets\output\VictoriaOaks_stingy\VictoriaOaks_stingy.funscript"

.EXAMPLE
  # Build more later — just point at another finished scene's main funscript:
  .\make_forge_fixture.ps1 -SrcFunscript "C:\...\AnotherScene\AnotherScene.funscript"
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)][string]$SrcFunscript,
  [string]$OutDir = "C:\Users\bruce\Projects\_lqr\forgeassembler\test_media\forge_bundles",
  [string]$Stem,
  [switch]$IncludeMedia,
  [switch]$FromLooseChannels
)

$ErrorActionPreference = "Stop"

$FsfRoot = "C:\Users\bruce\Projects\_lqr\funscriptforge"
$Python  = Join-Path $FsfRoot ".venv\Scripts\python.exe"
$Cli     = Join-Path $FsfRoot "cli.py"

if (-not (Test-Path $Python))       { throw "FSF venv python not found: $Python" }
if (-not (Test-Path $SrcFunscript)) { throw "Source funscript not found: $SrcFunscript" }
if (-not $Stem) { $Stem = [System.IO.Path]::GetFileNameWithoutExtension($SrcFunscript) }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

# ── Loose-channel mode: repackage existing output funscripts ──────────
if ($FromLooseChannels) {
  $Builder = Join-Path $PSScriptRoot "build_forge_from_loose.py"
  $Folder  = Split-Path -Parent $SrcFunscript
  $Out     = Join-Path $OutDir "$Stem.full.forge"
  Write-Host "Repackaging loose channels for '$Stem'" -ForegroundColor Cyan
  Write-Host "  folder : $Folder"
  Write-Host "  out    : $Out"
  & $Python $Builder $Folder $Stem --out $Out
  Write-Host "`nDone." -ForegroundColor Green
  return
}

# ── Default mode: real FSF export ─────────────────────────────────────
if (-not (Test-Path $Cli)) { throw "FSF cli.py not found: $Cli" }
$Out = Join-Path $OutDir "$Stem.forge"

$cliArgs = @($Cli, "export", $SrcFunscript, "--mode", "forge", "--out", $Out, "--stem", $Stem)
if ($IncludeMedia) { $cliArgs += "--include-media" }

Write-Host "Exporting '$Stem'" -ForegroundColor Cyan
Write-Host "  src : $SrcFunscript"
Write-Host "  out : $Out"
Write-Host "  cmd : python cli.py $($cliArgs[1..($cliArgs.Length-1)] -join ' ')"
Write-Host ""

# cmd_export prints a JSON summary to stdout (mode/path/artifacts/stations/manifest).
& $Python @cliArgs

Write-Host ""
Write-Host "Done. (export auto-increments to avoid clobbering a prior snapshot)" -ForegroundColor Green
