param([switch]$Regen, [string]$TectonicPath)

$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    if ($Regen) {
        $python = Join-Path $PSScriptRoot '../.venv/Scripts/python.exe'
        if (-not (Test-Path $python)) { $python = 'python' }
        Push-Location ../code
        try { & $python run_updated.py --paper $PSScriptRoot } finally { Pop-Location }
        if ($LASTEXITCODE -ne 0) { throw 'Survey/case-study generation failed.' }
    }
    $portable = Join-Path $env:LOCALAPPDATA 'RoleOfSemanticsTools/tectonic/tectonic.exe'
    if (Get-Command latexmk -ErrorAction SilentlyContinue) {
        latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
    }
    elseif (Get-Command tectonic -ErrorAction SilentlyContinue) {
        tectonic -X compile main.tex --keep-logs --keep-intermediates
    }
    elseif ($TectonicPath -and (Test-Path $TectonicPath)) {
        & $TectonicPath -X compile main.tex --keep-logs --keep-intermediates
    }
    elseif (Test-Path $portable) {
        & $portable -X compile main.tex --keep-logs --keep-intermediates
    }
    else {
        throw 'No LaTeX toolchain found (latexmk or Tectonic).'
    }
    if ($LASTEXITCODE -ne 0) { throw 'Survey paper build failed.' }
}
finally {
    Pop-Location
}
