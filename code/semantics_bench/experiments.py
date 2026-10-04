"""The nine experiments, all deterministic and offline.

======  ==========================================================
E1      entity grounding under homograph pressure, separating
        correct resolution from *verifiable* resolution
E2      context sufficiency: can the retrieved context support a
        grounded answer at all?
E3      context economy: coverage per thousand tokens, and the
        token bill of each serialisation of the *same* plant
E4      guardrail efficacy: detection, diagnosis and false alarms
        across the five validator tiers
E5      action-space reduction and fidelity (bits, precision, recall)
E6      end-to-end task accuracy with a *context-bounded oracle* -
        an answerer that is perfect at reading but cannot invent,
        giving the accuracy ceiling each representation permits
E7      answering by query execution instead of context stuffing
E8      robustness of grounding to the tag naming convention, with
        the un-grounded baseline steelmanned by a mnemonic decoder
E9      neighbourhood projection versus intent-routed projection
======  ==========================================================

E6 deserves a word.  We do not benchmark a particular LLM: model rankings
expire, and attributing an accuracy delta to a representation requires holding
the reader constant.  Instead we bound the problem from above.  The oracle
answers correctly **iff** the context expresses every fact the question needs.
Any real model is at or below this ceiling, so a gap in the ceiling is a gap no
amount of prompting, fine-tuning or scaling can close.  :mod:`semantics_bench.llm`
provides an adapter for running the identical suite against a real model when
one is available.

E8 and E9 exist because the two obvious objections to the rest of the study --
"tag names already carry the semantics" and "richer models just cost more
context than they are worth" -- are empirical claims, and both are testable here
rather than conceded in a limitations paragraph.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from . import conditions as C
from . import kg as KG
from . import retrieval as R
from . import sparql_probe as SP
from . import tasks as TK
from . import toolgen as TG
from . import validation as V
from .metrics import coverage, score_binary, surrogate_tokens, wilson_interval

TOKEN_BUDGET = 6000
MAX_ELEMENTS = 200
BUDGET_SWEEP = (750, 1500, 3000, 6000, 12000, 24000)

#: resolver strategies compared in E8: ``(key, condition, decode-convention)``
RESOLVERS: tuple[tuple[str, str, bool], ...] = (
    ("C1", "C1", False),
    ("C1+conv", "C1", True),
    ("C2+conv", "C2", True),
    ("C4", "C4", False),
)

RESOLVER_LABEL = {
    "C1": "description text only",
    "C1+conv": "description $+$ decoded mnemonic",
    "C2+conv": "typed model $+$ decoded mnemonic",
    "C4": "resolve the asset, then search its scope",
}


# ---------------------------------------------------------------------------
# E1 - grounding
# ---------------------------------------------------------------------------


@dataclass
class GroundingRow:
    task: str
    condition: str
    top1: bool
    rank: int | None
    mrr: float
    distractors_in_top5: int
    verifiable: bool  # is the membership claim provable from the context?


def e1_grounding() -> list[GroundingRow]:
    rows: list[GroundingRow] = []
    for t in TK.TASKS:
        if not t.gold_tag:
            continue
        owner = TK.P.SIGNAL_OWNER[t.gold_tag]
        membership = C.fact("sig_of", t.gold_tag, owner)
        for cond in C.CONDITIONS:
            cands = R.candidate_signals(t.question, cond, top=5)
            rank = cands.index(t.gold_tag) + 1 if t.gold_tag in cands else None
            top1 = bool(cands and cands[0] == t.gold_tag)
            els = R.retrieve(t.question, cond, MAX_ELEMENTS)
            _text, facts, _tok = C.build_context(els, cond, TOKEN_BUDGET)
            rows.append(GroundingRow(
                task=t.tid,
                condition=cond.key,
                top1=top1,
                rank=rank,
                mrr=1.0 / rank if rank else 0.0,
                distractors_in_top5=sum(1 for d in t.distractors if d in cands),
                verifiable=top1 and membership in facts,
            ))
    return rows


# ---------------------------------------------------------------------------
# E8 - is grounding robust to the naming convention?
# ---------------------------------------------------------------------------


def e8_convention_robustness() -> list[dict]:
    """Re-tag the plant five ways and re-measure grounding.

    Descriptions, relations, units, ranges, states and values are held constant;
    only the identifier strings change. Any movement is therefore attributable
    to the naming convention alone -- which is precisely the semantics a tag
    mnemonic carries informally and that no machine has verified.

    The un-grounded baseline is deliberately steelmanned: resolver ``C1+conv``
    is allowed to *decode* the mnemonic, which is what a language model does
    with ``L1_FIL_PT0301_PV`` and what an un-grounded pipeline silently relies
    on. The question is not whether that works -- it does -- but whether it
    survives a plant whose convention is different, absent or untruthful.
    """
    from . import naming

    grounding_tasks = [t for t in TK.TASKS if t.gold_tag]
    out: list[dict] = []
    for sch in naming.SCHEMES:
        with naming.scheme(sch) as mapping:
            for res_key, cond_key, decode in RESOLVERS:
                cond = C.BY_KEY[cond_key]
                hits = 0
                mrr = 0.0
                wrong = 0
                for t in grounding_tasks:
                    gold = mapping[str(t.gold_tag)]
                    cands = R.candidate_signals(t.question, cond, 5, decode=decode)
                    if cands and cands[0] == gold:
                        hits += 1
                    elif cands:
                        wrong += 1  # returned something, confidently, and it is wrong
                    if gold in cands:
                        mrr += 1.0 / (cands.index(gold) + 1)
                n = len(grounding_tasks)
                lo, hi = wilson_interval(hits, n)
                out.append({
                    "scheme": sch, "scheme_label": naming.SCHEME_LABEL[sch],
                    "example": naming.SCHEME_EXAMPLE[sch],
                    "resolver": res_key, "resolver_label": RESOLVER_LABEL[res_key],
                    "n": n, "top1": hits / n, "top1_lo": lo, "top1_hi": hi,
                    "mrr": mrr / n, "confidently_wrong": wrong / n,
                })
    return out


# ---------------------------------------------------------------------------
# E9 - does intent routing remove the richness/budget trade-off?
# ---------------------------------------------------------------------------


def e9_routing() -> list[dict]:
    """Compare neighbourhood projection with intent-routed projection.

    Condition C4 carries five semantic layers. At a fixed budget the layers
    compete: interlock, event and recipe nodes displace the signal records a
    grounding question needs. Routing spends budget on a layer only when the
    question gives a reason to, using cues available before retrieval.
    """
    out: list[dict] = []
    grounding_tasks = [t for t in TK.TASKS if t.gold_tag]
    for cond_key in ("C3", "C4"):
        cond = C.BY_KEY[cond_key]
        for routed in (False, True):
            for budget in BUDGET_SWEEP:
                suff = 0
                cov = 0.0
                toks = 0
                by_cat: dict[str, list[bool]] = {}
                for t in TK.TASKS:
                    els = R.retrieve(t.question, cond, MAX_ELEMENTS, routed=routed)
                    _txt, facts, tokens = C.build_context(els, cond, budget)
                    ok = not (set(t.required) - facts)
                    suff += ok
                    cov += coverage(set(t.required), facts)
                    toks += tokens
                    by_cat.setdefault(t.category, []).append(ok)
                # can the agent also *prove* the membership it grounded on?
                verifiable = 0
                for t in grounding_tasks:
                    owner = TK.P.SIGNAL_OWNER[str(t.gold_tag)]
                    els = R.retrieve(t.question, cond, MAX_ELEMENTS, routed=routed)
                    _txt, facts, _tk = C.build_context(els, cond, budget)
                    verifiable += C.fact("sig_of", str(t.gold_tag), owner) in facts
                n = len(TK.TASKS)
                row = {"condition": cond_key, "routed": routed, "budget": budget,
                       "ceiling": suff / n, "coverage": cov / n,
                       "mean_tokens": toks / n,
                       "verifiable_grounding": verifiable / len(grounding_tasks)}
                row.update({f"cat_{c}": sum(v) / len(v) for c, v in by_cat.items()})
                out.append(row)
    return out


# ---------------------------------------------------------------------------
# E2 / E3 - sufficiency and economy
# ---------------------------------------------------------------------------


@dataclass
class ContextRow:
    task: str
    category: str
    condition: str
    tokens: int
    n_required: int
    n_covered: int
    coverage: float
    sufficient: bool
    missing: str


def e2_context(budget: int = TOKEN_BUDGET) -> list[ContextRow]:
    rows: list[ContextRow] = []
    for t in TK.TASKS:
        for cond in C.CONDITIONS:
            els = R.retrieve(t.question, cond, MAX_ELEMENTS)
            _text, facts, tokens = C.build_context(els, cond, budget)
            missing = sorted(set(t.required) - facts)
            rows.append(ContextRow(
                task=t.tid, category=t.category, condition=cond.key,
                tokens=tokens, n_required=len(t.required),
                n_covered=len(set(t.required) & facts),
                coverage=coverage(set(t.required), facts),
                sufficient=not missing,
                missing=";".join(m.split(":")[0] for m in missing[:6]),
            ))
    return rows


def e2_budget_sweep() -> list[dict]:
    """Does simply enlarging the context window close the gap?  It does not."""
    out = []
    for budget in BUDGET_SWEEP:
        rows = e2_context(budget)
        for cond in C.CONDITIONS:
            sub = [r for r in rows if r.condition == cond.key]
            out.append({
                "budget": budget, "condition": cond.key,
                "ceiling": sum(1 for r in sub if r.sufficient) / len(sub),
                "coverage": sum(r.coverage for r in sub) / len(sub),
                "mean_tokens": sum(r.tokens for r in sub) / len(sub),
            })
    return out


def e3_serialisation_cost() -> list[dict]:
    """Token bill of the *whole* plant in each interchange format."""
    artefacts = {
        "Historian CSV (tags only)": KG.flat_tag_csv(),
        "NGSI-LD entities (JSON-LD)": json.dumps(KG.ngsild_entities()),
        "WoT Thing Descriptions (JSON-LD)": json.dumps(KG.wot_thing_descriptions()),
        "RDF Turtle (full KG)": KG.build_graph().serialize(format="turtle"),
        "OPC UA NodeSet2 (XML)": KG.opcua_nodeset(),
        "AAS Environment (JSON, IDTA v3)": json.dumps(KG.aas_environment()),
        "RDF N-Triples (full KG)": KG.build_graph().serialize(format="nt"),
        "RDF JSON-LD (expanded)": KG.build_graph().serialize(format="json-ld"),
    }
    base = None
    out = []
    for name, text in sorted(artefacts.items(), key=lambda kv: len(kv[1])):
        tok = surrogate_tokens(text)
        if base is None:
            base = tok
        out.append({"format": name, "bytes": len(text), "tokens": tok,
                    "ratio_to_csv": tok / base})
    return out


# ---------------------------------------------------------------------------
# E4 - guardrails
# ---------------------------------------------------------------------------


def e4_guardrails() -> tuple[list[dict], list[dict], dict]:
    cases, meta = V.evaluate()
    per_tier = []
    for tier in V.TIERS:
        pairs = [(c.gold != V.VALID, c.detected_by[tier]) for c in cases]
        sc = score_binary(pairs)
        faulty = [c for c in cases if c.gold != V.VALID]
        diagnosed = sum(1 for c in faulty if c.diagnosed_by[tier])
        lo, hi = wilson_interval(sc.tp, sc.tp + sc.fn)
        per_tier.append({
            "tier": tier, "label": V.TIER_LABEL[tier],
            "assets": V.TIER_ASSETS[tier],
            "detected": sc.tp, "missed": sc.fn,
            "recall": sc.recall, "recall_lo": lo, "recall_hi": hi,
            "false_alarms": sc.fp, "fp_rate": sc.false_positive_rate,
            "precision": sc.precision, "f1": sc.f1,
            "diagnosis_rate": diagnosed / len(faulty) if faulty else 0.0,
        })
    per_family = []
    for fam in sorted(V.FAULT_FAMILIES):
        sub = [c for c in cases if c.gold == fam]
        if not sub:
            continue
        row = {"family": fam, "description": V.FAULT_FAMILIES[fam], "n": len(sub)}
        for tier in V.TIERS:
            row[tier] = sum(1 for c in sub if c.detected_by[tier])
        per_family.append(row)

    # ---- E4b: non-RDF procedural baseline vs. the semantic tiers -----------
    faulty = [c for c in cases if c.gold != V.VALID]
    behavioural = ("F-ILK", "F-STATE", "F-STALE", "F-VALUE")
    n_behav = sum(1 for c in faulty if c.gold in behavioural)
    n_uscale = sum(1 for c in faulty if c.gold == "F-UNITSCALE")
    proc = []
    for tier in V.PROC_COHORT:
        pairs = [(c.gold != V.VALID, c.detected_by[tier]) for c in cases]
        sc = score_binary(pairs)
        diagnosed = sum(1 for c in faulty if c.diagnosed_by[tier])
        proc.append({
            "tier": tier, "label": V.PROC_LABEL[tier],
            "recall": sc.recall, "false_alarms": sc.fp,
            "fp_rate": sc.false_positive_rate,
            "diagnosis_rate": diagnosed / len(faulty) if faulty else 0.0,
            "unitscale_caught": sum(1 for c in faulty
                                    if c.gold == "F-UNITSCALE" and c.diagnosed_by[tier]),
            "unitscale_n": n_uscale,
            "behavioural_caught": sum(1 for c in faulty
                                      if c.gold in behavioural and c.detected_by[tier]),
            "behavioural_n": n_behav,
        })
    meta = {**meta, "behavioural_families": list(behavioural)}
    return per_tier, per_family, meta, proc


# ---------------------------------------------------------------------------
# E5 - action space
# ---------------------------------------------------------------------------


def e5_action_space() -> tuple[list[dict], list[dict], dict[str, int]]:
    writes = [asdict(s) for s in TG.write_action_space()]
    cmds = [asdict(s) for s in TG.command_action_space()]
    return writes, cmds, TG.schema_sizes()


# ---------------------------------------------------------------------------
# E6 - context-bounded oracle
# ---------------------------------------------------------------------------


def e6_ceiling(context_rows: list[ContextRow]) -> list[dict]:
    out = []
    for cond in C.CONDITIONS:
        rows = [r for r in context_rows if r.condition == cond.key]
        k = sum(1 for r in rows if r.sufficient)
        lo, hi = wilson_interval(k, len(rows))
        by_cat = {}
        for cat in TK.CATEGORIES:
            sub = [r for r in rows if r.category == cat]
            by_cat[cat] = sum(1 for r in sub if r.sufficient) / len(sub) if sub else 0.0
        mean_tokens = sum(r.tokens for r in rows) / len(rows)
        mean_cov = sum(r.coverage for r in rows) / len(rows)
        out.append({
            "condition": cond.key, "label": cond.label,
            "counterpart": cond.counterpart,
            "n_tasks": len(rows), "ceiling": k / len(rows),
            "ceiling_lo": lo, "ceiling_hi": hi,
            "mean_coverage": mean_cov,
            "mean_tokens": mean_tokens,
            "coverage_per_1k_tokens": mean_cov / (mean_tokens / 1000.0),
            **{f"cat_{c}": v for c, v in by_cat.items()},
        })
    return out


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def run_all(outdir: str | Path = "../results") -> dict:
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)

    grounding = e1_grounding()
    context = e2_context()
    sweep = e2_budget_sweep()
    serial = e3_serialisation_cost()
    tiers, families, meta, proc = e4_guardrails()
    writes, cmds, schema_tokens = e5_action_space()
    ceiling = e6_ceiling(context)
    convention = e8_convention_robustness()
    routing = e9_routing()
    graph = KG.build_graph()
    probes = [asdict(p) for p in SP.run(graph)]
    stuffing = {r.task: r.tokens for r in context if r.condition == "C4"}
    sufficient = {r.task: r.sufficient for r in context if r.condition == "C4"}
    for p in probes:
        p["stuffing_tokens_C4"] = stuffing.get(p["task"])
        p["stuffing_sufficient"] = sufficient.get(p["task"], False)
        p["reduction"] = (stuffing.get(p["task"], 0) / p["total_tokens"]
                          if p["total_tokens"] else None)

    results = {
        "config": {"token_budget": TOKEN_BUDGET, "max_elements": MAX_ELEMENTS,
                   "n_tasks": len(TK.TASKS), "n_signals": len(TK.P.ALL_SIGNALS),
                   "n_assets": len(TK.P.PLANT),
                   "n_homographs": len(TK.homograph_index()),
                   "kg_triples": len(graph),
                   "n_cases": meta["n_cases"]},
        "e1_grounding": [asdict(r) for r in grounding],
        "e2_context": [asdict(r) for r in context],
        "e2_sweep": sweep,
        "e3_serialisation": serial,
        "e4_tiers": tiers,
        "e4_families": families,
        "e4_meta": meta,
        "e4b_procedural": proc,
        "e5_writes": writes,
        "e5_commands": cmds,
        "e5_schema_tokens": schema_tokens,
        "e6_ceiling": ceiling,
        "e7_sparql": probes,
        "e8_convention": convention,
        "e9_routing": routing,
    }
    (out / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    return results
