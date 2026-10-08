"""Isolated revision controls; no PLC connection or model API calls."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from math import isfinite
from typing import Any

from . import conditions as C
from . import kg as KG
from . import plant as P
from . import retrieval as R
from . import statemachine as SM
from . import tasks as TK
from . import units as U
from . import validation as V
from .metrics import coverage, score_binary, surrogate_tokens, wilson_interval

CAPABILITIES = frozenset({"units", "topology", "behaviour", "constraints", "provenance"})
REMOVED_KINDS = {
    "units": {"dim", "conv"},
    "topology": {"feeds"},
    "behaviour": {"state", "legalcmd"},
    "constraints": {"interlock"},
    "provenance": {"time", "event"},
}


@dataclass
class Snapshot:
    signals: dict[str, P.Signal]
    assets: dict[str, P.Asset]
    interlocks: list[dict[str, Any]]
    observations: dict[str, float]
    unit_names: set[str]
    freshness_cutoff: datetime

    @classmethod
    def reference(cls) -> Snapshot:
        return cls(
            signals={signal.tag: signal for signal in P.ALL_SIGNALS},
            assets=dict(P.ASSETS_BY_ID),
            interlocks=[dict(interlock) for interlock in P.INTERLOCKS],
            observations={signal.tag: signal.sample_value for signal in P.ALL_SIGNALS
                          if signal.sample_value is not None},
            unit_names=set(U.BY_IRI),
            freshness_cutoff=datetime.fromisoformat("2026-07-14T02:05:00+00:00"),
        )


@dataclass
class Verdict:
    faults: set[str] = field(default_factory=set)
    missing: set[str] = field(default_factory=set)

    @property
    def disposition(self) -> str:
        if self.faults:
            return "reject"
        return "abstain" if self.missing else "accept"


def _contained(owner: str, scope: str, snapshot: Snapshot) -> bool:
    visited: set[str] = set()
    while owner not in visited:
        if owner == scope:
            return True
        visited.add(owner)
        asset = snapshot.assets.get(owner)
        if asset is None or asset.parent is None:
            return False
        owner = asset.parent
    return False


def _command(payload: dict, snapshot: Snapshot, capabilities: frozenset[str],
             verdict: Verdict) -> None:
    asset = snapshot.assets.get(payload.get("asset", ""))
    if asset is None or not asset.packml_capable:
        verdict.faults.add("F-REF")
    elif "behaviour" not in capabilities or asset.packml_state is None:
        verdict.missing.add("behaviour")
    elif payload.get("command") not in SM.legal_commands(asset.packml_state):
        verdict.faults.add("F-STATE")


def _native_value(payload: dict, signal: P.Signal, snapshot: Snapshot,
                  capabilities: frozenset[str], verdict: Verdict) -> float | None:
    value, unit = payload.get("value"), payload.get("unit")
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not isfinite(value):
        verdict.faults.add("F-CARD")
        return None
    if unit is None:
        return None
    if "units" not in capabilities or unit not in snapshot.unit_names \
            or signal.unit not in snapshot.unit_names:
        verdict.missing.add("units")
        return None
    try:
        return U.convert(float(value), unit, signal.unit)
    except U.DimensionError:
        verdict.faults.add("F-DIM")
        return None


def _answer(signal: P.Signal, native: float | None, snapshot: Snapshot,
            capabilities: frozenset[str], verdict: Verdict) -> None:
    if "provenance" not in capabilities or signal.tag not in snapshot.observations:
        verdict.missing.add("provenance")
    elif native is not None:
        observed = snapshot.observations[signal.tag]
        if abs(native - observed) > 0.01 * abs(observed) + 1e-9:
            verdict.faults.add("F-VALUE")


def _state_guard(interlock: dict, snapshot: Snapshot, capabilities: frozenset[str],
                 verdict: Verdict) -> None:
    asset = snapshot.assets.get(P.SIGNAL_OWNER[str(interlock["guard_tag"])])
    if "behaviour" not in capabilities or asset is None or asset.packml_state is None:
        verdict.missing.add("guard_state")
        return
    listed = asset.packml_state in interlock["threshold"]
    if (interlock["operator"] == "state_in" and not listed) \
            or (interlock["operator"] == "state_not_in" and listed):
        verdict.faults.add("F-ILK")


def _numeric_guard(interlock: dict, snapshot: Snapshot, capabilities: frozenset[str],
                   verdict: Verdict) -> None:
    guard_tag = str(interlock["guard_tag"])
    if "provenance" not in capabilities or guard_tag not in snapshot.observations:
        verdict.missing.add("guard_observation")
    elif snapshot.observations[guard_tag] < float(interlock["threshold"]):
        verdict.faults.add("F-ILK")


def _interlocks(signal: P.Signal, snapshot: Snapshot, capabilities: frozenset[str],
                verdict: Verdict) -> None:
    if "constraints" not in capabilities:
        verdict.missing.add("constraints")
        return
    for interlock in snapshot.interlocks:
        if interlock["tag"] != signal.tag:
            continue
        if interlock["operator"] == ">=":
            _numeric_guard(interlock, snapshot, capabilities, verdict)
        elif interlock["operator"] in ("state_in", "state_not_in"):
            _state_guard(interlock, snapshot, capabilities, verdict)
        else:
            verdict.missing.add("guard_operator")


def _freshness(payload: dict, snapshot: Snapshot, capabilities: frozenset[str],
               verdict: Verdict) -> None:
    if "evidence_time" not in payload:
        return
    if "provenance" not in capabilities:
        verdict.missing.add("provenance")
        return
    try:
        evidence_time = datetime.fromisoformat(payload["evidence_time"].replace("Z", "+00:00"))
        if evidence_time.tzinfo is None:
            raise ValueError("timezone required")
        if evidence_time < snapshot.freshness_cutoff:
            verdict.faults.add("F-STALE")
    except (ValueError, TypeError, AttributeError):
        verdict.missing.add("evidence_time")


def _write(payload: dict, signal: P.Signal, native: float | None, snapshot: Snapshot,
           capabilities: frozenset[str], verdict: Verdict) -> None:
    if signal.access == "r":
        verdict.faults.add("F-ACC")
    if native is not None and not signal.eng_low <= native <= signal.eng_high:
        verdict.faults.add("F-RANGE")
    scope = payload.get("scope")
    if scope is not None:
        if "topology" not in capabilities:
            verdict.missing.add("topology")
        elif not _contained(P.SIGNAL_OWNER[signal.tag], scope, snapshot):
            verdict.faults.add("F-SCOPE")
    _interlocks(signal, snapshot, capabilities, verdict)
    _freshness(payload, snapshot, capabilities, verdict)


def validate_procedural(case: V.Case, snapshot: Snapshot,
                        capabilities: frozenset[str] = CAPABILITIES) -> Verdict:
    """Check shared facts without gold labels; abstain on required missing evidence.

    This synthetic control uses the reference SHACL cutoff and tolerance. It is
    not a production gateway or a substitute for PLC-side validation.
    """
    verdict = Verdict(faults=V.tier_g1(case))
    if case.kind == "command":
        _command(case.payload, snapshot, capabilities, verdict)
        return verdict
    signal = snapshot.signals.get(case.payload.get("tag", ""))
    if signal is None:
        verdict.faults.add("F-REF")
        return verdict
    native = _native_value(case.payload, signal, snapshot, capabilities, verdict)
    if case.kind == "answer":
        _answer(signal, native, snapshot, capabilities, verdict)
    else:
        _write(case.payload, signal, native, snapshot, capabilities, verdict)
    return verdict


def _validator_summary(name: str, cases: list[V.Case], verdicts: list[Verdict]) -> dict:
    score = score_binary([(case.gold != V.VALID, verdict.disposition == "reject")
                          for case, verdict in zip(cases, verdicts)])
    diagnosed = sum(("F-RANGE" if case.gold == "F-UNITSCALE" else case.gold) in verdict.faults
                    for case, verdict in zip(cases, verdicts) if case.gold != V.VALID)
    return {
        "validator": name, "n": len(cases), "tp": score.tp, "fp": score.fp,
        "fn": score.fn, "tn": score.tn, "recall": score.recall,
        "false_positive_rate": score.false_positive_rate,
        "diagnosis_rate": diagnosed / (score.tp + score.fn),
        "abstentions": sum(verdict.disposition == "abstain" for verdict in verdicts),
        "recall_interval": wilson_interval(score.tp, score.tp + score.fn),
        "false_positive_interval": wilson_interval(score.fp, score.fp + score.tn),
    }


def equal_information_validation() -> dict:
    cases = V.build_corpus()
    snapshot = Snapshot.reference()
    shacl_map, seconds = V.run_shacl(cases)
    procedural = [validate_procedural(case, snapshot) for case in cases]
    shacl = [Verdict(faults=shacl_map.get(case.cid, set())) for case in cases]
    return {
        "summary": [_validator_summary("procedural_full", cases, procedural),
                    _validator_summary("shacl_full", cases, shacl)],
        "shacl_batch_seconds": seconds,
        "disagreements": [{"case": case.cid, "gold": case.gold,
                           "procedural": sorted(first.faults), "shacl": sorted(second.faults)}
                          for case, first, second in zip(cases, procedural, shacl)
                          if first.faults != second.faults],
        "cases": [{"case": case.cid, "kind": case.kind, "gold": case.gold,
                   "payload": case.payload, "procedural": sorted(first.faults),
                   "shacl": sorted(second.faults)}
                  for case, first, second in zip(cases, procedural, shacl)],
        "limitation": "Shared synthetic facts and rules; not an independent industrial validation.",
    }


def audited_context(elements: list[C.Element], condition: C.Condition,
                    budget: int | None) -> tuple[str, set[str], int]:
    text, facts, tokens = C.build_context(elements, condition, budget)
    declared_units = {unit for unit in U.BY_IRI if f"unit:{unit} a qudt:Unit ;" in text}
    audited = set()
    for fact_key in facts:
        kind, parts = fact_key.split(":", 1)
        if kind == "conv" and not set(parts.split("|")) <= declared_units:
            continue
        audited.add(fact_key)
    return text, audited, tokens


def _elements(question: str, condition: C.Condition, strategy: str) -> list[C.Element]:
    if strategy == "oracle_all":
        return list(C.ELEMENTS)
    if strategy == "lexical":
        return [element for element, _score in R.lexical_for(condition).rank(question)]
    if strategy == "membership":
        seeds = R.resolve_entities(question).asset_ids
        eligible = [element for element in C.ELEMENTS
                    if element.eid in seeds or (element.etype == "signal"
                       and P.SIGNAL_OWNER[element.eid] in seeds)]
        if not eligible:
            return _elements(question, condition, "lexical")
        eligible_ids = {element.eid for element in eligible}
        ranked = _elements(question, condition, "lexical")
        return ([element for element in ranked if element.eid in eligible_ids]
                + [element for element in eligible if element not in ranked])
    if strategy == "graph":
        return R.retrieve(question, condition, 200, routed=True)
    raise ValueError(f"Unknown strategy: {strategy}")


def _retrieval_rows(condition: C.Condition, strategy: str, budget: int | None) -> list[dict]:
    rows = []
    for task in TK.TASKS:
        _text, facts, tokens = audited_context(
            _elements(task.question, condition, strategy), condition, budget)
        required = set(task.required)
        rows.append({"task": task.tid, "category": task.category,
                     "condition": condition.key, "strategy": strategy,
                     "budget": budget, "tokens": tokens,
                     "coverage": coverage(required, facts),
                     "sufficient": required <= facts,
                     "missing": sorted(required - facts),
                     "diagnostic_only": strategy == "oracle_all"})
    return rows


def retrieval_controls(budgets: tuple[int, ...] = (1500, 6000, 24000)) -> list[dict]:
    rows = []
    for condition in C.CONDITIONS:
        strategies = ["lexical", "oracle_all"]
        if condition.can("sig_of"):
            strategies.append("membership")
        if condition.can("feeds"):
            strategies.append("graph")
        for strategy in strategies:
            for budget in ((None,) if strategy == "oracle_all" else budgets):
                rows.extend(_retrieval_rows(condition, strategy, budget))
    return rows


def capability_ablation(budget: int = 6000) -> dict:
    context_rows = []
    for removed in ("none", *sorted(CAPABILITIES)):
        kinds = C.BY_KEY["C4"].kinds - REMOVED_KINDS.get(removed, set())
        condition = replace(C.BY_KEY["C4"], kinds=frozenset(kinds))
        for task in TK.TASKS:
            elements = _elements(task.question, C.BY_KEY["C4"], "graph")
            _text, facts, tokens = audited_context(elements, condition, budget)
            required = set(task.required)
            context_rows.append({"removed": removed, "task": task.tid,
                                 "category": task.category, "tokens": tokens,
                                 "coverage": coverage(required, facts),
                                 "sufficient": required <= facts})
    cases = V.build_corpus()
    snapshot = Snapshot.reference()
    validator_rows = []
    for removed in ("none", *sorted(CAPABILITIES)):
        capabilities = CAPABILITIES - {removed}
        verdicts = [validate_procedural(case, snapshot, capabilities) for case in cases]
        row = _validator_summary(removed, cases, verdicts)
        row["valid_abstentions"] = sum(case.gold == V.VALID and verdict.disposition == "abstain"
                                       for case, verdict in zip(cases, verdicts))
        row["faulty_accepted"] = sum(case.gold != V.VALID and verdict.disposition == "accept"
                                    for case, verdict in zip(cases, verdicts))
        validator_rows.append(row)
    return {"contexts": context_rows, "validators": validator_rows,
            "limitation": "Context ordering fixed to full C4 as a diagnostic; validator abstention is not detection."}


def degradation_probes() -> list[dict]:
    tag = "L1_FIL_QIC0305_SP"
    case = V.Case("dispatch", "write", V.VALID,
                  {"tag": tag, "value": 330.0, "unit": "MilliL"})
    probes = []
    for name in ("before_state_change", "after_state_change", "missing_state",
                 "missing_unit", "unknown_unit", "malformed_time", "missing_observation"):
        snapshot = Snapshot.reference()
        payload = dict(case.payload)
        if name in ("before_state_change", "missing_state"):
            snapshot.assets["L1-FIL"] = replace(snapshot.assets["L1-FIL"],
                                                packml_state="Idle" if name == "before_state_change" else None)
        elif name == "missing_unit":
            snapshot.unit_names.remove("MilliL")
        elif name == "unknown_unit":
            payload["unit"] = "UNDECLARED"
        elif name == "malformed_time":
            payload["evidence_time"] = "not-a-time"
        elif name == "missing_observation":
            case = V.Case("observation", "answer", V.VALID,
                          {"tag": "L1_FIL_PT0301_PV", "value": 3.0, "unit": "BAR"})
            payload = dict(case.payload)
            snapshot.observations.pop(payload["tag"])
        verdict = validate_procedural(replace(case, payload=payload), snapshot)
        probes.append({"probe": name, "disposition": verdict.disposition,
                       "faults": sorted(verdict.faults), "missing": sorted(verdict.missing),
                       "synthetic": True})
    return probes


def equal_information_serialisation() -> list[dict]:
    from rdflib import Graph
    from rdflib.compare import graph_diff, isomorphic, to_isomorphic

    source = KG.build_graph()
    rows = []
    for syntax in ("turtle", "nt", "json-ld"):
        text = source.serialize(format=syntax)
        reconstructed = Graph().parse(data=text, format=syntax)
        equivalent = isomorphic(source, reconstructed)
        _common, missing, added = graph_diff(to_isomorphic(source), to_isomorphic(reconstructed))
        rows.append({"syntax": syntax, "triples": len(reconstructed),
                     "roundtrip_isomorphic": equivalent,
                     "included_equal_information": equivalent,
                     "missing_triples": len(missing), "added_triples": len(added),
                     "bytes_utf8": len(text.encode("utf-8")),
                     "surrogate_tokens": surrogate_tokens(text)})
    return rows