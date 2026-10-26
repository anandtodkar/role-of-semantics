"""Survey pipeline: harvest open APIs, import database exports, deduplicate, build screening sheets.

Usage (from repository root):
  python code/run_survey.py harvest --sources openalex arxiv
  python code/run_survey.py import --source scopus path/to/scopus.csv
  python code/run_survey.py dedup
  python code/run_survey.py fulltext
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

from survey_tools import dedup as D
from survey_tools import harvest as H
from survey_tools import importers as I
from survey_tools import screening as S
from survey_tools.records import read_jsonl, write_jsonl

ROOT = Path(__file__).resolve().parent.parent
SURVEY = ROOT / "paper_updated" / "survey"


SURVEY_TOPICS = {
    "llm_agents": r"large language model|\bllms?\b|agentic|\bagents?\b|generative ai",
    "knowledge_graphs": r"knowledge graph|ontolog|semantic web",
    "information_models": r"opc[ -]?ua|asset administration shell|automationml|information model|digital twin",
    "interoperability": r"interoperab|semantic",
    "validation_safety": r"validat|verif|guardrail|safety|trustworth|constraint",
    "industrial": r"industr|manufactur|automation|cyber-physical|production|\bplc",
}


def _shortlist(surveys: list[dict]) -> list[dict]:
    rows = []
    for item in surveys:
        text = f"{item['title']} {item.get('abstract') or ''}"
        hits = {name: bool(re.search(pattern, text, re.IGNORECASE)) for name, pattern in SURVEY_TOPICS.items()}
        if not hits["industrial"] or not re.search(r"\b(survey|review|state[- ]of[- ]the[- ]art|overview)\b",
                                                   item["title"], re.IGNORECASE):
            continue
        rows.append({"topic_overlap": sum(hits.values()), **hits, "year": item["year"] or "",
                     "peer_reviewed": item["peer_reviewed"], "doi": item.get("doi") or "",
                     "title": item["title"], "venue": item.get("venue") or "",
                     "retracted": "yes" if "retracted" in item["title"].lower() else ""})
    return sorted(rows, key=lambda row: (-row["topic_overlap"], row["peer_reviewed"] != "yes", -(row["year"] or 0)))


def _protocol() -> dict:
    return json.loads((SURVEY / "protocol.json").read_text(encoding="utf-8"))


def harvest(sources: list[str]) -> None:
    records, log = H.run_protocol(_protocol(), SURVEY, sources)
    for source in sources:
        subset = [record for record in records if record.source == source]
        write_jsonl(subset, SURVEY / "records" / f"{source}.jsonl")
    log_path = SURVEY / "records" / "harvest_log.json"
    if log_path.exists():
        previous = json.loads(log_path.read_text(encoding="utf-8"))
        log["queries"] = [query for query in previous["queries"] if query["source"] not in sources] + log["queries"]
    log_path.write_text(json.dumps(log, indent=2) + "\n", encoding="utf-8")
    for query in log["queries"]:
        print(f"{query['source']:16s} {query['family']:24s} {query['status']:6s} "
              f"retrieved={query['retrieved']} reported={query.get('reported_total')}")


def import_exports(source: str, paths: list[Path]) -> None:
    families = [family["id"] for family in _protocol()["search_families"]]
    records = []
    for path in paths:
        match = next((family for family in families
                      if re.search(rf"(^|[_\-. ]){family.split('_')[0]}([_\-. ]|$)", path.stem, re.IGNORECASE)), None)
        if match is None:
            raise SystemExit(f"{path.name}: name the file with its family code, e.g. {source}_F1.csv or {source}_R1.csv")
        for record in I.import_file(path, source):
            record.query_family = match
            records.append(record)
        print(f"{path.name}: family {match}")
    count = write_jsonl(records, SURVEY / "records" / f"{source}.jsonl")
    print(f"Imported {count} records from {source}")


def print_queries(database: str) -> None:
    protocol = _protocol()
    years = protocol["time_window"]
    print(f"Protocol {protocol['version']}; publication years {years['from_year']}-{years['to_year']}\n")
    for family in protocol["search_families"]:
        query = family["queries"].get(database)
        if query:
            print(f"[{family['id'].split('_')[0]}] {family['description']}\n{query}\n")


def deduplicate() -> None:
    files = sorted((SURVEY / "records").glob("*.jsonl"))
    records = [record for path in files for record in read_jsonl(path)]
    merged, uncertain = D.deduplicate(records)
    protocol = _protocol()
    kept, excluded = S.auto_screen(merged, protocol.get("automation_rules", {}))
    S.write_csv(excluded, SURVEY / "screening" / "automation_excluded.csv", S.AUTO_COLUMNS)
    surveys = [item for item in kept if "R1_related_surveys" in item["query_families"]
               or re.search(r"\b(survey|review|overview|state[- ]of[- ]the[- ]art)\b", item["title"], re.IGNORECASE)]
    S.write_csv([{"record_id": item["record_id"], "title": item["title"], "year": item["year"] or "",
                  "venue": item.get("venue") or "", "doi": item.get("doi") or "",
                  "peer_reviewed": item["peer_reviewed"], "sources": ";".join(item["sources"])}
                 for item in surveys], SURVEY / "screening" / "related_survey_candidates.csv",
                ["record_id", "title", "year", "venue", "doi", "peer_reviewed", "sources"])
    shortlist = _shortlist(surveys)
    S.write_csv(shortlist, SURVEY / "screening" / "related_survey_shortlist.csv",
                ["topic_overlap", *SURVEY_TOPICS, "year", "peer_reviewed", "retracted", "doi", "title", "venue"])
    with (SURVEY / "records" / "unique.json").open("w", encoding="utf-8") as handle:
        json.dump({"identified_by_source": {path.stem: len(read_jsonl(path)) for path in files},
                   "automation_excluded": len(excluded), "records": kept}, handle, indent=1, ensure_ascii=False)
    with (SURVEY / "screening" / "uncertain_duplicates.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["first", "second", "title_similarity",
                                                    "first_title", "second_title", "decision"])
        writer.writeheader()
        writer.writerows(uncertain)
    rows = S.build_title_abstract_sheet(kept, SURVEY / "screening" / "title_abstract.csv",
                                        protocol["harvest"]["double_code_fraction"], protocol["harvest"]["seed"])
    print(f"Identified {len(records)}; unique {len(merged)}; automation-excluded {len(excluded)}; "
          f"uncertain pairs {len(uncertain)}; sheet rows {rows}; related-survey candidates {len(surveys)}")


def full_text() -> None:
    protocol = _protocol()
    rows = S.build_full_text_sheet(SURVEY / "screening" / "title_abstract.csv",
                                   SURVEY / "screening" / "full_text.csv",
                                   protocol["harvest"]["double_code_fraction"], protocol["harvest"]["seed"])
    print(f"Full-text sheet rows: {rows}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    harvest_parser = commands.add_parser("harvest")
    harvest_parser.add_argument("--sources", nargs="+", default=["openalex", "arxiv"], choices=sorted(H.HARVESTERS))
    import_parser = commands.add_parser("import")
    import_parser.add_argument("--source", required=True, help="e.g. ieee, scopus, wos, acm, sciencedirect")
    import_parser.add_argument("paths", nargs="+", type=Path)
    commands.add_parser("dedup")
    commands.add_parser("fulltext")
    queries_parser = commands.add_parser("queries")
    queries_parser.add_argument("database", choices=["ieee_xplore", "scopus", "web_of_science", "openalex", "arxiv", "crossref"])
    args = parser.parse_args()
    (SURVEY / "screening").mkdir(parents=True, exist_ok=True)
    if args.command == "queries":
        print_queries(args.database)
    elif args.command == "harvest":
        harvest(args.sources)
    elif args.command == "import":
        import_exports(args.source, args.paths)
    elif args.command == "dedup":
        deduplicate()
    else:
        full_text()


if __name__ == "__main__":
    main()
