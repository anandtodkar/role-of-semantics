"""SHACL shapes that turn an agent's proposed action into a *checkable* claim.

The shapes below validate an **action graph** - the RDF lifting of whatever the
LLM agent decided to do - against the plant knowledge graph.  This is the
neuro-symbolic pattern evaluated in Experiment E4: generation stays statistical,
acceptance becomes deductive.

Constraint families, in increasing order of the semantic assets they consume:

===========================  =========================================
constraint                    semantic asset required
===========================  =========================================
existence of the target       an identifier system (IRI / NodeId / IRDI)
cardinality & datatype        a typed information model (OPC UA, AAS)
engineering range             ``EURange`` / AAS value constraints
**dimensional compatibility** QUDT quantity kinds + dimension vectors
**unit-aware range**          QUDT affine conversion (multiplier/offset)
write permission              OPC UA ``AccessLevel`` / AAS ``kind``
ISA-95 scope containment      a mereological hierarchy (transitive)
**interlock guard**           an explicit constraint model in the KG
**PackML legality**           an explicit behavioural model
freshness                     provenance / observation timestamps
===========================  =========================================
"""

from __future__ import annotations

from rdflib import Graph

from .vocab import SPARQL_PROLOGUE, bind_all

SHAPES_TTL = """
@prefix sh:    <http://www.w3.org/ns/shacl#> .
@prefix xsd:   <http://www.w3.org/2001/XMLSchema#> .
@prefix rdfs:  <http://www.w3.org/2000/01/rdf-schema#> .
@prefix sio:   <https://w3id.org/semindus/ontology#> .
@prefix shp:   <https://w3id.org/semindus/shapes#> .
@prefix qudt:  <http://qudt.org/schema/qudt/> .

shp:SignalShape a sh:NodeShape ;
    sh:targetClass sio:Signal ;
    sh:property [ sh:path qudt:unit ;            sh:minCount 1 ; sh:maxCount 1 ;
                  sh:message "F-META: signal has no unit of measure" ] ;
    sh:property [ sh:path qudt:hasQuantityKind ; sh:minCount 1 ;
                  sh:message "F-META: signal has no quantity kind" ] ;
    sh:property [ sh:path sio:accessMode ;       sh:minCount 1 ;
                  sh:in ( "r" "rw" ) ;
                  sh:message "F-META: signal has no / invalid access mode" ] .

########################################################################
#  Setpoint write actions
########################################################################

shp:SetpointWriteShape a sh:NodeShape ;
    sh:targetClass sio:SetpointWrite ;

    sh:property [ sh:path sio:targetSignal ; sh:minCount 1 ; sh:maxCount 1 ;
                  sh:class sio:Signal ;
                  sh:message "F-REF: target signal does not exist in the plant model" ] ;
    sh:property [ sh:path sio:value ; sh:minCount 1 ; sh:maxCount 1 ;
                  sh:datatype xsd:double ;
                  sh:message "F-CARD: missing or non-numeric value" ] ;
    sh:property [ sh:path sio:valueUnit ; sh:minCount 1 ; sh:maxCount 1 ;
                  sh:nodeKind sh:IRI ;
                  sh:message "F-CARD: missing unit on the proposed value" ] ;

    # --- writability -------------------------------------------------
    sh:sparql [ a sh:SPARQLConstraint ;
        sh:message "F-ACC: {?sigtag} is read-only (AccessLevel=CurrentRead)" ;
        sh:prefixes shp:prefixes ;
        sh:select \"\"\"
            SELECT $this ?sigtag WHERE {
                $this sio:targetSignal ?sig .
                ?sig sio:accessMode "r" ; skos:notation ?sigtag .
            }\"\"\" ] ;

    # --- dimensional compatibility (QUDT dimension vectors) -----------
    sh:sparql [ a sh:SPARQLConstraint ;
        sh:message "F-DIM: unit dimension {?du} does not match signal dimension {?ds} for {?sigtag}" ;
        sh:prefixes shp:prefixes ;
        sh:select \"\"\"
            SELECT $this ?du ?ds ?sigtag WHERE {
                $this sio:targetSignal ?sig ; sio:valueUnit ?u .
                ?sig qudt:unit ?su ; skos:notation ?sigtag .
                ?u  sio:dimensionVector ?du .
                ?su sio:dimensionVector ?ds .
                FILTER (?du != ?ds)
            }\"\"\" ] ;

    # --- unit-aware engineering range --------------------------------
    sh:sparql [ a sh:SPARQLConstraint ;
        sh:message "F-RANGE: {?conv} is outside the engineering range [{?lo},{?hi}] of {?sigtag}" ;
        sh:prefixes shp:prefixes ;
        sh:select \"\"\"
            SELECT $this ?conv ?lo ?hi ?sigtag WHERE {
                $this sio:targetSignal ?sig ; sio:value ?v ; sio:valueUnit ?u .
                ?sig qudt:unit ?su ; sio:engineeringLow ?lo ; sio:engineeringHigh ?hi ;
                     skos:notation ?sigtag .
                ?u  qudt:conversionMultiplier ?mu ; qudt:conversionOffset ?ou ;
                    sio:dimensionVector ?du .
                ?su qudt:conversionMultiplier ?ms ; qudt:conversionOffset ?os ;
                    sio:dimensionVector ?ds .
                FILTER (?du = ?ds)
                BIND ((((?v * ?mu) + ?ou) - ?os) / ?ms AS ?conv)
                FILTER (?conv < ?lo || ?conv > ?hi)
            }\"\"\" ] ;

    # --- ISA-95 scope containment ------------------------------------
    sh:sparql [ a sh:SPARQLConstraint ;
        sh:message "F-SCOPE: {?sigtag} is not inside the authorised scope {?scope}" ;
        sh:prefixes shp:prefixes ;
        sh:select \"\"\"
            SELECT $this ?sigtag ?scope WHERE {
                $this sio:targetSignal ?sig ; sio:scopeAsset ?scope .
                ?sig skos:notation ?sigtag .
                FILTER NOT EXISTS { ?sig sio:belongsTo/sio:isPartOf* ?scope }
            }\"\"\" ] ;

    # --- numeric interlock guard -------------------------------------
    sh:sparql [ a sh:SPARQLConstraint ;
        sh:message "F-ILK: interlock violated - {?text} (guard reads {?gv})" ;
        sh:prefixes shp:prefixes ;
        sh:select \"\"\"
            SELECT $this ?text ?gv WHERE {
                $this sio:targetSignal ?sig .
                ?sig sio:interlockedBy ?ilk .
                ?ilk sio:guardOperator ">=" ; sio:guardValue ?thr ;
                     sio:guardSignal ?gsig ; rdfs:comment ?text .
                ?obs sosa:observedProperty ?gsig ; sosa:hasResult ?res .
                ?res qudt:numericValue ?gv .
                FILTER (?gv < ?thr)
            }\"\"\" ] ;

    # --- state-dependent interlock (PackML) ---------------------------
    sh:sparql [ a sh:SPARQLConstraint ;
        sh:message "F-ILK: interlock violated - {?text} (unit is in state {?state})" ;
        sh:prefixes shp:prefixes ;
        sh:select \"\"\"
            SELECT $this ?text ?state WHERE {
                $this sio:targetSignal ?sig .
                ?sig sio:interlockedBy ?ilk .
                ?ilk sio:guardSignal ?gsig ; rdfs:comment ?text ;
                     sio:guardOperator ?op .
                ?gsig sio:belongsTo ?asset .
                ?asset sio:packMLState ?state .
                FILTER (?op = "state_in" || ?op = "state_not_in")
                OPTIONAL { ?ilk sio:guardValue ?state . BIND (true AS ?listed) }
                FILTER ((?op = "state_in"     && !BOUND(?listed)) ||
                        (?op = "state_not_in" &&  BOUND(?listed)))
            }\"\"\" ] ;

    # --- evidence freshness ------------------------------------------
    sh:sparql [ a sh:SPARQLConstraint ;
        sh:message "F-STALE: decision is based on evidence from {?et}, older than the 15-minute window" ;
        sh:prefixes shp:prefixes ;
        sh:select \"\"\"
            SELECT $this ?et WHERE {
                $this sio:evidenceTime ?et .
                FILTER (?et < "2026-07-14T02:05:00Z"^^xsd:dateTime)
            }\"\"\" ] .

########################################################################
#  PackML unit commands
########################################################################

shp:UnitCommandShape a sh:NodeShape ;
    sh:targetClass sio:UnitCommand ;

    sh:property [ sh:path sio:targetAsset ; sh:minCount 1 ; sh:maxCount 1 ;
                  sh:nodeKind sh:IRI ;
                  sh:message "F-CARD: missing target asset" ] ;
    sh:property [ sh:path sio:command ; sh:minCount 1 ; sh:maxCount 1 ;
                  sh:in ( "Reset" "Start" "Stop" "Hold" "Unhold" "Suspend"
                          "Unsuspend" "Abort" "Clear" ) ;
                  sh:message "F-ENUM: not a PackML command" ] ;

    sh:sparql [ a sh:SPARQLConstraint ;
        sh:message "F-REF: target asset is not a PackML-capable unit" ;
        sh:prefixes shp:prefixes ;
        sh:select \"\"\"
            SELECT $this WHERE {
                $this sio:targetAsset ?a .
                FILTER NOT EXISTS { ?a a sio:PackMLUnit }
            }\"\"\" ] ;

    sh:sparql [ a sh:SPARQLConstraint ;
        sh:message "F-STATE: command {?cmd} is illegal while {?a} is in PackML state {?state}" ;
        sh:prefixes shp:prefixes ;
        sh:select \"\"\"
            SELECT $this ?cmd ?state ?a WHERE {
                $this sio:targetAsset ?a ; sio:command ?cmd .
                ?a a sio:PackMLUnit ; sio:packMLState ?state .
                FILTER NOT EXISTS { ?a sio:legalCommand ?cmd }
            }\"\"\" ] .

########################################################################
#  Grounded numeric answers (report / analytics actions)
########################################################################

shp:AnswerShape a sh:NodeShape ;
    sh:targetClass sio:GroundedAnswer ;
    sh:property [ sh:path sio:aboutSignal ; sh:minCount 1 ; sh:class sio:Signal ;
                  sh:message "F-REF: answer references a signal that does not exist" ] ;
    sh:property [ sh:path sio:answerUnit ; sh:minCount 1 ; sh:nodeKind sh:IRI ;
                  sh:message "F-CARD: numeric answer carries no unit" ] ;
    sh:sparql [ a sh:SPARQLConstraint ;
        sh:message "F-DIM: reported unit is dimensionally incompatible with {?sigtag}" ;
        sh:prefixes shp:prefixes ;
        sh:select \"\"\"
            SELECT $this ?sigtag WHERE {
                $this sio:aboutSignal ?sig ; sio:answerUnit ?u .
                ?sig qudt:unit ?su ; skos:notation ?sigtag .
                ?u sio:dimensionVector ?du . ?su sio:dimensionVector ?ds .
                FILTER (?du != ?ds)
            }\"\"\" ] ;
    sh:sparql [ a sh:SPARQLConstraint ;
        sh:message "F-VALUE: reported value {?v} disagrees with the observation {?obsv} for {?sigtag}" ;
        sh:prefixes shp:prefixes ;
        sh:select \"\"\"
            SELECT $this ?v ?obsv ?sigtag WHERE {
                $this sio:aboutSignal ?sig ; sio:answerValue ?v ; sio:answerUnit ?u .
                ?sig qudt:unit ?su ; skos:notation ?sigtag .
                ?obs sosa:observedProperty ?sig ; sosa:hasResult ?res .
                ?res qudt:numericValue ?obsv .
                ?u  qudt:conversionMultiplier ?mu ; qudt:conversionOffset ?ou ;
                    sio:dimensionVector ?du .
                ?su qudt:conversionMultiplier ?ms ; qudt:conversionOffset ?os ;
                    sio:dimensionVector ?ds .
                FILTER (?du = ?ds)
                BIND ((((?v * ?mu) + ?ou) - ?os) / ?ms AS ?conv)
                FILTER (abs(?conv - ?obsv) > 0.01 * abs(?obsv) + 1e-9)
            }\"\"\" ] .
"""

_PREFIX_DECLS = """
@prefix sh:    <http://www.w3.org/ns/shacl#> .
@prefix shp:   <https://w3id.org/semindus/shapes#> .

shp:prefixes
    sh:declare [ sh:prefix "sio"   ; sh:namespace "https://w3id.org/semindus/ontology#"^^<http://www.w3.org/2001/XMLSchema#anyURI> ] ;
    sh:declare [ sh:prefix "qudt"  ; sh:namespace "http://qudt.org/schema/qudt/"^^<http://www.w3.org/2001/XMLSchema#anyURI> ] ;
    sh:declare [ sh:prefix "unit"  ; sh:namespace "http://qudt.org/vocab/unit/"^^<http://www.w3.org/2001/XMLSchema#anyURI> ] ;
    sh:declare [ sh:prefix "sosa"  ; sh:namespace "http://www.w3.org/ns/sosa/"^^<http://www.w3.org/2001/XMLSchema#anyURI> ] ;
    sh:declare [ sh:prefix "skos"  ; sh:namespace "http://www.w3.org/2004/02/skos/core#"^^<http://www.w3.org/2001/XMLSchema#anyURI> ] ;
    sh:declare [ sh:prefix "rdfs"  ; sh:namespace "http://www.w3.org/2000/01/rdf-schema#"^^<http://www.w3.org/2001/XMLSchema#anyURI> ] ;
    sh:declare [ sh:prefix "xsd"   ; sh:namespace "http://www.w3.org/2001/XMLSchema#"^^<http://www.w3.org/2001/XMLSchema#anyURI> ] .
"""


def shapes_graph() -> Graph:
    g = Graph()
    bind_all(g)
    g.parse(data=_PREFIX_DECLS, format="turtle")
    g.parse(data=SHAPES_TTL, format="turtle")
    return g


#: Constraint families, tagged by the message prefix they emit, together with
#: the *minimum* semantic layer that makes the check possible at all.
CONSTRAINT_LAYERS: dict[str, str] = {
    "F-CARD": "L1 typed information model",
    "F-ENUM": "L1 typed information model",
    "F-REF": "L0 global identifier system",
    "F-ACC": "L1 typed information model",
    "F-RANGE": "L1 + L3 (range + unit conversion)",
    "F-DIM": "L3 unit/quantity ontology (QUDT)",
    "F-SCOPE": "L2 formal graph (transitive mereology)",
    "F-ILK": "L2 explicit constraint model",
    "F-STATE": "L1 behavioural model (PackML)",
    "F-STALE": "L2 provenance",
    "F-VALUE": "L2 grounded observation",
    "F-META": "L1 metadata completeness",
}

__all__ = ["SHAPES_TTL", "shapes_graph", "CONSTRAINT_LAYERS", "SPARQL_PROLOGUE"]
