"""Fact-level OPC UA versus AAS coverage on matched assets (case study CS5).

Two inputs are supported, both labelled by provenance:
* the synthetic reference plant, whose OPC UA NodeSet2 and AAS projections are generated
  from one authored specification (circular: measures the emitted profiles only);
* the KUKA NodeSet pilot, whose AAS was derived from the NodeSet (retention check only).
Facts absent from a projection reflect the profile emitted here, not a limit of either standard.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from . import kg as KG
from . import plant as P
from . import statemachine as SM
from . import units as U
from .metrics import surrogate_tokens
from .nodeset_case import _json_text, parse_nodeset

CATEGORIES = {
    "identity": "U1", "semantic_id": "U1", "nameplate": "U1",
    "datatype": "U2", "access": "U2", "range": "U2",
    "unit": "U3", "quantity_kind": "U3",
    "membership": "U4", "parent": "U4", "feeds": "U4",
    "state": "U5", "legal_commands": "U5",
    "interlock": "U6",
    "value": "U7", "observation_time": "U7",
}
OBSERVATION_TIME = "2026-07-14T02:20:00Z"
Facts = dict[tuple[str, str], Any]


def reference_facts() -> Facts:
    facts: Facts = {}
    for asset in P.PLANT:
        if asset.parent:
            facts[("parent", asset.local_id)] = asset.parent
        if asset.manufacturer != "-":
            facts[("nameplate", asset.local_id)] = (asset.manufacturer, asset.model, asset.serial)
        if asset.packml_state:
            facts[("state", asset.local_id)] = asset.packml_state
            facts[("legal_commands", asset.local_id)] = tuple(sorted(SM.legal_commands(asset.packml_state)))
        for signal in asset.signals:
            tag = signal.tag
            facts[("identity", tag)] = tag
            facts[("datatype", tag)] = "numeric"
            facts[("access", tag)] = signal.access
            facts[("range", tag)] = (float(signal.eng_low), float(signal.eng_high))
            facts[("unit", tag)] = U.BY_IRI[signal.unit].symbol
            facts[("quantity_kind", tag)] = signal.quantity_kind
            facts[("membership", tag)] = asset.local_id
            if signal.eclass_irdi:
                facts[("semantic_id", tag)] = signal.eclass_irdi
            if signal.sample_value is not None:
                facts[("value", tag)] = float(signal.sample_value)
                facts[("observation_time", tag)] = OBSERVATION_TIME
    for upstream, downstream in P.FEEDS:
        facts[("feeds", f"{upstream}->{downstream}")] = True
    for interlock in P.INTERLOCKS:
        facts[("interlock", str(interlock["id"]))] = (str(interlock["tag"]), str(interlock["guard_tag"]))
    return facts


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child(element: ET.Element, name: str) -> ET.Element | None:
    return next((child for child in element.iter() if _local(child.tag) == name), None)


def opcua_facts(xml_text: str) -> Facts:
    root = ET.fromstring(xml_text)
    facts: Facts = {}
    tags_by_node: dict[str, str] = {}
    variables = [element for element in root if _local(element.tag) == "UAVariable"]
    for element in variables:
        browse = element.get("BrowseName", "")
        if element.get("ParentNodeId") is None and ":" in browse:
            tags_by_node[element.get("NodeId", "")] = browse.split(":", 1)[1]
    for element in root:
        kind = _local(element.tag)
        references = [(ref.get("ReferenceType"), ref.get("IsForward", "true") != "false", (ref.text or "").strip())
                      for ref in element.iter() if _local(ref.tag) == "Reference"]
        if kind == "UAObject":
            asset = element.get("BrowseName", "").split(":", 1)[-1]
            for ref_type, forward, target in references:
                if ref_type == "Organizes" and not forward:
                    facts[("parent", asset)] = target.split(";s=", 1)[-1]
        elif kind == "UAVariable" and element.get("NodeId") in tags_by_node:
            tag = tags_by_node[element.get("NodeId")]
            facts[("identity", tag)] = tag
            if element.get("DataType") in ("i=11", "i=7", "Double", "UInt32"):
                facts[("datatype", tag)] = "numeric"
            access = element.get("AccessLevel")
            if access:
                facts[("access", tag)] = "rw" if int(access) & 2 else "r"
            for ref_type, forward, target in references:
                if ref_type == "HasComponent" and not forward:
                    facts[("membership", tag)] = target.split(";s=", 1)[-1]
            value = _child(element, "Value")
            if value is not None and _child(value, "Double") is not None:
                facts[("value", tag)] = float(_child(value, "Double").text)
        elif kind == "UAVariable":
            parent = tags_by_node.get(element.get("ParentNodeId", ""))
            if parent is None:
                continue
            if element.get("BrowseName") == "EURange":
                facts[("range", parent)] = (float(_child(element, "Low").text), float(_child(element, "High").text))
            elif element.get("BrowseName") == "EngineeringUnits":
                info = _child(element, "EUInformation")
                display, description = _child(info, "DisplayName"), _child(info, "Description")
                if display is not None:
                    facts[("unit", parent)] = "".join(display.itertext()).strip()
                if description is not None:
                    facts[("quantity_kind", parent)] = "".join(description.itertext()).strip()
    return facts


def _iec61360_unit(element: dict) -> str | None:
    for spec in element.get("embeddedDataSpecifications", []):
        unit = (spec.get("dataSpecificationContent") or {}).get("unit")
        if unit:
            return unit
    return None


def aas_facts(environment: dict) -> Facts:
    facts: Facts = {}
    owner_of_submodel = {}
    for shell in environment["assetAdministrationShells"]:
        asset = shell["assetInformation"]["globalAssetId"].rsplit("/", 1)[-1]
        for reference in shell.get("submodels", []):
            owner_of_submodel[reference["keys"][-1]["value"]] = asset
    for submodel in environment["submodels"]:
        asset = owner_of_submodel.get(submodel["id"])
        if asset is None:
            continue
        elements = submodel.get("submodelElements", [])
        if submodel["idShort"] == "Nameplate":
            values = {element["idShort"]: element.get("value") for element in elements}
            plate = (values.get("ManufacturerName"), values.get("ManufacturerProductDesignation"),
                     values.get("SerialNumber"))
            if all(plate) and plate[0] != "-":
                facts[("nameplate", asset)] = plate
        if submodel["idShort"] != "OperationalData":
            continue
        for element in elements:
            name = element["idShort"]
            if name == "PackMLState":
                if element.get("value"):
                    facts[("state", asset)] = element["value"]
                continue
            facts[("identity", name)] = name
            facts[("membership", name)] = asset
            if element.get("valueType") in ("xs:double", "xs:float", "xs:int", "xs:unsignedInt"):
                facts[("datatype", name)] = "numeric"
            if element.get("value") not in (None, ""):
                facts[("value", name)] = float(element["value"])
            unit = _iec61360_unit(element)
            if unit:
                facts[("unit", name)] = unit
            semantic = (element.get("semanticId") or {}).get("keys") or []
            if semantic:
                facts[("semantic_id", name)] = semantic[0]["value"]
    return facts


def _equal(expected: Any, observed: Any) -> bool:
    if isinstance(expected, float) or isinstance(expected, tuple) and expected and isinstance(expected[0], float):
        left = expected if isinstance(expected, tuple) else (expected,)
        right = observed if isinstance(observed, tuple) else (observed,)
        return len(left) == len(right) and all(abs(float(a) - float(b)) <= 1e-9 * max(1.0, abs(a))
                                               for a, b in zip(left, right))
    return expected == observed


def coverage(reference: Facts, observed: Facts) -> dict[str, dict[str, int]]:
    rows: dict[str, dict[str, int]] = defaultdict(lambda: {"reference": 0, "correct": 0,
                                                            "conflict": 0, "missing": 0})
    for key, expected in reference.items():
        row = rows[key[0]]
        row["reference"] += 1
        if key not in observed:
            row["missing"] += 1
        elif _equal(expected, observed[key]):
            row["correct"] += 1
        else:
            row["conflict"] += 1
    return {category: dict(rows[category]) for category in CATEGORIES if category in rows}


def _union(first: Facts, second: Facts, reference: Facts) -> Facts:
    merged = dict(second)
    for key, value in first.items():
        if key not in merged or (key in reference and _equal(reference[key], value)):
            merged[key] = value
    return merged


def synthetic_case() -> dict:
    xml_text = KG.opcua_nodeset()
    aas_text = json.dumps(KG.aas_environment(), indent=1)
    reference = reference_facts()
    opcua, aas = opcua_facts(xml_text), aas_facts(json.loads(aas_text))
    return {
        "input": "synthetic reference plant (one authored specification; circular)",
        "assets": len(P.PLANT), "signals": len(P.ALL_SIGNALS), "reference_facts": len(reference),
        "serialisations": {"opcua_nodeset2_xml": {"bytes": len(xml_text.encode("utf-8")),
                                                  "surrogate_tokens": surrogate_tokens(xml_text)},
                           "aas_v3_json": {"bytes": len(aas_text.encode("utf-8")),
                                           "surrogate_tokens": surrogate_tokens(aas_text)}},
        "coverage": {"opcua": coverage(reference, opcua), "aas": coverage(reference, aas),
                     "union": coverage(reference, _union(opcua, aas, reference))},
    }


def _kuka_reference(instance_path: Path) -> Facts:
    document = parse_nodeset(instance_path, "instance")
    facts: Facts = {}
    for node in document.nodes:
        node_id = node["nodeId"]["expanded"]
        facts[("identity", node_id)] = node_id
        if node["browseName"]:
            facts[("browse_name", node_id)] = node["browseName"]["raw"]
        if node["displayName"] is not None:
            facts[("display_name", node_id)] = node["displayName"]
        if node["description"] is not None:
            facts[("description", node_id)] = node["description"]
        if node["dataType"]:
            facts[("datatype", node_id)] = node["dataType"]["expanded"]
        if node["value"] is not None:
            value = node["value"]
            facts[("value", node_id)] = value if isinstance(value, str) else _json_text(value)
        for reference in node["references"]:
            target, ref_type = reference["target"], reference["referenceType"]
            if target and target["expanded"]:
                key = f"{node_id}|{ref_type['expanded'] if ref_type else 'unknown'}|{reference['isForward']}|{target['expanded']}"
                facts[("reference", key)] = True
    return facts


def _iri_to_expanded(iri: str) -> str:
    namespace, identifier = iri.removeprefix("urn:opcua-node:").split(":", 1)
    return f"nsu={unquote(namespace)};{unquote(identifier)}"


def _kuka_aas(environment: dict) -> Facts:
    facts: Facts = {}
    elements = environment["submodels"][0]["submodelElements"]
    expanded_of = {}
    for element in elements:
        if element["modelType"] != "SubmodelElementCollection":
            continue
        props = {prop["idShort"]: prop.get("value") for prop in element["value"]}
        node_id = props["ExpandedNodeId"]
        expanded_of[element["idShort"]] = node_id
        facts[("identity", node_id)] = node_id
        for field, category in (("BrowseName", "browse_name"), ("DisplayName", "display_name"),
                                ("Description", "description"), ("DataType", "datatype"),
                                ("DecodedValue", "value")):
            if props.get(field) is not None:
                facts[(category, node_id)] = props[field]

    def resolve(reference: dict) -> str:
        key = reference["keys"][-1]["value"]
        return expanded_of[key] if reference["type"] == "ModelReference" else _iri_to_expanded(key)

    for element in elements:
        if element["modelType"] != "RelationshipElement":
            continue
        text = element["description"][0]["text"]
        parts = dict(part.split("=", 1) for part in text.split("; "))
        forward = parts["IsForward"] == "true"
        target = resolve(element["second"] if forward else element["first"])
        facts[("reference", f"{parts['NodeSet owner']}|{parts['ReferenceType']}|{forward}|{target}")] = True
    return facts


def kuka_case(instance_path: Path, aas_path: Path) -> dict:
    reference = _kuka_reference(instance_path)
    aas_text = aas_path.read_text(encoding="utf-8")
    observed = _kuka_aas(json.loads(aas_text))
    rows: dict[str, dict[str, int]] = defaultdict(lambda: {"reference": 0, "correct": 0, "conflict": 0, "missing": 0})
    for key, expected in reference.items():
        row = rows[key[0]]
        row["reference"] += 1
        if key not in observed:
            row["missing"] += 1
        elif expected == observed[key]:
            row["correct"] += 1
        else:
            row["conflict"] += 1
    xml_text = instance_path.read_text(encoding="utf-8")
    return {"input": "KUKA instance NodeSet (IIH-attributed) and AAS derived from it (retention only)",
            "reference_facts": len(reference), "coverage": {key: dict(value) for key, value in rows.items()},
            "serialisations": {"opcua_nodeset2_xml": {"bytes": len(xml_text.encode("utf-8")),
                                                      "surrogate_tokens": surrogate_tokens(xml_text)},
                               "aas_v3_json": {"bytes": len(aas_text.encode("utf-8")),
                                               "surrogate_tokens": surrogate_tokens(aas_text)}}}
