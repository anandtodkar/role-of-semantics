# Revision plan and submission gates

## Scope and claim discipline

Target a research-led industrial grounding paper. The five-layer standards map
and AUF support the intervention; neither is advertised as a new industrial
reference architecture or a new ontology. The original broad survey remains in
`../paper/` and can become supplementary material subject to journal rules.

Three proposed contributions, each requiring a distinct evidence gate:

| Contribution | Existing/new evidence | Remaining gate |
| --- | --- | --- |
| Agent-time capability assessment | Explicit U1-U10, failures and source crosswalk | Independent scoring and held-out AUF utility |
| Engineering-evidence integration | Retrieval, typed proposals, validation and dispatch recheck protocol | Working physical pipeline and latency |
| Controlled industrial evaluation | R1-R5 synthetic controls now implemented | Physical trials, independent labels, transfer effort |

The equal-information result is a tie, not an inconvenient result to discard.
R1 compares the same facts through competent code and SHACL. The old unit-only
procedural baseline is retained in the original paper but cannot establish
behavioural superiority over an equally informed program.

## All five rejection risks

| Risk | Work and deliverable | Acceptance criterion |
| --- | --- | --- |
| Incremental novelty | RAMI crosswalk, AAS/OPC UA profile inventory, AUF utility trial, R1 and transfer study | Every difference names a predecessor, decision enabled and supporting evidence |
| Industrial validation | Physical process on S7-1500 and IPCs, shadow trials, approved bounded execution | Hardware/software manifest, raw observations and independently reviewed episodes |
| Advanced-agent positioning | Verify CausalTrace and RCA metric source; common evidence/task protocol | Specific comparisons supported by sources; no guessed absences or unmatched leaderboard comparisons |
| Ten-page limit | Compact research-led main manuscript; original survey as supplement candidate | Compiled PDF meets verified current article rules, including references if required |
| Generic AI framing | Asset identity, units, commissioning, supervisory deadlines, IT/OT boundary and controller authority | Each claimed benefit connects to an industrial workload and measured deployment consequence |

## Implemented synthetic controls

- R1: full procedural vs full SHACL; raw family disagreement audit, gold-blind predictions,
  detection/diagnosis/FPR and descriptive Wilson intervals.
- R2: lexical/membership/graph retrieval under supported context conditions, three
  budgets, unbudgeted oracle-all diagnostic. No graph privilege is silently given
  to C2. Entity synonyms remain a shared manually authored assumption.
- R3: leave-one-capability-out context and procedural validator studies. Context
  ordering is fixed to full C4 and labelled diagnostic. Missing checking evidence
  yields abstention, not a counted detection. Context topology removes flow while
  validator topology removes scope containment; report separately.
- R4: synthetic missing state, missing/unknown unit, malformed timestamp, missing
  observation and dispatch-time state-change probes. This is not a PLC execution test.
- R5: syntax cost on one graph, qualified by graph isomorphism. Measured Turtle
  rounding is visible and excluded from equal-information comparisons.

Conversion bookkeeping in the revision requires both unit definitions in the
context. Consequently these results are not numerically interchangeable with
the original tables. R2/R3 are evidence measures, not actual LLM accuracy.

## Remaining experiment protocols

| ID | Experiment | Protocol and outputs | Dependency |
| --- | --- | --- | --- |
| P1 | Physical grounding/reporting | Independently written questions, physical observations, unit/value/source/time scoring | Commissioned sensors and reviewed task set |
| P2 | Physical legal task completion | Shadow proposals, then approved bounded legal commands; separate gateway and PLC rejection | Risk assessment and controller handshake |
| P3 | State/freshness robustness | State change between plan and dispatch, stale subscriptions, reconnect, mapping version change | Timestamped independent trace |
| P4 | Transfer/maintenance | Freeze methods; hold out station B/configuration; measure engineer-hours, edits and regressions | Mapping/rule freeze and engineer log |
| P5 | RCA comparator | Verify CausalTrace source/code; matched incidents, evidence and candidate causes; MAP@3 only if appropriate | Real reviewed incident corpus and comparator |
| P6 | AUF reliability | Two independent raters, versioned spec-clause evidence, ordinal agreement and adjudication | Domain experts and source registry |
| P7 | AUF utility | Budget-matched AUF-guided vs normal capability selection on held-out configuration | Independent teams or counterbalanced assignment |
| P8 | Cross-model agent evaluation | At least two available model families; frozen prompts/tools, repeats within episodes | Model access, privacy and cost approval |
| P9 | Real token/runtime cost | Real model tokenizer; retrieval/validation/dispatch p50/p95 and deadline misses | Selected runtime and commissioned hardware |

Do not invent measurements for these protocols. Archived E11 is a model run on
synthetic context, not physical industrial validation. No LLM credentials or PLC
endpoint are needed by `run_revision.py`.

## Baselines and control variables

Evaluate a practical typed OPC UA/AAS agent, an equally informed structured-record
agent, a full procedural validator, the declarative semantic integration, and a
relevant specialised comparator where its task applies. Do not handicap the
practical baseline by deleting behaviour it actually exposes. Use the same model,
task, observation snapshot, authorization and operator approval policy within
each matched comparison. Distinguish three axes: available facts, retrieval and
representation/engine. Frozen decoder schemas and model tool support must also
be documented; enumerate constraints only if the selected decoder enforces them.

## Statistical and annotation protocol

Predeclare legal task completion and invalid proposal admission as primary
outcomes; set operational thresholds with the commissioning engineer. Select
episode counts using a pilot and desired confidence widths, not a target result.
For illustration, zero events in 300 independent trials still gives an approximate
95% one-sided upper risk bound of 1%; correlated repeats do not satisfy that
assumption. For clustered data use episode-level intervals or cluster bootstrap.
Report per-fault and per-workflow counts, uncertainty and paired differences.
Do not extrapolate the synthetic fault mix to plant incident frequencies.

Separate task author, gold-label reviewer and implementation owner where feasible.
Freeze labels and splits before running models. Score identity, native-unit value,
tolerance, evidence source/time, command legality and process outcome separately.
Define RCA candidate causes and handling of multi-cause incidents before ranking.
Document manual corrections rather than silently changing labels after results.

## Literature/source register to resolve

- RAMI 4.0: obtain the exact normative/reference edition and validate the
  conceptual crosswalk with a domain reviewer.
- OPC UA and AAS: document selected profiles and the facts actually published,
  versus extension capability; cite relevant clauses and versions.
- CausalTrace: exact title/authors/DOI or repository needed. No inferred algorithm,
  feature matrix or bibliographic placeholder is presented as a verified source.
- 94% MAP@3: exact paper, dataset, evaluation split, cause-ranking definition,
  available inputs and whether physical validation was used.
- TII: confirm article category, length/overlength policy, supplementary material
  rules and reference accounting at submission time. Ten pages is a design target,
  not a policy checked in this workspace.
- Dataspaces: policies need trusted enforcement; do not claim confidentiality
  retention or physical safety follows merely from an ODRL annotation.

## Page budget

| Material | Target pages |
| --- | ---: |
| Abstract, introduction, three contributions | 1.0 |
| Specific related work and standards positioning | 0.8 |
| Framework and operational method | 1.5 |
| Protocol and physical testbed | 1.5 |
| Main comparisons and ablations | 2.5 |
| Deployment implications and limitations | 0.7 |
| Conclusion | 0.2 |
| References | 1.3 |
| Layout contingency | 0.5 |
| Total | 10.0 |

The expanded draft now compiles to ten pages including references. It restores
all original experiment groups, the 24-technology matrix, R1-R5 and a detailed
hardware protocol, without shrinking the IEEE 10pt text or altering margins.
Physical results remain pending and must replace protocol/discussion space
rather than silently increasing the page count. The E11 generated full-suite
summary does not match the retained five-response smoke archive and must be
reconciled before submission.
Keep the architecture, testbed, decisive comparisons and uncertainty in the
main paper. Move full matrices, scoring evidence, raw cases, alternate formats,
secondary budget sweeps and reproduction detail to allowed supplements.

## Sequence and owners

1. Week 1: lead author + OT owner confirm equipment/access, venue rules and
   competitors; freeze the contribution/evidence map.
2. Weeks 2-3: benchmark owner + independent engineer review tasks, baselines,
   labels, splits and pilot statistical requirements.
3. Weeks 3-6: OT owner commissions the rig; evaluation owner collects shadow,
   approved bounded and transfer trials. Timeline depends on approvals.
4. Weeks 6-7: lead author replaces pending sections with measured evidence and
   source-verified comparisons; regenerate all reported numbers.
5. Week 8: independent reviewer checks claims, baseline fairness, replay,
   reproducibility and final compiled page count.

## Submission decision

Do not submit this draft as a validated physical deployment. Proceed with the
research-led TII framing after independent evaluation, source verification,
runtime measurements, reconciled E11 provenance and real hardware/process evidence. If only a PLC simulated
process is available, state that boundary and reconsider claims or venue. A tie
against equally informed code leaves reuse and maintenance as hypotheses until
P4 measures them.