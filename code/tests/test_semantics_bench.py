"""Unit tests. Run with:  python -m pytest code/tests -q   (or unittest)."""

from __future__ import annotations

import unittest

from semantics_bench import conditions as C
from semantics_bench import kg
from semantics_bench import metrics as M
from semantics_bench import plant as P
from semantics_bench import retrieval as R
from semantics_bench import statemachine as sm
from semantics_bench import tasks as TK
from semantics_bench import toolgen as TG
from semantics_bench import units as U
from semantics_bench import validation as V
from semantics_bench import revision as REV


class TestRevisionControls(unittest.TestCase):
    def test_serialisation_control_preserves_the_same_graph(self):
        rows = REV.equal_information_serialisation()
        self.assertEqual(len(rows), 3)
        faithful = [row for row in rows if row["included_equal_information"]]
        self.assertTrue(all(row["roundtrip_isomorphic"] for row in faithful))
        self.assertTrue({"nt", "json-ld"} <= {row["syntax"] for row in faithful})
        for row in faithful:
            self.assertEqual(row["missing_triples"], 0)
            self.assertEqual(row["added_triples"], 0)
        self.assertEqual(len({row["triples"] for row in rows}), 1)

    def test_equal_information_validator_matches_raw_shacl(self):
        result = REV.equal_information_validation()
        self.assertEqual(result["disagreements"], [])
        for row in result["summary"]:
            self.assertEqual(row["recall"], 1.0)
            self.assertEqual(row["false_positive_rate"], 0.0)

    def test_prediction_does_not_consult_gold_label(self):
        from dataclasses import replace
        snapshot = REV.Snapshot.reference()
        for case in V.build_corpus():
            first = REV.validate_procedural(case, snapshot)
            second = REV.validate_procedural(replace(case, gold="arbitrary"), snapshot)
            self.assertEqual(first, second)

    def test_nonfinite_and_boolean_values_are_rejected(self):
        snapshot = REV.Snapshot.reference()
        for value in (True, float("nan"), float("inf"), "330"):
            case = V.Case("malformed", "write", V.VALID,
                          {"tag": "L1_FIL_QIC0305_SP", "value": value, "unit": "MilliL"})
            self.assertIn("F-CARD", REV.validate_procedural(case, snapshot).faults)

    def test_ablation_reports_abstention_separately(self):
        result = REV.capability_ablation()
        rows = {row["validator"]: row for row in result["validators"]}
        self.assertEqual(rows["none"]["abstentions"], 0)
        self.assertGreater(rows["units"]["valid_abstentions"], 0)

    def test_degradation_and_dispatch_revalidation(self):
        probes = {row["probe"]: row for row in REV.degradation_probes()}
        self.assertEqual(probes["before_state_change"]["disposition"], "accept")
        self.assertEqual(probes["after_state_change"]["disposition"], "reject")
        self.assertIn("F-ILK", probes["after_state_change"]["faults"])
        self.assertIn("guard_state", probes["missing_state"]["missing"])
        self.assertIn("units", probes["unknown_unit"]["missing"])
        self.assertIn("evidence_time", probes["malformed_time"]["missing"])
        self.assertEqual(probes["missing_observation"]["disposition"], "abstain")

    def test_conversion_facts_require_both_definitions(self):
        element = C.ELEMENT_BY_ID["L1_FIL_PT0301_PV"]
        _text, facts, _tokens = REV.audited_context([element], C.BY_KEY["C4"], None)
        self.assertIn(C.fact("conv", "BAR", "BAR"), facts)
        self.assertNotIn(C.fact("conv", "BAR", "PSI"), facts)

    def test_crossed_retrieval_respects_budgets(self):
        rows = REV.retrieval_controls((1500,))
        self.assertTrue(rows)
        for row in rows:
            if row["budget"] is not None:
                self.assertLessEqual(row["tokens"], row["budget"])
        self.assertFalse(any(row["condition"] == "C2" and row["strategy"] == "graph"
                             for row in rows))
        self.assertTrue(any(row["condition"] == "C2" and row["strategy"] == "membership"
                            for row in rows))

    def test_ablation_cannot_create_oracle_evidence(self):
        from dataclasses import replace
        _text, full, _tokens = REV.audited_context(list(C.ELEMENTS), C.BY_KEY["C4"], None)
        for removed in REV.CAPABILITIES:
            condition = replace(C.BY_KEY["C4"],
                                kinds=C.BY_KEY["C4"].kinds - REV.REMOVED_KINDS[removed])
            _text, facts, _tokens = REV.audited_context(list(C.ELEMENTS), condition, None)
            self.assertLessEqual(facts, full)
            self.assertFalse({key.split(":", 1)[0] for key in facts}
                             & REV.REMOVED_KINDS[removed])


class TestUnits(unittest.TestCase):
    def test_affine_temperature(self):
        self.assertAlmostEqual(U.convert(0.0, "DEG_C", "K"), 273.15, places=6)
        self.assertAlmostEqual(U.convert(212.0, "DEG_F", "DEG_C"), 100.0, places=6)
        self.assertAlmostEqual(U.convert(161.6, "DEG_F", "DEG_C"), 72.0, places=4)

    def test_linear_conversions(self):
        self.assertAlmostEqual(U.convert(1.0, "BAR", "KiloPA"), 100.0, places=6)
        self.assertAlmostEqual(U.convert(180.0, "L-PER-MIN", "M3-PER-HR"), 10.8, places=6)
        self.assertAlmostEqual(U.convert(43.5, "PSI", "BAR"), 2.9990, places=3)

    def test_dimension_guard(self):
        self.assertFalse(U.compatible("BAR", "DEG_C"))
        self.assertTrue(U.compatible("BAR", "PSI"))
        with self.assertRaises(U.DimensionError):
            U.convert(1.0, "BAR", "L-PER-MIN")

    def test_round_trip(self):
        for iri, unit in U.BY_IRI.items():
            for other in U.units_for(unit.quantity_kind):
                v = 42.0
                back = U.convert(U.convert(v, iri, other.iri_local), other.iri_local, iri)
                self.assertAlmostEqual(v, back, places=6, msg=f"{iri}->{other.iri_local}")


class TestStateMachine(unittest.TestCase):
    def test_legality(self):
        self.assertTrue(sm.step("Idle", "Start").allowed)
        self.assertFalse(sm.step("Stopped", "Start").allowed)
        self.assertFalse(sm.step("Aborted", "Reset").allowed)
        self.assertTrue(sm.step("Aborted", "Clear").allowed)

    def test_stop_is_universal_except_terminal(self):
        self.assertTrue(sm.step("Execute", "Stop").allowed)
        self.assertFalse(sm.step("Stopped", "Stop").allowed)

    def test_planning(self):
        self.assertEqual(sm.reachable("Aborted", "Execute"), ["Clear", "Reset", "Start"])
        self.assertEqual(sm.reachable("Idle", "Execute"), ["Start"])

    def test_legal_command_sets_are_consistent(self):
        for state in sm.WAIT_STATES:
            for cmd in sm.legal_commands(state):
                self.assertTrue(sm.step(state, cmd).allowed)


class TestPlantAndGraph(unittest.TestCase):
    def test_plant_integrity(self):
        for a in P.PLANT:
            if a.parent:
                self.assertIn(a.parent, P.ASSETS_BY_ID, a.local_id)
        self.assertEqual(len(P.ALL_SIGNALS), len({s.tag for s in P.ALL_SIGNALS}))
        for ilk in P.INTERLOCKS:
            self.assertIn(str(ilk["tag"]), P.SIGNAL_OWNER)
            self.assertIn(str(ilk["guard_tag"]), P.SIGNAL_OWNER)

    def test_homographs_exist(self):
        self.assertGreaterEqual(len(TK.homograph_index()), 10)

    def test_graph_projections(self):
        g = kg.build_graph()
        self.assertGreater(len(g), 2000)
        self.assertGreater(len(kg.aas_environment()["submodels"]), 10)
        self.assertIn("<UANodeSet", kg.opcua_nodeset())
        self.assertGreater(len(kg.wot_thing_descriptions()), 5)
        self.assertGreater(len(kg.ngsild_entities()), 5)

    def test_units_are_heterogeneous(self):
        """The experiment is meaningless if every line uses the same units."""
        l1 = P.ASSETS_BY_ID["L1-FIL"].signals[0].unit
        l2 = P.ASSETS_BY_ID["L2-FIL"].signals[0].unit
        self.assertNotEqual(l1, l2)


class TestConditionsAndRetrieval(unittest.TestCase):
    def test_conditions_are_cumulative(self):
        for a, b in zip(C.CONDITIONS, C.CONDITIONS[1:]):
            self.assertTrue(a.kinds <= b.kinds, f"{a.key} !<= {b.key}")

    def test_raw_condition_exposes_nothing_but_values(self):
        el = C.ELEMENT_BY_ID["L1_FIL_PT0301_PV"]
        self.assertEqual(C.facts_of(el, C.BY_KEY["C0"]),
                         {C.fact("value", "L1_FIL_PT0301_PV")})

    def test_budget_is_respected(self):
        for cond in C.CONDITIONS:
            els = R.retrieve("outlet pressure of the line 1 filler", cond, 200)
            _t, _f, tokens = C.build_context(els, cond, 1500)
            self.assertLessEqual(tokens, 1500, cond.key)

    def test_entity_resolution(self):
        res = R.resolve_entities("What is the outlet pressure of the Line 1 filler?")
        self.assertIn("L1-FIL", res.asset_ids)
        res = R.resolve_entities("Can I start the Line 2 filler right now?")
        self.assertIn("L2-FIL", res.asset_ids)

    def test_grounding_improves_with_semantics(self):
        task = TK.TASKS_BY_ID["GRD-01"]
        c1 = R.candidate_signals(task.question, C.BY_KEY["C1"], 5)
        c4 = R.candidate_signals(task.question, C.BY_KEY["C4"], 5)
        self.assertEqual(c4[0], task.gold_tag)
        self.assertLessEqual(
            sum(1 for d in task.distractors if d in c4),
            sum(1 for d in task.distractors if d in c1))


class TestValidation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases, cls.meta = V.evaluate()

    def test_corpus_shape(self):
        self.assertGreater(self.meta["n_faulty"], 50)
        self.assertGreater(self.meta["n_valid"], 30)

    def test_tiers_are_monotone_on_faults(self):
        for c in self.cases:
            if c.gold == V.VALID:
                continue
            prev = False
            for tier in V.TIERS:
                cur = c.detected_by[tier]
                if prev:
                    self.assertTrue(cur, f"{c.cid} {tier} regressed")
                prev = cur or prev

    def test_full_stack_catches_everything(self):
        missed = [c.cid for c in self.cases
                  if c.gold != V.VALID and not c.detected_by["G4"]]
        self.assertEqual(missed, [])

    def test_full_stack_has_no_false_alarms(self):
        fp = [c.cid for c in self.cases
              if c.gold == V.VALID and c.detected_by["G4"]]
        self.assertEqual(fp, [])

    def test_flat_catalogue_raises_false_alarms(self):
        """The G2 pathology the paper reports must actually be present."""
        fp = [c for c in self.cases if c.gold == V.VALID and c.detected_by["G2"]]
        self.assertGreater(len(fp), 0)

    def test_behavioural_faults_need_the_behaviour_model(self):
        for fam in ("F-STATE", "F-ILK", "F-STALE", "F-VALUE"):
            sub = [c for c in self.cases if c.gold == fam]
            self.assertTrue(sub, fam)
            self.assertTrue(all(c.detected_by["G4"] for c in sub), fam)
            self.assertFalse(any(c.detected_by["G3"] for c in sub), fam)


class TestActionSpace(unittest.TestCase):
    def test_write_space_narrows_and_stays_faithful(self):
        stats = {s.tier: s for s in TG.write_action_space()}
        self.assertGreater(stats["G0"].size, stats["G2"].size)
        self.assertEqual(stats["G4"].precision, 1.0)
        self.assertEqual(stats["G4"].recall, 1.0)
        self.assertLess(stats["G2"].recall, 0.5)  # over-constraining

    def test_command_space(self):
        stats = {s.tier: s for s in TG.command_action_space()}
        self.assertEqual(stats["G4"].precision, 1.0)
        self.assertLess(stats["G1"].precision, 0.5)

    def test_schema_grows_with_semantics(self):
        sizes = TG.schema_sizes()
        keys = ["C0", "C1", "C2", "C3", "C4"]
        for a, b in zip(keys, keys[1:]):
            self.assertLessEqual(sizes[a], sizes[b])


class TestNamingSchemes(unittest.TestCase):
    def test_every_scheme_is_injective(self):
        from semantics_bench import naming
        for sch in naming.SCHEMES:
            m = naming.tag_map(sch)
            self.assertEqual(len(m), len(P.ALL_SIGNALS), sch)
            self.assertEqual(len(set(m.values())), len(m), sch)

    def test_scheme_changes_only_identifiers(self):
        """Descriptions, units, ranges, access and relations must be invariant."""
        from semantics_bench import naming
        before = sorted((s.description, s.unit, s.eng_low, s.eng_high, s.access,
                         s.role, P.SIGNAL_OWNER[s.tag]) for s in P.ALL_SIGNALS)
        with naming.scheme("opaque"):
            during = sorted((s.description, s.unit, s.eng_low, s.eng_high, s.access,
                             s.role, P.SIGNAL_OWNER[s.tag]) for s in P.ALL_SIGNALS)
        self.assertEqual(before, during)

    def test_context_manager_restores_state(self):
        from semantics_bench import naming
        tags = tuple(s.tag for s in P.ALL_SIGNALS)
        elements = tuple(e.eid for e in C.ELEMENTS)
        with naming.scheme("kks"):
            self.assertNotEqual(tuple(s.tag for s in P.ALL_SIGNALS), tags)
        self.assertEqual(tuple(s.tag for s in P.ALL_SIGNALS), tags)
        self.assertEqual(tuple(e.eid for e in C.ELEMENTS), elements)

    def test_decoder_reads_mnemonics_and_nothing_else(self):
        self.assertIn("filler", R.decode_convention("L1_FIL_PT0301_PV"))
        self.assertIn("pressure", R.decode_convention("L1_FIL_PT0301_PV"))
        self.assertEqual(R.decode_convention("AI_04213"), "")
        self.assertEqual(R.decode_convention("=1LCA10CP001XQ01"), "")

    def test_grounding_is_convention_invariant_only_when_grounded(self):
        from semantics_bench import experiments as EX
        rows = EX.e8_convention_robustness()
        by = {(r["scheme"], r["resolver"]): r for r in rows}
        schemes = list(dict.fromkeys(r["scheme"] for r in rows))
        spread = {k: max(by[(s, k)]["top1"] for s in schemes)
                     - min(by[(s, k)]["top1"] for s in schemes)
                  for k, _c, _d in EX.RESOLVERS}
        self.assertGreater(spread["C1+conv"], 0.3)   # fragile
        self.assertEqual(spread["C4"], 0.0)          # invariant
        # decoding a convention that lies is worse than ignoring it
        self.assertLess(by[("inconsistent", "C1+conv")]["top1"],
                        by[("inconsistent", "C1")]["top1"])
        self.assertEqual(by[("mnemonic", "C4")]["confidently_wrong"], 0.0)


class TestIntentRouting(unittest.TestCase):
    def test_profile_detects_intent(self):
        self.assertIn("behaviour", R.intent_profile("Can I start the Line 2 filler?"))
        self.assertIn("provenance", R.intent_profile("Why did the filler stop at 02:15?"))
        self.assertIn("recipe", R.intent_profile("Does it match the Cola recipe?"))
        self.assertNotIn("recipe",
                         R.intent_profile("What is the bowl level of the Line 1 filler?"))

    def test_routing_never_degrades_and_usually_helps(self):
        from semantics_bench import experiments as EX
        rows = EX.e9_routing()
        by = {(r["condition"], r["routed"], r["budget"]): r for r in rows}
        for cond in ("C3", "C4"):
            for b in EX.BUDGET_SWEEP:
                self.assertGreaterEqual(by[(cond, True, b)]["ceiling"],
                                        by[(cond, False, b)]["ceiling"] - 1e-9,
                                        f"{cond}@{b}")
        budget = EX.TOKEN_BUDGET
        self.assertGreater(by[("C4", True, budget)]["ceiling"],
                           by[("C4", False, budget)]["ceiling"])

    def test_routing_restores_verifiable_grounding(self):
        from semantics_bench import experiments as EX
        rows = EX.e9_routing()
        by = {(r["condition"], r["routed"], r["budget"]): r for r in rows}
        b = EX.TOKEN_BUDGET
        self.assertLess(by[("C4", False, b)]["verifiable_grounding"], 1.0)
        self.assertEqual(by[("C4", True, b)]["verifiable_grounding"], 1.0)

    def test_routing_costs_no_extra_budget(self):
        from semantics_bench import experiments as EX
        rows = EX.e9_routing()
        by = {(r["condition"], r["routed"], r["budget"]): r for r in rows}
        b = EX.TOKEN_BUDGET
        self.assertLess(abs(by[("C4", True, b)]["mean_tokens"]
                            - by[("C4", False, b)]["mean_tokens"]), 200)


class TestDeterminism(unittest.TestCase):
    """The paper claims every number is reproducible; that claim is testable.

    Iterating a ``set`` anywhere in the retrieval path makes traversal order --
    and therefore what survives the token budget -- depend on ``PYTHONHASHSEED``.
    """

    PROBE = (
        "from semantics_bench import experiments as E, conditions as C;"
        "rows = E.e2_context(6000);"
        "g = E.e1_grounding();"
        "print([sum(1 for r in rows if r.condition == c.key and r.sufficient)"
        "       for c in C.CONDITIONS],"
        "      [sum(1 for r in g if r.condition == c.key and r.top1)"
        "       for c in C.CONDITIONS])"
    )

    def test_results_are_hash_seed_independent(self):
        import os
        import subprocess
        import sys

        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        outputs = []
        for seed in ("0", "1", "424242"):
            env = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": here}
            res = subprocess.run([sys.executable, "-c", self.PROBE], cwd=here,
                                 env=env, capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, res.stderr)
            outputs.append(res.stdout.strip())
        self.assertEqual(len(set(outputs)), 1, f"non-deterministic: {outputs}")


class TestMetrics(unittest.TestCase):
    def test_tokeniser_is_monotone_and_deterministic(self):
        a = M.surrogate_tokens("hello world")
        self.assertEqual(a, M.surrogate_tokens("hello world"))
        self.assertGreater(M.surrogate_tokens("hello world hello"), a)

    def test_wilson(self):
        lo, hi = M.wilson_interval(5, 10)
        self.assertLess(lo, 0.5)
        self.assertGreater(hi, 0.5)

    def test_binary_scoring(self):
        sc = M.score_binary([(True, True), (True, False), (False, True), (False, False)])
        self.assertEqual(sc.tp, 1)
        self.assertEqual(sc.fn, 1)
        self.assertAlmostEqual(sc.false_positive_rate, 0.5)


class TestSparqlProbes(unittest.TestCase):
    def test_all_probes_execute(self):
        from semantics_bench import sparql_probe as SP
        rows = SP.run()
        self.assertEqual(len(rows), len(SP.QUERIES))
        for r in rows:
            self.assertGreater(r.query_tokens, 0)
        by_task = {r.task: r for r in rows}
        self.assertEqual(by_task["TOP-02"].result_rows, 3)
        self.assertEqual(by_task["RNG-04"].result_rows, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
