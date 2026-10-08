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
| Contribution positioning | RAMI/AAS mapping and specific competing systems | Planned |
| Equal-information validation | Procedural and SHACL checks over identical facts | Implemented and measured, synthetic only |
| Retrieval control | Crossed retrieval and context conditions; oracle diagnostic | Implemented and measured, synthetic only |
| Capability ablation | Leave-one-capability-out, including missing evidence | Implemented and measured, synthetic only |
| Syntax fidelity | One graph; round-trip isomorphism qualification | Implemented and measured, synthetic only |
| Independent evaluation | Held-out assets/episodes and engineer-reviewed labels | Pending external review |
| Physical case study | S7-1500, IPC, physical sensors and actuators | Not conducted |
| Transfer and maintenance | Configuration change and measured engineering effort | Not conducted |
| CausalTrace and RCA comparison | Verified source, artefact and common incident protocol | Source verification pending |
| AUF reliability and utility | Independent scorers and held-out capability selection | Not conducted |
| Ten-page manuscript | Compact research-led draft; current venue rules and compiled PDF | Draft started, build/policy pending |

No physical measurements, independent assessments or literature-comparison
results may be inferred from the synthetic benchmark.

## Outputs

- `main.tex`: a research-led revision, with pending evidence explicitly marked.
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

R1 matches all 137 synthetic cases across equally informed implementations.
This is not evidence of engine superiority. R2/R3 count conversion evidence only
when both unit definitions are supplied, so they differ from the original
bookkeeping. R5 excludes non-isomorphic round trips from equal-information
comparisons; the installed Turtle serializer rounds some numeric literals.
There is no physical trial dataset yet. Future traces belong in
`protocol/trials.jsonl`, following the supplied record schema.

## Verification on 2026-10-07

All 49 existing and revision unit tests pass. The five revision controls run and
generate their JSON and LaTeX tables. New experiment files have no editor
diagnostics; the PowerShell build script parses and the trial schema is valid
JSON. A dependency deprecation warning from RDFLib's JSON-LD parser is present.

The PDF has not been compiled: no local LaTeX executable is available and the
Docker engine is not running. The current page count and journal policy are
therefore unverified. Hardware trials, independent scoring/labels, live latency,
maintenance effort and source-verified competitor comparisons remain pending.

Run the existing suite into isolated folders, if baseline regeneration is needed:

```bash
python code/run_experiments.py --results paper_revision/baseline_results --paper paper_revision/baseline
```

The revision must not claim superiority over an equally informed procedural
implementation unless an appropriate controlled experiment demonstrates it.
Matching accuracy is a valid outcome; portability and maintenance advantages
then require separate measurements.