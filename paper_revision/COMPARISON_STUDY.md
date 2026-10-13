# Comparison Study: Original Paper vs. Revised Paper

## Executive Summary

The original paper is a broad **survey plus empirical evaluation**: it maps 24 industrial semantic technologies into five layers, defines the ten-criterion agent-usability framework (AUF), and evaluates a generated bottling-plant benchmark. The revision is a shorter, more cautious **industrial grounding evaluation**. It keeps the AUF, layer map and core benchmark results, makes the baseline comparison fairer, adds the author-reported IIH acquisition context and a separate KUKA NodeSet projection check, and narrows claims that the data does not support.

The main claim is substantially the same: **agents need explicit engineering evidence about identity, units, relations, behaviour, constraints and provenance to produce outputs that can be checked**. The revision adds an important qualification: the experiments do not show that SHACL or RDF is inherently better than an equally informed procedural implementation. On the equal-information action corpus, those validators perform identically.

## Side-by-Side

| Dimension | Original paper (`paper/`) | Revised paper (`paper_revision/`) |
|---|---|---|
| Main framing | Survey of industrial semantics and empirical evaluation for AI-agent grounding | Engineering semantics as evidence for industrial-agent grounding, with explicit controls on what the experiments establish |
| Primary contribution | Five-layer landscape, AUF, benchmark and design pattern | AUF and integration pattern retained; emphasis moves to evidence sufficiency, validator fairness and deployment boundaries |
| Standards coverage | Detailed technology-by-technology survey; 24 technologies; five layers L0-L4 | Retains the five-layer map and 24-technology AUF matrix, in substantially compressed form |
| Reference benchmark | Generated two-line bottling model: 17 assets, 73 signals, 35 tasks and 137 proposed actions | Same reference benchmark retained; authored faults/tasks are explicitly distinguished from acquired PLC data |
| Core experiments | E1-E9, plus E4b procedural baseline and E11 model check | Original E1-E9/E4b results retained; R1-R5 controls and separate KUKA structural case added |
| Validation comparison | G0-G4; original procedural baseline lacks the full behaviour/provenance facts available to G4 | R1 gives procedural and SHACL validators the same engineering facts and rules |
| Interpretation of sufficiency | Often called an “accuracy ceiling” | Renamed/qualified as declared-fact sufficiency; not an unconditional upper bound on model accuracy |
| Model evidence | Generated E11 aggregates report a full 35-task, three-repeat run | Preserves aggregates alongside a raw-data audit showing only five retained responses; does not treat them as fully corroborated |
| Hardware evidence | No physical process trial; experiments use the generated reference model | Adds reported IIH/PLC acquisition provenance and a KUKA NodeSet projection; still no closed-loop physical-process results |
| Length | Existing PDF in the workspace is 29 pages; source has 15 main sections and two appendices | Current `main_updated.pdf` is 10 pages including references; detail is retained in artifacts and companion documentation |

The PDF page counts above describe the PDF files currently present in the workspace. The LaTeX sources are authoritative if an older PDF is stale.

## Original Paper: Summary and Claims

The original manuscript begins with an industrial grounding failure: a natural-language request can match several similarly named tags, while unit, write-access, asset membership and current machine state decide which answer or action is valid. It then surveys identification and property dictionaries (L0), information/interface models (L1), formal semantics (L2), domain ontologies (L3), and dataspaces and policy (L4). AUF scores technologies against identity, types, units, relations, behaviour, constraints, provenance, queryability, context economy and deployability.

Its generated bottling-plant benchmark varies information conditions C0-C4 and validator tiers G0-G4. The original results emphasize improved grounding and evidence coverage as information is added; higher G4 fault detection than the flat catalogue; lower false alarms once unit conversion is modelled; reduced action spaces; query execution versus context stuffing; sensitivity to naming conventions; and intent-routed retrieval.

The original thesis is that a fully typed model is a local optimum: types and access do not, by themselves, supply unit calculus, plant topology, state-dependent legality, interlock guards or observation provenance. The practical design advice is to retrieve targeted facts, synthesize constrained tools and validate proposals before dispatch.

**Evidence boundary:** these are controlled results on an authored reference plant and injected action cases. They are not measurements of how often these faults occur in a particular factory, not a closed-loop PLC trial, and not evidence of physical safety. The original context conditions also change retrieval method between lexical and graph-based paths, so some effects mix representation and retrieval.

## Revised Paper: Summary and Changes

The revision retains the industrial motivation, five layers, AUF matrix and the principal E1-E9/E4b benchmark results. It adds the equal-information R1 validator comparison, R2 retrieval controls, R3 capability removals, R4 missing-evidence/state-change probes, and R5 RDF syntax round-trip checks. It also includes a compact, separate KUKA case derived from the supplied instance NodeSet and Robotics/DI companion models.

The most important interpretive changes are:

- **It separates information benefit from implementation benefit.** R1 compares full procedural validation with SHACL using the same facts. Both detect 84/84 injected faults, reject none of 53 legal cases, and have no raw-family disagreements. The benchmark therefore supports the value of explicit engineering facts, not superiority of SHACL over competent code.
- **It corrects the meaning of sufficiency.** Required-fact coverage is an operational measure defined by the benchmark’s task annotations. It is not a universal ceiling on what a model can answer; prior knowledge, conventions or alternative derivations can produce answers without all declared facts.
- **It makes the retrieval confound visible.** The original C0-C2 and C3-C4 paths use different retrieval strategies. R2 crosses supported strategies and contexts but still uses a fixed, hand-authored entity resolver and an unbudgeted oracle diagnostic. It narrows, but does not erase, all retrieval assumptions.
- **It separates the IIH acquisition from the original benchmark.** The author reports an IIH 2.6.1 / IPC427E path to an S7-1500 CPU 1518-4 PN/DP, with PLC-hosted test variables. The acquisition export and mapping to the stored generated plant have not been established. The revised paper correctly does not attribute the older benchmark or E11 run to this later capture.
- **It adds a KUKA format-preservation result, not a robot-control result.** The separate input bundle has 90 instance nodes and 277 references. The generated AAS, RDF, NGSI-LD and CSV projections retain the expanded instance NodeId set and reference count; Turtle, N-Triples and JSON-LD round-trip isomorphically. The source namespace metadata discrepancy and six datatype namespace-index conflicts are reported, not corrected. No external AAS/NGSI-LD schema conformance, live endpoint equivalence, agent task accuracy or physical robot operation was tested.

## E11: Important Provenance Difference

The original generated E11 table reports `gpt-5.6-sol`, 35 tasks per condition and three repeats, but the retained JSON contains only GRD-01 with one repeat in each of five conditions. The revised paper includes the reported aggregate table for transparency and a second table from the five auditable raw responses. The aggregates cannot be reconstructed from the available raw archive. The mock 525-row run validates the E11 pipeline only; it is not GPT data and is not included as model evidence.

This is a material limitation of the revised submission as currently archived. The text discloses it, but the full-suite E11 aggregates should not be presented as independently reproducible until the original raw file is recovered or the table is removed/replaced by a new, separately dated, fully archived run.

## Overall Assessment

The revision is **narrower and more defensible** than the original: it is clearer about what its synthetic/reference benchmark proves, includes a fair procedural baseline, acknowledges prior IIH Semantics work, and avoids implying that format transformation or validation alone establishes physical safety. It also adds an external engineering-model example without conflating that example with the generated bottling benchmark.

The revised paper’s central argument remains coherent without using IIH as its proof: the controlled benchmark tests how specified engineering facts support grounding and validation. IIH is relevant as acquisition/integration provenance and as a future route to validate the data path, but its current capture is not mapped to the benchmark. The KUKA NodeSet case is useful supplementary evidence for structural projection and format fidelity, not for the core agent-accuracy or physical-safety claims.

The current PDF is ten pages. Remaining caveats are not future-experiment promises; they delimit what is and is not claimed. The main unresolved documentary issue is E11’s aggregate/raw-data mismatch. Physical closed-loop performance is outside the results reported in this paper.
