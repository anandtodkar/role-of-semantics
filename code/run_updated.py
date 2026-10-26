"""Generate all tables, figures and macros of the state-of-the-art survey in paper_updated/.

Inputs: survey sheets under paper_updated/survey, the archived benchmark (results/results.json),
re-run revision controls R1-R3, and the OPC UA/AAS case study. No model API is called.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
from collections import Counter, defaultdict
from pathlib import Path

from run_revision import summarize_contexts
from semantics_bench import opcua_aas as OA
from semantics_bench import revision as REV
from survey_tools import agreement as AG
from survey_tools import screening as S
from survey_tools.records import read_csv

ROOT = Path(__file__).resolve().parent.parent
CRITERIA = [f"U{index}" for index in range(1, 11)]
ROW_END = " " + chr(92) * 2
DIGIT_WORDS = dict(zip("01234", ("Zero", "One", "Two", "Three", "Four")))


def _name(prefix: str, label: str) -> str:
    return prefix + "".join(DIGIT_WORDS.get(char, char) for char in label)


def _tex(value: object) -> str:
    return "".join({"_": r"\_", "%": r"\%", "&": r"\&", "#": r"\#"}.get(c, c) for c in str(value))


def _pct(value: float) -> str:
    return f"{100 * value:.0f}\\%"


def _table(caption: str, label: str, headers: list[str], rows: list[list], spec: str | None = None,
           wide: bool = False, size: str = r"\footnotesize") -> str:
    environment = "table*" if wide else "table"
    lines = [f"\\begin{{{environment}}}[t]", r"\centering" + size, r"\setlength{\tabcolsep}{3pt}",
             "\\caption{" + caption + "}", "\\label{" + label + "}",
             "\\begin{tabular}{@{}" + (spec or "l" + "r" * (len(headers) - 1)) + "@{}}",
             r"\toprule", " & ".join(headers) + ROW_END, r"\midrule"]
    lines.extend(" & ".join(str(cell) for cell in row) + ROW_END for row in rows)
    lines.extend([r"\bottomrule", r"\end{tabular}", f"\\end{{{environment}}}", ""])
    return "\n".join(lines)


def survey_outputs(survey: Path) -> tuple[dict, dict[str, str], dict[str, str]]:
    tables, figures, macros = {}, {}, {}
    unique = json.loads((survey / "records" / "unique.json").read_text(encoding="utf-8"))
    log = json.loads((survey / "records" / "harvest_log.json").read_text(encoding="utf-8"))
    counts = S.prisma_counts(unique["identified_by_source"], survey / "screening" / "title_abstract.csv",
                             survey / "screening" / "full_text.csv", unique.get("automation_excluded", 0))
    figures["prisma.tex"] = S.prisma_tikz(counts)
    failed = sorted({query["source"] for query in log["queries"] if query["status"] != "ok"})
    macros.update(SurveyIdentified=counts["identified"], SurveyUnique=counts["screened"],
                  SurveyDuplicates=counts["duplicates_removed"], SurveyIncluded=counts["included"],
                  SurveyPendingTA=counts["ta_pending"], SurveyHarvestDate=log["run_utc"][:10],
                  SurveyFailedSources=_tex(", ".join(failed) or "none"),
                  SurveyFamilies=len({query["family"] for query in log["queries"]}),
                  SurveyArxiv=unique["identified_by_source"].get("arxiv", 0),
                  SurveyOpenAlex=unique["identified_by_source"].get("openalex", 0),
                  SurveyCrossref=unique["identified_by_source"].get("crossref", 0),
                  SurveyAutoExcluded=counts["automation_excluded"],
                  SurveyProtocolVersion=json.loads((survey / "protocol.json").read_text(encoding="utf-8"))["version"],
                  SurveyHarvestProtocolVersion=log["protocol_version"],
                  SurveyRelatedCandidates=len(read_csv(survey / "screening" / "related_survey_shortlist.csv"))
                  if (survey / "screening" / "related_survey_shortlist.csv").exists() else 0)

    scores = read_csv(survey / "auf_scores.csv")
    evidence = read_csv(survey / "auf_evidence.csv")
    located = sum(bool(row["locator"]) for row in evidence)
    uncited = [row["technology"] for row in scores if not row["citation_keys"]]
    lines, previous = [], None
    for row in scores:
        cite = ("\\cite{" + ",".join(row["citation_keys"].split(";")) + "}") if row["citation_keys"] else "$^\\dagger$"
        if previous is not None and row["layer"] != previous:
            lines.append(r"\midrule")
        layer = row["layer"] if row["layer"] != previous else ""
        previous = row["layer"]
        lines.append(" & ".join([layer, _tex(row["technology"]) + " " + cite, *[row[c] for c in CRITERIA]]) + ROW_END)
    tables["auf_matrix.tex"] = "\n".join([
        r"\begin{table*}[t]", r"\centering\footnotesize", r"\setlength{\tabcolsep}{3.4pt}",
        r"\caption{AUF coding of 24 standards and vocabularies (scores 0--3, rubric in Table~\ref{tab:rubric}). "
        r"Scores describe what the specification standardises by default, not deployed profiles; single-rater (R1) "
        r"coding, inter-rater agreement pending. $^\dagger$specification reference to be added.}",
        r"\label{tab:auf-matrix}", r"\begin{tabular}{@{}ll" + "c" * 10 + "@{}}", r"\toprule",
        "L & Technology & " + " & ".join(CRITERIA) + ROW_END, r"\midrule",
        *lines, r"\bottomrule", r"\end{tabular}", r"\end{table*}", ""])

    numeric = {row["technology"]: {c: int(row[c]) for c in CRITERIA} for row in scores}
    first_class = {c: sum(values[c] == 3 for values in numeric.values()) for c in CRITERIA}
    full_cover = [name for name, values in numeric.items() if all(values[c] >= 2 for c in ("U3", "U5", "U6"))]
    all_first = [name for name, values in numeric.items() if all(values[c] == 3 for c in ("U3", "U5", "U6"))]
    macros.update(AufAllThreeFirstClass=len(all_first), AufAllThreeStrongNames=_tex(", ".join(full_cover)))
    macros.update(AufTechnologies=len(scores), AufCells=len(scores) * 10, AufLocated=located,
                  AufUncited=len(uncited), AufTypesFirstClass=first_class["U2"],
                  AufUnitsFirstClass=first_class["U3"], AufBehaviourFirstClass=first_class["U5"],
                  AufConstraintsFirstClass=first_class["U6"], AufProvenanceFirstClass=first_class["U7"],
                  AufAllThreeStrong=len(full_cover))
    second = survey / "auf_scores_r2.csv"
    if second.exists():
        other = {row["technology"]: row for row in read_csv(second)}
        first_codes, second_codes = [], []
        for row in scores:
            for criterion in CRITERIA:
                value = (other.get(row["technology"]) or {}).get(criterion)
                first_codes.append(int(row[criterion]))
                second_codes.append(int(value) if value not in (None, "") else None)
        if any(value is not None for value in second_codes):
            macros["AufKappa"] = f"{AG.cohen_kappa(first_codes, second_codes, 'quadratic'):.2f}"
            macros["AufAlpha"] = f"{AG.krippendorff_alpha(list(zip(first_codes, second_codes)), 'ordinal'):.2f}"
    macros.setdefault("AufKappa", "pending")
    macros.setdefault("AufAlpha", "pending")

    systems = read_csv(survey / "agent_systems.csv")
    categories = Counter(row["grounding_category"] for row in systems if row["grounding_category"])
    macros["AgentSystemsCoded"] = len(systems)
    if systems:
        system_rows = [["\\cite{" + row["citation_key"] + "}", row["grounding_category"], *[row[c] for c in CRITERIA],
                        row["runtime_validation"], row["evaluation_level"]] for row in systems]
    else:
        system_rows = [[r"\multicolumn{14}{c}{\textit{Full-text coding of included systems pending (Sec.~\ref{sec:method}).}}"]]
    tables["agent_systems.tex"] = _table(
        "AUF coding of industrial AI-agent systems (0 absent, 1 prose/implicit, 2 explicit, 3 checked at runtime). "
        "Cat.: grounding category A--E (Fig.~\\ref{fig:categories}).", "tab:agent-systems",
        ["System", "Cat.", *CRITERIA, "Valid.", "Eval."], system_rows, spec="ll" + "c" * 12, wide=True)
    macros.update({f"AgentCat{key}": categories.get(key, 0) for key in "ABCDE"})

    surveys = [row for row in read_csv(survey / "related_surveys.csv") if row.get("verified_by")]
    columns = ["industrial_llm_agents", "industrial_kg", "information_models", "semantic_interop",
               "runtime_validation", "capability_framework", "systematic_method"]
    mark = {"yes": r"\checkmark", "partial": r"(\checkmark)"}
    survey_rows = [["\\cite{" + row["citation_key"] + "}", *[mark.get(row[c], "") for c in columns]] for row in surveys]
    survey_rows.append([r"\textbf{This survey}", *[r"\checkmark"] * len(columns)])
    tables["related_surveys.tex"] = _table(
        "Scope of existing surveys versus this survey (\\checkmark{} central, (\\checkmark) partial). "
        "Agt.: industrial LLM agents; KG: industrial knowledge graphs; IM: information models; Int.: semantic "
        "interoperability; Val.: runtime validation; Fw.: capability framework; Sys.: systematic method. "
        "Rows are added only after the authors verify each survey's full text.",
        "tab:related-surveys", ["Survey", "Agt.", "KG", "IM", "Int.", "Val.", "Fw.", "Sys."],
        survey_rows, spec="l" + "c" * len(columns))
    macros["RelatedSurveysVerified"] = len(surveys)
    return counts, tables | {"_figures": figures}, macros


def case_study_outputs(root: Path) -> tuple[dict, dict[str, str], dict[str, str]]:
    data = json.loads((root / "results" / "results.json").read_text(encoding="utf-8"))
    tables, macros = {}, {}
    grounding = defaultdict(list)
    for row in data["e1_grounding"]:
        grounding[row["condition"]].append(row)
    tiers = {row["tier"]: row for row in data["e4_tiers"]}
    cs1 = []
    for row in data["e6_ceiling"]:
        condition, group = row["condition"], grounding[row["condition"]]
        tier = tiers["G" + condition[1]]
        cs1.append([condition, row["counterpart"] if "counterpart" in row else "",
                    _pct(sum(item["top1"] for item in group) / len(group)),
                    _pct(sum(item["verifiable"] for item in group) / len(group)),
                    _pct(row["ceiling"]), tier["tier"], _pct(tier["recall"]), _pct(tier["fp_rate"])])
        macros[_name("CsSuff", condition)] = _pct(row["ceiling"])
        macros[_name("CsTop", condition)] = _pct(sum(item["top1"] for item in group) / len(group))
        macros[_name("CsRecall", tier["tier"])] = _pct(tier["recall"])
        macros[_name("CsFPR", tier["tier"])] = _pct(tier["fp_rate"])
    tables["cs1_exposure.tex"] = _table(
        "CS1: progressive capability exposure on the authored reference plant (17 assets, 73 signals, "
        "35 tasks, 84 faulty and 53 legal proposals). Suff.: declared required facts present at 6,000 "
        "surrogate tokens (not an accuracy bound). Context C$k$ is paired with validator G$k$.",
        "tab:cs1", ["Ctx.", "Projection", "Top-1", "Verif.", "Suff.", "Val.", "Recall", "FPR"], cs1,
        spec="llrrrlrr", wide=True)

    retrieval = summarize_contexts(REV.retrieval_controls(), ("condition", "strategy", "budget"))
    cs2 = [[row["condition"], row["strategy"], _pct(row["sufficiency"]), _pct(row["coverage"]),
            round(row["mean_tokens"])] for row in retrieval
           if row["condition"] in ("C2", "C3", "C4") and row["budget"] == 6000]
    tables["cs2_retrieval.tex"] = _table(
        "CS2: retrieval strategy crossed with exposed capabilities at 6,000 surrogate tokens. Membership "
        "and graph retrieval share a fixed entity resolver; graph traversal requires C3/C4 relations.",
        "tab:cs2", ["Ctx.", "Retrieval", "Suff.", "Coverage", "Tokens"], cs2, spec="llrrr")

    ablation = REV.capability_ablation()
    context = {row["removed"]: row for row in summarize_contexts(ablation["contexts"], ("removed",))}
    cs3 = [[row["validator"], _pct(context[row["validator"]]["sufficiency"]), _pct(row["recall"]),
            row["abstentions"]] for row in ablation["validators"]]
    tables["cs3_ablation.tex"] = _table(
        "CS3: removing one AUF capability at a time from the full C4/G4 configuration. Abstentions on "
        "missing evidence are not counted as detections.", "tab:cs3",
        ["Removed", "Suff.", "Recall", "Abstain"], cs3, spec="lrrr")

    equal = REV.equal_information_validation()
    cs4 = [["Procedural" if row["validator"] == "procedural_full" else "SHACL", f"{row['tp']}/{row['tp'] + row['fn']}",
            f"{row['fp']}/{row['fp'] + row['tn']}", _pct(row["diagnosis_rate"])] for row in equal["summary"]]
    tables["cs4_equal.tex"] = _table(
        "CS4: equally informed procedural and SHACL validators on identical engineering facts.",
        "tab:cs4", ["Validator", "Faults caught", "False alarms", "Diagnosis"], cs4, spec="lrrr")
    macros["CsDisagreements"] = len(equal["disagreements"])

    synthetic = OA.synthetic_case()
    kuka_dir = root / "paper_revision" / "adhoc_kuka"
    kuka = OA.kuka_case(kuka_dir / "source_nodesets" / "example.kuka.robot_raw.xml",
                        kuka_dir / "kuka_instance_aas_v3.json")
    cs5 = []
    for category, auf in OA.CATEGORIES.items():
        cells = []
        for projection in ("opcua", "aas", "union"):
            row = synthetic["coverage"][projection][category]
            cell = f"{row['correct']}/{row['reference']}"
            cells.append(cell + (f" ({row['conflict']}$\\neq$)" if row["conflict"] else ""))
        cs5.append([category.replace("_", " "), auf, *cells])
    tables["cs5_opcua_aas.tex"] = _table(
        "CS5: matched facts recovered from the emitted OPC UA NodeSet2 and AAS v3 projections of the same "
        "plant ($\\neq$: conflicting value). Both projections are generated from one specification, so this "
        "measures the emitted profiles, not limits of either standard.", "tab:cs5",
        ["Fact", "AUF", "OPC UA", "AAS", "Union"], cs5, spec="llrrr")
    totals = {projection: sum(row["correct"] for row in synthetic["coverage"][projection].values())
              for projection in ("opcua", "aas", "union")}
    kuka_total = sum(row["correct"] for row in kuka["coverage"].values())
    macros.update(CsFacts=synthetic["reference_facts"], CsOpcuaFacts=totals["opcua"],
                  CsAasFacts=totals["aas"], CsUnionFacts=totals["union"],
                  CsOpcuaPct=_pct(totals["opcua"] / synthetic["reference_facts"]),
                  CsAasPct=_pct(totals["aas"] / synthetic["reference_facts"]),
                  CsUnionPct=_pct(totals["union"] / synthetic["reference_facts"]),
                  CsQkConflicts=synthetic["coverage"]["opcua"]["quantity_kind"]["conflict"],
                  CsOpcuaTokens=f"{synthetic['serialisations']['opcua_nodeset2_xml']['surrogate_tokens']:,}",
                  CsAasTokens=f"{synthetic['serialisations']['aas_v3_json']['surrogate_tokens']:,}",
                  CsKukaFacts=kuka["reference_facts"], CsKukaRetained=kuka_total)
    results = {"cs2": retrieval, "cs3": ablation["validators"], "cs4": equal["summary"],
               "cs4_disagreements": equal["disagreements"], "cs5_synthetic": synthetic, "cs5_kuka": kuka}
    return results, tables, macros


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paper", type=Path, default=ROOT / "paper_updated")
    args = parser.parse_args()
    destination = args.paper.resolve()
    if destination in {(ROOT / "paper").resolve(), (ROOT / "paper_revision").resolve()}:
        parser.error("Write to paper_updated, never to the original or revision manuscripts.")
    counts, survey_tables, survey_macros = survey_outputs(destination / "survey")
    figures = survey_tables.pop("_figures")
    case_results, case_tables, case_macros = case_study_outputs(ROOT)
    (destination / "tables").mkdir(parents=True, exist_ok=True)
    (destination / "figures").mkdir(parents=True, exist_ok=True)
    for name, text in (survey_tables | case_tables).items():
        (destination / "tables" / name).write_text(text, encoding="utf-8")
    for name, text in figures.items():
        (destination / "figures" / name).write_text(text, encoding="utf-8")
    macros = survey_macros | case_macros
    (destination / "generated_updated.tex").write_text(
        "".join(f"\\newcommand{{\\{name}}}{{{value}}}\n" for name, value in sorted(macros.items())),
        encoding="utf-8")
    sources = sorted((ROOT / "code" / "semantics_bench").glob("*.py")) + sorted((ROOT / "code" / "survey_tools").glob("*.py"))
    results = {"config": {"python": platform.python_version(),
                          "sources_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}},
               "prisma": counts, "macros": {key: str(value) for key, value in macros.items()}, **case_results}
    (destination / "results").mkdir(parents=True, exist_ok=True)
    (destination / "results" / "updated_results.json").write_text(
        json.dumps(results, indent=1, allow_nan=False, default=str) + "\n", encoding="utf-8")
    print(f"PRISMA: identified={counts['identified']} unique={counts['screened']} included={counts['included']}")
    print(f"CS5 facts: OPC UA {macros['CsOpcuaFacts']}, AAS {macros['CsAasFacts']}, union {macros['CsUnionFacts']} of {macros['CsFacts']}")
    print(f"Tables: {len(survey_tables) + len(case_tables)}; macros: {len(macros)}")


if __name__ == "__main__":
    main()
