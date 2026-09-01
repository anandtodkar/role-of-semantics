"""Two retrievers: lexical over records, and structured over the graph.

Conditions C0-C2 have no graph, so an agent can only do what every RAG stack
does today - embed or index the tag records and take the top *k*.  C3 and C4
expose a graph, so the agent can *resolve* the entities named in the question
and then traverse typed relations from them.

Both retrievers are budgeted with the same number of context tokens, which is
the constraint that actually binds in production.  The comparison therefore
measures *what a fixed token budget buys you* under each representation.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass

from . import plant as P
from . import units as U
from .conditions import ELEMENTS, ELEMENT_BY_ID, Condition, Element

_WORD = re.compile(r"[a-z0-9]+")


def _tokenise(text: str) -> list[str]:
    text = text.lower()
    # split identifier conventions so that L1_FIL_PT0301_PV also yields l1, fil, pt, 0301
    text = re.sub(r"[_\-.]", " ", text)
    text = re.sub(r"(?<=[a-z])(?=[0-9])|(?<=[0-9])(?=[a-z])", " ", text)
    return _WORD.findall(text)


# ---------------------------------------------------------------------------
# Lexical (TF-IDF, cosine) - the C0-C2 retriever
# ---------------------------------------------------------------------------


class LexicalRetriever:
    def __init__(self, elements: list[Element] | None = None,
                 index_fn=None) -> None:
        self.elements = elements or ELEMENTS
        self.index_fn = index_fn or (lambda e: e.text_index)
        self.docs = [Counter(_tokenise(self.index_fn(e))) for e in self.elements]
        df: Counter = Counter()
        for d in self.docs:
            df.update(d.keys())
        n = len(self.docs)
        self.idf = {t: math.log((n + 1) / (c + 1)) + 1.0 for t, c in df.items()}
        self.vecs = [self._vec(d) for d in self.docs]

    def _vec(self, counts: Counter) -> dict[str, float]:
        v = {t: (1 + math.log(c)) * self.idf.get(t, 1.0) for t, c in counts.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {t: x / norm for t, x in v.items()}

    def rank(self, query: str) -> list[tuple[Element, float]]:
        q = self._vec(Counter(_tokenise(query)))
        scored = []
        for el, v in zip(self.elements, self.vecs):
            s = sum(w * v.get(t, 0.0) for t, w in q.items())
            if s > 0:
                scored.append((el, s))
        scored.sort(key=lambda x: (-x[1], x[0].eid))
        return scored


# ---------------------------------------------------------------------------
# Structured graph retrieval - the C3/C4 retriever
# ---------------------------------------------------------------------------

#: surface forms an operator would actually type, mapped to asset kinds
_KIND_SYNONYMS: dict[str, tuple[str, ...]] = {
    "Filler": ("filler", "filling machine", "fill"),
    "Capper": ("capper", "crowner", "capping", "cap"),
    "Pasteuriser": ("pasteuriser", "pasteurizer", "tunnel", "pasteurisation", "pasteurization"),
    "Labeller": ("labeller", "labeler", "labelling", "labeling", "label"),
    "CIPSkid": ("cip", "clean in place", "cleaning"),
    "Compressor": ("compressor", "compressed air", "air compressor"),
    "Chiller": ("chiller", "chilled water", "cooling"),
    "ProductionLine": ("line",),
}

_LINE_SYNONYMS = {
    "L1": ("line 1", "line1", "l1", "first line"),
    "L2": ("line 2", "line2", "l2", "second line"),
    "AREA-UTIL": ("utilities", "utility"),
    "AREA-FILL": ("filling hall",),
}


@dataclass(frozen=True)
class Resolution:
    asset_ids: tuple[str, ...]
    kinds: tuple[str, ...]
    lines: tuple[str, ...]
    ambiguous: bool


def resolve_entities(question: str) -> Resolution:
    """Entity linking against the asset taxonomy - the step C0-C2 cannot do."""
    q = question.lower()
    qtokens = set(_tokenise(question))
    kinds = tuple(k for k, syns in _KIND_SYNONYMS.items()
                  if any(s in q for s in syns) and k != "ProductionLine")
    lines = tuple(lid for lid, syns in _LINE_SYNONYMS.items()
                  if any(s in q for s in syns))
    hits: list[str] = []
    for a in P.PLANT:
        id_tokens = set(_tokenise(a.local_id))
        if id_tokens and id_tokens <= qtokens and len(a.local_id) > 2:
            hits.append(a.local_id)
        elif a.name.lower() in q:
            hits.append(a.local_id)
    if not hits and kinds:
        for a in P.PLANT:
            if a.kind not in kinds:
                continue
            if lines:
                root = a.parent or ""
                if not any(a.local_id.startswith(l) or root.startswith(l) or a.local_id == l
                           for l in lines):
                    continue
            hits.append(a.local_id)
    if not hits and lines:
        hits = [l for l in lines if l in P.ASSETS_BY_ID]
    ambiguous = len(set(hits)) > 1
    return Resolution(tuple(dict.fromkeys(hits)), kinds, lines, ambiguous)


#: traversal plan: relation -> priority (lower is fetched first)
_HOP_PRIORITY = (
    "self", "signals", "parents", "children", "feeds_out", "feeds_in",
    "interlocks", "events", "products", "siblings",
)


def graph_expand(seed_ids: list[str], question: str, max_elements: int = 200,
                 routed: bool = False) -> list[Element]:
    """k-hop, relation-typed expansion around the resolved seeds."""
    q = question.lower()
    buckets: dict[str, list[str]] = defaultdict(list)
    # insertion-ordered: iterating a plain set would make the traversal order --
    # and therefore what survives the token budget -- depend on the hash seed
    seen: dict[str, None] = {}

    def push(bucket: str, eid: str) -> None:
        if eid in seen or eid not in ELEMENT_BY_ID:
            return
        seen[eid] = None
        buckets[bucket].append(eid)

    for sid in seed_ids:
        push("self", sid)
    # hierarchy: pull descendants of a line / area seed
    for sid in list(seed_ids):
        for a in P.PLANT:
            if a.parent == sid:
                push("children", a.local_id)
    for sid in list(seen):
        a = P.ASSETS_BY_ID.get(sid)
        if a is None:
            continue
        if a.parent:
            push("parents", a.parent)
    for sid in list(seen):
        a = P.ASSETS_BY_ID.get(sid)
        if a is None:
            continue
        for s in a.signals:
            push("signals", s.tag)
    for sid in list(seen):
        for up, down in P.FEEDS:
            if up == sid:
                push("feeds_out", down)
            if down == sid:
                push("feeds_in", up)
    for sid in list(seed_ids):
        parent = P.ASSETS_BY_ID[sid].parent if sid in P.ASSETS_BY_ID else None
        if parent:
            for a in P.PLANT:
                if a.parent == parent and a.local_id != sid:
                    push("siblings", a.local_id)
    # second-order: signals of the newly reached neighbours
    for sid in list(buckets["feeds_out"]) + list(buckets["feeds_in"]) + list(buckets["children"]):
        a = P.ASSETS_BY_ID.get(sid)
        if a is None:
            continue
        for s in a.signals:
            push("signals", s.tag)
    for ilk in P.INTERLOCKS:
        if ilk["tag"] in seen or P.SIGNAL_OWNER.get(str(ilk["tag"])) in seen:
            push("interlocks", str(ilk["id"]))
            push("signals", str(ilk["guard_tag"]))
    for ev in P.EVENTS:
        if ev["asset"] in seen:
            push("events", ev["id"])
    for pr in P.PRODUCTS:
        if pr["line"] in seen or any(s.startswith(str(pr["line"])) for s in seen):
            push("products", str(pr["id"]))
    ordered: list[Element] = []
    for bucket in _HOP_PRIORITY:
        for eid in buckets.get(bucket, []):
            ordered.append(ELEMENT_BY_ID[eid])
    return _rerank(ordered, seed_ids, question, routed)[:max_elements]


#: elements reached by these hops stay in front of the lexical re-ranking
_ANCHOR_BUCKETS = ("self", "signals")

# ---------------------------------------------------------------------------
# Intent routing
# ---------------------------------------------------------------------------

#: surface cues that a question needs a particular semantic layer.  Deliberately
#: a small, inspectable lexicon rather than a learned classifier: the point is
#: that the routing signal is cheap and available *before* retrieval, not that
#: this particular lexicon is optimal.
_INTENT_CUES: dict[str, tuple[str, ...]] = {
    "behaviour": ("can i", "may i", "is it legal", "allowed", "permitted", "safe",
                  "start", "stop", "reset", "hold", "unhold", "abort", "suspend",
                  "command", "sequence", "state", "change", "write", "set "),
    "constraint": ("safe", "interlock", "protect", "locked", "lock", "may i",
                   "can i", "permitted", "allowed", "while", "guard"),
    "provenance": ("why", "when", "how old", "before", "after", "alarm", "fired",
                   "maintenance", "history", "recent", "last", "quoting",
                   "preced", "root cause"),
    "recipe": ("recipe", "specification", "spec", "batch", "product", "match",
               "target", "conform", "cola", "lemonade"),
}

#: which element types serve which intent
_ETYPE_INTENT = {"interlock": ("constraint", "behaviour"),
                 "event": ("provenance",),
                 "product": ("recipe",)}


def intent_profile(question: str) -> frozenset[str]:
    """Which semantic layers the question gives us reason to spend budget on."""
    q = question.lower()
    return frozenset(name for name, cues in _INTENT_CUES.items()
                     if any(c in q for c in cues))


def _serves_intent(el: Element, profile: frozenset[str]) -> bool:
    wanted = _ETYPE_INTENT.get(el.etype)
    return wanted is None or any(w in profile for w in wanted)


def _rerank(elements: list[Element], seed_ids: list[str], question: str,
            routed: bool = False) -> list[Element]:
    """Order the reachable neighbourhood so that a token budget buys the most.

    Four principles, all of which follow from having a graph in the first place:

    1. **Anchors first** - the resolved assets and their own signals.
    2. **Skeleton before payload** - asset nodes are cheap and carry the
       relations (parentage, topology, state) that make everything else
       interpretable, so they precede signal nodes.
    3. **Constraint closure** - when a constraint node is included, the nodes it
       refers to are pulled in with it; a guard you cannot evaluate is useless.
    4. **Intent routing** (when ``routed``) - constraint, event and recipe nodes
       are only fetched ahead of payload when the question gives a reason to.
       Without this a rich representation crowds out the data it was asked
       about; with it, richness stops competing with relevance.
    """
    if not elements:
        return elements
    profile = intent_profile(question) if routed else frozenset(_INTENT_CUES)
    anchor_assets = [e for e in elements if e.etype == "asset" and e.eid in seed_ids]
    anchor_signals = [e for e in elements
                      if e.etype == "signal" and P.SIGNAL_OWNER.get(e.eid) in seed_ids]
    fixed_ids = {e.eid for e in anchor_assets} | {e.eid for e in anchor_signals}
    rest = [e for e in elements if e.eid not in fixed_ids]
    lex = LexicalRetriever(rest) if rest else None
    scores = dict((e.eid, s) for e, s in lex.rank(question)) if lex else {}
    skeleton = sorted((e for e in rest if e.etype == "asset"),
                      key=lambda e: (-scores.get(e.eid, 0.0), e.eid))
    other_nodes = [e for e in rest if e.etype not in ("asset", "signal")]
    others = sorted((e for e in other_nodes if _serves_intent(e, profile)),
                    key=lambda e: (-scores.get(e.eid, 0.0), e.eid))
    deferred = sorted((e for e in other_nodes if not _serves_intent(e, profile)),
                      key=lambda e: (-scores.get(e.eid, 0.0), e.eid))
    scope = set(seed_ids) | {a.local_id for a in P.PLANT if a.parent in seed_ids}
    signals = sorted((e for e in rest if e.etype == "signal"),
                     key=lambda e: (P.SIGNAL_OWNER.get(e.eid) not in scope,
                                    -scores.get(e.eid, 0.0), e.eid))
    by_id = {e.eid: e for e in elements}

    ordered: list[Element] = []
    seen_out: set[str] = set()

    def emit(el: Element) -> None:
        if el.eid in seen_out:
            return
        seen_out.add(el.eid)
        ordered.append(el)

    def emit_with_closure(el: Element) -> None:
        emit(el)
        if el.etype == "interlock":
            for key in ("tag", "guard_tag"):
                dep = by_id.get(str(el.payload[key]))  # type: ignore[index]
                if dep is not None:
                    emit(dep)

    for el in anchor_assets:  # 1. anchors
        emit(el)
    for el in skeleton:  # 2. skeleton
        emit(el)
    for el in others:  # 3. constraints, events, recipes the question asked for
        emit_with_closure(el)
    for el in anchor_signals:  # 4. payload
        emit(el)
    for el in deferred:  # 5. the layers the question gave no reason to fetch
        emit_with_closure(el)
    for el in signals:
        emit(el)
    return ordered


# ---------------------------------------------------------------------------
# Unified entry point
# ---------------------------------------------------------------------------


def _index_text(el: Element, cond: Condition) -> str:
    """Only index what the condition's representation actually exposes."""
    if el.etype == "signal":
        s = el.payload  # type: ignore[assignment]
        owner = P.ASSETS_BY_ID[P.SIGNAL_OWNER[s.tag]]  # type: ignore[union-attr]
        parts = [s.tag]  # type: ignore[union-attr]
        if cond.can("desc"):
            parts.append(s.description)  # type: ignore[union-attr]
        if cond.can("unit"):
            parts.append(U.BY_IRI[s.unit].symbol)  # type: ignore[union-attr]
        if cond.can("qk"):
            parts += [s.quantity_kind, s.role]  # type: ignore[union-attr]
        if cond.can("sig_of"):
            parts.append(owner.local_id)
        if cond.can("label"):
            parts += [owner.name, owner.kind]
        return " ".join(parts)
    if el.etype == "asset":
        a = el.payload  # type: ignore[assignment]
        if not cond.can("label"):
            return a.local_id  # type: ignore[union-attr]
        return el.text_index
    if el.etype == "event" and not cond.can("event"):
        return ""
    if el.etype == "product" and not cond.can("recipe"):
        return ""
    if el.etype == "interlock" and not cond.can("interlock"):
        return ""
    return el.text_index


_LEX_CACHE: dict[str, LexicalRetriever] = {}


# ---------------------------------------------------------------------------
# Convention decoding - a steelman for the un-grounded baseline
# ---------------------------------------------------------------------------

#: What a human -- or an LLM -- reads out of an ISA-5.1 style mnemonic. This is
#: the informal semantics that a tag catalogue carries and that no machine has
#: verified. Modelling it explicitly lets us measure how much of the baseline's
#: grounding accuracy rests on it, and what happens when the convention changes
#: or lies.
_MNEMONIC_GLOSS: dict[str, str] = {
    "L1": "line 1 first line", "L2": "line 2 second line",
    "UT": "utilities utility",
    "FIL": "filler filling fill", "PAS": "pasteuriser pasteurizer tunnel",
    "CAP": "capper crowner capping cap", "LAB": "labeller labeler labelling label",
    "CIP": "cip cleaning clean in place", "CMP": "compressor compressed air",
    "CHL": "chiller chilled water cooling",
    "PT": "pressure", "TT": "temperature", "FT": "flow", "LT": "level",
    "ST": "speed carousel", "TQ": "torque", "AT": "analyser concentration ph",
    "JT": "power electrical", "VT": "vibration bearing", "ZT": "position deviation",
    "PU": "pasteurisation units", "CNT": "count reject", "KPI": "oee effectiveness",
    "XV": "valve product valve", "UNIT": "unit packml",
    "PIC": "pressure setpoint", "TIC": "temperature setpoint",
    "LIC": "level setpoint", "SIC": "speed setpoint", "QIC": "volume setpoint",
    "TQC": "torque setpoint",
    "PV": "measurement reading value", "SP": "setpoint target",
    "CMD": "command", "STATE": "state", "OEE": "overall equipment effectiveness",
}

_ALPHA_PREFIX = re.compile(r"^([A-Za-z]+)")


def decode_convention(tag: str) -> str:
    """Expand a tag mnemonic into the words a reader would infer from it.

    Returns an empty string for identifiers that carry no legible convention
    (sequential I/O addresses, KKS designations, vendor browse paths), which is
    precisely the point: the inference is only available when the convention
    happens to be one the reader knows.
    """
    words: list[str] = []
    for part in re.split(r"[_.]", tag):
        m = _ALPHA_PREFIX.match(part)
        code = m.group(1).upper() if m else part.upper()
        gloss = _MNEMONIC_GLOSS.get(code) or _MNEMONIC_GLOSS.get(part.upper())
        if gloss:
            words.append(gloss)
    return " ".join(words)


def convention_index(el: Element) -> str:
    if el.etype != "signal":
        return ""
    return decode_convention(el.eid)



def lexical_for(cond: Condition) -> LexicalRetriever:
    if cond.key not in _LEX_CACHE:
        _LEX_CACHE[cond.key] = LexicalRetriever(
            ELEMENTS, index_fn=lambda e, c=cond: _index_text(e, c))
    return _LEX_CACHE[cond.key]


def retrieve(question: str, cond: Condition, max_elements: int = 200,
             routed: bool = False) -> list[Element]:
    """Pick the retrieval strategy the condition's representation supports."""
    if cond.key in ("C0", "C1", "C2"):
        return [e for e, _ in lexical_for(cond).rank(question)][:max_elements]
    seeds = resolve_entities(question)
    els = graph_expand(list(seeds.asset_ids), question, max_elements, routed)
    if not els:  # entity linking failed - fall back to lexical over the graph
        els = [e for e, _ in lexical_for(cond).rank(question)][:max_elements]
    return els


def candidate_signals(question: str, cond: Condition, top: int = 5,
                      decode: bool = False) -> list[str]:
    """Tags an agent would consider for a natural-language mention.

    Used by Experiments E1 and E8 (grounding / disambiguation). With
    ``decode=True`` the resolver additionally reads the tag naming convention,
    which is what a language model does with a mnemonic and what an
    un-grounded pipeline silently depends on.
    """
    if cond.key in ("C0", "C1", "C2"):
        lex = (_decoding_retriever(cond) if decode else lexical_for(cond))
        ranked = [e for e, _ in lex.rank(question) if e.etype == "signal"]
        return [e.eid for e in ranked[:top]]
    seeds = resolve_entities(question)
    els = graph_expand(list(seeds.asset_ids), question, max_elements=400)
    sigs = [e for e in els if e.etype == "signal"]
    if not sigs:
        return [e.eid for e, _ in lexical_for(cond).rank(question)
                if e.etype == "signal"][:top]
    lex = LexicalRetriever(sigs, index_fn=lambda e, c=cond: _index_text(e, c))
    return [e.eid for e, _ in lex.rank(question)][:top]


_DECODE_CACHE: dict[str, LexicalRetriever] = {}


def _decoding_retriever(cond: Condition) -> LexicalRetriever:
    """Lexical retrieval over descriptions *plus* the decoded tag convention."""
    if cond.key not in _DECODE_CACHE:
        _DECODE_CACHE[cond.key] = LexicalRetriever(
            ELEMENTS,
            index_fn=lambda e, c=cond: (_index_text(e, c) + " " + convention_index(e)))
    return _DECODE_CACHE[cond.key]
