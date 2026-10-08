param([switch]$Regen)

$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    if ($Regen) {
        $python = Join-Path $PSScriptRoot '../.venv/Scripts/python.exe'
        if (-not (Test-Path $python)) { $python = 'python' }
        & $python ../code/run_revision.py --paper $PSScriptRoot
        if ($LASTEXITCODE -ne 0) { throw 'Revision experiments failed.' }
    }
    if (Get-Command latexmk -ErrorAction SilentlyContinue) {
        latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
    }
    elseif (Get-Command tectonic -ErrorAction SilentlyContinue) {
        tectonic -X compile main.tex
    }
    elseif (Get-Command pdflatex -ErrorAction SilentlyContinue) {
        pdflatex -interaction=nonstopmode -halt-on-error main.tex
        if ($LASTEXITCODE -ne 0) { throw 'Initial LaTeX pass failed.' }
        bibtex main
        if ($LASTEXITCODE -ne 0) { throw 'Bibliography build failed.' }
        pdflatex -interaction=nonstopmode -halt-on-error main.tex
        if ($LASTEXITCODE -ne 0) { throw 'Second LaTeX pass failed.' }
        pdflatex -interaction=nonstopmode -halt-on-error main.tex
    }
    else {
        throw 'No LaTeX toolchain found. Install one or build in a TeX-enabled environment; include ../paper/refs.bib.'
    }
    if ($LASTEXITCODE -ne 0) { throw 'Revision paper build failed.' }
}
finally {
    Pop-Location
}