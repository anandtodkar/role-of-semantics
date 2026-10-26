from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from semantics_bench import kg as KG
from semantics_bench import opcua_aas as OA

KUKA = Path(__file__).resolve().parents[2] / "paper_revision" / "adhoc_kuka"


class TestOpcuaAasCoverage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case = OA.synthetic_case()

    def test_projections_carry_complementary_profiles(self):
        opcua, aas = self.case["coverage"]["opcua"], self.case["coverage"]["aas"]
        for category in ("access", "range", "parent"):
            self.assertEqual(opcua[category]["correct"], opcua[category]["reference"])
            self.assertEqual(aas[category]["correct"], 0)
        for category in ("semantic_id", "nameplate", "state", "value"):
            self.assertEqual(aas[category]["correct"], aas[category]["reference"])
            self.assertEqual(opcua[category]["correct"], 0)

    def test_union_still_lacks_behaviour_constraint_topology_and_time(self):
        union = self.case["coverage"]["union"]
        for category in ("feeds", "legal_commands", "interlock", "observation_time"):
            self.assertEqual(union[category]["correct"], 0)

    def test_unit_level_quantity_kind_conflicts_are_reported(self):
        self.assertEqual(self.case["coverage"]["opcua"]["quantity_kind"]["conflict"], 20)

    def test_conflicting_aas_value_is_detected(self):
        environment = copy.deepcopy(KG.aas_environment())
        operational = next(submodel for submodel in environment["submodels"]
                           if submodel["idShort"] == "OperationalData")
        element = next(item for item in operational["submodelElements"] if item.get("value"))
        element["value"] = str(float(element["value"]) + 1.0)
        coverage = OA.coverage(OA.reference_facts(), OA.aas_facts(environment))
        self.assertEqual(coverage["value"]["conflict"], 1)

    @unittest.skipUnless((KUKA / "kuka_instance_aas_v3.json").exists(), "KUKA pilot bundle not present")
    def test_kuka_derived_aas_retains_all_source_facts(self):
        case = OA.kuka_case(KUKA / "source_nodesets" / "example.kuka.robot_raw.xml",
                            KUKA / "kuka_instance_aas_v3.json")
        self.assertEqual(case["coverage"]["identity"]["reference"], 90)
        self.assertEqual(case["coverage"]["reference"]["reference"], 277)
        self.assertEqual(sum(row["correct"] for row in case["coverage"].values()), case["reference_facts"])


if __name__ == "__main__":
    unittest.main()
