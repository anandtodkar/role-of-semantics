# Industrial agent grounding: revision workspace

This folder is a sibling of `paper/`, not a replacement. The original manuscript,
generated tables, archived model run and results must remain unchanged.

## Research question

What does executable engineering semantics improve over an equally informed,
well-engineered OPC UA/AAS-based agent, and at what integration and runtime cost?

The five survey layers are a classification of sources. C0-C4 are context
conditions and G0-G4 are validator tiers; they are not those five layers.
Dataspace policy is outside the evaluated scope. Evidence sufficiency is not an
unconditional accuracy ceiling or proof of physical safety.

## Work register

| Work item | Required evidence | Initial status |
| --- | --- | --- |
| Contribution positioning | RAMI/AAS crosswalk, full five-layer survey and 24-technology AUF matrix | Included; specific comparator verification pending |
| Original benchmark | E1-E9, E4b, category/fault breakdowns, action spaces and budget figure | Restored from saved baseline JSON |
| GPT E11 evaluation | Original aggregate report and retained raw-response audit | Included with unresolved full-suite provenance mismatch |
| Equal-information validation | Procedural and SHACL checks over identical facts | Implemented and measured, synthetic only |
| Retrieval control | Crossed retrieval and context conditions; oracle diagnostic | Implemented and measured, synthetic only |
| Capability ablation | Leave-one-capability-out, including missing evidence | Implemented and measured, synthetic only |
| Syntax fidelity | One graph; round-trip isomorphism qualification | Implemented and measured, synthetic only |
| Independent evaluation | Held-out assets/episodes and engineer-reviewed labels | Pending external review |
| Physical case study | S7-1500, IPC, physical sensors and actuators | Not conducted |
| Transfer and maintenance | Configuration change and measured engineering effort | Not conducted |
| CausalTrace and RCA comparison | Verified source, artefact and common incident protocol | Source verification pending |
| AUF reliability and utility | Independent scorers and held-out capability selection | Not conducted |
| Ten-page manuscript | Expanded research-led draft and actual compiled PDF | Verified 10 pages including references; venue policy pending |

No physical measurements, independent assessments or literature-comparison
results may be inferred from the synthetic benchmark.

## Outputs

- `main.tex`: a research-led revision, with pending evidence explicitly marked.
- `main.pdf`: compiled ten-page manuscript, including references, 19 tables and two figures.
- `sections/`: compact standards, operational-method, original-results and hardware sections.
- `REVISION_PLAN.md`: contributions, dependencies, acceptance gates and page budget.
- `TESTBED.md`: proposed hardware architecture, commissioning and trial protocol.
- `results/`: outputs from the isolated revision experiment runner.
- `tables/`: generated revision tables, never hand-entered measurements.

The draft uses the existing `../paper/refs.bib` read-only. New RAMI/CausalTrace
citations await source verification; no fictitious references are inserted.

Run the new controls from the repository root:

```bash
.venv/Scripts/python.exe code/run_revision.py
.venv/Scripts/python.exe -m unittest discover -s code/tests -t code -k TestRevisionControls -v
```

In PowerShell, `./paper_revision/build.ps1 -Regen` regenerates the revision and
builds it if a LaTeX toolchain is installed. In a Bash shell use
`cd paper_revision && latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex`.

The build script also detects the official portable Tectonic installation at
`$env:LOCALAPPDATA/RoleOfSemanticsTools/tectonic/tectonic.exe`. An alternate executable
can be supplied with `-TectonicPath`. The compiler is outside the repository;
its cached TeX bundle may need network access on a new machine. Regeneration
includes original experiment tables and the raw E11 audit without model API calls.

R1 matches all 137 synthetic cases across equally informed implementations.
This is not evidence of engine superiority. R2/R3 count conversion evidence only
when both unit definitions are supplied, so they differ from the original
bookkeeping. R5 excludes non-isomorphic round trips from equal-information
comparisons; the installed Turtle serializer rounds some numeric literals.
There is no physical trial dataset yet. Future traces belong in
`protocol/trials.jsonl`, following the supplied record schema.

## E11 Provenance

The original generated E11 table reports `gpt-5.6-sol`, 35 tasks per condition,
three repeats and a date of 2026-10-06. Its full-suite aggregates are retained
in the paper, explicitly marked as currently unreconstructable. The only saved
JSON, including its committed historical version, has one task (`GRD-01`), one
repeat and five responses. It is a smoke test, not the full 525-response study.

`tables/e11_verified.tex` is generated from those five raw responses; the
source hash, metadata and count checks are in `results/archive_manifest.json`.
No second model archive, missing full-suite responses or physical data has been
invented. Resolve/recover the full run or conduct a separately dated new evaluation
before submission. A model deployment name is not independently verified lineage.

## Verification on 2026-10-08

The expanded PDF compiles with Tectonic 0.17.0 to exactly 10 pages, including
references, with no overfull boxes or unresolved citation/reference warnings.
Rendered pages were inspected; text lies within page bounds. The manuscript
passes all 51 unit tests and the complete `build.ps1 -Regen` workflow reproduces
the tables and PDF without GPT API calls. The compiler emits non-fatal font and
underfull-spacing diagnostics, but the rendered output was checked.
The manuscript
contains E1-E9/E4b, E11 with provenance qualification, R1-R5 and a detailed
S7-1500/IPC hardware evaluation design. Hardware trials, independent scoring,
live latency, maintenance effort and source-verified comparator evidence remain
pending. The requested ten-page target is verified; current journal policy is not.

Run the existing suite into isolated folders, if baseline regeneration is needed:

```bash
python code/run_experiments.py --results paper_revision/baseline_results --paper paper_revision/baseline
```

The revision must not claim superiority over an equally informed procedural
implementation unless an appropriate controlled experiment demonstrates it.
Matching accuracy is a valid outcome; portability and maintenance advantages
then require separate measurements.