"""Import exports from subscription databases (RIS, BibTeX, CSV/TSV) into Records."""

from __future__ import annotations

import csv
import hashlib
import re
from pathlib import Path

from .records import Record, normalize_doi

PEER_REVIEWED_TYPES = {"jour", "conf", "cpaper", "article", "inproceedings", "journal article",
                       "conference paper", "proceedings paper", "review", "journal",
                       "conference", "early access", "ieee journals", "ieee conferences",
                       "ieee early access articles", "ieee magazines", "conference review"}

CSV_ALIASES = {
    "title": ("title", "document title", "ti", "article title"),
    "year": ("year", "publication year", "py", "pubyear"),
    "authors": ("authors", "author", "au", "author full names"),
    "doi": ("doi", "di"),
    "venue": ("source title", "publication title", "so", "journal", "venue"),
    "abstract": ("abstract", "ab"),
    "url": ("link", "pdf link", "url"),
    "work_type": ("document type", "dt", "type", "content type", "document identifier"),
}


def _record_id(source: str, title: str, year: object) -> str:
    return hashlib.sha1(f"{source}|{title}|{year}".encode("utf-8")).hexdigest()[:16]


def _year(value: object) -> int | None:
    match = re.search(r"(19|20)\d{2}", str(value or ""))
    return int(match.group(0)) if match else None


def _peer_reviewed(work_type: str | None) -> str:
    if not work_type:
        return "unknown"
    parts = {part.strip().lower() for part in re.split(r"[;,]", work_type)}
    return "yes" if parts & PEER_REVIEWED_TYPES else "unknown"


def parse_ris(text: str, source: str) -> list[Record]:
    records, current = [], {}
    for line in text.splitlines():
        match = re.match(r"^([A-Z][A-Z0-9])  -\s?(.*)$", line)
        if not match:
            continue
        tag, value = match.groups()
        if tag == "ER":
            if current.get("TI") or current.get("T1"):
                records.append(_ris_record(current, source))
            current = {}
        else:
            current.setdefault(tag, []).append(value.strip())
    return records


def _ris_record(tags: dict[str, list[str]], source: str) -> Record:
    title = (tags.get("TI") or tags.get("T1"))[0]
    year = _year((tags.get("PY") or tags.get("Y1") or tags.get("DA") or [None])[0])
    work_type = (tags.get("TY") or [None])[0]
    return Record(source=source, source_id=_record_id(source, title, year), title=title,
                  year=year, authors=tags.get("AU", []) + tags.get("A1", []),
                  doi=normalize_doi((tags.get("DO") or [None])[0]),
                  venue=(tags.get("T2") or tags.get("JO") or tags.get("JF") or [None])[0],
                  abstract=(tags.get("AB") or tags.get("N2") or [None])[0],
                  url=(tags.get("UR") or [None])[0], work_type=work_type,
                  peer_reviewed=_peer_reviewed(work_type))


def _bibtex_entries(text: str):
    for match in re.finditer(r"@(\w+)\s*\{", text):
        start, depth = match.end(), 1
        index = start
        while index < len(text) and depth:
            depth += {"{": 1, "}": -1}.get(text[index], 0)
            index += 1
        yield match.group(1).lower(), text[start:index - 1]


def _bibtex_fields(body: str) -> dict[str, str]:
    result, index = {}, body.find(",") + 1
    pattern = re.compile(r"\s*(\w[\w-]*)\s*=\s*")
    while True:
        match = pattern.match(body, index)
        if not match:
            break
        name, index = match.group(1).lower(), match.end()
        if index < len(body) and body[index] in "{\"":
            closing = "}" if body[index] == "{" else "\""
            depth, index, start = 1, index + 1, index + 1
            while index < len(body) and depth:
                char = body[index]
                if closing == "}" and char == "{":
                    depth += 1
                elif char == closing:
                    depth -= 1
                index += 1
            value = body[start:index - 1]
        else:
            end = body.find(",", index)
            end = len(body) if end < 0 else end
            value, index = body[index:end], end
        result[name] = re.sub(r"[{}]", "", re.sub(r"\s+", " ", value)).strip()
        comma = body.find(",", index)
        if comma < 0:
            break
        index = comma + 1
    return result


def parse_bibtex(text: str, source: str) -> list[Record]:
    records = []
    for entry_type, body in _bibtex_entries(text):
        if entry_type in {"comment", "string", "preamble"}:
            continue
        data = _bibtex_fields(body)
        if not data.get("title"):
            continue
        year = _year(data.get("year"))
        records.append(Record(
            source=source, source_id=_record_id(source, data["title"], year), title=data["title"],
            year=year, authors=[name.strip() for name in data.get("author", "").split(" and ") if name.strip()],
            doi=normalize_doi(data.get("doi")),
            venue=data.get("journal") or data.get("booktitle"), abstract=data.get("abstract"),
            url=data.get("url"), work_type=entry_type, peer_reviewed=_peer_reviewed(entry_type)))
    return records


def _column(row: dict, field_name: str) -> str | None:
    lowered = {key.strip().lower(): value for key, value in row.items() if key}
    for alias in CSV_ALIASES[field_name]:
        if lowered.get(alias):
            return lowered[alias].strip()
    return None


def parse_table(text: str, source: str) -> list[Record]:
    delimiter = "\t" if text.split("\n", 1)[0].count("\t") > text.split("\n", 1)[0].count(",") else ","
    records = []
    for row in csv.DictReader(text.splitlines(), delimiter=delimiter):
        title = _column(row, "title")
        if not title:
            continue
        year = _year(_column(row, "year"))
        authors_text = _column(row, "authors") or ""
        separator = ";" if ";" in authors_text else ","
        work_type = _column(row, "work_type")
        records.append(Record(
            source=source, source_id=_record_id(source, title, year), title=title, year=year,
            authors=[name.strip() for name in authors_text.split(separator) if name.strip()],
            doi=normalize_doi(_column(row, "doi")), venue=_column(row, "venue"),
            abstract=_column(row, "abstract"), url=_column(row, "url"),
            work_type=work_type, peer_reviewed=_peer_reviewed(work_type)))
    return records


def import_file(path: Path, source: str) -> list[Record]:
    raw = path.read_bytes()
    encoding = "utf-16" if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else "utf-8-sig"
    text = raw.decode(encoding, errors="replace")
    suffix = path.suffix.lower()
    if suffix in {".ris", ".txt"} and re.search(r"^TY  -", text, re.MULTILINE):
        return parse_ris(text, source)
    if suffix in {".bib", ".bibtex"}:
        return parse_bibtex(text, source)
    if suffix in {".csv", ".tsv", ".txt"}:
        return parse_table(text, source)
    raise ValueError(f"Unsupported export format: {path.name}")
