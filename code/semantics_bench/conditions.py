"""The five context conditions - a controlled ablation of the semantic stack.

Every condition is a *projection* of the same plant.  A condition is defined by
(i) the set of **fact kinds** its representation is able to carry and (ii) the
concrete syntax in which those facts are serialised, because syntax determines
the token bill.

======  =====================================  =========================================
cond.   real-world counterpart                  fact kinds added
======  =====================================  =========================================
C0      raw PLC/OPC-DA tag list                 value
C1      historian / SCADA CSV export            description, unit *symbol*
C2      typed information model
        (OPC UA NodeSet2, AAS submodels)        quantity kind, EU range, alarm limits,
                                                access mode, role, asset membership,
                                                ISA-95 parentage, nameplate, semanticId
C3      + formal ontology
        (RDF/OWL, QUDT, Brick, ISA-95)          unit dimension, unit conversion,
                                                material/utility topology, class
                                                taxonomy, location
C4      + behaviour, constraints, provenance
        (PackML, interlock model, SOSA/PROV)    PackML state and legal command set,
                                                interlock guards, observation time,
                                                event log, recipe parameters
======  =====================================  =========================================

Note what C0-C2 have in common with almost every deployed "AI-ready data layer":
they describe *things*, never *what may be done to them*.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable, Iterable

from . import plant as P
from . import statemachine as sm
from . import units as U
from .metrics import surrogate_tokens

# ---------------------------------------------------------------------------
# Fact model
# ---------------------------------------------------------------------------

FACT_KINDS = (
    "value", "desc", "unit", "qk", "range", "alarm", "access", "role",
    "sig_of", "parent", "label", "nameplate", "semid", "isa95", "location",
    "class", "dim", "conv", "feeds", "state", "legalcmd", "interlock",
    "time", "event", "recipe",
)


def fact(kind: str, *parts: str) -> str:
    return f"{kind}:" + "|".join(parts)


@dataclass(frozen=True)
class Condition:
    key: str
    label: str
    counterpart: str
    kinds: frozenset[str]

    def can(self, kind: str) -> bool:
        return kind in self.kinds


_C0 = frozenset({"value"})
_C1 = _C0 | {"desc", "unit"}
_C2 = _C1 | {"qk", "range", "alarm", "access", "role", "sig_of", "parent",
             "label", "nameplate", "semid", "isa95"}
_C3 = _C2 | {"dim", "conv", "feeds", "class", "location"}
_C4 = _C3 | {"state", "legalcmd", "interlock", "time", "event", "recipe"}

CONDITIONS: tuple[Condition, ...] = (
    Condition("C0", "C0 raw tag list", "OPC DA / PLC symbol table", _C0),
    Condition("C1", "C1 historian export", "SCADA/historian CSV", _C1),
    Condition("C2", "C2 typed information model", "OPC UA NodeSet2 / AAS submodels", _C2),
    Condition("C3", "C3 + formal ontology", "RDF/OWL + QUDT + Brick + ISA-95", _C3),
    Condition("C4", "C4 + behaviour and constraints", "PackML + interlocks + SOSA/PROV", _C4),
)
BY_KEY = {c.key: c for c in CONDITIONS}


# ---------------------------------------------------------------------------
# Retrievable elements
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Element:
    eid: str
    etype: str  # signal | asset | event | product | interlock | unitdef
    text_index: str  # what a lexical retriever sees
    payload: object


def all_elements() -> list[Element]:
    els: list[Element] = []
    for a in P.PLANT:
        idx = " ".join([a.local_id, a.name, a.kind, a.isa95_level,
                        a.manufacturer, a.model, a.serial, a.location or "",
                        " ".join(a.mtp_services)])
        els.append(Element(a.local_id, "asset", idx, a))
        for s in a.signals:
            sidx = " ".join([s.tag, s.description, U.BY_IRI[s.unit].symbol,
                             s.quantity_kind, s.role, a.name, a.local_id])
            els.append(Element(s.tag, "signal", sidx, s))
    for ev in P.EVENTS:
        els.append(Element(ev["id"], "event",
                           f"{ev['id']} {ev['asset']} {ev['type']} {ev['text']} {ev['ts']}", ev))
    for pr in P.PRODUCTS:
        els.append(Element(str(pr["id"]), "product",
                           f"{pr['id']} {pr['name']} recipe {pr['line']}", pr))
    for ilk in P.INTERLOCKS:
        els.append(Element(str(ilk["id"]), "interlock",
                           f"{ilk['id']} interlock {ilk['tag']} {ilk['text']}", ilk))
    return els


ELEMENTS: list[Element] = all_elements()
ELEMENT_BY_ID: dict[str, Element] = {e.eid: e for e in ELEMENTS}


# ---------------------------------------------------------------------------
# Fact emission (what each condition can say about an element)
# ---------------------------------------------------------------------------


def facts_of(el: Element, cond: Condition) -> set[str]:
    f: set[str] = set()
    add = f.add
    if el.etype == "signal":
        s: P.Signal = el.payload  # type: ignore[assignment]
        owner = P.SIGNAL_OWNER[s.tag]
        if cond.can("value") and s.sample_value is not None:
            add(fact("value", s.tag))
        if cond.can("desc"):
            add(fact("desc", s.tag))
        if cond.can("unit"):
            add(fact("unit", s.tag))
        if cond.can("qk"):
            add(fact("qk", s.tag))
        if cond.can("range"):
            add(fact("range", s.tag))
        if cond.can("alarm") and (s.alarm_low is not None or s.alarm_high is not None):
            add(fact("alarm", s.tag))
        if cond.can("access"):
            add(fact("access", s.tag))
        if cond.can("role"):
            add(fact("role", s.tag))
        if cond.can("sig_of"):
            add(fact("sig_of", s.tag, owner))
        if cond.can("semid") and s.eclass_irdi:
            add(fact("semid", s.tag))
        if cond.can("time") and s.sample_value is not None:
            add(fact("time", s.tag))
        if cond.can("interlock"):
            for ilk in P.INTERLOCKS:
                if ilk["tag"] == s.tag:
                    add(fact("interlock", s.tag))
    elif el.etype == "asset":
        a: P.Asset = el.payload  # type: ignore[assignment]
        if cond.can("label"):
            add(fact("label", a.local_id))
        if cond.can("parent") and a.parent:
            add(fact("parent", a.local_id, a.parent))
        if cond.can("isa95"):
            add(fact("isa95", a.local_id))
        if cond.can("nameplate") and a.manufacturer != "-":
            add(fact("nameplate", a.local_id))
        if cond.can("class"):
            add(fact("class", a.local_id))
        if cond.can("location") and a.location:
            add(fact("location", a.local_id))
        if cond.can("feeds"):
            for up, down in P.FEEDS:
                if up == a.local_id or down == a.local_id:
                    add(fact("feeds", up, down))
        if cond.can("state") and a.packml_state:
            add(fact("state", a.local_id))
        if cond.can("legalcmd") and a.packml_state:
            add(fact("legalcmd", a.local_id))
    elif el.etype == "event" and cond.can("event"):
        add(fact("event", str(el.payload["id"])))  # type: ignore[index]
    elif el.etype == "product" and cond.can("recipe"):
        add(fact("recipe", str(el.payload["id"])))  # type: ignore[index]
    elif el.etype == "interlock" and cond.can("interlock"):
        add(fact("interlock", str(el.payload["tag"])))  # type: ignore[index]
    return f


# ---------------------------------------------------------------------------
# Rendering (native syntax per condition -> the token bill)
# ---------------------------------------------------------------------------


def _render_signal(s: P.Signal, cond: Condition) -> str:
    u = U.BY_IRI[s.unit]
    owner = P.SIGNAL_OWNER[s.tag]
    if cond.key == "C0":
        v = "" if s.sample_value is None else f"{s.sample_value:g}"
        return f"{s.tag}={v}"
    if cond.key == "C1":
        v = "" if s.sample_value is None else f"{s.sample_value:g}"
        return f'"{s.tag}","{s.description}","{u.symbol}","{v}"'
    if cond.key == "C2":
        rec = {
            "NodeId": s.node_id,
            "BrowseName": s.tag,
            "DisplayName": s.description,
            "ParentObject": owner,
            "DataType": "Double",
            "AccessLevel": "CurrentRead" if s.access == "r" else "CurrentRead|CurrentWrite",
            "EngineeringUnits": {"DisplayName": u.symbol, "Description": s.quantity_kind},
            "EURange": {"Low": s.eng_low, "High": s.eng_high},
            "Role": s.role,
            "Value": s.sample_value,
        }
        if s.eclass_irdi:
            rec["SemanticId"] = s.eclass_irdi
        if s.alarm_low is not None or s.alarm_high is not None:
            rec["AlarmLimits"] = {"Low": s.alarm_low, "High": s.alarm_high}
        return json.dumps(rec, separators=(",", ":"))
    # C3 / C4 - compact Turtle
    lines = [
        f"plant:signal/{s.tag} a sio:Signal ; skos:notation \"{s.tag}\" ;",
        f'  rdfs:label "{s.description}" ; sio:belongsTo plant:{owner} ;',
        f"  qudt:unit unit:{s.unit} ; qudt:hasQuantityKind qk:{s.quantity_kind} ;",
        f"  sio:engineeringLow {s.eng_low:g} ; sio:engineeringHigh {s.eng_high:g} ;",
        f'  sio:accessMode "{s.access}" ; sio:signalRole "{s.role}"',
    ]
    if s.eclass_irdi:
        lines.append(f'  ; sio:semanticId "{s.eclass_irdi}"')
    if s.alarm_low is not None:
        lines.append(f"  ; sio:alarmLow {s.alarm_low:g}")
    if s.alarm_high is not None:
        lines.append(f"  ; sio:alarmHigh {s.alarm_high:g}")
    if cond.can("interlock"):
        for ilk in P.INTERLOCKS:
            if ilk["tag"] == s.tag:
                lines.append(f"  ; sio:interlockedBy plant:interlock/{ilk['id']}")
    lines.append(" .")
    if s.sample_value is not None:
        if cond.can("time"):
            lines.append(
                f"plant:obs/{s.tag} a sosa:Observation ; sosa:observedProperty "
                f"plant:signal/{s.tag} ; sosa:resultTime \"2026-07-14T02:20:00Z\" ; "
                f"sosa:hasResult [ qudt:numericValue {s.sample_value:g} ; qudt:unit unit:{s.unit} ] ."
            )
        else:
            lines.append(
                f"plant:obs/{s.tag} sosa:observedProperty plant:signal/{s.tag} ; "
                f"sosa:hasResult [ qudt:numericValue {s.sample_value:g} ; qudt:unit unit:{s.unit} ] ."
            )
    return "\n".join(lines)


def _render_asset(a: P.Asset, cond: Condition) -> str:
    if cond.key in ("C0",):
        return ""
    if cond.key == "C1":
        return ""
    if cond.key == "C2":
        rec = {"NodeId": f"ns=3;s={a.local_id}", "BrowseName": a.local_id,
               "DisplayName": a.name, "ISA95Level": a.isa95_level,
               "Organizes": [s.tag for s in a.signals]}
        if a.parent:
            rec["OrganizedBy"] = a.parent
        if a.manufacturer != "-":
            rec["Nameplate"] = {"ManufacturerName": a.manufacturer,
                                "ManufacturerProductDesignation": a.model,
                                "SerialNumber": a.serial}
        return json.dumps(rec, separators=(",", ":"))
    lines = [f'plant:{a.local_id} a sio:{a.kind} ; rdfs:label "{a.name}" ;',
             f'  sio:isa95Level "{a.isa95_level}"']
    if a.parent:
        lines.append(f"  ; sio:isPartOf plant:{a.parent}")
    if a.location and cond.can("location"):
        lines.append(f'  ; sio:location "{a.location}"')
    if a.manufacturer != "-" and cond.can("nameplate"):
        lines.append(f'  ; sio:manufacturer "{a.manufacturer}" ; '
                     f'sio:modelDesignation "{a.model}" ; sio:serialNumber "{a.serial}"')
    if cond.can("feeds"):
        for up, down in P.FEEDS:
            if up == a.local_id:
                lines.append(f"  ; sio:feeds plant:{down}")
            elif down == a.local_id:
                lines.append(f"  ; sio:isFedBy plant:{up}")
    if cond.can("state") and a.packml_state:
        lines.append(f'  ; sio:packMLState "{a.packml_state}"')
        if cond.can("legalcmd"):
            cmds = " ".join(f'"{c}"' for c in sm.legal_commands(a.packml_state))
            lines.append(f"  ; sio:legalCommand {cmds.replace(' ', ', ')}")
    lines.append(" .")
    return "\n".join(lines)


def _render_other(el: Element, cond: Condition) -> str:
    if el.etype == "event" and cond.can("event"):
        e = el.payload  # type: ignore[assignment]
        return (f'plant:event/{e["id"]} a prov:Activity, sio:{e["type"]} ; '  # type: ignore[index]
                f'prov:startedAtTime "{e["ts"]}" ; '  # type: ignore[index]
                f'prov:wasAssociatedWith plant:{e["asset"]} ; '  # type: ignore[index]
                f'rdfs:comment "{e["text"]}" ; sio:severity "{e["severity"]}" .')  # type: ignore[index]
    if el.etype == "product" and cond.can("recipe"):
        p = el.payload  # type: ignore[assignment]
        return (f'plant:product/{p["id"]} a sio:Product ; rdfs:label "{p["name"]}" ; '  # type: ignore[index]
                f'sio:producedOn plant:{p["line"]} ; '  # type: ignore[index]
                f'sio:fillVolume [ qudt:numericValue {p["fill_volume_ml"]} ; qudt:unit unit:MilliL ] ; '  # type: ignore[index]
                f'sio:fillPressure [ qudt:numericValue {p["fill_pressure_bar"]} ; qudt:unit unit:BAR ] ; '  # type: ignore[index]
                f'sio:capTorque [ qudt:numericValue {p["cap_torque_nm"]} ; qudt:unit unit:N-M ] .')  # type: ignore[index]
    if el.etype == "interlock" and cond.can("interlock"):
        i = el.payload  # type: ignore[assignment]
        thr = i["threshold"]  # type: ignore[index]
        thr_s = " ".join(f'"{t}"' for t in thr) if isinstance(thr, tuple) else str(thr)
        return (f'plant:interlock/{i["id"]} a sio:Interlock ; '  # type: ignore[index]
                f'rdfs:comment "{i["text"]}" ; '  # type: ignore[index]
                f'sio:guardSignal plant:signal/{i["guard_tag"]} ; '  # type: ignore[index]
                f'sio:guardOperator "{i["operator"]}" ; sio:guardValue {thr_s} .')  # type: ignore[index]
    return ""


def render(el: Element, cond: Condition) -> str:
    if el.etype == "signal":
        return _render_signal(el.payload, cond)  # type: ignore[arg-type]
    if el.etype == "asset":
        return _render_asset(el.payload, cond)  # type: ignore[arg-type]
    return _render_other(el, cond)


_UNIT_BLOCK_CACHE: dict[str, str] = {}


def unit_definition_block(unit_iris: Iterable[str]) -> str:
    """The QUDT slice an agent needs to convert between the units in play."""
    lines = []
    for iri in sorted(set(unit_iris)):
        u = U.BY_IRI[iri]
        lines.append(
            f'unit:{iri} a qudt:Unit ; qudt:symbol "{u.symbol}" ; '
            f"qudt:hasQuantityKind qk:{u.quantity_kind} ; "
            f"qudt:conversionMultiplier {u.multiplier:g} ; "
            f"qudt:conversionOffset {u.offset:g} ; "
            f'sio:dimensionVector "{U.format_dimension(u.dimension)}" .'
        )
    return "\n".join(lines)


HEADERS = {
    "C0": "# tag=value",
    "C1": "TagName,Description,EngUnits,Value",
    "C2": "# OPC UA / AAS typed nodes (JSON projection of NodeSet2 + submodels)",
    "C3": "# RDF (Turtle) - plant knowledge graph excerpt",
    "C4": "# RDF (Turtle) - plant knowledge graph excerpt",
}


def build_context(elements: list[Element], cond: Condition,
                  token_budget: int | None = None) -> tuple[str, set[str], int]:
    """Serialise ``elements`` under ``cond``, honouring a token budget.

    When the condition carries a unit ontology, part of the budget is reserved
    for the QUDT definition block: conversion factors are schema, not payload,
    and an agent that runs out of budget before reading them cannot convert.

    Returns ``(text, expressed_facts, tokens)``.
    """
    parts: list[str] = [HEADERS[cond.key]]
    facts: set[str] = set()
    used_units: set[str] = set()
    total = surrogate_tokens(parts[0])
    payload_budget = token_budget
    if token_budget is not None and cond.can("dim"):
        payload_budget = int(token_budget * 0.85)
    for el in elements:
        chunk = render(el, cond)
        if not chunk:
            continue
        cost = surrogate_tokens(chunk) + 1
        if payload_budget is not None and total + cost > payload_budget:
            continue
        parts.append(chunk)
        total += cost
        facts |= facts_of(el, cond)
        if el.etype == "signal":
            used_units.add(el.payload.unit)  # type: ignore[union-attr]
    if cond.can("dim") and used_units:
        block = unit_definition_block(used_units)
        cost = surrogate_tokens(block)
        if token_budget is None or total + cost <= token_budget:
            parts.append(block)
            total += cost
            for iri in used_units:
                facts.add(fact("dim", iri))
            for a_iri in used_units:
                for b in U.units_for(U.BY_IRI[a_iri].quantity_kind):
                    facts.add(fact("conv", a_iri, b.iri_local))
                    facts.add(fact("conv", b.iri_local, a_iri))
    return "\n".join(parts), facts, total
