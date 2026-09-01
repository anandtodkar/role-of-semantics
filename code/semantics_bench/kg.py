"""Materialise the reference plant into every semantic representation studied.

One declarative plant specification (:mod:`semantics_bench.plant`) is projected
into:

======================  =====================================================
``build_graph()``       RDF/OWL knowledge graph (SOSA/SSN, QUDT, Brick, PROV,
                        ISA-95 alignment) - the *formal* layer
``aas_environment()``   IDTA Asset Administration Shell environment (JSON,
                        metamodel v3) with semanticIds as IRDIs
``opcua_nodeset()``     OPC UA (IEC 62541) NodeSet2 XML fragment
``wot_thing_descriptions()``  W3C WoT Thing Description 1.1 (JSON-LD)
``ngsild_entities()``   ETSI NGSI-LD context entities
``flat_tag_table()``    the historian CSV export - the *no-semantics* baseline
======================  =====================================================

Because every artefact is generated from the same source, differences measured
between them are differences of **representation**, not of content.
"""

from __future__ import annotations

import json
from xml.sax.saxutils import escape

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SKOS, XSD

from . import plant as P
from . import statemachine as sm
from . import units as U
from .vocab import (
    AAS,
    BRICK,
    DCTERMS,
    ECLASS,
    OPCUA,
    PLANT,
    PROV,
    QK,
    QUDT,
    SIO,
    SOSA,
    SSN,
    UNIT,
    bind_all,
)

# ---------------------------------------------------------------------------
# 1. RDF knowledge graph
# ---------------------------------------------------------------------------

_ISA95_RANK = {
    "Enterprise": 4,
    "Site": 3,
    "Area": 2,
    "WorkCenter": 1,
    "WorkUnit": 0,
    "ControlModule": -1,
}


def _tbox(g: Graph) -> None:
    """Minimal OWL 2 RL T-Box aligning local classes to external vocabularies."""
    g.add((SIO.PhysicalAsset, RDF.type, OWL.Class))
    g.add((SIO.Signal, RDF.type, OWL.Class))
    g.add((SIO.Signal, RDFS.subClassOf, SOSA.ObservableProperty))

    for cls, parent, brick in [
        ("Enterprise", "PhysicalAsset", None),
        ("Site", "PhysicalAsset", "Site"),
        ("Area", "PhysicalAsset", None),
        ("ProductionLine", "PhysicalAsset", None),
        ("Pasteuriser", "ProcessUnit", None),
        ("Filler", "ProcessUnit", None),
        ("Capper", "ProcessUnit", None),
        ("Labeller", "ProcessUnit", None),
        ("CIPSkid", "ProcessUnit", None),
        ("Compressor", "UtilityEquipment", "Compressor"),
        ("Chiller", "UtilityEquipment", "Chiller"),
        ("ProcessUnit", "PhysicalAsset", None),
        ("UtilityEquipment", "PhysicalAsset", None),
    ]:
        g.add((SIO[cls], RDF.type, OWL.Class))
        g.add((SIO[cls], RDFS.subClassOf, SIO[parent]))
        if brick:
            g.add((SIO[cls], OWL.equivalentClass, BRICK[brick]))

    # object / datatype properties (domain+range give an agent join semantics)
    for prop, dom, rng, kind in [
        ("hasPart", "PhysicalAsset", "PhysicalAsset", OWL.ObjectProperty),
        ("isPartOf", "PhysicalAsset", "PhysicalAsset", OWL.ObjectProperty),
        ("feeds", "PhysicalAsset", "PhysicalAsset", OWL.ObjectProperty),
        ("isFedBy", "PhysicalAsset", "PhysicalAsset", OWL.ObjectProperty),
        ("hasSignal", "PhysicalAsset", "Signal", OWL.ObjectProperty),
        ("interlockedBy", "Signal", "Interlock", OWL.ObjectProperty),
        ("guardSignal", "Interlock", "Signal", OWL.ObjectProperty),
        ("isa95Level", "PhysicalAsset", None, OWL.DatatypeProperty),
        ("opcuaNodeId", "Signal", None, OWL.DatatypeProperty),
        ("engineeringLow", "Signal", None, OWL.DatatypeProperty),
        ("engineeringHigh", "Signal", None, OWL.DatatypeProperty),
        ("alarmLow", "Signal", None, OWL.DatatypeProperty),
        ("alarmHigh", "Signal", None, OWL.DatatypeProperty),
        ("accessMode", "Signal", None, OWL.DatatypeProperty),
        ("signalRole", "Signal", None, OWL.DatatypeProperty),
        ("safetyCritical", "Signal", None, OWL.DatatypeProperty),
        ("packMLState", "PhysicalAsset", None, OWL.DatatypeProperty),
        ("providesService", "PhysicalAsset", None, OWL.DatatypeProperty),
    ]:
        g.add((SIO[prop], RDF.type, kind))
        if dom:
            g.add((SIO[prop], RDFS.domain, SIO[dom]))
        if rng:
            g.add((SIO[prop], RDFS.range, SIO[rng]))

    g.add((SIO.hasPart, OWL.inverseOf, SIO.isPartOf))
    g.add((SIO.feeds, OWL.inverseOf, SIO.isFedBy))
    g.add((SIO.isPartOf, RDF.type, OWL.TransitiveProperty))
    g.add((SIO.hasSignal, RDFS.subPropertyOf, SSN.hasProperty))


def build_graph() -> Graph:
    """Return the fully populated A-Box + T-Box knowledge graph."""
    g = Graph()
    bind_all(g)
    _tbox(g)

    # --- units and quantity kinds (a local QUDT slice) --------------------
    for u in U.BY_IRI.values():
        node = UNIT[u.iri_local]
        g.add((node, RDF.type, QUDT.Unit))
        g.add((node, QUDT.symbol, Literal(u.symbol)))
        g.add((node, QUDT.hasQuantityKind, QK[u.quantity_kind]))
        g.add((node, QUDT.conversionMultiplier, Literal(u.multiplier, datatype=XSD.double)))
        g.add((node, QUDT.conversionOffset, Literal(u.offset, datatype=XSD.double)))
        g.add((node, SIO.dimensionVector, Literal(U.format_dimension(u.dimension))))
    for qk, d in U.QUANTITY_KINDS.items():
        g.add((QK[qk], RDF.type, QUDT.QuantityKind))
        g.add((QK[qk], QUDT.hasDimensionVector, Literal(U.format_dimension(d))))

    # --- assets ------------------------------------------------------------
    for a in P.PLANT:
        node = PLANT[a.local_id]
        g.add((node, RDF.type, SIO[a.kind]))
        g.add((node, RDFS.label, Literal(a.name, lang="en")))
        g.add((node, SKOS.notation, Literal(a.local_id)))
        g.add((node, SIO.isa95Level, Literal(a.isa95_level)))
        g.add((node, SIO.criticality, Literal(a.criticality)))
        if a.parent:
            g.add((node, SIO.isPartOf, PLANT[a.parent]))
            g.add((PLANT[a.parent], SIO.hasPart, node))
        if a.location:
            g.add((node, SIO.location, Literal(a.location)))
        if a.commissioned:
            g.add((node, DCTERMS.created, Literal(a.commissioned, datatype=XSD.date)))
        if a.manufacturer != "-":
            g.add((node, SIO.manufacturer, Literal(a.manufacturer)))
            g.add((node, SIO.modelDesignation, Literal(a.model)))
            g.add((node, SIO.serialNumber, Literal(a.serial)))
            g.add((node, SIO.eclassClass, ECLASS[a.eclass_class]))
        if a.packml_capable:
            g.add((node, RDF.type, SIO.PackMLUnit))
            if a.packml_state:
                g.add((node, SIO.packMLState, Literal(a.packml_state)))
                for cmd in sm.legal_commands(a.packml_state):
                    g.add((node, SIO.legalCommand, Literal(cmd)))
        for svc in a.mtp_services:
            g.add((node, SIO.providesService, Literal(svc)))

        # --- signals -------------------------------------------------------
        for s in a.signals:
            sn = PLANT[f"signal/{s.tag}"]
            g.add((node, SIO.hasSignal, sn))
            g.add((sn, RDF.type, SIO.Signal))
            g.add((sn, RDF.type, SOSA.ObservableProperty))
            g.add((sn, SIO.belongsTo, node))
            g.add((sn, SKOS.notation, Literal(s.tag)))
            g.add((sn, RDFS.label, Literal(f"{a.name} - {s.description}", lang="en")))
            g.add((sn, SKOS.altLabel, Literal(s.description, lang="en")))
            g.add((sn, DCTERMS.description, Literal(s.description, lang="en")))
            g.add((sn, SIO.opcuaNodeId, Literal(s.node_id)))
            g.add((sn, QUDT.unit, UNIT[s.unit]))
            g.add((sn, QUDT.hasQuantityKind, QK[s.quantity_kind]))
            g.add((sn, SIO.engineeringLow, Literal(s.eng_low, datatype=XSD.double)))
            g.add((sn, SIO.engineeringHigh, Literal(s.eng_high, datatype=XSD.double)))
            g.add((sn, SIO.accessMode, Literal(s.access)))
            g.add((sn, SIO.signalRole, Literal(s.role)))
            g.add((sn, SIO.safetyCritical, Literal(s.safety_critical, datatype=XSD.boolean)))
            if s.alarm_low is not None:
                g.add((sn, SIO.alarmLow, Literal(s.alarm_low, datatype=XSD.double)))
            if s.alarm_high is not None:
                g.add((sn, SIO.alarmHigh, Literal(s.alarm_high, datatype=XSD.double)))
            if s.brick_class:
                g.add((sn, SIO.brickClass, BRICK[s.brick_class]))
            if s.eclass_irdi:
                g.add((sn, SIO.semanticId, Literal(s.eclass_irdi)))
            if s.aas_id_short:
                g.add((sn, AAS.idShort, Literal(s.aas_id_short)))
            if s.sample_value is not None:
                obs = PLANT[f"obs/{s.tag}"]
                g.add((obs, RDF.type, SOSA.Observation))
                g.add((obs, SOSA.observedProperty, sn))
                g.add((obs, SOSA.hasFeatureOfInterest, node))
                g.add((obs, SOSA.resultTime, Literal("2026-07-14T02:20:00Z", datatype=XSD.dateTime)))
                res = BNode()
                g.add((obs, SOSA.hasResult, res))
                g.add((res, RDF.type, QUDT.QuantityValue))
                g.add((res, QUDT.numericValue, Literal(s.sample_value, datatype=XSD.double)))
                g.add((res, QUDT.unit, UNIT[s.unit]))

    # --- topology -----------------------------------------------------------
    for up, down in P.FEEDS:
        g.add((PLANT[up], SIO.feeds, PLANT[down]))
        g.add((PLANT[down], SIO.isFedBy, PLANT[up]))

    # --- interlocks ---------------------------------------------------------
    for ilk in P.INTERLOCKS:
        n = PLANT[f"interlock/{ilk['id']}"]
        g.add((n, RDF.type, SIO.Interlock))
        g.add((n, RDFS.comment, Literal(ilk["text"], lang="en")))
        g.add((PLANT[f"signal/{ilk['tag']}"], SIO.interlockedBy, n))
        g.add((n, SIO.guardSignal, PLANT[f"signal/{ilk['guard_tag']}"]))
        g.add((n, SIO.guardOperator, Literal(str(ilk["operator"]))))
        thr = ilk["threshold"]
        if isinstance(thr, tuple):
            for t in thr:
                g.add((n, SIO.guardValue, Literal(t)))
        else:
            g.add((n, SIO.guardValue, Literal(thr, datatype=XSD.double)))

    # --- products / recipes -------------------------------------------------
    for pr in P.PRODUCTS:
        n = PLANT[f"product/{pr['id']}"]
        g.add((n, RDF.type, SIO.Product))
        g.add((n, RDFS.label, Literal(pr["name"], lang="en")))
        g.add((n, SIO.producedOn, PLANT[str(pr["line"])]))
        for key, unit_iri in [
            ("fill_volume_ml", "MilliL"),
            ("fill_pressure_bar", "BAR"),
            ("product_temperature_degC", "DEG_C"),
            ("cap_torque_nm", "N-M"),
        ]:
            qv = BNode()
            g.add((n, SIO[key], qv))
            g.add((qv, QUDT.numericValue, Literal(pr[key], datatype=XSD.double)))
            g.add((qv, QUDT.unit, UNIT[unit_iri]))
        g.add((n, SIO.targetRateBPH, Literal(pr["target_rate_bph"], datatype=XSD.integer)))

    # --- events (PROV-O) ----------------------------------------------------
    for ev in P.EVENTS:
        n = PLANT[f"event/{ev['id']}"]
        g.add((n, RDF.type, PROV.Activity))
        g.add((n, RDF.type, SIO[ev["type"]]))
        g.add((n, PROV.startedAtTime, Literal(ev["ts"], datatype=XSD.dateTime)))
        g.add((n, RDFS.comment, Literal(ev["text"], lang="en")))
        g.add((n, PROV.wasAssociatedWith, PLANT[ev["asset"]]))
        g.add((n, SIO.severity, Literal(ev["severity"])))
    return g


# ---------------------------------------------------------------------------
# 2. Asset Administration Shell (IDTA metamodel v3.0)
# ---------------------------------------------------------------------------


def _sem_id(value: str, kind: str = "GlobalReference") -> dict:
    return {"type": "ExternalReference", "keys": [{"type": kind, "value": value}]}


def _property(id_short: str, value, value_type: str, semantic_id: str | None = None,
              unit: str | None = None, description: str | None = None) -> dict:
    el: dict = {
        "modelType": "Property",
        "idShort": id_short,
        "valueType": value_type,
        "value": None if value is None else str(value),
    }
    if semantic_id:
        el["semanticId"] = _sem_id(semantic_id)
    if description:
        el["description"] = [{"language": "en", "text": description}]
    if unit:
        el["embeddedDataSpecifications"] = [{
            "dataSpecification": _sem_id(
                "https://admin-shell.io/DataSpecificationTemplates/DataSpecificationIec61360/3/0"),
            "dataSpecificationContent": {
                "modelType": "DataSpecificationIec61360",
                "preferredName": [{"language": "en", "text": id_short}],
                "unit": unit,
                "dataType": "REAL_MEASURE",
            },
        }]
    return el


def aas_environment() -> dict:
    """An IDTA AAS *Environment* covering every asset of the plant."""
    shells, submodels = [], []
    for a in P.PLANT:
        if not a.signals and a.manufacturer == "-":
            continue
        aas_id = f"https://w3id.org/semindus/aas/{a.local_id}"
        sm_ids: list[str] = []

        # Submodel: Digital Nameplate (IDTA 02006)
        np_id = f"{aas_id}/nameplate"
        sm_ids.append(np_id)
        submodels.append({
            "modelType": "Submodel",
            "id": np_id,
            "idShort": "Nameplate",
            "kind": "Instance",
            "semanticId": _sem_id("https://admin-shell.io/zvei/nameplate/2/0/Nameplate"),
            "submodelElements": [
                _property("ManufacturerName", a.manufacturer, "xs:string",
                          "0173-1#02-AAO677#002"),
                _property("ManufacturerProductDesignation", a.model, "xs:string",
                          "0173-1#02-AAW338#001"),
                _property("SerialNumber", a.serial, "xs:string", "0173-1#02-AAM556#002"),
                _property("YearOfConstruction", (a.commissioned or "")[:4], "xs:string",
                          "0173-1#02-AAP906#001"),
            ],
        })

        # Submodel: Technical Data (IDTA 02003)
        td_id = f"{aas_id}/technicaldata"
        sm_ids.append(td_id)
        submodels.append({
            "modelType": "Submodel",
            "id": td_id,
            "idShort": "TechnicalData",
            "kind": "Instance",
            "semanticId": _sem_id("https://admin-shell.io/ZVEI/TechnicalData/Submodel/1/2"),
            "submodelElements": [{
                "modelType": "SubmodelElementCollection",
                "idShort": "TechnicalProperties",
                "value": [
                    _property(
                        s.aas_id_short or s.tag,
                        s.sample_value,
                        "xs:double",
                        s.eclass_irdi,
                        unit=U.BY_IRI[s.unit].symbol,
                        description=s.description,
                    )
                    for s in a.signals
                ],
            }],
        })

        # Submodel: Operational Data (runtime, AAS Type 2/3)
        if a.signals:
            od_id = f"{aas_id}/operationaldata"
            sm_ids.append(od_id)
            submodels.append({
                "modelType": "Submodel",
                "id": od_id,
                "idShort": "OperationalData",
                "kind": "Instance",
                "semanticId": _sem_id("https://w3id.org/semindus/sm/OperationalData"),
                "submodelElements": [
                    _property(s.tag, s.sample_value, "xs:double", s.eclass_irdi,
                              unit=U.BY_IRI[s.unit].symbol, description=s.description)
                    for s in a.signals
                ] + ([_property("PackMLState", a.packml_state, "xs:string",
                                "https://w3id.org/semindus/sm/PackMLState")]
                     if a.packml_state else []),
            })

        shells.append({
            "modelType": "AssetAdministrationShell",
            "id": aas_id,
            "idShort": a.local_id.replace("-", "_"),
            "assetInformation": {
                "assetKind": "Instance",
                "globalAssetId": f"https://w3id.org/semindus/asset/{a.local_id}",
                "specificAssetIds": [{
                    "name": "SerialNumber", "value": a.serial,
                    "semanticId": _sem_id("0173-1#02-AAM556#002"),
                }],
            },
            "submodels": [_sem_id(i, "Submodel") for i in sm_ids],
        })
    return {"assetAdministrationShells": shells, "submodels": submodels,
            "conceptDescriptions": []}


# ---------------------------------------------------------------------------
# 3. OPC UA NodeSet2 (IEC 62541-6 XML)
# ---------------------------------------------------------------------------

_OPCUA_DATATYPE = {
    "measurement": "i=11",  # Double
    "setpoint": "i=11",
    "kpi": "i=11",
    "state": "i=7",  # UInt32
    "command": "i=7",
}
_ACCESS_LEVEL = {"r": "1", "rw": "3"}


def opcua_nodeset() -> str:
    """A NodeSet2 XML fragment - the exchange format of an OPC UA server."""
    out: list[str] = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<UANodeSet xmlns="http://opcfoundation.org/UA/2011/03/UANodeSet.xsd" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">',
        "  <NamespaceUris><Uri>https://w3id.org/semindus/opcua</Uri></NamespaceUris>",
        "  <Models><Model ModelUri=\"https://w3id.org/semindus/opcua\" "
        "Version=\"1.0.0\" PublicationDate=\"2026-07-14T00:00:00Z\"/></Models>",
    ]
    for a in P.PLANT:
        oid = f"ns=3;s={a.local_id}"
        out.append(f'  <UAObject NodeId="{escape(oid)}" BrowseName="3:{escape(a.local_id)}">')
        out.append(f"    <DisplayName>{escape(a.name)}</DisplayName>")
        out.append(f"    <Description>{escape(a.kind)} at ISA-95 level {a.isa95_level}</Description>")
        out.append("    <References>")
        if a.parent:
            out.append(f'      <Reference ReferenceType="Organizes" IsForward="false">'
                       f"{escape('ns=3;s=' + a.parent)}</Reference>")
        for s in a.signals:
            out.append(f'      <Reference ReferenceType="HasComponent">{escape(s.node_id)}</Reference>')
        out.append("    </References>")
        out.append("  </UAObject>")
        for s in a.signals:
            u = U.BY_IRI[s.unit]
            out.append(
                f'  <UAVariable NodeId="{escape(s.node_id)}" BrowseName="3:{escape(s.tag)}" '
                f'DataType="{_OPCUA_DATATYPE[s.role]}" AccessLevel="{_ACCESS_LEVEL[s.access]}" '
                f'UserAccessLevel="{_ACCESS_LEVEL[s.access]}">'
            )
            out.append(f"    <DisplayName>{escape(s.description)}</DisplayName>")
            out.append(f"    <Description>{escape(s.description)}</Description>")
            out.append("    <References>")
            out.append('      <Reference ReferenceType="HasTypeDefinition">i=2368</Reference>')
            out.append(f'      <Reference ReferenceType="HasComponent" IsForward="false">'
                       f"{escape(oid)}</Reference>")
            out.append('      <Reference ReferenceType="HasProperty">'
                       f"{escape(s.node_id)}.EURange</Reference>")
            out.append('      <Reference ReferenceType="HasProperty">'
                       f"{escape(s.node_id)}.EngineeringUnits</Reference>")
            out.append("    </References>")
            out.append("  </UAVariable>")
            out.append(
                f'  <UAVariable NodeId="{escape(s.node_id)}.EURange" '
                f'BrowseName="EURange" DataType="i=884" ParentNodeId="{escape(s.node_id)}">'
            )
            out.append("    <DisplayName>EURange</DisplayName>")
            out.append("    <Value><ExtensionObject><Body><Range>"
                       f"<Low>{s.eng_low}</Low><High>{s.eng_high}</High>"
                       "</Range></Body></ExtensionObject></Value>")
            out.append("  </UAVariable>")
            out.append(
                f'  <UAVariable NodeId="{escape(s.node_id)}.EngineeringUnits" '
                f'BrowseName="EngineeringUnits" DataType="i=887" ParentNodeId="{escape(s.node_id)}">'
            )
            out.append("    <DisplayName>EngineeringUnits</DisplayName>")
            out.append("    <Value><ExtensionObject><Body><EUInformation>"
                       "<NamespaceUri>http://www.opcfoundation.org/UA/units/un/cefact</NamespaceUri>"
                       f"<DisplayName><Text>{escape(u.symbol)}</Text></DisplayName>"
                       f"<Description><Text>{escape(u.quantity_kind)}</Text></Description>"
                       "</EUInformation></Body></ExtensionObject></Value>")
            out.append("  </UAVariable>")
    out.append("</UANodeSet>")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# 4. W3C WoT Thing Descriptions
# ---------------------------------------------------------------------------


def wot_thing_descriptions() -> list[dict]:
    tds = []
    for a in P.PLANT:
        if not a.signals:
            continue
        props: dict[str, dict] = {}
        actions: dict[str, dict] = {}
        for s in a.signals:
            u = U.BY_IRI[s.unit]
            entry = {
                "title": s.description,
                "type": "number",
                "unit": f"qudt:{s.unit}",
                "minimum": s.eng_low,
                "maximum": s.eng_high,
                "readOnly": s.access == "r",
                "observable": True,
                "@type": f"qk:{s.quantity_kind}",
                "forms": [{
                    "href": f"opc.tcp://plant.example/{s.node_id}",
                    "op": ["readproperty"] + (["writeproperty"] if s.access == "rw" else []),
                    "contentType": "application/opcua+json",
                }],
            }
            props[s.tag] = entry
        if a.packml_capable:
            actions["packmlCommand"] = {
                "title": "PackML unit command",
                "input": {"type": "string", "enum": list(sm.COMMANDS)},
                "forms": [{"href": f"opc.tcp://plant.example/ns=3;s={a.local_id}.UNIT.CMD",
                           "op": ["invokeaction"]}],
            }
        tds.append({
            "@context": [
                "https://www.w3.org/2022/wot/td/v1.1",
                {"qudt": "http://qudt.org/vocab/unit/",
                 "qk": "http://qudt.org/vocab/quantitykind/",
                 "sio": "https://w3id.org/semindus/ontology#"},
            ],
            "@type": ["Thing", f"sio:{a.kind}"],
            "id": f"urn:semindus:{a.local_id}",
            "title": a.name,
            "description": f"{a.kind} - ISA-95 {a.isa95_level}",
            "securityDefinitions": {"nosec_sc": {"scheme": "nosec"}},
            "security": "nosec_sc",
            "properties": props,
            "actions": actions,
        })
    return tds


# ---------------------------------------------------------------------------
# 5. NGSI-LD entities (ETSI GS CIM 009)
# ---------------------------------------------------------------------------


def ngsild_entities() -> list[dict]:
    ents = []
    for a in P.PLANT:
        ent: dict = {
            "id": f"urn:ngsi-ld:{a.kind}:{a.local_id}",
            "type": a.kind,
            "name": {"type": "Property", "value": a.name},
            "isa95Level": {"type": "Property", "value": a.isa95_level},
            "@context": [
                "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context-v1.7.jsonld",
                {"sio": "https://w3id.org/semindus/ontology#"},
            ],
        }
        if a.parent:
            ent["isPartOf"] = {"type": "Relationship",
                               "object": f"urn:ngsi-ld:Asset:{a.parent}"}
        for s in a.signals:
            ent[s.aas_id_short or s.tag] = {
                "type": "Property",
                "value": s.sample_value,
                "unitCode": U.BY_IRI[s.unit].symbol,
                "observedAt": "2026-07-14T02:20:00Z",
                "sourceTag": {"type": "Property", "value": s.tag},
            }
        ents.append(ent)
    return ents


# ---------------------------------------------------------------------------
# 6. The un-semantic baseline: a historian tag export
# ---------------------------------------------------------------------------


def flat_tag_table() -> list[dict[str, str]]:
    """What an agent gets from a plain historian/SCADA export: name + text."""
    rows = []
    for a in P.PLANT:
        for s in a.signals:
            rows.append({
                "TagName": s.tag,
                "Description": s.description,
                "EngUnits": U.BY_IRI[s.unit].symbol,
                "Value": "" if s.sample_value is None else f"{s.sample_value:g}",
            })
    return rows


def flat_tag_csv() -> str:
    rows = flat_tag_table()
    head = ",".join(rows[0].keys())
    body = "\n".join(",".join(f'"{r[k]}"' for k in rows[0]) for r in rows)
    return head + "\n" + body


def serialise_all(outdir) -> dict[str, int]:
    """Write every representation to ``outdir``; return byte sizes."""
    from pathlib import Path

    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    g = build_graph()
    artefacts = {
        "plant.ttl": g.serialize(format="turtle"),
        "plant.nt": g.serialize(format="nt"),
        "plant.jsonld": g.serialize(format="json-ld", indent=2),
        "plant.aas.json": json.dumps(aas_environment(), indent=2),
        "plant.nodeset2.xml": opcua_nodeset(),
        "plant.wot.json": json.dumps(wot_thing_descriptions(), indent=2),
        "plant.ngsild.json": json.dumps(ngsild_entities(), indent=2),
        "plant.tags.csv": flat_tag_csv(),
    }
    sizes = {}
    for name, text in artefacts.items():
        path = outdir / name
        path.write_text(text, encoding="utf-8")
        sizes[name] = len(text)
    return sizes
