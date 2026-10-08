"""Run isolated revision controls and generate their manuscript tables."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
from collections import defaultdict
from pathlib import Path

from semantics_bench import revision as REV
from semantics_bench import archive_report

ROOT = Path(__file__).resolve().parent.parent


def _escape(value: object) -> str:
    replacements = {"_": r"\_", "%": r"\%", "&": r"\&", "#": r"\#"}
    return "".join(replacements.get(character, character) for character in str(value))


def _table(caption: str, label: str, headers: tuple[str, ...], rows: list[list]) -> str:
    row_end = " " + chr(92) * 2
    lines = [r"\begin{table}[t]", r"\centering\footnotesize",
             r"\caption{" + caption + "}", r"\label{" + label + "}",
             r"\begin{tabular}{@{}" + "l" * len(headers) + "@{}}", r"\toprule",
             " & ".join(headers) + row_end, r"\midrule"]
    lines.extend(" & ".join(_escape(cell) for cell in row) + row_end for row in rows)
    lines.extend([r"\bottomrule", r"\end{tabular}", r"\end{table}", ""])
    return "\n".join(lines)


def summarize_contexts(rows: list[dict], keys: tuple[str, ...]) -> list[dict]:
    groups = defaultdict(list)
    for row in rows:
        groups[tuple(row[key] for key in keys)].append(row)
    output = []
    for values, group in groups.items():
        result = dict(zip(keys, values))
        result.update(n=len(group),
                      sufficiency=sum(row["sufficient"] for row in group) / len(group),
                      coverage=sum(row["coverage"] for row in group) / len(group),
                      mean_tokens=sum(row["tokens"] for row in group) / len(group))
        output.append(result)
    return output


def emit(results: dict, destination: Path) -> None:
    tables = destination / "tables"
    tables.mkdir(parents=True, exist_ok=True)
    equal = results["r1_equal_information"]["summary"]
    tables.joinpath("r1_equal.tex").write_text(_table(
        "R1: equal-information validation on the synthetic reference corpus. "
        "Diagnosis maps scale faults to range violations for both implementations.",
        "tab:revision-equal", ("Validator", "Recall", "FPR", "Diagnosis"),
        [["Procedural" if row["validator"] == "procedural_full" else "SHACL",
          f"{row['recall']:.3f}", f"{row['false_positive_rate']:.3f}",
          f"{row['diagnosis_rate']:.3f}"] for row in equal]), encoding="utf-8")
    selected = [row for row in results["r2_summary"]
                if row["condition"] in ("C2", "C4") and row["budget"] in (None, 6000)]
    tables.joinpath("r2_retrieval.tex").write_text(_table(
        "R2: crossed retrieval at 6,000 surrogate tokens. Oracle-all is unbudgeted "
        "and diagnostic only. Membership uses a fixed shared entity resolver.",
        "tab:revision-retrieval", ("Context", "Retrieval", "Suff.", "Coverage"),
        [[row["condition"], row["strategy"], f"{row['sufficiency']:.3f}",
          f"{row['coverage']:.3f}"] for row in selected]), encoding="utf-8")
    ablation = {row["removed"]: row for row in results["r3_context_summary"]}
    tables.joinpath("r3_ablation.tex").write_text(_table(
        "R3: capability removal. Context sufficiency uses a fixed full-C4 ordering; "
        "abstentions are not detections. Context topology removes flow only; "
        "validator topology removes scope-containment checks.",
        "tab:revision-ablation", ("Removed", "Suff.", "Recall", "Abstain"),
        [[row["validator"], f"{ablation[row['validator']]['sufficiency']:.3f}",
          f"{row['recall']:.3f}", row["abstentions"]]
         for row in results["r3_ablation"]["validators"]]), encoding="utf-8")
    tables.joinpath("r4_degradation.tex").write_text(_table(
        "R4: synthetic missing-evidence and dispatch-time state probes. "
        "These are not PLC trials or physical safety measurements.",
        "tab:revision-degradation", ("Probe", "Disposition"),
        [[row["probe"], row["disposition"]] for row in results["r4_degradation"]]), encoding="utf-8")
    tables.joinpath("r5_serialisation.tex").write_text(_table(
        "R5: identical RDF graph round-tripped through three syntaxes. "
        "Only isomorphic round trips qualify as equal-information controls. "
        "Counts use the surrogate tokenizer.",
        "tab:revision-serialisation", ("Syntax", "Triples", "Tokens", "Isomorphic"),
        [[row["syntax"], row["triples"], row["surrogate_tokens"],
          "yes" if row["roundtrip_isomorphic"] else "no"]
         for row in results["r5_serialisation"]]), encoding="utf-8")
    destination.joinpath("generated_revision.tex").write_text(
        r"\newcommand{\RevisionCases}{" + str(equal[0]["n"]) + "}\n"
        + r"\newcommand{\RevisionDisagreements}{"
        + str(len(results["r1_equal_information"]["disagreements"])) + "}\n",
        encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paper", type=Path, default=ROOT / "paper_revision")
    args = parser.parse_args()
    destination = args.paper.resolve()
    if destination == (ROOT / "paper").resolve():
        parser.error("Use a revision output folder, not the original paper folder.")
    source_paths = sorted((ROOT / "code" / "semantics_bench").glob("*.py"))
    results = {
        "config": {"schema_version": 1, "synthetic_only": True,
                   "python": platform.python_version(), "budgets": [1500, 6000, 24000],
                   "tokenizer": "deterministic surrogate, not model billing tokens",
                   "sources_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                                      for path in source_paths}},
        "r1_equal_information": REV.equal_information_validation(),
        "r2_retrieval": REV.retrieval_controls(),
        "r3_ablation": REV.capability_ablation(),
        "r4_degradation": REV.degradation_probes(),
        "r5_serialisation": REV.equal_information_serialisation(),
    }
    results["r2_summary"] = summarize_contexts(
        results["r2_retrieval"], ("condition", "strategy", "budget"))
    results["r3_context_summary"] = summarize_contexts(
        results["r3_ablation"]["contexts"], ("removed",))
    result_dir = destination / "results"
    result_dir.mkdir(parents=True, exist_ok=True)
    result_path = result_dir / "revision_results.json"
    result_path.write_text(json.dumps(results, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    emit(results, destination)
    manifest = archive_report.emit(ROOT, destination)
    print(f"Restored archive tables: {len(manifest['tables'])}")
    print(f"E11 raw responses available: {sum(run['raw_rows'] for run in manifest['e11_archives'])}")
    for row in results["r1_equal_information"]["summary"]:
        print(f"R1 {row['validator']}: n={row['n']}, recall={row['recall']:.3f}, "
              f"FPR={row['false_positive_rate']:.3f}")
    print(f"R1 raw-family disagreements: {len(results['r1_equal_information']['disagreements'])}")
    print(f"R2 task-condition-strategy-budget rows: {len(results['r2_retrieval'])}")
    print(f"R3 context rows: {len(results['r3_ablation']['contexts'])}")
    print(f"R4 synthetic probes: {len(results['r4_degradation'])}")
    print(f"R5 isomorphic syntax round trips: "
          f"{sum(row['roundtrip_isomorphic'] for row in results['r5_serialisation'])}/3")
    print(f"Results: {result_path}")
    print(f"Tables: {destination / 'tables'}")


if __name__ == "__main__":
    main()