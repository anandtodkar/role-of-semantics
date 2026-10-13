"""Provenance-preserving projections for a supplied OPC UA NodeSet bundle.

This module handles a concrete instance NodeSet and companion model NodeSets.
It does not connect to OPC UA, repair NodeIds, infer missing engineering facts,
or run the synthetic reference-plant benchmark against this case.
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

import rdflib
from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.compare import isomorphic
from rdflib.namespace import RDF, XSD

from .metrics import surrogate_tokens

NODESET_NS = "http://opcfoundation.org/UA/2011/03/UANodeSet.xsd"
UA_CORE_URI = "http://opcfoundation.org/UA/"
UA = Namespace("https://w3id.org/semindus/opcua-instance#")


def _tag_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _qname(local: str) -> str:
    return f"{{{NODESET_NS}}}{local}"


def _safe_id(text: str) -> str:
    value = re.sub(r"\W+", "_", text, flags=re.ASCII).strip("_")
    if not value or not value[0].isalpha():
        value = "N_" + value
    return value[:80]


def _expanded_node_id(namespace_uri: str, identifier: str) -> str:
    return f"nsu={namespace_uri};{identifier}"


def node_iri(expanded_node_id: str) -> URIRef:
    namespace_uri, identifier = expanded_node_id.removeprefix("nsu=").split(";", 1)
    return URIRef(f"urn:opcua-node:{quote(namespace_uri, safe='')}:{quote(identifier, safe='')}")


@dataclass(frozen=True)
class NodeSetDocument:
    role: str
    path: Path
    sha256: str
    last_modified: str | None
    namespaces: tuple[str, ...]
    aliases: dict[str, str]
    models: tuple[dict[str, Any], ...]
    nodes: tuple[dict[str, Any], ...]

    @property
    def namespace_by_index(self) -> dict[int, str]:
        return {0: UA_CORE_URI, **dict(enumerate(self.namespaces, 1))}


def _resolve_node_id(raw: str | None, document: NodeSetDocument | None = None,
                     namespace_by_index: dict[int, str] | None = None,
                     aliases: dict[str, str] | None = None) -> dict[str, Any] | None:
    if raw is None:
        return None
    value = (aliases or (document.aliases if document else {})).get(raw, raw)
    if value.startswith("ns="):
        head, identifier = value.split(";", 1)
        index = int(head[3:])
    else:
        index, identifier = 0, value
    uri_map = namespace_by_index or (document.namespace_by_index if document else {0: UA_CORE_URI})
    namespace_uri = uri_map.get(index)
    return {
        "raw": raw,
        "resolvedRaw": value,
        "namespaceIndex": index,
        "namespaceUri": namespace_uri,
        "identifier": identifier,
        "expanded": _expanded_node_id(namespace_uri, identifier) if namespace_uri else None,
    }


def _qualified_name(raw: str | None, namespace_by_index: dict[int, str]) -> dict[str, Any] | None:
    if raw is None:
        return None
    prefix, separator, name = raw.partition(":")
    if separator and prefix.isdigit():
        index = int(prefix)
        local_name = name
    else:
        index = 0
        local_name = raw
    return {"raw": raw, "namespaceIndex": index,
            "namespaceUri": namespace_by_index.get(index), "name": local_name}


def _decode_scalar(element: ET.Element, local: str) -> Any:
    text = (element.text or "").strip()
    if local == "Boolean":
        return text.lower() == "true"
    if local in {"SByte", "Byte", "Int16", "UInt16", "Int32", "UInt32", "Int64", "UInt64"}:
        try:
            return int(text)
        except ValueError:
            return text
    if local in {"Float", "Double"}:
        try:
            return float(text)
        except ValueError:
            return text
    return text


def _decode_children(local: str, children: list[ET.Element]) -> Any:
    if local == "LocalizedText":
        return {_tag_name(child.tag): _decode_value_element(child) for child in children}
    if local.startswith("ListOf"):
        return [_decode_value_element(child) for child in children]
    if local == "ExtensionObject":
        return {_tag_name(child.tag): _decode_value_element(child[0] if _tag_name(child.tag) == "Body" and len(child) else child)
                for child in children}
    output: dict[str, Any] = {}
    for child in children:
        child_name = _tag_name(child.tag)
        child_value = _decode_value_element(child)
        if child_name in output:
            previous = output[child_name]
            output[child_name] = previous + [child_value] if isinstance(previous, list) else [previous, child_value]
        else:
            output[child_name] = child_value
    return output


def _decode_value_element(element: ET.Element) -> Any:
    if element.attrib.get("{http://www.w3.org/2001/XMLSchema-instance}nil") == "true":
        return None
    local = _tag_name(element.tag)
    children = list(element)
    if not children:
        return [] if local.startswith("ListOf") else _decode_scalar(element, local)
    return _decode_children(local, children)


def _parse_node(element: ET.Element, document: NodeSetDocument) -> dict[str, Any]:
    namespaces = document.namespace_by_index
    node_id = _resolve_node_id(element.get("NodeId"), document)
    datatype = _resolve_node_id(element.get("DataType"), document)
    parent = _resolve_node_id(element.get("ParentNodeId"), document)
    browse_name = _qualified_name(element.get("BrowseName"), namespaces)
    display_name = element.find(_qname("DisplayName"))
    description = element.find(_qname("Description"))
    value_element = element.find(_qname("Value"))
    decoded_value = None
    if value_element is not None and len(value_element):
        decoded_value = _decode_value_element(value_element[0])
    elif value_element is not None:
        decoded_value = value_element.text
    references = []
    for reference in element.findall(f"{_qname('References')}/{_qname('Reference')}"):
        references.append({
            "referenceType": _resolve_node_id(reference.get("ReferenceType"), document),
            "isForward": reference.get("IsForward", "true").lower() != "false",
            "target": _resolve_node_id((reference.text or "").strip(), document),
        })
    extensions = []
    for extension in element.findall(f"{_qname('Extensions')}/{_qname('Extension')}"):
        extensions.extend(ET.tostring(child, encoding="unicode") for child in extension)
    standard_children = {"References", "DisplayName", "Description", "Value", "Extensions"}
    additional_metadata = [ET.tostring(child, encoding="unicode") for child in element
                           if _tag_name(child.tag) not in standard_children]
    return {
        "sourceRole": document.role,
        "nodeClass": _tag_name(element.tag),
        "nodeId": node_id,
        "parentNodeId": parent,
        "browseName": browse_name,
        "displayName": display_name.text if display_name is not None else None,
        "description": description.text if description is not None else None,
        "symbolicName": element.get("SymbolicName"),
        "dataType": datatype,
        "valueRank": element.get("ValueRank"),
        "arrayDimensions": element.get("ArrayDimensions"),
        "attributes": dict(element.attrib),
        "value": decoded_value,
        "valueXml": ET.tostring(value_element, encoding="unicode") if value_element is not None else None,
        "references": references,
        "extensionsXml": extensions,
        "additionalMetadataXml": additional_metadata,
    }


def parse_nodeset(path: str | Path, role: str) -> NodeSetDocument:
    source_path = Path(path)
    raw_bytes = source_path.read_bytes()
    root = ET.fromstring(raw_bytes)
    namespaces = tuple(uri.text or "" for uri in root.findall(f"{_qname('NamespaceUris')}/{_qname('Uri')}"))
    aliases = {alias.get("Alias", ""): alias.text or ""
               for alias in root.findall(f"{_qname('Aliases')}/{_qname('Alias')}")}
    models = []
    for model in root.findall(f"{_qname('Models')}/{_qname('Model')}"):
        models.append({
            "modelUri": model.get("ModelUri"),
            "version": model.get("Version"),
            "publicationDate": model.get("PublicationDate"),
            "requiredModels": [{"modelUri": required.get("ModelUri"),
                                "version": required.get("Version"),
                                "publicationDate": required.get("PublicationDate")}
                               for required in model.findall(_qname("RequiredModel"))],
        })
    last_modified = root.get("LastModified")
    document = NodeSetDocument(role, source_path, hashlib.sha256(raw_bytes).hexdigest(),
                               last_modified, namespaces, aliases, tuple(models), ())
    nodes = tuple(_parse_node(child, document) for child in root
                  if _tag_name(child.tag).startswith("UA") and child.get("NodeId"))
    return NodeSetDocument(role, source_path, document.sha256, last_modified,
                           namespaces, aliases, tuple(models), nodes)


def _definition_index(documents: list[NodeSetDocument]) -> dict[tuple[str | None, str], list[dict[str, Any]]]:
    index: dict[tuple[str | None, str], list[dict[str, Any]]] = {}
    for document in documents:
        for node in document.nodes:
            node_id = node["nodeId"]
            if node_id:
                index.setdefault((node_id["namespaceUri"], node_id["identifier"]), []).append(node)
    return index


def _audit_references(documents: list[NodeSetDocument],
                      definitions: dict[tuple[str | None, str], list[dict[str, Any]]]) -> tuple[dict[str, int], list, list]:
    counts: dict[str, int] = {}
    unresolved_models = []
    external_core = []
    for document in documents:
        references = [reference for node in document.nodes for reference in node["references"]]
        counts[document.role] = len(references)
        for node in document.nodes:
            for reference in node["references"]:
                target = reference["target"]
                if not target or (target["namespaceUri"], target["identifier"]) in definitions:
                    continue
                issue = {"sourceFile": document.path.name,
                         "sourceNodeId": node["nodeId"]["raw"],
                         "referenceType": reference["referenceType"], "target": target}
                destination = external_core if target["namespaceUri"] == UA_CORE_URI else unresolved_models
                destination.append(issue)
    return counts, unresolved_models, external_core


def _datatype_namespace_conflicts(instance: NodeSetDocument,
                                  definitions: dict[tuple[str | None, str], list[dict[str, Any]]]) -> list:
    conflicts = []
    for node in instance.nodes:
        datatype = node["dataType"]
        browse_name = node["browseName"] or {}
        if not datatype or not browse_name.get("namespaceUri"):
            continue
        target_key = (datatype["namespaceUri"], datatype["identifier"])
        if target_key in definitions:
            continue
        alternatives = {}
        for (namespace_uri, identifier), entries in definitions.items():
            if identifier == datatype["identifier"] and namespace_uri != datatype["namespaceUri"]:
                alternatives.setdefault(namespace_uri, set()).update(entry["sourceRole"] for entry in entries)
        if alternatives:
            conflicts.append({"sourceNodeId": node["nodeId"]["raw"],
                              "browseName": node["browseName"],
                              "declaredDataType": datatype,
                              "browseNameNamespaceUri": browse_name["namespaceUri"],
                              "sameIdentifierDefinitions": [{"namespaceUri": uri,
                                                              "sourceFiles": sorted(roles)}
                                                             for uri, roles in alternatives.items()]})
    return conflicts


def _namespace_metadata(instance: NodeSetDocument) -> list[dict[str, Any]]:
    declared = set(instance.namespaces)
    return [{"nodeId": node["nodeId"]["raw"], "value": node["value"],
             "declaredInNamespaceUris": node["value"] in declared}
            for node in instance.nodes
            if (node["browseName"] or {}).get("name") == "NamespaceUri"
            and isinstance(node["value"], str)]


def audit_bundle(instance: NodeSetDocument, dependencies: list[NodeSetDocument]) -> dict[str, Any]:
    documents = [instance, *dependencies]
    definitions = _definition_index(documents)
    node_counts = {document.role: len(document.nodes) for document in documents}
    reference_counts, unresolved_model_references, external_core_references = _audit_references(
        documents, definitions)
    datatype_conflicts = _datatype_namespace_conflicts(instance, definitions)
    namespace_metadata_values = _namespace_metadata(instance)
    namespace_metadata_conflicts = [entry for entry in namespace_metadata_values
                                    if not entry["declaredInNamespaceUris"]]
    dependency_summaries = [{"role": document.role, "sourceFile": document.path.name,
                             "sha256": document.sha256, "lastModified": document.last_modified,
                             "models": list(document.models)} for document in dependencies]
    return {
        "sourceInstance": instance.path.name,
        "sourceInstanceSha256": instance.sha256,
        "instanceLastModified": instance.last_modified,
        "instanceNamespaceUris": list(instance.namespaces),
        "namespaceMetadataValues": namespace_metadata_values,
        "namespaceMetadataConflicts": namespace_metadata_conflicts,
        "nodeCountsByDocument": node_counts,
        "referenceCountsByDocument": reference_counts,
        "uniqueExpandedNodeIds": len(definitions),
        "unresolvedModelReferenceCount": len(unresolved_model_references),
        "unresolvedModelReferences": unresolved_model_references,
        "externalOpcUaCoreReferenceCount": len(external_core_references),
        "datatypeNamespaceConflictCount": len(datatype_conflicts),
        "datatypeNamespaceConflicts": datatype_conflicts,
        "dependencies": dependency_summaries,
        "status": "source-preserving audit; no NodeSet repairs or live-server validation performed",
    }


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _node_map(nodes: list[dict[str, Any]]) -> dict[str, str]:
    result = {}
    for index, node in enumerate(nodes, 1):
        source_id = node["nodeId"]["expanded"]
        browse_name = (node["browseName"] or {}).get("name") or node["nodeClass"]
        result[source_id] = f"Node{index:03d}_{_safe_id(browse_name)}"
    return result


def _aas_reference(node_map: dict[str, str], submodel_id: str,
                   expanded_node_id: str) -> dict[str, Any]:
    if expanded_node_id in node_map:
        return {"type": "ModelReference", "keys": [
            {"type": "Submodel", "value": submodel_id},
            {"type": "SubmodelElementCollection", "value": node_map[expanded_node_id]},
        ]}
    return {"type": "ExternalReference", "keys": [
        {"type": "GlobalReference", "value": node_iri(expanded_node_id).toPython()},
    ]}


def _aas_property(id_short: str, value: Any, value_type: str = "xs:string",
                  description: str | None = None) -> dict[str, Any]:
    if value is None:
        serialized_value = None
    elif isinstance(value, str):
        serialized_value = value
    else:
        serialized_value = _json_text(value)
    output = {"modelType": "Property", "idShort": id_short, "valueType": value_type,
              "value": serialized_value}
    if description:
        output["description"] = [{"language": "en", "text": description}]
    return output


def _aas_node_collection(node: dict[str, Any], node_map: dict[str, str]) -> dict[str, Any]:
    properties = [
        _aas_property("SourceNodeId", node["nodeId"]["raw"]),
        _aas_property("ExpandedNodeId", node["nodeId"]["expanded"]),
        _aas_property("NodeClass", node["nodeClass"]),
        _aas_property("NamespaceUri", (node["nodeId"] or {}).get("namespaceUri")),
        _aas_property("BrowseName", (node["browseName"] or {}).get("raw")),
        _aas_property("DisplayName", node["displayName"]),
        _aas_property("Description", node["description"]),
        _aas_property("DataType", (node["dataType"] or {}).get("expanded")),
        _aas_property("ValueRank", node["valueRank"]),
        _aas_property("SourceAttributes", node["attributes"]),
        _aas_property("DecodedValue", node["value"]),
        _aas_property("SourceValueXml", node["valueXml"]),
        _aas_property("SourceExtensionsXml", node["extensionsXml"]),
        _aas_property("AdditionalNodeMetadataXml", node["additionalMetadataXml"]),
    ]
    if node["parentNodeId"]:
        properties.append(_aas_property("ParentNodeId", node["parentNodeId"]["expanded"]))
    return {"modelType": "SubmodelElementCollection",
            "idShort": node_map[node["nodeId"]["expanded"]],
            "value": properties, "ordered": True, "allowDuplicates": False}


def _aas_relationship_element(index: int, node: dict[str, Any], reference: dict[str, Any],
                             node_map: dict[str, str], submodel_id: str) -> dict[str, Any] | None:
    target = reference["target"]
    if not target or not target["expanded"]:
        return None
    source_id = node["nodeId"]["expanded"]
    target_id = target["expanded"]
    first_id, second_id = ((source_id, target_id) if reference["isForward"]
                           else (target_id, source_id))
    ref_type = reference["referenceType"]
    element = {
        "modelType": "RelationshipElement", "idShort": f"Reference{index:04d}",
        "first": _aas_reference(node_map, submodel_id, first_id),
        "second": _aas_reference(node_map, submodel_id, second_id),
        "description": [{"language": "en", "text":
                         f"NodeSet owner={source_id}; IsForward={str(reference['isForward']).lower()}; ReferenceType={ref_type['expanded'] if ref_type else 'unknown'}"}],
    }
    if ref_type and ref_type["expanded"]:
        element["semanticId"] = {"type": "ExternalReference", "keys": [
            {"type": "GlobalReference", "value": node_iri(ref_type["expanded"]).toPython()}]}
    return element


def _aas_elements(nodes: list[dict[str, Any]], node_map: dict[str, str],
                  submodel_id: str) -> list[dict[str, Any]]:
    elements = [_aas_node_collection(node, node_map) for node in nodes]
    relationship_index = 0
    for node in nodes:
        for reference in node["references"]:
            relationship_index += 1
            relationship = _aas_relationship_element(relationship_index, node, reference,
                                                     node_map, submodel_id)
            if relationship is not None:
                elements.append(relationship)
    return elements


def project_aas(instance: NodeSetDocument) -> dict[str, Any]:
    nodes = list(instance.nodes)
    node_map = _node_map(nodes)
    shell_node = next((node for node in nodes
                       if (node["browseName"] or {}).get("name") == "KUKABfr"), nodes[0])
    shell_id = node_iri(shell_node["nodeId"]["expanded"]).toPython()
    submodel_id = shell_id + "/submodel/opcua-instance"
    elements = _aas_elements(nodes, node_map, submodel_id)

    aas_shell = {
        "modelType": "AssetAdministrationShell",
        "id": shell_id,
        "idShort": _safe_id((shell_node["browseName"] or {}).get("name", "KukaRobot")),
        "assetInformation": {"assetKind": "Instance", "globalAssetId": shell_id},
        "submodels": [{"type": "ModelReference", "keys": [
            {"type": "Submodel", "value": submodel_id}]}],
    }
    submodel = {
        "modelType": "Submodel", "id": submodel_id, "idShort": "OpcUaInstanceSnapshot",
        "kind": "Instance",
        "description": [{"language": "en", "text":
                         "Loss-preserving AAS projection of the supplied KUKA OPC UA instance NodeSet; source attributes and references are retained as exported, including detected inconsistencies."}],
        "submodelElements": elements,
    }
    return {"assetAdministrationShells": [aas_shell], "submodels": [submodel],
            "conceptDescriptions": []}


def _add_rdf_node_labels(graph: Graph, subject: URIRef, node: dict[str, Any]) -> None:
    browse_name = node["browseName"]
    if browse_name:
        graph.add((subject, UA.browseName, Literal(browse_name["raw"] or "")))
        graph.add((subject, UA.browseNameNamespace, Literal(browse_name["namespaceUri"] or "")))
    for predicate, value in ((UA.displayName, node["displayName"]),
                             (UA.description, node["description"])):
        if value is not None:
            graph.add((subject, predicate, Literal(value)))


def _add_rdf_node_datatype(graph: Graph, subject: URIRef, node: dict[str, Any]) -> None:
    datatype = node["dataType"]
    if not datatype:
        return
    graph.add((subject, UA.sourceDataType, Literal(datatype["raw"])))
    if datatype["expanded"]:
        graph.add((subject, UA.expandedDataType, Literal(datatype["expanded"])))


def _add_rdf_node_values(graph: Graph, subject: URIRef, node: dict[str, Any]) -> None:
    if node["value"] is not None:
        graph.add((subject, UA.valueJson, Literal(_json_text(node["value"]))))
    if node["valueXml"] is not None:
        graph.add((subject, UA.valueXml, Literal(node["valueXml"])))
    parent = node["parentNodeId"]
    if parent and parent["expanded"]:
        graph.add((subject, UA.parentNodeId, Literal(parent["expanded"])))


def _add_rdf_node(graph: Graph, node: dict[str, Any]) -> None:
    expanded = node["nodeId"]["expanded"]
    if not expanded:
        return
    subject = node_iri(expanded)
    graph.add((subject, RDF.type, UA[_tag_name(node["nodeClass"])]))
    literals = ((UA.sourceNodeId, node["nodeId"]["raw"]),
                (UA.expandedNodeId, expanded),
                (UA.namespaceUri, node["nodeId"]["namespaceUri"] or ""),
                (UA.nodeClass, node["nodeClass"]),
                (UA.attributesJson, _json_text(node["attributes"])),
                (UA.additionalMetadataXml, _json_text(node["additionalMetadataXml"])))
    for predicate, value in literals:
        graph.add((subject, predicate, Literal(value)))
    _add_rdf_node_labels(graph, subject, node)
    _add_rdf_node_datatype(graph, subject, node)
    _add_rdf_node_values(graph, subject, node)
    for reference in node["references"]:
        _add_rdf_reference(graph, subject, reference)


def _add_rdf_reference(graph: Graph, subject: URIRef, reference: dict[str, Any]) -> None:
    edge = BNode()
    graph.add((subject, UA.reference, edge))
    if reference["referenceType"]:
        graph.add((edge, UA.referenceType, Literal(reference["referenceType"]["expanded"] or "")))
    if reference["target"]:
        graph.add((edge, UA.targetNodeId, Literal(reference["target"]["expanded"] or "")))
    graph.add((edge, UA.isForward, Literal(reference["isForward"], datatype=XSD.boolean)))


def project_rdf(instance: NodeSetDocument) -> Graph:
    graph = Graph()
    graph.bind("opcua", UA)
    graph.bind("rdf", RDF)
    for node in instance.nodes:
        _add_rdf_node(graph, node)
    return graph


def _ngsild_context() -> list[Any]:
    return [
        "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context-v1.8.jsonld",
        {"opcua": str(UA), "sourceNodeId": "opcua:sourceNodeId",
         "expandedNodeId": "opcua:expandedNodeId", "nodeClass": "opcua:nodeClass",
         "browseName": "opcua:browseName", "displayName": "opcua:displayName",
         "description": "opcua:description", "dataType": "opcua:dataType",
         "nodeValue": "opcua:nodeValue", "references": "opcua:references"},
    ]


def _ngsild_reference(reference: dict[str, Any]) -> dict[str, Any]:
    return {"referenceType": reference["referenceType"]["expanded"] if reference["referenceType"] else None,
            "isForward": reference["isForward"],
            "targetNodeId": reference["target"]["expanded"] if reference["target"] else None}


def _ngsild_entity(node: dict[str, Any], context: list[Any]) -> dict[str, Any]:
    attributes: dict[str, Any] = {
        "sourceNodeId": {"type": "Property", "value": node["nodeId"]["raw"]},
        "expandedNodeId": {"type": "Property", "value": node["nodeId"]["expanded"]},
        "nodeClass": {"type": "Property", "value": node["nodeClass"]},
    }
    for key in ("browseName", "displayName", "description"):
        value = (node[key] or {}).get("raw") if key == "browseName" else node[key]
        if value is not None:
            attributes[key] = {"type": "Property", "value": value}
    if node["dataType"]:
        attributes["dataType"] = {"type": "Property", "value": node["dataType"]["raw"]}
    if node["value"] is not None:
        attributes["nodeValue"] = {"type": "Property", "value": node["value"]}
    attributes["additionalNodeMetadataXml"] = {
        "type": "Property", "value": node["additionalMetadataXml"]}
    attributes["references"] = {"type": "Property", "value": [
        _ngsild_reference(reference) for reference in node["references"]]}
    return {"id": node_iri(node["nodeId"]["expanded"]).toPython(),
            "type": "OPCUAInstanceNode", **attributes, "@context": context}


def project_ngsild(instance: NodeSetDocument) -> list[dict[str, Any]]:
    context = _ngsild_context()
    return [_ngsild_entity(node, context) for node in instance.nodes]


def _csv_rows(nodes: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows = []
    for node in nodes:
        rows.append({
            "source_role": node["sourceRole"], "node_class": node["nodeClass"],
            "node_id": node["nodeId"]["raw"], "expanded_node_id": node["nodeId"]["expanded"],
            "namespace_uri": node["nodeId"]["namespaceUri"] or "",
            "browse_name": (node["browseName"] or {}).get("raw") or "",
            "browse_name_uri": (node["browseName"] or {}).get("namespaceUri") or "",
            "display_name": node["displayName"] or "", "description": node["description"] or "",
            "data_type": (node["dataType"] or {}).get("raw") or "",
            "value_json": "" if node["value"] is None else _json_text(node["value"]),
            "parent_node_id": (node["parentNodeId"] or {}).get("expanded") or "",
            "attributes_json": _json_text(node["attributes"]),
            "additional_metadata_xml_json": _json_text(node["additionalMetadataXml"]),
            "references_json": _json_text(node["references"]),
            "value_xml": node["valueXml"] or "",
        })
    return rows


def _jsonld_from_graph(graph: Graph) -> Any:
    serialized = graph.serialize(format="json-ld", auto_compact=False)
    return json.loads(serialized)


def _rdf_serialization_audit(graph: Graph) -> list[dict[str, Any]]:
    rows = []
    for syntax in ("turtle", "nt", "json-ld"):
        serialized = graph.serialize(format=syntax)
        parsed = Graph().parse(data=serialized, format=syntax)
        rows.append({"syntax": syntax, "serializedBytes": len(serialized.encode("utf-8")),
                     "tripleCount": len(parsed), "roundTripIsomorphic": isomorphic(graph, parsed)})
    return rows


def _comparison_latex(comparison: dict[str, Any]) -> str:
    output_names = {
        "canonical_json": ("Canonical JSON", "kuka_instance_snapshot.json"),
        "aas_v3_projection": ("AAS v3 snapshot", "kuka_instance_aas_v3.json"),
        "rdf": ("RDF graph", "kuka_instance.ttl"),
        "ngsi_ld_snapshot": ("NGSI-LD snapshot", "kuka_instance_ngsild.json"),
        "csv": ("CSV snapshot", "kuka_instance.csv"),
    }
    costs = {row["file"]: row["bytes"] for row in comparison["serializationCosts"]}
    row_end = " " + chr(92) * 2
    lines = [r"\begin{table}[t]", r"\centering\footnotesize",
             r"\caption{Ad hoc KUKA NodeSet projection check. The input is user-attributed to an IIH export; structural retention only, not task accuracy or physical validation. AAS/NGSI-LD conformance was not externally validated.}",
             r"\label{tab:kuka-adhoc-projections}",
             r"\begin{tabular}{@{}lrrr@{}}", r"\toprule",
             "Projection & Nodes/entities/rows & References & Bytes" + row_end,
             r"\midrule"]
    for key, (name, filename) in output_names.items():
        details = comparison["outputs"][key]
        node_count = details.get("nodeCount", details.get("entityCount", details.get("rowCount", 0)))
        reference_count = details.get("referenceCount", details.get("relationshipElementCount", "--"))
        lines.append(f"{name} & {node_count} & {reference_count} & {costs[filename]}" + row_end)
    lines.extend([r"\bottomrule", r"\end{tabular}", r"\end{table}"])
    return "\n".join(lines) + "\n"


def build_case(instance_path: str | Path, robotics_path: str | Path,
               di_path: str | Path) -> tuple[dict[str, Any], dict[str, Any]]:
    instance = parse_nodeset(instance_path, "instance")
    robotics = parse_nodeset(robotics_path, "robotics_companion")
    di = parse_nodeset(di_path, "device_integration_companion")
    audit = audit_bundle(instance, [robotics, di])
    nodes = list(instance.nodes)
    canonical = {
        "schemaVersion": 1,
        "caseId": "kuka_iih_nodeset_example",
        "provenance": {
            "status": "user-provided IIH-export attribution; not independently verified against a live server",
            "sourceFile": instance.path.name,
            "sourceSha256": instance.sha256,
            "sourceLastModified": instance.last_modified,
            "capturedAt": None,
            "valueOrigin": "Embedded values in supplied NodeSet XML; live sensor/physical-process origin is not established by this file.",
            "licenses": ["Input NodeSets carry OPC Foundation MIT License notices; retain notices when redistributing source files."],
        },
        "instanceNodeSet": {"namespaceUris": list(instance.namespaces),
                             "models": list(instance.models), "nodes": nodes},
        "companionModels": audit["dependencies"],
        "audit": audit,
    }
    aas = project_aas(instance)
    graph = project_rdf(instance)
    ngsild = project_ngsild(instance)
    csv_rows = _csv_rows(nodes)

    output_records = {
        "canonical_json": {record["nodeId"]["expanded"] for record in nodes},
        "aas": {prop["value"] for element in aas["submodels"][0]["submodelElements"]
                if element["modelType"] == "SubmodelElementCollection"
                for prop in element["value"] if prop["idShort"] == "ExpandedNodeId"},
        "rdf": {str(value) for value in graph.objects(None, UA.expandedNodeId)},
        "ngsi_ld": {entity["expandedNodeId"]["value"] for entity in ngsild},
        "csv": {row["expanded_node_id"] for row in csv_rows},
    }
    expected_ids = output_records["canonical_json"]
    representation_summary = {
        "sourceInstanceSha256": instance.sha256,
        "sourceInstanceFile": instance.path.name,
        "sourceInstanceNodes": len(nodes),
        "sourceInstanceReferences": sum(len(node["references"]) for node in nodes),
        "sourceVariables": sum(node["nodeClass"] == "UAVariable" for node in nodes),
        "sourceVariablesWithEmbeddedValues": sum(
            node["nodeClass"] == "UAVariable" and node["value"] is not None for node in nodes),
        "uniqueExpandedNodeIds": len(expected_ids),
        "outputs": {
            "canonical_json": {"nodeCount": len(output_records["canonical_json"]),
                                "referenceCount": sum(len(node["references"]) for node in nodes)},
            "aas_v3_projection": {"nodeCount": len(output_records["aas"]),
                                  "relationshipElementCount": sum(e["modelType"] == "RelationshipElement"
                                                                   for e in aas["submodels"][0]["submodelElements"]),
                                  "idSetMatchesSource": output_records["aas"] == expected_ids,
                                  "officialSchemaValidated": False},
            "rdf": {"tripleCount": len(graph), "nodeCount": len(output_records["rdf"]),
                    "referenceCount": len(list(graph.objects(None, UA.reference))),
                    "idSetMatchesSource": output_records["rdf"] == expected_ids},
            "ngsi_ld_snapshot": {"entityCount": len(ngsild),
                                  "referenceCount": sum(len(entity["references"]["value"]) for entity in ngsild),
                                  "idSetMatchesSource": output_records["ngsi_ld"] == expected_ids},
            "csv": {"rowCount": len(csv_rows),
                    "referenceCount": sum(len(node["references"]) for node in nodes),
                    "idSetMatchesSource": output_records["csv"] == expected_ids},
        },
            "rdfSyntaxRoundTrips": _rdf_serialization_audit(graph),
        "scope": "Structural and serialization comparison only; no LLM task accuracy, safety or physical trial is inferred.",
    }
    return canonical, {
        "aas": aas,
        "rdf_graph": graph,
        "jsonld": _jsonld_from_graph(graph),
        "ngsild": ngsild,
        "csv_rows": csv_rows,
        "comparison": representation_summary,
    }


def write_case(instance_path: str | Path, robotics_path: str | Path,
               di_path: str | Path, output_dir: str | Path) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    canonical, projections = build_case(instance_path, robotics_path, di_path)
    source_dir = output / "source_nodesets"
    source_dir.mkdir(parents=True, exist_ok=True)
    source_files: dict[str, str] = {}
    for source_path in (Path(instance_path), Path(robotics_path), Path(di_path)):
        destination_path = source_dir / source_path.name
        if source_path.resolve() != destination_path.resolve():
            shutil.copyfile(source_path, destination_path)
        source_files[f"source_nodesets/{destination_path.name}"] = hashlib.sha256(
            destination_path.read_bytes()).hexdigest()
    graph: Graph = projections.pop("rdf_graph")
    jsonld = projections.pop("jsonld")
    ngsild = projections.pop("ngsild")
    aas = projections.pop("aas")
    csv_rows = projections.pop("csv_rows")
    comparison = projections.pop("comparison")

    files: dict[str, str] = dict(source_files)
    canonical_path = output / "kuka_instance_snapshot.json"
    canonical_path.write_text(json.dumps(canonical, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    files[canonical_path.name] = hashlib.sha256(canonical_path.read_bytes()).hexdigest()
    aas_path = output / "kuka_instance_aas_v3.json"
    aas_path.write_text(json.dumps(aas, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    files[aas_path.name] = hashlib.sha256(aas_path.read_bytes()).hexdigest()
    turtle_text = graph.serialize(format="turtle")
    turtle_path = output / "kuka_instance.ttl"
    turtle_path.write_text(turtle_text, encoding="utf-8")
    files[turtle_path.name] = hashlib.sha256(turtle_path.read_bytes()).hexdigest()
    jsonld_path = output / "kuka_instance.jsonld"
    jsonld_path.write_text(json.dumps(jsonld, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    files[jsonld_path.name] = hashlib.sha256(jsonld_path.read_bytes()).hexdigest()
    ngsild_path = output / "kuka_instance_ngsild.json"
    ngsild_path.write_text(json.dumps(ngsild, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    files[ngsild_path.name] = hashlib.sha256(ngsild_path.read_bytes()).hexdigest()
    csv_path = output / "kuka_instance.csv"
    fieldnames = list(csv_rows[0]) if csv_rows else []
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(csv_rows)
    files[csv_path.name] = hashlib.sha256(csv_path.read_bytes()).hexdigest()

    serialization = []
    for filename in (canonical_path.name, aas_path.name, turtle_path.name,
                     jsonld_path.name, ngsild_path.name, csv_path.name):
        data = (output / filename).read_bytes()
        text = data.decode("utf-8-sig")
        serialization.append({"file": filename, "bytes": len(data),
                               "surrogateTokens": surrogate_tokens(text),
                               "sha256": files[filename]})
    comparison = {**comparison, "serializationCosts": serialization,
                  "comparisonNote": "Counts and byte/token costs compare these emitted projections only; no external AAS/NGSI-LD conformance validator was run."}
    comparison_path = output / "comparison.json"
    comparison_path.write_text(json.dumps(comparison, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    files[comparison_path.name] = hashlib.sha256(comparison_path.read_bytes()).hexdigest()
    comparison_latex_path = output / "comparison.tex"
    comparison_latex_path.write_text(_comparison_latex(comparison), encoding="utf-8")
    files[comparison_latex_path.name] = hashlib.sha256(comparison_latex_path.read_bytes()).hexdigest()
    report_path = output / "ADHOC_REPORT.md"
    audit = canonical["audit"]
    projection_rows = []
    for name, details in comparison["outputs"].items():
        retained_count = details.get("nodeCount", details.get("entityCount", details.get("rowCount", 0)))
        reference_count = details.get("referenceCount", details.get("relationshipElementCount", "not measured"))
        ids_match = details.get("idSetMatchesSource", "not applicable")
        projection_rows.append(f"| `{name}` | {retained_count} | {reference_count} | {ids_match} |")
    syntax_rows = [f"| `{row['syntax']}` | {row['tripleCount']} | {row['serializedBytes']} | {row['roundTripIsomorphic']} |"
                   for row in comparison["rdfSyntaxRoundTrips"]]
    report_text = "\n".join([
        "# KUKA OPC UA NodeSet Ad Hoc Projection Experiment",
        "",
        "## Provenance and Scope",
        "",
        f"The user supplied `{canonical['provenance']['sourceFile']}` as an IIH export mapped from a KUKA OPC UA server. This attribution is user-provided and was not independently checked against a live endpoint. The instance file SHA-256 is `{canonical['provenance']['sourceSha256']}`. Its NodeSet `LastModified` is `{canonical['provenance']['sourceLastModified']}`; this is not an independently verified capture time.",
        "",
        "The Robotics and DI companion NodeSets are parsed as model dependencies. Their definitions are not counted as observed robot instances. Embedded XML values are retained as exported; their live/historical measurement origin is unknown. No physical trial, agent answer-quality, control safety, latency, or IIH throughput claim is made.",
        "",
        "## Structural Audit",
        "",
        f"The instance contains {audit['nodeCountsByDocument']['instance']} nodes, {audit['sourceInstanceReferences'] if 'sourceInstanceReferences' in audit else comparison['sourceInstanceReferences']} references, and {comparison['sourceVariablesWithEmbeddedValues']} of {comparison['sourceVariables']} variables with embedded values. Companion definitions yield {audit['uniqueExpandedNodeIds']} unique expanded NodeIds. There are {audit['unresolvedModelReferenceCount']} unresolved model-namespace references and {audit['externalOpcUaCoreReferenceCount']} references to external OPC UA core nodes not included in this three-file bundle.",
        "",
        f"The raw file declares a namespace URI that conflicts with its NamespaceUri metadata value ({len(audit['namespaceMetadataConflicts'])} detected conflict). The parser also flags {audit['datatypeNamespaceConflictCount']} custom DataType namespace-index conflicts where a matching numeric identifier exists in a different supplied model namespace. Inputs are preserved and not repaired.",
        "",
        "## Projection Comparison",
        "",
        "| Projection | Instance nodes/entities/rows | References or relationship elements | Expanded NodeId set matches |",
        "|---|---:|---:|---|",
        *projection_rows,
        "",
        "These are structural retention checks, not official AAS or NGSI-LD schema validation. The AAS output is a loss-aware instance snapshot that stores source NodeSet attributes and XML metadata in submodel properties; it is not asserted to be an IDTA semantic profile. The NGSI-LD file is a snapshot mapping with a local OPC UA context, not a deployed broker publication.",
        "",
        "## RDF Syntax Fidelity",
        "",
        "| Syntax | Parsed triples | Serialized bytes | Isomorphic round trip |",
        "|---|---:|---:|---|",
        *syntax_rows,
        "",
        "## Reproduction",
        "",
        "Run `code/run_kuka_case.py` with the three source NodeSet paths and a separate `--out` directory. Exact input files are copied to `source_nodesets/` and hashed. Original `artifacts/`, `results/` and core benchmark scores are not read or modified by this experiment.",
        "",
    ])
    report_path.write_text(report_text, encoding="utf-8")
    files[report_path.name] = hashlib.sha256(report_path.read_bytes()).hexdigest()
    source_roles = {
        "instance": Path(instance_path),
        "robotics_companion": Path(robotics_path),
        "device_integration_companion": Path(di_path),
    }
    manifest = {
        "schemaVersion": 1,
        "caseId": canonical["caseId"],
        "generatedAtUtc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "runner": {"python": sys.version.split()[0], "rdflib": rdflib.__version__},
        "inputs": {role: {"file": path.name,
                          "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                   for role, path in source_roles.items()},
        "outputs": files,
        "scope": "offline projections and structural diagnostics; no live-server, AAS-schema, NGSI-LD-broker, LLM or physical validation",
    }
    manifest_path = output / "artifact_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                             encoding="utf-8")
    return {"outputDirectory": str(output), "files": files, "comparison": comparison}