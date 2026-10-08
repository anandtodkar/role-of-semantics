# Proposed S7-1500 / IPC industrial grounding testbed

## Recommendation

Build a two-station guarded 24 V handling cell, optionally augmented with a
low-head water-filling module. Use real sensors and actuators, not just a PLC
program generating synthetic values. This is manageable with the available
controllers/industrial PCs and exercises actual identity, units, state, guards,
communication faults and physical outcomes without needing a complete bottling line.

Start with the handling cell if process instrumentation is unavailable. Add the
water module for measured volume/flow and unit-conversion tasks. Do not use a
pressurized process or thermal/heater rig solely to reproduce the simulated
plant's pressure and temperature examples. Selection and commissioning require
a competent engineer's local risk assessment.

## Roles for available hardware

| Hardware | Recommended role | Verify before commitment |
| --- | --- | --- |
| S7-1500 | Deterministic sequencing, state, operating guards, output authority and command acknowledgements | CPU order number, firmware, TIA version, OPC UA server capability/license, I/O |
| IPC427E | Agent gateway, local graph/SHACL, procedural baseline, experiment supervisor and historian | CPU/RAM/SSD/OS, network interfaces, software/runtime compatibility |
| IPC227G | Optional acquisition/gateway or separate disturbance/replay service | Exact model/order number, compute/storage, OS, NICs; do not assume its specifications |
| Additional PLC, if available | Held-out station B or independent transfer configuration | Matching engineering access, I/O and commissioning approval |

Use cloud or another suitable machine for the LLM if the IPC lacks inference
resources. The IPC remains the industrial service host. Local execution of a
large model is not presumed, nor is a standard S7-1500 presumed an F-CPU.

## Logical architecture

```text
Operator approval / reviewed task manifest
                 |
Agent and benchmark supervisor (IPC427E)
    |          |            |
Typed records  RDF/SHACL    Full procedural baseline
    |          |            |
    +---- evidence service / audit logger ----+
                         |
     allowlisted command mailbox / OPC UA adapter
                         |
S7-1500: state + live guards + command acknowledgement
                         |
Guarded 24 V handling stations / optional water module
                         |
Independent observation and outcome log

IPC227G: optional read gateway or controlled replay/disturbance service
```

OPC UA availability and supported security modes must be checked for the exact
CPU/firmware. If unavailable, choose a supported, documented gateway and record
it as part of the integration; do not assume direct OPC UA access exists.
Put OT on an isolated lab network with controlled access. Provision certificates
and accounts through normal engineering procedures; do not place secrets in logs.
Give the agent no controller-programming, unrestricted memory or raw-output access.

## Physical rig and additional equipment

| Component | Minimum purpose |
| --- | --- |
| Two small guarded low-voltage conveyors/indexing stations | Repeated descriptions and independently addressable equipment |
| Photoelectric/proximity sensors and physical counters | Actual presence, transfer and cycle observations |
| Speed feedback/encoder if speed-control tasks are included | Confirm requested vs actual motion, not merely written settings |
| Rated power supply, protected wiring and compatible DI/DO modules | Commissioned field I/O; confirm load ratings and isolation |
| Operator stop, local enabling controls and suitable independent protection | Engineer-assessed safe operation; protection not entrusted to the agent |
| Optional reservoir, low-head pump, valve and catch vessel | Actual bounded filling operation, spill containment and electrical separation |
| Optional level switches, flow sensor or weighing scale/load cell | Measure overfill protection and delivered volume/mass with uncertainty |
| Compatible AI modules or sensor gateway, where required | Capture actual analogue quantities and quality/status |

Final bill of materials and protection depend on existing trainers, I/O modules
and lab approvals. Calibrate sensors; record resolution, tolerances, sampling
rates and actual unit conventions. Do not fabricate mixed units at the sensor:
declare software projections as metadata treatments when the physical source is shared.

## Controller interface to commission

Publish stable asset identity, current state, sensor values, timestamps/quality,
writable supervisory setpoints, engineering bounds and acknowledged commands.
Use separate namespaces/objects for StationA and StationB with deliberately
similar DisplayNames, but unique identifiers. Record source NodeIds and semantic
mapping versions. PackML-style states may be implemented for the demonstrator,
but claim PackML conformance only after checking the actual state/transition profile.

Do not let an agent write outputs directly. A bounded supervisory command
mailbox should contain command ID, target, opcode, native-unit value, approval
reference and expiry/state-version reference as supported by the design. The
PLC checks current guards, request validity and allowed states in its own scan,
then records accepted/rejected, reason, execution result and acknowledgement ID.
Do not rely on a multi-field OPC UA write being atomic: use a staged mailbox with
a sequence/commit handshake and PLC-side consistent snapshot. Design duplicate
handling/idempotency and reconnect behaviour before enabling physical writes.

PLC interlocks and a suitable stop/protection system remain authoritative.
Failure of the agent, graph, IPC, network or acknowledgement must not permit
uncontrolled actuation. Commission this behaviour without an LLM first.

## Suggested signal/task inventory

| Capability | Actual testbed example | Observable outcome |
| --- | --- | --- |
| Identity/access | Both stations show "Belt speed"; PV vs SP distinction | Correct NodeId, no PV write |
| Units | Report one physical flow measurement in L/min or m3/h; mL vs L recipe | Correct conversion with declared definitions and tolerance |
| Topology/scope | Station A feeds B; B unavailable; authorisation limited to A | Correct dependency explanation and no cross-station request |
| Behaviour | Start/Reset/Hold proposals in different reviewed states | Matching controller legality and acknowledgements |
| Constraints | Filling only with vessel present and permitted level/guard state | Gateway decision; PLC guard decision logged separately |
| Provenance | Delayed subscription, invalid quality, missing observation | Refresh/abstention rather than invented current value |
| Dispatch race | Operator changes state after proposal, before commit | Current-state rejection in dispatcher/PLC |
| Incident diagnosis | Vessel absent, sensor outage or downstream blocked episode | Independently recorded cause, cited evidence and ranked candidates |

RCA needs an actual causal incident definition. A retrieved alarm description is
not causal inference. Inject only disturbances approved as safe; use replay for
unsafe conditions and identify those episodes as replay, not physical incidents.

## Commissioning and collection sequence

1. Inventory CPU/firmware/licenses, IPCs, I/O and existing trainers. Approve risk
   assessment, guarding, wiring and permitted operating envelope.
2. Commission manual/controller-only operation and stop/protection behaviour.
   Verify command mailbox semantics, duplication and expiry without an agent.
3. Verify OPC UA read-only acquisition, timestamps, quality and asset mappings.
   Log observation age; configure freshness for this supervisory workload.
4. Freeze an engineer-reviewed task list, legal cases and incident causes. Split
   by station or independently scheduled operating episodes before model runs.
5. Run paired baselines in read-only shadow mode over the same live snapshots.
   Never execute a known-invalid proposal just to demonstrate rejection.
6. Enable only approved legal bounded actions. Capture proposal, validation,
   dispatch revalidation, controller acceptance and actual sensor outcome.
7. Run approved state/freshness/reconnect probes. If no safe physical condition
   exists, replay evidence and label it explicitly.
8. Hold out StationB or a configuration change. Track engineer-hours, mappings,
   rule/code edits, regression tests and total recommissioning effort.

## Matched baselines and measurement

Use the same model, prompts, sensor snapshots, authorization, operator policy and
task set when comparing equally informed procedural and semantic integrations.
Keep a realistic typed OPC UA/AAS baseline rather than assuming all models expose
only ranges. Freeze versions and model access dates. Multi-model repetitions
are grouped by operating episode; question paraphrases do not create independent
industrial validation samples.

Record grounded-answer correctness, evidence correctness, admitted invalid
proposals, rejected legal proposals, abstention and full legal task completion.
Separate gateway rejection from controller rejection and actual plant outcome.
Log p50/p95 retrieval/validation/dispatch/end-to-end latency, deadline misses,
observation age, real tokenizer counts, API cost and integration effort. Agree
supervisory deadlines with the engineer instead of asserting millisecond control.
For RCA use MAP@3 only when the candidate-cause protocol supports it; never
compare to an unrelated published percentage as if it were the same experiment.

## Trial record

Use `protocol/trial_record.schema.json` to define exported records. Future
`protocol/trials.jsonl` is a collection destination, not an existing dataset.
Create it only when real traces exist. Include episode/method/asset/configuration IDs,
input snapshot and task/label provenance; record units, source/quality, times,
proposal, gateway and PLC decisions, approval, actual outcome and operator notes.
Use monotonic elapsed durations within each process and synchronized UTC for
cross-device correlation; record clock uncertainty rather than assuming it away.

Use distinct `physical`, `hardware_in_loop` and `replay` provenance values. No
physical findings can be generated by the offline revision runner. Raw traces
must be privacy/security reviewed before release.

## What is needed from the lab next

- Exact S7-1500 CPU order number, firmware and TIA Portal version.
- OPC UA server availability/license and supported security configuration.
- Existing DI/DO/AI modules, sensors, actuators, trainer/conveyor/process rig.
- IPC227G/IPC427E order numbers, RAM, OS and available network interfaces.
- Lab access, independent engineer and permitted physical operating envelope.

Choose an existing commissioned trainer if one is available; reuse reduces
commissioning effort and gives stronger validation than a rushed bespoke rig.