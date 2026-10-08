"""Compact manuscript tables from saved experiments; never call a model API."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path

SUFFICIENCY_HEADER = "Suff."


def _tex(value: object) -> str:
    replacements = {"_": r"\_", "%": r"\%", "&": r"\&", "#": r"\#"}
    return "".join(replacements.get(character, character) for character in str(value))


def _table(caption: str, label: str, headers: list[str], rows: list[list],
           wide: bool = False) -> str:
    environment = "table*" if wide else "table"
    row_end = " " + chr(92) * 2
    lines = [f"\\begin{{{environment}}}[t]", r"\centering\footnotesize",
             "\\caption{" + caption + "}", "\\label{" + label + "}",
             r"\setlength{\tabcolsep}{3.5pt}",
             "\\begin{tabular}{@{}" + "l" + "r" * (len(headers) - 1) + "@{}}",
             r"\toprule", " & ".join(headers) + row_end, r"\midrule"]
    lines.extend(" & ".join(_tex(cell) for cell in row) + row_end for row in rows)
    lines.extend([r"\bottomrule", r"\end{tabular}", f"\\end{{{environment}}}", ""])
    return "\n".join(lines)


def _number(value: float | None) -> str:
    return "--" if value is None else f"{value:.3f}"


def inspect_e11(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    groups = defaultdict(list)
    for row in data["rows"]:
        groups[row["condition"]].append(row)
    checks = []
    for aggregate in data["per_condition"]:
        rows = groups[aggregate["condition"]]
        checks.append({"condition": aggregate["condition"], "reported_n": aggregate["n"],
                       "raw_n": len(rows), "count_matches": aggregate["n"] == len(rows)})
    return {"source": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "model": data["meta"]["model"], "timestamp": data["meta"]["timestamp"],
            "declared_tasks": data["meta"]["n_tasks"], "declared_repeats": data["meta"]["repeats"],
            "raw_rows": len(data["rows"]),
            "observed_tasks": sorted({row["task"] for row in data["rows"]}),
            "checks": checks, "per_condition": data["per_condition"],
            "per_category": data["per_category"]}


def emit(root: Path, destination: Path) -> dict:
    source = root / "results" / "results.json"
    data = json.loads(source.read_text(encoding="utf-8"))
    tables = destination / "tables"
    tables.mkdir(parents=True, exist_ok=True)
    outputs = {}
    grounding = defaultdict(list)
    for row in data["e1_grounding"]:
        grounding[row["condition"]].append(row)
    conditions = []
    for row in data["e6_ceiling"]:
        group = grounding[row["condition"]]
        conditions.append([row["condition"], _number(sum(item["top1"] for item in group) / len(group)),
                           _number(sum(item["mrr"] for item in group) / len(group)),
                           _number(sum(item["rank"] is not None for item in group) / len(group)),
                           _number(sum(item["verifiable"] for item in group) / len(group)),
                           sum(item["distractors_in_top5"] for item in group),
                           _number(row["mean_coverage"]), _number(row["ceiling"]),
                           round(row["mean_tokens"]), _number(row["coverage_per_1k_tokens"])])
    outputs["e1_e2_e6.tex"] = _table(
        "E1/E2/E6: archived grounding and evidence sufficiency at 6,000 surrogate tokens. "
        "Sufficiency uses the original declared-fact bookkeeping, not a universal accuracy bound.",
        "tab:archive-context", ["Context", "Top-1", "MRR", "R@5", "Verif.", "Distr@5", "Coverage", SUFFICIENCY_HEADER, "Tokens", "Cov./1k"],
        conditions, wide=True)
    outputs["e6_categories.tex"] = _table(
        "E6: archived evidence sufficiency by task category. GRD identity; UNI units; "
        "RNG ranges; TOP topology; PRV provenance; ACT actions; SAF guards; REC recipes.",
        "tab:archive-categories", ["Context", "GRD", "UNI", "RNG", "TOP", "PRV", "ACT", "SAF", "REC"],
        [[row["condition"], *[_number(row[f"cat_{category}"])
                             for category in ("GRD", "UNI", "RNG", "TOP", "PRV", "ACT", "SAF", "REC")]]
         for row in data["e6_ceiling"]], wide=True)
    names = ["CSV", "NGSI-LD", "WoT TD", "Turtle", "OPC UA XML", "AAS JSON", "N-Triples", "JSON-LD"]
    format_rows = []
    for name in names:
        match = next(row for row in data["e3_serialisation"] if {
            "CSV": "Historian", "NGSI-LD": "NGSI", "WoT TD": "WoT", "Turtle": "Turtle",
            "OPC UA XML": "OPC UA", "AAS JSON": "AAS", "N-Triples": "N-Triples",
            "JSON-LD": "RDF JSON-LD"}[name] in row["format"])
        format_rows.append([name, match["tokens"], f"{match['ratio_to_csv']:.1f}"])
    outputs["e3_formats.tex"] = _table(
        "E3: archived format costs. Formats do not preserve identical fact inventories; "
        "ratios mix content and syntax. R5 tests fidelity separately.",
        "tab:archive-formats", ["Format", "Tokens", "Ratio/CSV"], format_rows)
    outputs["e4_guardrails.tex"] = _table(
        "E4: archived validator results on 84 faulty and 53 valid actions. "
        "Intervals are descriptive Wilson recall intervals.", "tab:archive-guardrails",
        ["Tier", "Caught", "Recall", "95\\% CI", "Diag.", "FPR"],
        [[row["tier"], f"{row['caught']}/84" if "caught" in row else f"{round(row['recall'] * 84)}/84",
          _number(row["recall"]), f"[{row['recall_lo']:.2f},{row['recall_hi']:.2f}]",
          _number(row["diagnosis_rate"]), _number(row["fp_rate"])] for row in data["e4_tiers"]])
    outputs["e4_families.tex"] = _table(
        "E4: detected counts by injected fault family. R1 audits raw family sets without gold-derived reclassification.",
        "tab:archive-families", ["Family", "$n$", "G1", "G2", "G3", "G4"],
        [[row["family"], row["n"], *[row[tier] for tier in ("G1", "G2", "G3", "G4")]]
         for row in data["e4_families"]])
    outputs["e4b_procedural.tex"] = _table(
        "E4b: original unit-calculus procedural baseline (GP), not the equally informed R1 implementation.",
        "tab:archive-procedural", ["Tier", "Recall", "FPR", "Scale", "Behav."],
        [[row["tier"], _number(row["recall"]), _number(row["fp_rate"]),
          f"{row['unitscale_caught']}/{row['unitscale_n']}",
          f"{row['behavioural_caught']}/{row['behavioural_n']}"] for row in data["e4b_procedural"]])
    commands = {row["tier"]: row for row in data["e5_commands"]}
    outputs["e5_actions.tex"] = _table(
        "E5: admitted write and command spaces; P and R are precision and recall against reference legality.",
        "tab:archive-actions", ["Tier", "Writes", "Write P", "Write R", "Bits removed", "Commands", "Cmd P", "Cmd R"],
        [[row["tier"], row["size"], _number(row["precision"]), _number(row["recall"]),
          f"{row['reduction_bits']:.2f}", commands[row["tier"]]["size"],
          _number(commands[row["tier"]]["precision"]), _number(commands[row["tier"]]["recall"])]
         for row in data["e5_writes"]], wide=True)
    outputs["e7_queries.tex"] = _table(
        "E7: hand-authored SPARQL execution costs, including query and result. "
        "Suff. marks the original stuffed context; query generation is not evaluated.",
        "tab:archive-queries", ["Task", "Query+result", "Stuffed", "Ratio", SUFFICIENCY_HEADER],
        [[row["task"], row["total_tokens"], row["stuffing_tokens_C4"],
          f"{row['reduction']:.1f}", "yes" if row["stuffing_sufficient"] else "no"]
         for row in data["e7_sparql"]])
    naming = defaultdict(dict)
    for row in data["e8_convention"]:
        naming[row["scheme"]][row["resolver"]] = row
    outputs["e8_naming.tex"] = _table(
        "E8: top-1 accuracy / wrong non-empty resolution across naming conventions. "
        "Wrong non-empty resolution is not calibrated model confidence.",
        "tab:archive-naming", ["Scheme", "C1", "C1+decode", "C2+decode", "C4"],
        [[scheme, *[f"{group[resolver]['top1']:.2f}/{group[resolver]['confidently_wrong']:.2f}"
                    for resolver in ("C1", "C1+conv", "C2+conv", "C4")]]
         for scheme, group in naming.items()])
    outputs["e9_routing.tex"] = _table(
        "E9: original neighbourhood (N) and routed (R) projection at 6,000 tokens. "
        "R2 uses a more conservative conversion-evidence audit.",
        "tab:archive-routing", ["Context", "Mode", SUFFICIENCY_HEADER, "Coverage", "Verif.", "Tokens"],
        [[row["condition"], "R" if row["routed"] else "N", _number(row["ceiling"]),
          _number(row["coverage"]), _number(row["verifiable_grounding"]), round(row["mean_tokens"])]
         for row in data["e9_routing"] if row["budget"] == 6000])
    archives = [inspect_e11(path) for path in sorted((root / "results").glob("e11_*.json"))]
    e11_rows = []
    for archive in archives:
        for row in archive["per_condition"]:
            e11_rows.append([row["condition"], row["n"], _number(row["accuracy"]),
                             _number(row["refusal_rate"]), _number(row["ceiling"])])
    outputs["e11_verified.tex"] = _table(
        "E11 raw-data audit: currently retained GPT smoke-test responses. "
        "Only GRD-01 and one repeat are available; no full-suite conclusion follows.",
        "tab:e11-verified", ["Context", "Responses", "Accuracy", "Refusal", SUFFICIENCY_HEADER], e11_rows)
    for filename, text in outputs.items():
        tables.joinpath(filename).write_text(text, encoding="utf-8")
    manifest = {"baseline_source": str(source.relative_to(root)),
                "baseline_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "baseline_config": data["config"], "e11_archives": archives,
                "tables": list(outputs), "schema_tokens": data["e5_schema_tokens"],
                "warning": "Original full-suite E11 generated aggregates do not match the available smoke-test raw archive."}
    result_dir = destination / "results"
    result_dir.mkdir(parents=True, exist_ok=True)
    result_dir.joinpath("archive_manifest.json").write_text(
        json.dumps(manifest, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return manifest