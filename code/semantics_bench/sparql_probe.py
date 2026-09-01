"""Experiment E7: answer by *query*, not by stuffing the context window.

Aggregate questions ("which tags are outside their limits?", "what is the total
power of the utilities area?") are the ones that break context-stuffing: the
evidence is spread over the whole plant, so no top-*k* retrieval fits it in a
window.  A knowledge graph offers a second option the flat representations do
not have - push the aggregation into the query engine and return only the
answer set.  This module runs the actual SPARQL and measures both sides.
"""

from __future__ import annotations

from dataclasses import dataclass

from rdflib import Graph

from .kg import build_graph
from .metrics import surrogate_tokens
from .vocab import SPARQL_PROLOGUE

QUERIES: dict[str, tuple[str, str]] = {
    "UNI-05": (
        "Total electrical power drawn by the utilities area, unit-normalised",
        """
        SELECT (SUM(?watt)/1000 AS ?kW) WHERE {
          ?a sio:isPartOf plant:AREA-UTIL ; sio:hasSignal ?s .
          ?s qudt:hasQuantityKind qk:Power ; qudt:unit ?u .
          ?u qudt:conversionMultiplier ?m .
          ?o sosa:observedProperty ?s ; sosa:hasResult ?r .
          ?r qudt:numericValue ?v .
          BIND (?v * ?m AS ?watt)
        }""",
    ),
    "RNG-04": (
        "Every tag in the plant whose latest observation violates an alarm limit",
        """
        SELECT ?tag ?v ?lo ?hi WHERE {
          ?a sio:isPartOf+ plant:SITE-KA ; sio:hasSignal ?s .
          ?s skos:notation ?tag .
          ?o sosa:observedProperty ?s ; sosa:hasResult ?r .
          ?r qudt:numericValue ?v .
          OPTIONAL { ?s sio:alarmLow  ?lo }
          OPTIONAL { ?s sio:alarmHigh ?hi }
          FILTER ((BOUND(?lo) && ?v < ?lo) || (BOUND(?hi) && ?v > ?hi))
        } ORDER BY ?tag""",
    ),
    "TOP-02": (
        "Transitive downstream closure of the Line 1 pasteuriser",
        """
        SELECT ?label WHERE {
          plant:L1-PAS sio:feeds+ ?d . ?d rdfs:label ?label .
        } ORDER BY ?label""",
    ),
    "TOP-03": (
        "Every asset belonging to Bottling Line 1",
        """
        SELECT ?id ?label WHERE {
          ?a sio:isPartOf plant:L1 ; skos:notation ?id ; rdfs:label ?label .
        } ORDER BY ?id""",
    ),
    "ACT-04": (
        "Line 1 units that accept Start in their current PackML state",
        """
        SELECT ?id ?state WHERE {
          ?a sio:isPartOf plant:L1 ; skos:notation ?id ;
             sio:packMLState ?state ; sio:legalCommand "Start" .
        } ORDER BY ?id""",
    ),
    "SAF-04": (
        "Writable Line 1 tags protected by an interlock",
        """
        SELECT ?tag ?text WHERE {
          ?a sio:isPartOf plant:L1 ; sio:hasSignal ?s .
          ?s skos:notation ?tag ; sio:accessMode "rw" ; sio:interlockedBy ?i .
          ?i rdfs:comment ?text .
        } ORDER BY ?tag""",
    ),
    "PRV-04": (
        "Alarms upstream of the Line 1 capper in the preceding five minutes",
        """
        SELECT ?ev ?ts ?text WHERE {
          ?up sio:feeds* plant:L1-CAP .
          ?e prov:wasAssociatedWith ?up ; prov:startedAtTime ?ts ;
             rdfs:comment ?text .
          BIND (STRAFTER(STR(?e), "event/") AS ?ev)
          FILTER (?ts >= "2026-07-14T02:09:00Z"^^xsd:dateTime &&
                  ?ts <= "2026-07-14T02:16:00Z"^^xsd:dateTime)
        } ORDER BY ?ts""",
    ),
    "GRD-01": (
        "Grounded lookup of one homograph-laden mention",
        """
        SELECT ?tag ?v ?sym WHERE {
          plant:L1-FIL sio:hasSignal ?s .
          ?s skos:notation ?tag ; skos:altLabel "Outlet pressure"@en ; qudt:unit ?u .
          ?u qudt:symbol ?sym .
          ?o sosa:observedProperty ?s ; sosa:hasResult ?r . ?r qudt:numericValue ?v .
        }""",
    ),
}


@dataclass
class QueryRow:
    task: str
    description: str
    query_tokens: int
    result_rows: int
    result_tokens: int
    total_tokens: int
    answer: str


def _format(rows) -> str:
    out = []
    for row in rows:
        out.append(" | ".join(str(v) for v in row))
    return "\n".join(out)


def run(graph: Graph | None = None) -> list[QueryRow]:
    g = graph if graph is not None else build_graph()
    out: list[QueryRow] = []
    for tid, (desc, body) in QUERIES.items():
        query = SPARQL_PROLOGUE + "\n" + body
        rows = list(g.query(query))
        text = _format(rows)
        qt = surrogate_tokens(body)
        rt = surrogate_tokens(text)
        out.append(QueryRow(tid, desc, qt, len(rows), rt, qt + rt,
                            text.replace("\n", " ; ")[:180]))
    return out
