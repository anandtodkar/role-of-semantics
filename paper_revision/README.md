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
| KUKA NodeSet ad hoc case | IIH-attributed instance NodeSet plus Robotics and DI companion models, projected to AAS/RDF/JSON-LD/NGSI-LD/CSV | Separate structural comparison under `adhoc_kuka/`; core benchmark unchanged |
| PLC/IIH acquisition | CPU 1518-4 PN/DP to IIH 2.6.1 on Industrial Edge IPC427E, 2026-10-08 | Author confirmed; exports and source/aggregate mapping pending |
| GPT E11 evaluation | Original aggregate report and retained raw-response audit | Original archive mismatch unresolved; live runner not configured |
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

## PLC Acquisition Provenance

The author confirms data collection on 2026-10-08 using Siemens Industrial
Information Hub (IIH) 2.6.1 on an Industrial Edge IPC427E. IIH connects as an
OPC UA client to the server on an S7-1500 CPU 1518-4 PN/DP and provides the
aggregation layer. Values came from PLC-hosted test variables, not physical
sensor I/O. The paper now describes a PLC/IIH snapshot
and cross-format projection workflow rather than calling the acquisition a
simulation. Authored tasks, injected faults and offline probes remain test cases.

The capture export is not attached. `protocol/acquisition_manifest.json` records
confirmed details and leaves missing firmware, capture time and source-file hash
unset. The downstream IIH extraction method and source-to-aggregate mapping also
remain unspecified; model/metadata equivalence and linkage to the stored
declarative benchmark still need verification. A PLC/IIH preservation audit is
specified in `TESTBED.md`; it is not a measured result.
Existing measurements have not been relabelled as results of this new capture:
in particular, E11 dated 2026-10-06 predates the 2026-10-08 acquisition.

## Final Validation Gates

The E11 runner was exercised offline with `--backend mock --repeats 3`: 525 rows,
105 per condition, are saved under
`results/e11_mock_pipeline_dryrun/`. This is only a pipeline/determinism check;
the mock answers from gold facts and is not a GPT evaluation. It is not included
in paper tables. No backend, endpoint, model or API configuration was available
in the current environment. Do not commit API secrets; configure them locally
and run a separately dated evaluation after confirming the exact model and cost.

Even with credentials, the existing E11 runner currently builds prompts from
the repository's `tasks.py` and offline generated reference context, not from
the newly acquired IIH snapshot. A valid follow-up must first attach and audit
the PLC/IIH exports, map their identifiers and facts into a versioned task/context
snapshot, then run and retain all raw model responses. It cannot repair the
missing raw data for the 2026-10-06 run.

No PLC endpoint or physical trial-capture path is configured in this workspace.
The only hardware fact currently supported here is the author-confirmed OPC UA
acquisition of PLC-hosted test variables via IIH. No closed-loop actuator trial,
operational latency distribution or physical process outcome has been measured.
Do not remove pending/hardware-status caveats or report these outcomes as
completed. Physical operation needs a local reviewed risk envelope, supervised
operator, commissioned PLC-side guards and raw paired observations from the rig.

## Outputs

- `main.tex`: a research-led revision, with pending evidence explicitly marked.
- `main.pdf`: compiled ten-page manuscript, including references, 19 tables and two figures.
- `main_updated.pdf`: latest verified ten-page build with the IIH chain and both new references; compiled separately because the open `main.pdf` was locked.
- `sections/`: compact standards, operational-method, original-results and hardware sections.
- `REVISION_PLAN.md`: contributions, dependencies, acceptance gates and page budget.
- `COMPARISON_STUDY.md`: source-based comparison of the original paper and revision, including claim/evidence differences.
- `TESTBED.md`: proposed hardware architecture, commissioning and trial protocol.
- `adhoc_kuka/`: separately attributed KUKA NodeSet inputs, provenance hashes, generated projections, structural comparison and report.
- `results/`: outputs from the isolated revision experiment runner.
- `tables/`: generated revision tables, never hand-entered measurements.

The draft uses `../paper/refs.bib` read-only plus local `refs.bib` for the new
IIH documentation and PHM framework citations. RAMI/CausalTrace source
verification remains pending; no fictitious references are inserted.

The KUKA files are retained byte-for-byte under `adhoc_kuka/source_nodesets/`;
`artifact_manifest.json` records input/output hashes and generator versions. The
generated `ADHOC_REPORT.md` describes counts, detected source inconsistencies,
RDF round-trip checks and limitations; `comparison.tex` is the generated summary
table referenced by the paper. The case is an ad hoc structural projection
experiment, not a physical KUKA trial and not part of E1-E11.

The case can be replayed from the bundled inputs without a OneDrive path:

```bash
python code/run_kuka_case.py \
    --instance paper_revision/adhoc_kuka/source_nodesets/example.kuka.robot_raw.xml \
    --robotics paper_revision/adhoc_kuka/source_nodesets/Opc.Ua.Robotics.NodeSet2.xml \
    --di paper_revision/adhoc_kuka/source_nodesets/Opc.Ua.Di.NodeSet2.xml \
    --out paper_revision/adhoc_kuka
```

## IIH References and Prior Work

- `siemensIIH26firststeps`: Siemens, *First steps: Industrial Information Hub*,
  Industrial Operations X Documentation, version 2.6. The supplied URL was visited
  on 2026-10-08 but returned "Unable to load document"; no unseen specification
  details are asserted. Documentation version 2.6 is distinct from the reported
  installed patch version 2.6.1.
- `todkar2025semanticitot`: Anand Todkar, Mrinmoy Sarkar and Jitendra Solanki,
  *Semantic Framework for IT-OT Integration in Industrial Environments*, Annual
  Conference of the PHM Society, 17(1), 2025, DOI
  `10.36001/phmconf.2025.v17i1.4551`. The landing page and eight-page PDF were
  checked. The paper explicitly discusses IIH Semantics and Siemens Industrial
  Edge deployment. The revision acknowledges this predecessor rather than
  claiming its OPC UA/RDF/SPARQL/GraphQL integration architecture as new.

`main_updated.tex` includes `main.tex` without duplicating manuscript content.
It provides an alternate compile target while Windows locks an open `main.pdf`.
Compile `main_updated.tex` with Tectonic, or close the open original PDF before
using the regular build script. Both new bibliography entries are verified in
the rendered `main_updated.pdf`, which has ten pages including references.

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
passes all 56 unit tests, including five KUKA NodeSet tests. The 10-page paper
includes a concise KUKA subsection; its detailed projection report is separate.
The compiler emits non-fatal font and
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