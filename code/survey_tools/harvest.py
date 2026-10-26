"""Harvest candidate records from open bibliographic APIs (OpenAlex, arXiv, Semantic Scholar).

Subscription databases (IEEE Xplore, Scopus, Web of Science, ACM, ScienceDirect) are
searched by the authors and imported with :mod:`survey_tools.importers`.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from .records import Record, normalize_doi

USER_AGENT = "RoleOfSemantics-survey/1.0"
OPENALEX_PEER_REVIEWED = {"article", "review", "book-chapter", "proceedings-article"}


def _get(url: str, retries: int = 4, backoff: float = 3.0) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            if error.code not in (429, 500, 502, 503) or attempt == retries - 1:
                raise
        time.sleep(backoff * (2 ** attempt))
    raise RuntimeError("unreachable")


def _abstract(inverted: dict | None) -> str | None:
    if not inverted:
        return None
    positions = sorted((index, word) for word, indexes in inverted.items() for index in indexes)
    return " ".join(word for _, word in positions)


def _openalex_record(work: dict, family: str) -> Record:
    source = ((work.get("primary_location") or {}).get("source") or {})
    work_type = work.get("type")
    is_preprint = source.get("type") == "repository" or work_type == "preprint"
    return Record(
        source="openalex", source_id=work["id"].rsplit("/", 1)[-1],
        title=(work.get("title") or "").strip(), year=work.get("publication_year"),
        authors=[(item.get("author") or {}).get("display_name", "")
                 for item in work.get("authorships", [])],
        doi=normalize_doi(work.get("doi")), venue=source.get("display_name"),
        abstract=_abstract(work.get("abstract_inverted_index")),
        url=work.get("doi") or work["id"], work_type=work_type,
        peer_reviewed="no" if is_preprint else ("yes" if work_type in OPENALEX_PEER_REVIEWED else "unknown"),
        query_family=family)


def harvest_openalex(query: str, family: str, years: tuple[int, int], raw_dir: Path,
                     max_records: int) -> tuple[list[Record], dict]:
    params = {"filter": f"title_and_abstract.search:{query},"
                        f"from_publication_date:{years[0]}-01-01,to_publication_date:{years[1]}-12-31",
              "per-page": "200", "cursor": "*"}
    if os.environ.get("OPENALEX_MAILTO"):
        params["mailto"] = os.environ["OPENALEX_MAILTO"]
    if os.environ.get("OPENALEX_API_KEY"):
        params["api_key"] = os.environ["OPENALEX_API_KEY"]
    records, pages, total = [], [], None
    while params["cursor"] and len(records) < max_records:
        payload = _get("https://api.openalex.org/works?" + urllib.parse.urlencode(params))
        data = json.loads(payload)
        total = data["meta"]["count"]
        page_path = raw_dir / f"page_{len(pages):03d}.json"
        page_path.parent.mkdir(parents=True, exist_ok=True)
        page_path.write_bytes(payload)
        pages.append({"file": page_path.name, "sha256": hashlib.sha256(payload).hexdigest()})
        records.extend(_openalex_record(work, family) for work in data["results"])
        params["cursor"] = data["meta"].get("next_cursor") if data["results"] else None
    return records[:max_records], {"reported_total": total, "pages": pages}


ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV = "{http://arxiv.org/schemas/atom}"


def harvest_arxiv(query: str, family: str, years: tuple[int, int], raw_dir: Path,
                  max_records: int) -> tuple[list[Record], dict]:
    records, pages, start, total = [], [], 0, None
    while start < max_records:
        params = {"search_query": query, "start": str(start), "max_results": "100",
                  "sortBy": "submittedDate", "sortOrder": "descending"}
        payload = _get("https://export.arxiv.org/api/query?" + urllib.parse.urlencode(params))
        page_path = raw_dir / f"page_{len(pages):03d}.xml"
        page_path.parent.mkdir(parents=True, exist_ok=True)
        page_path.write_bytes(payload)
        pages.append({"file": page_path.name, "sha256": hashlib.sha256(payload).hexdigest()})
        root = ET.fromstring(payload)
        total = int(root.findtext("{http://a9.com/-/spec/opensearch/1.1/}totalResults") or 0)
        entries = root.findall(f"{ATOM}entry")
        for entry in entries:
            year = int((entry.findtext(f"{ATOM}published") or "0")[:4] or 0)
            if not years[0] <= year <= years[1]:
                continue
            identifier = (entry.findtext(f"{ATOM}id") or "").rsplit("/abs/", 1)[-1]
            records.append(Record(
                source="arxiv", source_id=identifier,
                title=" ".join((entry.findtext(f"{ATOM}title") or "").split()), year=year,
                authors=[author.findtext(f"{ATOM}name") or "" for author in entry.findall(f"{ATOM}author")],
                doi=normalize_doi(entry.findtext(f"{ARXIV}doi")), venue="arXiv",
                abstract=" ".join((entry.findtext(f"{ATOM}summary") or "").split()),
                url=entry.findtext(f"{ATOM}id"), work_type="preprint", peer_reviewed="no",
                query_family=family))
        if not entries or start + 100 >= total:
            break
        start += 100
        time.sleep(3.0)
    return records[:max_records], {"reported_total": total, "pages": pages}


def harvest_semantic_scholar(query: str, family: str, years: tuple[int, int], raw_dir: Path,
                             max_records: int) -> tuple[list[Record], dict]:
    fields = "title,year,authors,externalIds,venue,abstract,url,publicationTypes"
    params = {"query": query, "year": f"{years[0]}-{years[1]}", "fields": fields, "limit": "100"}
    headers_key = os.environ.get("S2_API_KEY")
    records, pages, offset, total = [], [], 0, None
    while offset < max_records:
        params["offset"] = str(offset)
        url = "https://api.semanticscholar.org/graph/v1/paper/search?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                                       **({"x-api-key": headers_key} if headers_key else {})})
        for attempt in range(5):
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    payload = response.read()
                break
            except urllib.error.HTTPError as error:
                if error.code != 429 or attempt == 4:
                    raise
                time.sleep(5.0 * (2 ** attempt))
        data = json.loads(payload)
        page_path = raw_dir / f"page_{len(pages):03d}.json"
        page_path.parent.mkdir(parents=True, exist_ok=True)
        page_path.write_bytes(payload)
        pages.append({"file": page_path.name, "sha256": hashlib.sha256(payload).hexdigest()})
        total = data.get("total", 0)
        for paper in data.get("data", []):
            types = paper.get("publicationTypes") or []
            records.append(Record(
                source="semanticscholar", source_id=paper["paperId"], title=paper.get("title") or "",
                year=paper.get("year"), authors=[a.get("name", "") for a in paper.get("authors", [])],
                doi=normalize_doi((paper.get("externalIds") or {}).get("DOI")), venue=paper.get("venue"),
                abstract=paper.get("abstract"), url=paper.get("url"), work_type=",".join(types) or None,
                peer_reviewed="yes" if {"JournalArticle", "Conference"} & set(types) else "unknown",
                query_family=family))
        if "next" not in data:
            break
        offset = data["next"]
        time.sleep(3.0)
    return records[:max_records], {"reported_total": total, "pages": pages}


def _strip_tags(text: str | None) -> str | None:
    if not text:
        return None
    return " ".join(re.sub(r"<[^>]+>", " ", text).split()) or None


def harvest_crossref(query: str, family: str, years: tuple[int, int], raw_dir: Path,
                     max_records: int) -> tuple[list[Record], dict]:
    """Relevance-ranked Crossref search; the cap makes it supplementary, not exhaustive."""
    params = {"query.bibliographic": query, "rows": "100", "offset": "0", "sort": "relevance", "order": "desc",
              "filter": f"from-pub-date:{years[0]},until-pub-date:{years[1]},"
                        "type:journal-article,type:proceedings-article,type:book-chapter,type:posted-content",
              "select": "DOI,title,author,issued,container-title,abstract,type,URL"}
    if os.environ.get("CROSSREF_MAILTO"):
        params["mailto"] = os.environ["CROSSREF_MAILTO"]
    records, pages, total = [], [], None
    while len(records) < max_records:
        payload = _get("https://api.crossref.org/works?" + urllib.parse.urlencode(params))
        data = json.loads(payload)["message"]
        total = data.get("total-results")
        page_path = raw_dir / f"page_{len(pages):03d}.json"
        page_path.parent.mkdir(parents=True, exist_ok=True)
        page_path.write_bytes(payload)
        pages.append({"file": page_path.name, "sha256": hashlib.sha256(payload).hexdigest()})
        for item in data.get("items", []):
            title = " ".join((item.get("title") or [""])[0].split())
            if not title:
                continue
            work_type = item.get("type")
            year = ((item.get("issued") or {}).get("date-parts") or [[None]])[0][0]
            records.append(Record(
                source="crossref", source_id=normalize_doi(item["DOI"]), title=title, year=year,
                authors=[" ".join(filter(None, (a.get("given"), a.get("family")))) for a in item.get("author", [])],
                doi=normalize_doi(item["DOI"]), venue=(item.get("container-title") or [None])[0],
                abstract=_strip_tags(item.get("abstract")), url=item.get("URL"), work_type=work_type,
                peer_reviewed="no" if work_type == "posted-content" else "yes", query_family=family))
        if not data.get("items"):
            break
        params["offset"] = str(int(params["offset"]) + 100)
        time.sleep(1.0)
    return records[:max_records], {"reported_total": total, "pages": pages, "relevance_capped": True}


HARVESTERS = {"openalex": harvest_openalex, "arxiv": harvest_arxiv,
              "semanticscholar": harvest_semantic_scholar, "crossref": harvest_crossref}


def run_protocol(protocol: dict, survey_dir: Path, sources: list[str]) -> tuple[list[Record], dict]:
    years = (protocol["time_window"]["from_year"], protocol["time_window"]["to_year"])
    limits = protocol["harvest"]
    all_records, log = [], {"protocol_version": protocol["version"],
                            "run_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                            "queries": []}
    for family in protocol["search_families"]:
        for source in sources:
            queries = family["queries"].get(source)
            if not queries:
                continue
            for position, query in enumerate([queries] if isinstance(queries, str) else queries):
                raw_dir = survey_dir / "raw" / source / family["id"] / f"q{position}"
                limit = limits.get(f"max_records_{source}", limits["max_records_per_query"])
                try:
                    records, meta = HARVESTERS[source](query, family["id"], years, raw_dir, limit)
                    status = "ok"
                except (urllib.error.URLError, TimeoutError, ET.ParseError, json.JSONDecodeError) as error:
                    records, meta, status = [], {"error": str(error)}, "failed"
                all_records.extend(records)
                log["queries"].append({"family": family["id"], "source": source, "query": query,
                                       "status": status, "retrieved": len(records), **meta})
    return all_records, log
