"""Common bibliographic record shared by importers, harvesters and screening."""

from __future__ import annotations

import csv
import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Iterable

PEER_REVIEW_UNKNOWN = "unknown"


@dataclass
class Record:
    source: str
    source_id: str
    title: str
    year: int | None = None
    authors: list[str] = field(default_factory=list)
    doi: str | None = None
    venue: str | None = None
    abstract: str | None = None
    url: str | None = None
    work_type: str | None = None
    peer_reviewed: str = PEER_REVIEW_UNKNOWN
    query_family: str | None = None

    @property
    def record_id(self) -> str:
        return f"{self.source}:{self.source_id}"

    def to_dict(self) -> dict:
        return asdict(self) | {"record_id": self.record_id}

    @classmethod
    def from_dict(cls, data: dict) -> Record:
        names = {item.name for item in fields(cls)}
        return cls(**{key: value for key, value in data.items() if key in names})


def normalize_doi(value: str | None) -> str | None:
    if not value:
        return None
    doi = value.strip().lower()
    doi = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:\s*)", "", doi)
    return doi or None


def normalize_title(value: str) -> str:
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def first_author_key(authors: list[str]) -> str:
    if not authors:
        return ""
    name = authors[0].strip()
    surname = name.split(",")[0] if "," in name else name.split()[-1] if name.split() else ""
    return normalize_title(surname)


def write_jsonl(records: Iterable[Record], path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")
            count += 1
    return count


def read_jsonl(path: Path) -> list[Record]:
    with path.open(encoding="utf-8") as handle:
        return [Record.from_dict(json.loads(line)) for line in handle if line.strip()]


def write_csv(rows: list[dict], path: Path, columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))
