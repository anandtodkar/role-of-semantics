"""Experiment E5: how much of the agent's action space each semantic layer removes.

An LLM agent acting through a function-calling / MCP interface emits calls of
the form ``write_setpoint(tag, value, unit)``.  We enumerate a finite but
realistic candidate space and ask, for each semantic layer, two questions:

* **Reduction** - how many bits of the emittable action space does the layer
  eliminate?  ``log2(|A_0| / |A_L|)``.
* **Fidelity** - of the calls the layer still admits, what fraction are
  genuinely executable (precision), and of the genuinely executable calls, what
  fraction does the layer keep (recall)?

A layer that reduces the space but loses recall is *over-constraining*: it makes
the agent refuse legal work.  Layer G2 - a flat tag catalogue with a unit
string, i.e. what most industrial "semantic layers" ship - does exactly that.

The module also emits the JSON tool schemas themselves, which is the practical
deliverable: a schema generated from the AAS/OPC UA/KG carries the enumerations,
ranges and units that the model would otherwise have to invent.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass

from . import plant as P
from . import statemachine as sm
from . import units as U
from .validation import interlock_blocked

#: representative magnitudes an operator or an LLM would plausibly propose
VALUE_GRID: tuple[float, ...] = (
    0.0, 0.1, 0.5, 1.0, 2.0, 2.5, 3.0, 5.0, 7.5, 10.0, 15.0, 20.0, 25.0,
    30.0, 45.0, 50.0, 60.0, 75.0, 100.0, 120.0, 150.0, 200.0, 250.0, 330.0,
    500.0, 750.0, 1000.0, 2000.0,
)

ALL_UNITS: tuple[str, ...] = tuple(sorted(U.BY_IRI))
ALL_TAGS: tuple[str, ...] = tuple(s.tag for s in P.ALL_SIGNALS)
_SIG = {s.tag: s for s in P.ALL_SIGNALS}
_BLOCKED = interlock_blocked()


@dataclass(frozen=True)
class SpaceStats:
    tier: str
    size: int
    bits: float
    reduction_bits: float
    precision: float
    recall: float


def _accept(tier: str, tag: str, unit: str, value: float) -> bool:
    s = _SIG.get(tag)
    if tier in ("G0", "G1"):
        return True  # only structural well-formedness, which holds by construction
    if s is None:
        return False
    if s.access != "rw":
        return False
    if tier == "G2":
        # flat catalogue: literal unit string, range checked in the stated unit
        return unit == s.unit and s.eng_low <= value <= s.eng_high
    # G3 / G4: dimensional calculus
    if not U.compatible(unit, s.unit):
        return False
    conv = U.convert(value, unit, s.unit)
    if not (s.eng_low <= conv <= s.eng_high):
        return False
    if tier == "G3":
        return True
    return tag not in _BLOCKED  # G4 also honours the live interlock state


def write_action_space(tiers: tuple[str, ...] = ("G0", "G1", "G2", "G3", "G4")) -> list[SpaceStats]:
    candidates = [(t, u, v) for t in ALL_TAGS for u in ALL_UNITS for v in VALUE_GRID]
    accepted = {tier: {c for c in candidates if _accept(tier, *c)} for tier in tiers}
    truth = accepted["G4"]
    base = len(accepted[tiers[0]])
    out = []
    for tier in tiers:
        a = accepted[tier]
        inter = len(a & truth)
        out.append(SpaceStats(
            tier=tier,
            size=len(a),
            bits=math.log2(len(a)) if a else 0.0,
            reduction_bits=math.log2(base / len(a)) if a else float("inf"),
            precision=inter / len(a) if a else 0.0,
            recall=inter / len(truth) if truth else 0.0,
        ))
    return out


def command_action_space() -> list[SpaceStats]:
    """The same analysis for PackML unit commands."""
    assets = [a for a in P.PLANT]
    packml = {a.local_id: a.packml_state for a in P.PLANT
              if a.packml_capable and a.packml_state}
    candidates = [(a.local_id, c) for a in assets for c in sm.COMMANDS]
    truth = {(aid, c) for aid, st in packml.items() for c in sm.legal_commands(st)}
    tiers = {
        "G0": set(candidates),
        "G1": set(candidates),  # enum of verbs only - every asset still admissible
        "G2": {(aid, c) for aid, c in candidates if aid in packml},
        "G3": {(aid, c) for aid, c in candidates if aid in packml},
        "G4": truth,
    }
    base = len(tiers["G0"])
    out = []
    for tier in ("G0", "G1", "G2", "G3", "G4"):
        a = tiers[tier]
        inter = len(a & truth)
        out.append(SpaceStats(tier, len(a), math.log2(len(a)) if a else 0.0,
                              math.log2(base / len(a)) if a else float("inf"),
                              inter / len(a) if a else 0.0,
                              inter / len(truth) if truth else 0.0))
    return out


# ---------------------------------------------------------------------------
# Tool-schema projection
# ---------------------------------------------------------------------------


def write_tool_schema(condition_key: str, scope: str = "L1") -> dict:
    """Project the plant model into an OpenAI/MCP-style function schema.

    The schema is what actually reaches the model at inference time, so every
    constraint expressible here is a constraint the decoder can honour instead
    of a rule the model has to recall.
    """
    in_scope = [s for s in P.ALL_SIGNALS
                if P.SIGNAL_OWNER[s.tag].startswith(scope)]
    tag_prop: dict = {"type": "string", "description": "Tag to write"}
    value_prop: dict = {"type": "number", "description": "Value to write"}
    unit_prop: dict = {"type": "string", "description": "Unit of the value"}
    schema: dict = {
        "name": "write_setpoint",
        "description": "Write a value to a process setpoint.",
        "parameters": {"type": "object",
                       "properties": {"tag": tag_prop, "value": value_prop,
                                      "unit": unit_prop},
                       "required": ["tag", "value", "unit"]},
    }
    if condition_key == "C0":
        return schema
    if condition_key == "C1":
        tag_prop["description"] = "Tag name, e.g. " + in_scope[0].tag
        return schema
    writable = [s for s in in_scope if s.access == "rw"]
    tag_prop["enum"] = [s.tag for s in writable]
    schema["parameters"]["properties"] = {
        "tag": tag_prop,
        "value": value_prop,
        "unit": unit_prop,
    }
    if condition_key == "C2":
        unit_prop["enum"] = sorted({U.BY_IRI[s.unit].symbol for s in writable})
        schema["x-perTagConstraints"] = {
            s.tag: {"unit": U.BY_IRI[s.unit].symbol,
                    "minimum": s.eng_low, "maximum": s.eng_high}
            for s in writable
        }
        return schema
    # C3 / C4: quantity kinds allow *any* dimensionally compatible unit
    unit_prop["enum"] = sorted({u.symbol for s in writable
                                for u in U.units_for(s.quantity_kind)})
    schema["x-perTagConstraints"] = {
        s.tag: {
            "quantityKind": s.quantity_kind,
            "canonicalUnit": U.BY_IRI[s.unit].symbol,
            "acceptedUnits": sorted(u.symbol for u in U.units_for(s.quantity_kind)),
            "minimum": s.eng_low, "maximum": s.eng_high,
            "semanticId": s.eclass_irdi,
        }
        for s in writable
    }
    if condition_key == "C4":
        for s in writable:
            entry = schema["x-perTagConstraints"][s.tag]
            ilk = next((i for i in P.INTERLOCKS if i["tag"] == s.tag), None)
            if ilk:
                entry["interlock"] = {"id": ilk["id"], "guard": ilk["guard_tag"],
                                      "operator": ilk["operator"],
                                      "threshold": list(ilk["threshold"])
                                      if isinstance(ilk["threshold"], tuple)
                                      else ilk["threshold"],
                                      "currentlySatisfied": s.tag not in _BLOCKED}
            entry["writableNow"] = s.tag not in _BLOCKED
        schema["x-availableCommands"] = {
            a.local_id: {"packMLState": a.packml_state,
                         "legalCommands": list(sm.legal_commands(a.packml_state))}
            for a in P.PLANT
            if a.packml_capable and a.packml_state and a.local_id.startswith(scope)
        }
    return schema


def schema_sizes(scope: str = "L1") -> dict[str, int]:
    from .metrics import surrogate_tokens

    return {c: surrogate_tokens(json.dumps(write_tool_schema(c, scope)))
            for c in ("C0", "C1", "C2", "C3", "C4")}
