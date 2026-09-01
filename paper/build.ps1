<#
.SYNOPSIS
    Build the IEEE-format manuscript on Windows.
.DESCRIPTION
    Tries latexmk, then a pdflatex/bibtex/pdflatex/pdflatex sequence, then
    tectonic. With -Regen the experiments are re-run first, which rewrites every
    table, figure and inline number. The document uses the IEEEtran class and
    IEEEtran.bst; both ship with TeX Live and MiKTeX.
.EXAMPLE
    ./build.ps1 -Regen
#>
param(
    [switch]$Regen,
    [switch]$Clean
)

$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot

if ($Clean) {
    Get-ChildItem -Include *.aux, *.bbl, *.blg, *.log, *.out, *.toc, *.fls, *.fdb_latexmk `
        -Recurse -ErrorAction SilentlyContinue | Remove-Item -Force
    Write-Host 'Cleaned build artefacts.' -ForegroundColor Green
    return
}

if ($Regen) {
    Write-Host 'Regenerating results, tables and figures ...' -ForegroundColor Cyan
    $python = if (Test-Path '../.venv/Scripts/python.exe') { '../.venv/Scripts/python.exe' } else { 'python' }
    Push-Location ../code
    & $python run_experiments.py --dump-artifacts
    Pop-Location
}

function Test-Command($name) {
    return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

if (Test-Command 'latexmk') {
    Write-Host 'Building with latexmk ...' -ForegroundColor Cyan
    latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
}
elseif (Test-Command 'pdflatex') {
    Write-Host 'Building with pdflatex + bibtex ...' -ForegroundColor Cyan
    pdflatex -interaction=nonstopmode main.tex
    if (Test-Command 'bibtex') { bibtex main }
    pdflatex -interaction=nonstopmode main.tex
    pdflatex -interaction=nonstopmode main.tex
}
elseif (Test-Command 'tectonic') {
    Write-Host 'Building with tectonic ...' -ForegroundColor Cyan
    tectonic -X compile main.tex
}
else {
    Write-Warning @'
No LaTeX toolchain found. Options:
  1. Install MiKTeX      : winget install MiKTeX.MiKTeX
  2. Install TinyTeX     : https://yihui.org/tinytex/
  3. Install Tectonic    : winget install TectonicProject.Tectonic
  4. Use Docker          : docker run --rm -v "${PWD}:/w" -w /w texlive/texlive:latest latexmk -pdf main.tex
  5. Upload paper/ to Overleaf and set main.tex as the root document.
'@
    exit 1
}

if (Test-Path 'main.pdf') {
    Write-Host "Built $((Resolve-Path 'main.pdf').Path)" -ForegroundColor Green
}
