from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from semantics_bench.nodeset_case import audit_bundle, build_case, parse_nodeset, write_case


NODESET_NS = "http://opcfoundation.org/UA/2011/03/UANodeSet.xsd"


INSTANCE_XML = f'''<UANodeSet xmlns="{NODESET_NS}">
  <NamespaceUris><Uri>urn:test:instance</Uri><Uri>urn:test:robotics</Uri></NamespaceUris>
  <Aliases><Alias Alias="HasComponent">i=47</Alias></Aliases>
  <UAObject NodeId="ns=1;s=Robot" BrowseName="1:Robot">
    <DisplayName>Test Robot</DisplayName>
    <References><Reference ReferenceType="HasComponent">ns=1;s=Speed</Reference>
      <Reference ReferenceType="HasTypeDefinition">ns=2;i=1004</Reference>
    </References>
  </UAObject>
  <UAVariable NodeId="ns=1;s=Speed" BrowseName="2:ActualSpeed" DataType="ns=1;i=3008">
    <DisplayName>Actual Speed</DisplayName><Description>Axis speed</Description>
    <References><Reference ReferenceType="HasComponent" IsForward="false">ns=1;s=Robot</Reference></References>
    <Value xmlns:t="http://opcfoundation.org/UA/2008/02/Types.xsd"><t:Double>12.5</t:Double></Value>
    <Definition Name="SampleEnumeration"><Field Name="ONE" Value="1" /></Definition>
  </UAVariable>
  <UAVariable NodeId="ns=1;i=5000" BrowseName="1:NamespaceUri" DataType="String">
    <Value xmlns:t="http://opcfoundation.org/UA/2008/02/Types.xsd"><t:String>urn:wrong:instance</t:String></Value>
  </UAVariable>
</UANodeSet>'''

ROBOTICS_XML = f'''<UANodeSet xmlns="{NODESET_NS}">
  <NamespaceUris><Uri>urn:test:robotics</Uri><Uri>urn:test:di</Uri></NamespaceUris>
  <Models><Model ModelUri="urn:test:robotics" Version="1.0">
    <RequiredModel ModelUri="urn:test:di" Version="1.0" /></Model></Models>
  <UAObjectType NodeId="ns=1;i=1004" BrowseName="1:MotionDeviceType" />
  <UADataType NodeId="ns=1;i=3008" BrowseName="1:AxisMotionProfileEnumeration" />
</UANodeSet>'''

DI_XML = f'''<UANodeSet xmlns="{NODESET_NS}">
  <NamespaceUris><Uri>urn:test:di</Uri></NamespaceUris>
  <Models><Model ModelUri="urn:test:di" Version="1.0" /></Models>
  <UAObject NodeId="ns=1;i=5001" BrowseName="1:DeviceSet" />
</UANodeSet>'''


class TestNodeSetCase(unittest.TestCase):
    def _bundle(self, directory: Path):
        paths = {"instance": directory / "instance.xml",
                 "robotics": directory / "robotics.xml",
                 "di": directory / "di.xml"}
        paths["instance"].write_text(INSTANCE_XML, encoding="utf-8")
        paths["robotics"].write_text(ROBOTICS_XML, encoding="utf-8")
        paths["di"].write_text(DI_XML, encoding="utf-8")
        return paths

    def test_expands_qnames_values_aliases_and_node_ids(self):
        with tempfile.TemporaryDirectory() as folder:
            document = parse_nodeset(self._bundle(Path(folder))["instance"], "instance")
            speed = next(node for node in document.nodes if node["nodeId"]["raw"] == "ns=1;s=Speed")
            self.assertEqual(speed["browseName"]["namespaceUri"], "urn:test:robotics")
            self.assertEqual(speed["dataType"]["namespaceUri"], "urn:test:instance")
            self.assertEqual(speed["value"], 12.5)
            self.assertIn("Definition", speed["additionalMetadataXml"][0])
            self.assertEqual(speed["references"][0]["referenceType"]["resolvedRaw"], "i=47")

    def test_audit_reports_namespace_metadata_and_datatype_conflicts(self):
        with tempfile.TemporaryDirectory() as folder:
            paths = self._bundle(Path(folder))
            instance = parse_nodeset(paths["instance"], "instance")
            dependencies = [parse_nodeset(paths["robotics"], "robotics_companion"),
                            parse_nodeset(paths["di"], "device_integration_companion")]
            audit = audit_bundle(instance, dependencies)
            self.assertEqual(audit["unresolvedModelReferenceCount"], 0)
            self.assertEqual(audit["namespaceMetadataConflicts"][0]["value"], "urn:wrong:instance")
            self.assertEqual(audit["datatypeNamespaceConflictCount"], 1)

    def test_all_projections_retain_instance_nodes_and_edges(self):
        with tempfile.TemporaryDirectory() as folder:
            paths = self._bundle(Path(folder))
            canonical, projections = build_case(paths["instance"], paths["robotics"], paths["di"])
            expected = {node["nodeId"]["expanded"] for node in canonical["instanceNodeSet"]["nodes"]}
            self.assertEqual(len(expected), 3)
            summary = projections["comparison"]["outputs"]
            for key in ("aas_v3_projection", "rdf", "ngsi_ld_snapshot", "csv"):
                self.assertTrue(summary[key]["idSetMatchesSource"], key)
            self.assertEqual(summary["aas_v3_projection"]["relationshipElementCount"], 3)
            self.assertEqual(summary["rdf"]["referenceCount"], 3)
            self.assertEqual(summary["ngsi_ld_snapshot"]["referenceCount"], 3)
            self.assertTrue(all(row["roundTripIsomorphic"]
                                for row in projections["comparison"]["rdfSyntaxRoundTrips"]))

    def test_writer_keeps_outputs_isolated_and_records_hashes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            paths = self._bundle(root)
            output = root / "adhoc"
            result = write_case(paths["instance"], paths["robotics"], paths["di"], output)
            self.assertIn("kuka_instance_aas_v3.json", result["files"])
            self.assertTrue((output / "kuka_instance.ttl").exists())
            for source_name in ("instance.xml", "robotics.xml", "di.xml"):
                self.assertTrue((output / "source_nodesets" / source_name).exists())
            artifact_manifest = json.loads((output / "artifact_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(set(artifact_manifest["inputs"]),
                             {"instance", "robotics_companion", "device_integration_companion"})
            self.assertIn("ADHOC_REPORT.md", artifact_manifest["outputs"])
            self.assertIn("\\begin{table}", (output / "comparison.tex").read_text(encoding="utf-8"))
            report = (output / "ADHOC_REPORT.md").read_text(encoding="utf-8")
            self.assertIn("not asserted to be an IDTA semantic profile", report)
            manifest = json.loads((output / "kuka_instance_snapshot.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["provenance"]["sourceSha256"],
                             result["comparison"]["sourceInstanceSha256"])

    def test_writer_can_replay_from_bundled_inputs(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            paths = self._bundle(root)
            output = root / "adhoc"
            write_case(paths["instance"], paths["robotics"], paths["di"], output)
            write_case(output / "source_nodesets" / "instance.xml",
                       output / "source_nodesets" / "robotics.xml",
                       output / "source_nodesets" / "di.xml", output)
            manifest = json.loads((output / "artifact_manifest.json").read_text(encoding="utf-8"))
            snapshot = json.loads((output / "kuka_instance_snapshot.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["inputs"]["instance"]["sha256"],
                             snapshot["provenance"]["sourceSha256"])


if __name__ == "__main__":
    unittest.main()