# The Role of Semantics and Contextualised Data in Enhancing AI Results

**A survey of semantic technologies in industrial automation and their usability
for large language models and AI agents — with a reproducible benchmark.**

This repository contains a research paper (LaTeX) and the artefact that produces
every number, table and figure in it. Nothing in the manuscript is hand-typed
from a spreadsheet: `python run_experiments.py` regenerates the results, the
LaTeX tables, the figures and the inline numeric macros.

---

## What the study asks

Industrial automation has spent three decades standardising machine-readable
meaning — OPC UA information models, the Asset Administration Shell, ECLASS,
AutomationML, MTP, PackML, ISA-95 — and the semantic web has supplied RDF, OWL,
SHACL, SPARQL, QUDT, SOSA/SSN and a shelf of domain ontologies. All of it was
built so that two *machines* could agree.

The question here is what it is worth to an *agent*:

> How much of what an LLM agent needs is already standardised, which pieces are
> missing, and what does each piece buy in measurable accuracy?

The paper answers with a ten-criterion **agent-usability framework** applied to
30+ technologies across five layers, and with seven experiments over a
reproducible reference plant.

## Headline results

| Measure | No semantics | Historian export | Typed model (OPC UA / AAS) | + ontology & units | Full stack |
|---|---|---|---|---|---|
| Entity grounding (top-1) | 0 % | 79 % | 95 % | 100 % | 100 % |
| ...of which *verifiable* | 0 % | **0 %** | 95 % | 100 % | 100 % |
| Task ceiling @6k tokens | 0 % | 0 % | 23 % | 51 % | 86 % |
| Guardrail recall | 0 % | 14 % | 68 % | 74 % | **100 %** |
| False alarms on legal actions | 0 % | 0 % | **7.5 %** | 0 % | 0 % |
| Legal write actions still allowed | 100 % | 100 % | **25 %** | 100 % | 100 % |

Four findings drive the paper:

* **A fully typed information model is a local optimum.** It is what most
  industrial AI programmes reach and stop at. It handles grounding, ranges and
  permissions; it cannot see interlock violations, illegal state transitions,
  stale evidence or unfaithful numbers — 26 % of the fault corpus, and the part
  that stops a plant.
* **Bigger context windows do not fix missing semantics.** Growing the budget
  32× moves the typed model's ceiling by 2.8 points. Aggregate questions are not
  a context problem at all: pushing them into SPARQL saved up to 69× the tokens
  and answered a question no window could hold.
* **Tag naming conventions are semantics that cannot be audited.** A resolver
  that decodes mnemonics grounds 95 % of mentions — nearly matching a typed
  model, and the reason ungrounded pipelines demo well. Across five real naming
  conventions it swings by 53 points, and on a post-merger plant whose mnemonics
  no longer describe the asset they name it resolves 37 % of mentions
  *confidently to the wrong tag*. Representations that state membership
  explicitly are invariant.
* **Richness is only expensive when projected badly.** At a fixed budget the
  full stack loses grounding tasks the leaner stack answers, because interlocks
  and event logs crowd out signal records. Routing on cues available before
  retrieval lifts the ceiling 86 % → 94 % and verifiable grounding 84 % → 100 %
  at identical token cost, with no category degrading.

## Layout

```
paper/                    LaTeX manuscript (IEEEtran, two-column IEEE format)
  main.tex                entry point; `journal` -> `conference` in the class
                          options switches submission style
  sections/               15 sections + 2 appendices
  refs.bib                standards and literature
  tables/  figures/       GENERATED — do not edit by hand
  generated_macros.tex    GENERATED — inline numbers used in the prose
code/
  run_experiments.py      the single reproduction entry point
  semantics_bench/
    plant.py              the declarative reference plant (17 assets, 73 signals)
    kg.py                 projection into RDF / AAS / OPC UA / WoT / NGSI-LD / CSV
    vocab.py              namespaces and the alignment ontology
    units.py              QUDT-shaped dimension vectors and affine conversions
    statemachine.py       PackML states, legal commands, reachability
    shapes.py             the SHACL shapes graph
    conditions.py         context conditions C0–C4, fact model, renderers
    naming.py             five tag naming schemes (E8) + restoring context manager
    retrieval.py          lexical vs. graph retrieval, entity resolution,
                          convention decoding, intent routing
    tasks.py              35-task suite with declared evidence requirements
    validation.py         137-action fault corpus, validator tiers G0–G4
    toolgen.py            action-space enumeration + tool-schema projection
    sparql_probe.py       query-vs-stuffing probes
    llm.py                optional adapter for a real model (not used for results)
    metrics.py  report.py
  tests/                  39 unit testsartifacts/                the plant serialised in all seven formats
results/results.json      every measurement in the paper
```

## Reproducing everything

```bash
python -m venv .venv
.venv/Scripts/activate          # Windows;  source .venv/bin/activate elsewhere
pip install -r requirements.txt

cd code
python run_experiments.py --dump-artifacts
python -m unittest discover -s tests -t .

cd ../paper
latexmk -pdf main.tex           # or: make    or: ./build.ps1
```

Deterministic, offline, no API key, no GPU. Runtime is under a minute; the
dominant cost is the SHACL pass over the action corpus.

## The reference plant

A two-line beverage bottling facility with utilities, generated from one
declarative specification and projected into seven representations. It is seeded
with the pathologies that break ungrounded agents:

* **22 homograph description strings** — five tags called "Outlet pressure",
  on different machines, on different lines;
* **mixed units** — Line 1 metric (`bar`, `degC`, `L/min`), Line 2 a 2016
  retrofit in `psi`, `degF`, `m3/h`, recipes always in `bar` and `mL`;
* **measurement/setpoint pairs** with near-identical descriptions, one read-only;
* **four interlocks** gating writes on conditions that appear nowhere in the tag
  list (pasteurisation units, PackML state, CIP in progress);
* **14 `feeds` relations** linking utilities to production units, none of them
  inferable from tag names.

The tag naming convention is itself a variable: `naming.py` re-tags the plant as
ISA-5.1 mnemonics, sequential I/O addresses, KKS designations, OEM browse paths,
or a post-merger plant whose mnemonics survive but no longer describe the asset
they are attached to — holding every description, relation, unit and value
constant.

## The experiments

| | What it measures |
|---|---|
| **E1** | Entity grounding under homograph pressure (top-1, verifiable top-1, MRR, distractors@5) |
| **E2** | Context sufficiency — is the required evidence even present? |
| **E3** | Token bill of the same plant in seven interchange formats |
| **E4** | Guardrail detection, diagnosis and false alarms over 137 proposed actions |
| **E5** | Admissible action space: bits removed, precision and recall of what remains |
| **E6** | The accuracy ceiling a perfect reader could reach, and a budget sweep |
| **E7** | SPARQL query execution vs. context stuffing |
| **E8** | Grounding under five tag naming conventions, with the baseline steelmanned by a mnemonic decoder |
| **E9** | Neighbourhood projection vs. intent-routed projection |

E6 is deliberately model-independent. Benchmarking one LLM would date the
results and would confound the representation with that model's priors; instead
we bound the problem from above. Any real model sits at or below the ceiling, so
a gap in the ceiling is a gap no prompting, fine-tuning or scaling can close.

E8 and E9 exist because the two obvious objections to the rest of the study —
*"tag names already carry the semantics"* and *"richer models just cost more
context than they are worth"* — are empirical claims, and both are testable here
rather than conceded in a limitations paragraph.

## Using the artefact as a library

Validate a proposed agent action with the full semantic stack — the check an
MCP server should run before executing anything:

```python
from semantics_bench.llm import validate_proposal

ok, violations = validate_proposal({
    "action": "write_setpoint",
    "tag": "L1_FIL_QIC0305_SP",
    "value": 330.0,
    "unit": "MilliL",
    "evidence_time": "2026-07-14T02:19:00Z",
})
# ok == False, violations == ['F-ILK']
# ILK-02: fill volume may only be changed while the filler is Idle, Held or
# Stopped — it is in Execute.
```

Generate the tool schema an agent should be given:

```python
from semantics_bench.toolgen import write_tool_schema
schema = write_tool_schema("C4", scope="L1")   # enums, ranges, accepted units,
                                               # interlock status, legal commands
```

Run the task suite against a real model:

```bash
export SEMBENCH_BACKEND=openai SEMBENCH_MODEL=... OPENAI_API_KEY=...
python -c "from semantics_bench import llm; print(llm.run_suite(llm.get_backend(), 'C4'))"
```

## Building the PDF without a local LaTeX installation

`paper/` uses the standard `IEEEtran` class and compiles unmodified on Overleaf (upload the folder, set `main.tex` as
the root document) or in the TeX Live Docker image:

```bash
docker run --rm -v "$PWD/paper:/w" -w /w texlive/texlive:latest latexmk -pdf main.tex
```

## Licence and citation

Code and text are released for research use. If you use the benchmark, please
cite the paper and note the plant configuration and token budget you used, since
the magnitudes (though not the ordering) depend on both.
