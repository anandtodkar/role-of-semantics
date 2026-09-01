"""Namespaces and identifier helpers for the industrial semantic layers.

Wherever a real, dereferenceable vocabulary exists we use its official IRI so
that the generated graph is genuinely interoperable (QUDT, SOSA/SSN, SHACL,
Brick, SAREF, AAS, OPC UA).  Constructs that have no RDF-native publication
(ISA-95 equipment hierarchy, PackML state machine, MTP services) are minted in
a local ontology namespace that documents the intended alignment.
"""

from __future__ import annotations

from rdflib import Namespace
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS, SH, SKOS, XSD

# --- Local ontology (alignment layer used by this study) -------------------
SIO = Namespace("https://w3id.org/semindus/ontology#")  # Semantic INDUStrial ont.
PLANT = Namespace("https://w3id.org/semindus/plant/")  # ABox / instances
SHP = Namespace("https://w3id.org/semindus/shapes#")

# --- External, standardised vocabularies -----------------------------------
QUDT = Namespace("http://qudt.org/schema/qudt/")
UNIT = Namespace("http://qudt.org/vocab/unit/")
QK = Namespace("http://qudt.org/vocab/quantitykind/")
SOSA = Namespace("http://www.w3.org/ns/sosa/")
SSN = Namespace("http://www.w3.org/ns/ssn/")
SSN_SYSTEM = Namespace("http://www.w3.org/ns/ssn/systems/")
BRICK = Namespace("https://brickschema.org/schema/Brick#")
SAREF = Namespace("https://saref.etsi.org/core/")
S4INMA = Namespace("https://saref.etsi.org/saref4inma/")
TIME = Namespace("http://www.w3.org/2006/time#")
PROV = Namespace("http://www.w3.org/ns/prov#")
DCAT = Namespace("http://www.w3.org/ns/dcat#")
ODRL = Namespace("http://www.w3.org/ns/odrl/2/")

# Asset Administration Shell (IDTA / admin-shell.io)
AAS = Namespace("https://admin-shell.io/aas/3/0/")
IDTA = Namespace("https://admin-shell.io/idta/")

# OPC UA (IEC 62541)
OPCUA = Namespace("http://opcfoundation.org/UA/")

# W3C Web of Things
TD = Namespace("https://www.w3.org/2019/wot/td#")
JSONSCHEMA = Namespace("https://www.w3.org/2019/wot/json-schema#")

# ECLASS / IEC CDD are identified by IRDIs; we expose them as a resolvable stub
ECLASS = Namespace("https://api.eclass-cdp.com/0173-1%2301-")

PREFIXES: dict[str, Namespace] = {
    "sio": SIO,
    "plant": PLANT,
    "shp": SHP,
    "qudt": QUDT,
    "unit": UNIT,
    "qk": QK,
    "sosa": SOSA,
    "ssn": SSN,
    "brick": BRICK,
    "saref": SAREF,
    "s4inma": S4INMA,
    "time": TIME,
    "prov": PROV,
    "dcat": DCAT,
    "odrl": ODRL,
    "aas": AAS,
    "idta": IDTA,
    "opcua": OPCUA,
    "td": TD,
    "jsonschema": JSONSCHEMA,
    "eclass": ECLASS,
    "sh": SH,
    "skos": SKOS,
    "owl": OWL,
    "rdf": RDF,
    "rdfs": RDFS,
    "xsd": XSD,
    "dcterms": DCTERMS,
}

SPARQL_PROLOGUE = "\n".join(
    f"PREFIX {p}: <{str(ns)}>" for p, ns in PREFIXES.items()
)


def bind_all(graph) -> None:
    """Bind every known prefix on an ``rdflib.Graph`` for readable serialisation."""
    for prefix, ns in PREFIXES.items():
        graph.bind(prefix, ns, override=True)


def irdi(code: str) -> str:
    """Return an ECLASS/IEC-61360 IRDI string.

    IRDIs (ISO/IEC 11179-6, ISO 29002-5) are the *semanticId* currency of the
    Asset Administration Shell and of ECLASS. Format::

        <RAI>#<CSI>-<item code>#<version>
        0173-1#02-AAO677#002   (ECLASS property "ManufacturerName")
        0112/2///61987#ABA565  (IEC CDD property)
    """
    return code
