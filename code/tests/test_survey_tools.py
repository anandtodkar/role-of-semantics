from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from survey_tools import agreement as A
from survey_tools import dedup as D
from survey_tools import importers as I
from survey_tools import screening as S
from survey_tools.records import Record, normalize_doi, read_csv, write_csv

RIS = """TY  - JOUR
TI  - Grounding LLM agents with OPC UA
AU  - Doe, Jane
AU  - Roe, Rick
PY  - 2025
DO  - https://doi.org/10.1000/ABC.1
T2  - IEEE Trans. Ind. Informat.
AB  - An abstract.
ER  - 
TY  - CPAPER
TI  - Second paper
PY  - 2024
ER  - 
"""

BIB = """@article{key1,
  title = {Grounding {LLM} Agents with {OPC} {UA}},
  author = {Doe, Jane and Roe, Rick},
  year = {2025}, doi = {10.1000/abc.1}, journal = {TII}
}
@misc{key2, title = "Preprint, with comma", year = 2026}
"""

SCOPUS = '''Authors,Title,Year,Source title,DOI,Abstract,Document Type
"Doe J.; Roe R.","Grounding LLM agents with OPC UA",2025,"TII","10.1000/abc.1","x","Article"
'''


class TestImporters(unittest.TestCase):
    def test_ris_bibtex_and_csv_agree(self):
        ris = I.parse_ris(RIS, "ieee")
        bib = I.parse_bibtex(BIB, "acm")
        table = I.parse_table(SCOPUS, "scopus")
        self.assertEqual(len(ris), 2)
        self.assertEqual(ris[0].doi, "10.1000/abc.1")
        self.assertEqual(ris[0].authors, ["Doe, Jane", "Roe, Rick"])
        self.assertEqual(ris[0].peer_reviewed, "yes")
        self.assertEqual(bib[0].title, "Grounding LLM Agents with OPC UA")
        self.assertEqual(bib[1].title, "Preprint, with comma")
        self.assertEqual(bib[1].year, 2026)
        self.assertEqual(table[0].doi, bib[0].doi)
        self.assertEqual(table[0].authors, ["Doe J.", "Roe R."])

    def test_doi_normalisation(self):
        self.assertEqual(normalize_doi("DOI: 10.1/X"), "10.1/x")
        self.assertIsNone(normalize_doi(""))


class TestDedup(unittest.TestCase):
    def test_merges_doi_and_title_but_lists_near_matches(self):
        records = [
            Record("arxiv", "1", "Grounding LLM agents with OPC UA", 2025, ["Jane Doe"], peer_reviewed="no"),
            Record("scopus", "2", "Grounding LLM Agents with OPC-UA", 2025, ["Doe, J."], doi="10.1/a",
                   peer_reviewed="yes"),
            Record("ieee", "3", "Grounding LLM agents with OPC UA", 2025, ["X"], doi="10.1/a",
                   peer_reviewed="yes"),
            Record("openalex", "4", "Grounding LLM agents with OPC UAs", 2025, ["Jane Doe"]),
            Record("openalex", "5", "Grounding LLM agents with OPC UA", 2019, ["Jane Doe"]),
        ]
        merged, uncertain = D.deduplicate(records)
        self.assertEqual(len(merged), 3)
        main = next(item for item in merged if len(item["merged_ids"]) == 3)
        self.assertEqual(main["source"], "ieee")
        self.assertEqual(main["peer_reviewed"], "yes")
        self.assertEqual(len(uncertain), 1)


class TestAgreement(unittest.TestCase):
    def test_cohen_kappa_textbook(self):
        first = ["y"] * 25 + ["n"] * 25
        second = ["y"] * 20 + ["n"] * 5 + ["y"] * 10 + ["n"] * 15
        self.assertAlmostEqual(A.cohen_kappa(first, second), 0.4, places=6)
        self.assertAlmostEqual(A.percent_agreement(first, second), 0.7)

    def test_weighted_kappa_penalises_distance(self):
        first = [0, 1, 2, 3, 3, 2]
        near = [0, 1, 2, 3, 2, 2]
        far = [0, 1, 2, 3, 0, 2]
        self.assertGreater(A.cohen_kappa(first, near, "quadratic"),
                           A.cohen_kappa(first, far, "quadratic"))
        self.assertEqual(A.cohen_kappa(first, first, "linear"), 1.0)

    def test_krippendorff_reference_example(self):
        first = [0, 1, 0, 0, 0, 0, 0, 0, 1, 0]
        second = [1, 1, 1, 0, 0, 1, 0, 0, 0, 0]
        alpha = A.krippendorff_alpha(list(zip(first, second)))
        self.assertAlmostEqual(alpha, 0.095, places=3)
        self.assertAlmostEqual(A.krippendorff_alpha([(1, 1), (2, 2), (3, None)], "ordinal"), 1.0)

    def test_kappa_and_alpha_ignore_missing(self):
        self.assertEqual(A.disagreements(["a", "b", "c"], [1, 2, None], [1, 3, 2]),
                         [{"unit": "b", "rater_1": 2, "rater_2": 3}])


class TestScreening(unittest.TestCase):
    def test_automation_rule_requires_both_term_groups(self):
        rules = {"A1_ai_term": r"large language model|\bllm", "A2_industrial_term": r"manufactur|opc ua"}
        records = [{"record_id": str(i), "title": title, "abstract": abstract, "year": 2025,
                    "sources": ["crossref"]} for i, (title, abstract) in enumerate([
                        ("LLM agents for OPC UA", None),
                        ("Large prepubertal ovarian cyst", "model"),
                        ("Manufacturing scheduling", "using a large language model")])]
        kept, excluded = S.auto_screen(records, rules | {"description": "ignored"})
        self.assertEqual([item["record_id"] for item in kept], ["0", "2"])
        self.assertEqual(excluded[0]["rule"], "A1_ai_term")

    def test_sheet_preserves_decisions_and_prisma_adds_up(self):
        merged = [Record("openalex", str(i), f"Title {i}", 2025).to_dict()
                  | {"merged_ids": [], "sources": ["openalex"], "query_families": ["F1"]}
                  for i in range(10)]
        with tempfile.TemporaryDirectory() as folder:
            sheet = Path(folder) / "ta.csv"
            S.build_title_abstract_sheet(merged, sheet, 0.2, 1)
            rows = read_csv(sheet)
            self.assertEqual(sum(row["double_code"] == "yes" for row in rows), 2)
            for index, row in enumerate(rows):
                row["final_decision"] = "include" if index < 3 else ("exclude" if index < 8 else "")
            write_csv(rows, sheet, S.TA_COLUMNS)
            S.build_title_abstract_sheet(merged, sheet, 0.2, 1)
            self.assertEqual(sum(row["final_decision"] == "include" for row in read_csv(sheet)), 3)
            full = Path(folder) / "ft.csv"
            S.build_full_text_sheet(sheet, full, 0.2, 1)
            ft_rows = read_csv(full)
            ft_rows[0].update(final_decision="include")
            ft_rows[1].update(final_decision="exclude", final_reason="E2")
            ft_rows[2].update(retrieved="no")
            write_csv(ft_rows, full, S.FT_COLUMNS)
            counts = S.prisma_counts({"openalex": 12}, sheet, full)
            self.assertEqual(counts["duplicates_removed"], 2)
            self.assertEqual((counts["ta_excluded"], counts["ta_pending"], counts["ft_sought"]), (5, 2, 3))
            self.assertEqual((counts["ft_not_retrieved"], counts["included"]), (1, 1))
            self.assertFalse(counts["complete"])
            self.assertIn("Records identified: 12", S.prisma_tikz(counts))


if __name__ == "__main__":
    unittest.main()
