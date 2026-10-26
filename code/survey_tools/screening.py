"""Screening sheets and PRISMA 2020 flow counts derived only from those sheets."""

from __future__ import annotations

import random
import re
from collections import Counter
from pathlib import Path

from .records import read_csv, write_csv

AUTO_COLUMNS = ["record_id", "title", "year", "venue", "doi", "sources", "rule"]


def auto_screen(merged: list[dict], rules: dict) -> tuple[list[dict], list[dict]]:
    """Apply the protocol's deterministic title+abstract rules; return kept and excluded records."""
    patterns = {name: re.compile(pattern, re.IGNORECASE) for name, pattern in rules.items()
                if name.startswith("A") and name[1:2].isdigit()}
    kept, excluded = [], []
    for item in merged:
        text = f"{item['title']} {item.get('abstract') or ''}"
        failed = [name for name, pattern in sorted(patterns.items()) if not pattern.search(text)]
        if failed:
            excluded.append({"record_id": item["record_id"], "title": item["title"], "year": item["year"] or "",
                             "venue": item.get("venue") or "", "doi": item.get("doi") or "",
                             "sources": ";".join(item["sources"]), "rule": failed[0]})
        else:
            kept.append(item)
    return kept, excluded

DECISIONS = {"include", "exclude", "maybe"}
TA_COLUMNS = ["record_id", "title", "year", "venue", "doi", "peer_reviewed", "sources",
              "query_families", "abstract", "double_code", "r1_decision", "r1_reason",
              "r2_decision", "r2_reason", "final_decision", "final_reason", "notes"]
FT_COLUMNS = ["record_id", "title", "year", "venue", "doi", "peer_reviewed", "double_code",
              "retrieved", "r1_decision", "r1_reason", "r2_decision", "r2_reason",
              "final_decision", "final_reason", "quality_q1", "quality_q2", "quality_q3",
              "quality_q4", "quality_q5", "notes"]
HUMAN_COLUMNS = {"r1_decision", "r1_reason", "r2_decision", "r2_reason", "final_decision",
                 "final_reason", "notes", "retrieved", "quality_q1", "quality_q2", "quality_q3",
                 "quality_q4", "quality_q5"}


def _merge_existing(rows: list[dict], path: Path) -> list[dict]:
    if not path.exists():
        return rows
    previous = {row["record_id"]: row for row in read_csv(path)}
    for row in rows:
        old = previous.get(row["record_id"])
        if old:
            row.update({key: value for key, value in old.items() if key in HUMAN_COLUMNS and value})
            row["double_code"] = old.get("double_code", row["double_code"])
    return rows


def _double_code_sample(ids: list[str], fraction: float, seed: int) -> set[str]:
    count = round(len(ids) * fraction)
    return set(random.Random(seed).sample(sorted(ids), count)) if ids else set()


def build_title_abstract_sheet(merged: list[dict], path: Path, fraction: float, seed: int) -> int:
    sample = _double_code_sample([item["record_id"] for item in merged], fraction, seed)
    rows = [{"record_id": item["record_id"], "title": item["title"], "year": item["year"] or "",
             "venue": item.get("venue") or "", "doi": item.get("doi") or "",
             "peer_reviewed": item["peer_reviewed"], "sources": ";".join(item["sources"]),
             "query_families": ";".join(item["query_families"]),
             "abstract": (item.get("abstract") or "")[:3000],
             "double_code": "yes" if item["record_id"] in sample else "no"} for item in merged]
    write_csv(_merge_existing(rows, path), path, TA_COLUMNS)
    return len(rows)


def build_full_text_sheet(title_abstract: Path, path: Path, fraction: float, seed: int) -> int:
    candidates = [row for row in read_csv(title_abstract)
                  if row.get("final_decision") in ("include", "maybe")]
    sample = _double_code_sample([row["record_id"] for row in candidates], fraction, seed + 1)
    rows = [{column: row.get(column, "") for column in FT_COLUMNS} |
            {"double_code": "yes" if row["record_id"] in sample else "no",
             "r1_decision": "", "r1_reason": "", "r2_decision": "", "r2_reason": "",
             "final_decision": "", "final_reason": ""} for row in candidates]
    write_csv(_merge_existing(rows, path), path, FT_COLUMNS)
    return len(rows)


def prisma_counts(identified_by_source: dict[str, int], title_abstract: Path | None,
                  full_text: Path | None, automation_excluded: int = 0) -> dict:
    total = sum(identified_by_source.values())
    ta_rows = read_csv(title_abstract) if title_abstract and title_abstract.exists() else []
    ft_rows = read_csv(full_text) if full_text and full_text.exists() else []
    ta_final = Counter(row.get("final_decision") or "pending" for row in ta_rows)
    ft_retrieved = [row for row in ft_rows if row.get("retrieved") != "no"]
    ft_final = Counter(row.get("final_decision") or "pending" for row in ft_retrieved)
    ft_reasons = Counter(row.get("final_reason") or "unspecified" for row in ft_retrieved
                         if row.get("final_decision") == "exclude")
    counts = {
        "identified_by_source": dict(sorted(identified_by_source.items())),
        "identified": total,
        "duplicates_removed": total - len(ta_rows) - automation_excluded,
        "automation_excluded": automation_excluded,
        "screened": len(ta_rows),
        "ta_excluded": ta_final["exclude"],
        "ta_pending": ta_final["pending"],
        "ft_sought": ta_final["include"] + ta_final["maybe"],
        "ft_not_retrieved": sum(row.get("retrieved") == "no" for row in ft_rows),
        "ft_assessed": len(ft_retrieved),
        "ft_excluded": ft_final["exclude"],
        "ft_excluded_by_reason": dict(sorted(ft_reasons.items())),
        "ft_pending": ft_final["pending"] + ft_final["maybe"],
        "included": ft_final["include"],
    }
    counts["complete"] = (counts["ta_pending"] == 0 and counts["ft_pending"] == 0
                          and counts["screened"] > 0 and len(ft_rows) == counts["ft_sought"])
    _check(counts)
    return counts


def _check(counts: dict) -> None:
    if counts["duplicates_removed"] < 0:
        raise ValueError("Screening sheet has more rows than identified records.")
    if counts["screened"] != counts["ta_excluded"] + counts["ta_pending"] + counts["ft_sought"]:
        raise ValueError("Title/abstract decisions do not add up; use include/exclude/maybe.")
    if counts["ft_assessed"] != counts["ft_excluded"] + counts["ft_pending"] + counts["included"]:
        raise ValueError("Full-text decisions do not add up; use include/exclude/maybe.")


def _tex(text: object) -> str:
    return "".join({"_": r"\_", "%": r"\%", "&": r"\&", "#": r"\#"}.get(c, c) for c in str(text))


def prisma_tikz(counts: dict) -> str:
    sources = ", ".join(f"{_tex(name)} {value}" for name, value in counts["identified_by_source"].items())
    status = "" if counts["complete"] else r"\\\textit{screening in progress}"
    reasons = "; ".join(f"{_tex(name)} {value}"
                        for name, value in counts["ft_excluded_by_reason"].items()) or "--"
    box = r"draw, rounded corners=1pt, align=center, font=\scriptsize, text width=3.6cm, minimum height=7mm"
    side = r"draw, align=center, font=\scriptsize, text width=2.9cm, minimum height=7mm"
    return "\n".join([
        r"\begin{tikzpicture}[node distance=3.2mm and 3mm, >=Stealth]",
        rf"\node[{box}] (id) {{Records identified: {counts['identified']}\\{{\tiny {sources}}}}};",
        rf"\node[{side}, right=of id] (dup) {{Duplicates removed: {counts['duplicates_removed']}\\Ineligible by automation: {counts['automation_excluded']}}};",
        rf"\node[{box}, below=of id] (scr) {{Records screened: {counts['screened']}{status}}};",
        rf"\node[{side}, right=of scr] (tax) {{Excluded (title/abstract): {counts['ta_excluded']}\\pending: {counts['ta_pending']}}};",
        rf"\node[{box}, below=of scr] (ft) {{Full texts sought: {counts['ft_sought']}\\not retrieved: {counts['ft_not_retrieved']}}};",
        rf"\node[{side}, right=of ft] (ftx) {{Excluded (full text): {counts['ft_excluded']}\\{{\tiny {reasons}}}}};",
        rf"\node[{box}, below=of ft] (inc) {{Included and AUF-coded: {counts['included']}\\pending: {counts['ft_pending']}}};",
        r"\draw[->] (id) -- (scr); \draw[->] (scr) -- (ft); \draw[->] (ft) -- (inc);",
        r"\draw[->] (id) -- (dup); \draw[->] (scr) -- (tax); \draw[->] (ft) -- (ftx);",
        r"\end{tikzpicture}", ""])
