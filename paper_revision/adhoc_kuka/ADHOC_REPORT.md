# KUKA OPC UA NodeSet Ad Hoc Projection Experiment

## Provenance and Scope

The user supplied `example.kuka.robot_raw.xml` as an IIH export mapped from a KUKA OPC UA server. This attribution is user-provided and was not independently checked against a live endpoint. The instance file SHA-256 is `b22cf92cb49ef263bf86a3da0fc7d8b7c865e13ee500ead418175afcd0340778`. Its NodeSet `LastModified` is `2021-05-03T02:00:35.3300125Z`; this is not an independently verified capture time.

The Robotics and DI companion NodeSets are parsed as model dependencies. Their definitions are not counted as observed robot instances. Embedded XML values are retained as exported; their live/historical measurement origin is unknown. No physical trial, agent answer-quality, control safety, latency, or IIH throughput claim is made.

## Structural Audit

The instance contains 90 nodes, 277 references, and 52 of 60 variables with embedded values. Companion definitions yield 564 unique expanded NodeIds. There are 0 unresolved model-namespace references and 838 references to external OPC UA core nodes not included in this three-file bundle.

The raw file declares a namespace URI that conflicts with its NamespaceUri metadata value (1 detected conflict). The parser also flags 6 custom DataType namespace-index conflicts where a matching numeric identifier exists in a different supplied model namespace. Inputs are preserved and not repaired.

## Projection Comparison

| Projection | Instance nodes/entities/rows | References or relationship elements | Expanded NodeId set matches |
|---|---:|---:|---|
| `canonical_json` | 90 | 277 | not applicable |
| `aas_v3_projection` | 90 | 277 | True |
| `rdf` | 90 | 277 | True |
| `ngsi_ld_snapshot` | 90 | 277 | True |
| `csv` | 90 | 277 | True |

These are structural retention checks, not official AAS or NGSI-LD schema validation. The AAS output is a loss-aware instance snapshot that stores source NodeSet attributes and XML metadata in submodel properties; it is not asserted to be an IDTA semantic profile. The NGSI-LD file is a snapshot mapping with a local OPC UA context, not a deployed broker publication.

## RDF Syntax Fidelity

| Syntax | Parsed triples | Serialized bytes | Isomorphic round trip |
|---|---:|---:|---|
| `turtle` | 2249 | 129362 | True |
| `nt` | 2249 | 343201 | True |
| `json-ld` | 2249 | 336179 | True |

## Reproduction

Run `code/run_kuka_case.py` with the three source NodeSet paths and a separate `--out` directory. Exact input files are copied to `source_nodesets/` and hashed. Original `artifacts/`, `results/` and core benchmark scores are not read or modified by this experiment.
