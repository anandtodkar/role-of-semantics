"""Deduplicate records across databases; uncertain matches are listed, never merged silently."""

from __future__ import annotations

from collections import defaultdict
from difflib import SequenceMatcher

from .records import Record, first_author_key, normalize_title

SOURCE_PREFERENCE = ("ieee", "scopus", "wos", "acm", "sciencedirect", "springer",
                     "openalex", "semanticscholar", "arxiv")
FUZZY_THRESHOLD = 0.93


def _rank(record: Record) -> tuple[int, int, int]:
    source = record.source.lower()
    position = next((index for index, name in enumerate(SOURCE_PREFERENCE) if source.startswith(name)),
                    len(SOURCE_PREFERENCE))
    return (record.peer_reviewed != "yes", position, -len(record.abstract or ""))


class _Union:
    def __init__(self, size: int):
        self.parent = list(range(size))

    def find(self, index: int) -> int:
        while self.parent[index] != index:
            self.parent[index] = self.parent[self.parent[index]]
            index = self.parent[index]
        return index

    def join(self, first: int, second: int) -> None:
        self.parent[self.find(first)] = self.find(second)


def deduplicate(records: list[Record]) -> tuple[list[dict], list[dict]]:
    """Return merged unique records and uncertain pairs for manual review.

    Merges on identical DOI, or identical normalised title with compatible year and first author.
    """
    union = _Union(len(records))
    by_doi, by_title = defaultdict(list), defaultdict(list)
    for index, record in enumerate(records):
        if record.doi:
            by_doi[record.doi].append(index)
        by_title[normalize_title(record.title)].append(index)
    for group in by_doi.values():
        for index in group[1:]:
            union.join(group[0], index)
    for title, group in by_title.items():
        if not title:
            continue
        for position, first in enumerate(group):
            for second in group[position + 1:]:
                a, b = records[first], records[second]
                if a.doi and b.doi and a.doi != b.doi:
                    continue
                years_ok = a.year is None or b.year is None or abs(a.year - b.year) <= 1
                authors_ok = (not a.authors or not b.authors
                              or first_author_key(a.authors) == first_author_key(b.authors))
                if years_ok and authors_ok:
                    union.join(first, second)

    clusters = defaultdict(list)
    for index in range(len(records)):
        clusters[union.find(index)].append(index)
    merged = []
    for members in clusters.values():
        ordered = sorted((records[index] for index in members), key=_rank)
        primary = ordered[0]
        merged.append(primary.to_dict() | {
            "doi": primary.doi or next((item.doi for item in ordered if item.doi), None),
            "abstract": primary.abstract or next((item.abstract for item in ordered if item.abstract), None),
            "peer_reviewed": "yes" if any(item.peer_reviewed == "yes" for item in ordered) else primary.peer_reviewed,
            "merged_ids": sorted(item.record_id for item in ordered),
            "sources": sorted({item.source for item in ordered}),
            "query_families": sorted({item.query_family for item in ordered if item.query_family}),
        })
    merged.sort(key=lambda item: (item["year"] or 0, normalize_title(item["title"])))
    return merged, _uncertain_pairs(merged)


def _uncertain_pairs(merged: list[dict]) -> list[dict]:
    blocks = defaultdict(list)
    for item in merged:
        words = normalize_title(item["title"]).split()
        blocks[(item["year"], words[0] if words else "")].append(item)
    pairs = []
    for block in blocks.values():
        for position, first in enumerate(block):
            for second in block[position + 1:]:
                if first["doi"] and second["doi"] and first["doi"] != second["doi"]:
                    continue
                ratio = SequenceMatcher(None, normalize_title(first["title"]),
                                        normalize_title(second["title"])).ratio()
                if ratio >= FUZZY_THRESHOLD:
                    pairs.append({"first": first["record_id"], "second": second["record_id"],
                                  "title_similarity": round(ratio, 3),
                                  "first_title": first["title"], "second_title": second["title"]})
    return pairs
