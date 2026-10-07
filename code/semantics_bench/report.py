"""Turn ``results.json`` into the LaTeX tables and PDF figures used by the paper.

Nothing in ``paper/tables`` or ``paper/figures`` is written by hand: rerunning
``run_experiments.py`` regenerates every number in the manuscript.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from . import conditions as C  # noqa: E402
from . import tasks as TK  # noqa: E402
from . import validation as V  # noqa: E402

plt.rcParams.update({
    "font.family": "serif",
    "font.size": 8.5,
    "axes.titlesize": 8.5,
    "axes.labelsize": 8.5,
    "axes.grid": True,
    "grid.alpha": 0.3,
    "grid.linestyle": ":",
    "figure.dpi": 200,
    "figure.constrained_layout.use": True,
    "savefig.bbox": "tight",
    "axes.spines.top": False,
    "axes.spines.right": False,
})

PALETTE = ["#8c8c8c", "#5b7fa6", "#e0a458", "#5b8c5a", "#a4494f"]


_DIGIT_WORDS = str.maketrans({"0": "Zero", "1": "One", "2": "Two", "3": "Three",
                              "4": "Four", "5": "Five", "6": "Six", "7": "Seven",
                              "8": "Eight", "9": "Nine"})


def _alpha(key: str) -> str:
    """LaTeX command names may not contain digits."""
    return key.translate(_DIGIT_WORDS)


def _esc(s: str) -> str:
    return (str(s).replace("\\", r"\textbackslash{}").replace("&", r"\&")
            .replace("%", r"\%").replace("_", r"\_").replace("#", r"\#"))


def _table(caption: str, label: str, spec: str, header: list[str],
           rows: list[list[str]], note: str = "", small: bool = True,
           rule_before: tuple[int, ...] = (), wide: bool = True) -> str:
    env = "table*" if wide else "table"
    out = [f"\\begin{{{env}}}[t]", "\\centering", "\\caption{" + caption + "}",
           "\\label{tab:" + label + "}"]
    if small:
        out.append("\\footnotesize")
    # shrink only if the natural width exceeds the text block
    out.append("\\resizebox{\\ifdim\\width>\\linewidth\\linewidth\\else\\width\\fi}{!}{%")
    out.append("\\begin{tabular}{" + spec + "}")
    out.append("\\toprule")
    out.append(" & ".join(header) + " \\\\")
    out.append("\\midrule")
    for i, r in enumerate(rows):
        if i in rule_before:
            out.append("\\midrule")
        out.append(" & ".join(r) + " \\\\")
    out.append("\\bottomrule")
    out.append("\\end{tabular}}")
    if note:
        out.append("\\\\[4pt]\\begin{minipage}{\\linewidth}\\footnotesize " + note
                   + "\\end{minipage}")
    out.append(f"\\end{{{env}}}")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------

#: human-readable gloss for each fact kind, and the AUF criterion it serves.
#: Kept here rather than in ``conditions`` so that the empirical fact model and
#: its narrative labelling cannot silently diverge from the code that emits it.
FACT_KIND_INFO: dict[str, tuple[str, str]] = {
    "value": ("sampled value", "--"),
    "desc": ("description string", "U1"),
    "unit": ("unit \\emph{symbol}", "U3*"),
    "qk": ("quantity kind", "U3"),
    "range": ("engineering range", "U2"),
    "alarm": ("alarm limits", "U2"),
    "access": ("access mode (r/w)", "U2"),
    "role": ("signal role (PV/SP)", "U2"),
    "sig_of": ("signal--asset membership", "U4"),
    "parent": ("asset parentage", "U4"),
    "label": ("asset display name", "U1"),
    "nameplate": ("manufacturer nameplate", "U1"),
    "semid": ("semantic id (IRDI)", "U1"),
    "isa95": ("ISA-95 level", "U4"),
    "location": ("physical location", "U4"),
    "class": ("ontology class", "U4"),
    "dim": ("unit dimension vector", "U3"),
    "conv": ("unit conversion factor", "U3"),
    "feeds": ("material/utility topology", "U4"),
    "state": ("PackML state", "U5"),
    "legalcmd": ("legal command set", "U5"),
    "interlock": ("interlock guard", "U6"),
    "time": ("observation timestamp", "U7"),
    "event": ("event-log entry", "U7"),
    "recipe": ("recipe parameters", "U6"),
}


def table_factkeys(res: dict) -> str:
    """Fact kind x condition presence matrix, generated from ``conditions``.

    This is the auditable form of the ``same facts, different representations''
    claim: every fact kind the benchmark knows about, the AUF criterion it
    serves, and exactly which conditions are able to express it.  A condition
    cannot advantage a task on a fact kind whose cell here is empty.
    """
    rows = []
    for kind in C.FACT_KINDS:
        label, auf = FACT_KIND_INFO.get(kind, (kind, "--"))
        cells = ["\\checkmark" if cond.can(kind) else "" for cond in C.CONDITIONS]
        rows.append(["\\texttt{" + _esc(kind) + "}", label, auf] + cells)
    return _table(
        "The fact model. Every fact kind the benchmark distinguishes, the "
        "agent-usability criterion it serves, and the context conditions able to "
        "express it. A fact key is a kind together with the identifiers it ranges "
        "over (e.g.\\ \\texttt{sig\\_of:L1\\_FIL\\_PT0301\\_PV|L1-FIL}); a task is "
        "answerable under a condition only if every fact key it requires is "
        "expressible there.",
        "factkeys", "llc" + "c" * len(C.CONDITIONS),
        ["Fact kind", "Meaning", "AUF"] + [c.key for c in C.CONDITIONS], rows,
        "\\emph{U3*} marks the unit \\emph{symbol}, which C1 carries as an opaque "
        "string; the dimension and conversion that make it a calculus (U3) arrive "
        "only at C3. Because each condition is exactly the set of ticked rows, the "
        "accuracy differences in \\S\\ref{sec:results} are differences in which "
        "facts are present, not in how a fixed fact set is phrased.",
        small=True)


def table_design_ref(res: dict) -> str:
    """Task categories and fault families, defined up front, from the code."""
    cats = list(TK.CATEGORIES.items())
    fams = list(V.FAULT_FAMILIES.items())
    n = max(len(cats), len(fams))
    rows = []
    for i in range(n):
        if i < len(cats):
            ck, cd = cats[i]
            left = ["\\textbf{" + ck + "}", _esc(cd)]
        else:
            left = ["", ""]
        if i < len(fams):
            fk, fd = fams[i]
            right = ["\\textsc{" + _esc(fk.lower()) + "}", _esc(fd)]
        else:
            right = ["", ""]
        rows.append(left + right)
    return _table(
        "The eight task categories (left) and twelve action fault families "
        "(right) exercised by the benchmark, defined before the experiments that "
        "use them.",
        "design-ref", "lL{4.6cm}lL{4.8cm}",
        ["Cat.", "Task category", "Family", "Fault family"], rows,
        "Task categories drive Experiments E1--E9 (\\S\\ref{sec:results}); fault "
        "families drive the guardrail and action-space experiments E4--E5. "
        "Per-family detection by validator tier is reported in "
        "Table~\\ref{tab:e4-families}.")


def table_e1(res: dict) -> str:
    agg = defaultdict(list)
    for r in res["e1_grounding"]:
        agg[r["condition"]].append(r)
    rows = []
    for cond in C.CONDITIONS:
        v = agg[cond.key]
        n = len(v)
        top1 = sum(1 for x in v if x["top1"])
        ver = sum(1 for x in v if x["verifiable"])
        mrr = sum(x["mrr"] for x in v) / n
        top5 = sum(1 for x in v if x["rank"])
        distr = sum(x["distractors_in_top5"] for x in v)
        rows.append([cond.key, _esc(cond.counterpart),
                     f"{top1}/{n}", f"{top1/n:.3f}", f"{ver/n:.3f}", f"{mrr:.3f}",
                     f"{top5/n:.3f}", str(distr)])
    return _table(
        "E1: entity grounding under homograph pressure. "
        f"{len(agg[C.CONDITIONS[0].key])} mentions, each resolvable to exactly one tag; "
        f"{res['config']['n_homographs']} description strings in the plant are shared "
        "by two or more tags.",
        "e1-grounding", "llcccccc",
        ["Cond.", "Representation", "Top-1", "Acc@1", "Verif@1", "MRR", "Recall@5",
         "Distractors@5"],
        rows,
        "\\emph{Verif@1} is the fraction of mentions resolved correctly \\emph{and} "
        "supported by an explicit membership fact in the context; a correct answer "
        "that cannot be shown to be correct is a guess that happened to land. "
        "\\emph{Distractors@5} counts hand-labelled confusable tags admitted into the "
        "top five. C0 indexes tag mnemonics only; C1--C2 add free text and types; "
        "C3--C4 resolve the asset first and search only inside its scope. C4's "
        "shortfall on Verif@1 is a budget artefact, removed by intent routing "
        "(Table~\\ref{tab:e9-routing}).")


def table_e6(res: dict) -> str:
    cats = list(TK.CATEGORIES)
    rows = []
    for r in res["e6_ceiling"]:
        rows.append([r["condition"],
                     f"{r['mean_coverage']:.3f}",
                     f"{r['ceiling']:.3f}",
                     f"[{r['ceiling_lo']:.2f}, {r['ceiling_hi']:.2f}]",
                     f"{r['mean_tokens']:.0f}",
                     f"{r['coverage_per_1k_tokens']:.3f}"]
                    + [f"{r['cat_' + c]:.2f}" for c in cats])
    return _table(
        "E2/E3/E6: context sufficiency, accuracy ceiling, context economy and "
        "the per-category breakdown, at a "
        f"{res['config']['token_budget']}-token budget over "
        f"{res['config']['n_tasks']} tasks.",
        "e6-ceiling", "lccccc" + "c" * len(cats),
        ["Cond.", "Fact cov.", "Ceiling", "95\\% CI", "Tokens", "Cov./1k"] + cats,
        rows,
        "\\emph{Ceiling} is the fraction of tasks for which the retrieved context "
        "expresses \\emph{every} fact the question needs; no reader, however capable, "
        "can exceed it without guessing. Conditions are defined in "
        "Table~\\ref{tab:conditions}. Categories: "
        + "; ".join(f"\\textbf{{{c}}} {TK.CATEGORIES[c]}" for c in cats) + ".")


def table_e3(res: dict) -> str:
    rows = [[_esc(r["format"]), f"{r['bytes']/1024:.1f}", f"{r['tokens']:,}".replace(",", "\\,"),
             f"{r['ratio_to_csv']:.1f}$\\times$"] for r in res["e3_serialisation"]]
    return _table(
        "E3: token bill of the identical plant in each interchange format "
        f"({res['config']['n_assets']} assets, {res['config']['n_signals']} signals, "
        f"{res['config']['kg_triples']:,} triples).".replace(",", "\\,"),
        "e3-serialisation", "lrrr",
        ["Serialisation", "KiB", "Tokens", "vs.\\ CSV"], rows,
        "Semantic richness is not free. An agent cannot be handed a NodeSet2 or an AAS "
        "environment directly; the graph must be \\emph{queried}, and the answer, "
        "rather than the model, placed in the window.")


def table_e4_tiers(res: dict) -> str:
    rows = []
    for r in res["e4_tiers"]:
        rows.append([r["tier"], _esc(V.TIER_ASSETS[r["tier"]]),
                     f"{r['detected']}/{r['detected'] + r['missed']}",
                     f"{r['recall']:.3f}",
                     f"[{r['recall_lo']:.2f}, {r['recall_hi']:.2f}]",
                     f"{r['diagnosis_rate']:.3f}",
                     str(r["false_alarms"]), f"{r['fp_rate']:.3f}"])
    return _table(
        "E4: guardrail efficacy over "
        f"{res['e4_meta']['n_cases']} proposed agent actions "
        f"({res['e4_meta']['n_faulty']} faulty, {res['e4_meta']['n_valid']} valid).",
        "e4-tiers", "llccccrc",
        ["Tier", "Semantic assets available", "Caught", "Recall", "95\\% CI",
         "Correct diag.", "False alarms", "FP rate"],
        rows,
        "\\emph{Correct diagnosis} requires the validator to name the right fault "
        "family, not merely to reject. G2 rejects unit-scale errors for the wrong "
        "reason and rejects legal re-expressions of a value in a different unit.")


def table_e4_families(res: dict) -> str:
    rows = []
    for r in res["e4_families"]:
        rows.append([_esc(r["family"]), _esc(r["description"]), str(r["n"])]
                    + [f"{r[t]}" for t in V.TIERS])
    return _table(
        "E4: detection by fault family.",
        "e4-families", "llr" + "c" * len(V.TIERS),
        ["Family", "Failure mode", "$n$"] + list(V.TIERS), rows,
        "The last five fault families, namely interlock violation, illegal state transition, "
        "stale evidence and unfaithful read-back, are invisible to every tier that "
        "lacks an explicit behavioural, constraint or provenance model, no matter how "
        "complete its type information is.")


def table_e4b(res: dict) -> str:
    rows = []
    for r in res["e4b_procedural"]:
        rows.append([r["label"],  # controlled LaTeX from V.PROC_LABEL
                     f"{r['recall']:.3f}", str(r["false_alarms"]),
                     f"{r['fp_rate']:.3f}", f"{r['diagnosis_rate']:.3f}",
                     f"{r['unitscale_caught']}/{r['unitscale_n']}",
                     f"{r['behavioural_caught']}/{r['behavioural_n']}"])
    return _table(
        "E4b: is the guardrail gain from \\emph{any} strong rule system, or from "
        "explicit semantics? A non-RDF procedural validator (G-proc) with a "
        "hard-coded unit-conversion table is compared against the flat catalogue "
        "and the two graph tiers.",
        "e4b-procedural", "lcccccc",
        ["Validator", "Recall", "False alarms", "FP rate", "Diagnosis",
         "Unit-scale diag.", "Behavioural"], rows,
        "\\emph{Unit-scale diag.} is \\emph{correct diagnosis} of \\textsc{f-unitscale} "
        "(silent scale errors): the flat catalogue rejects them for the wrong reason "
        "(a unit-string mismatch), so it scores zero here although it happens to "
        "reject. \\emph{Behavioural} is detection across \\textsc{f-ilk}, "
        "\\textsc{f-state}, \\textsc{f-stale} and \\textsc{f-value}. Procedural "
        "code with a unit calculus matches the RDF+QUDT tier on the unit families "
        "and eliminates the flat catalogue's false alarms, so the unit result is "
        "\\emph{not} RDF-specific. The behavioural, interlock, temporal and "
        "provenance families remain out of reach until the corresponding model is "
        "re-implemented by hand; the semantic stack supplies each as a "
        "declarative, reusable asset instead.", wide=False)


def table_e11(e11: dict) -> str:
    """E11 real-model table, built from the frozen, dated E11 artefact."""
    def f(x: object) -> str:
        return "--" if x is None else f"{x:.2f}"
    rows = []
    for r in e11["per_condition"]:
        rows.append([r["condition"], f"{r['accuracy']:.2f}", f(r["ceiling"]),
                     f"{r['refusal_rate']:.2f}",
                     f(r["hallucination_rate_when_insufficient"]),
                     f(r["correct_when_sufficient"])])
    m = e11["meta"]
    return _table(
        f"E11: real-model sanity check. Model \\texttt{{{_esc(m['model'])}}}, "
        f"{m['repeats']} repeats, {m['n_tasks']} tasks per condition, accessed "
        f"{m['timestamp'][:10]}. A dated measurement; unlike every other table it "
        "is not regenerated by the deterministic pipeline.",
        "e11-realmodel", "lccccc",
        ["Cond.", "Accuracy", "Ceiling", "Refusal", "Halluc.(ins.)",
         "Acc.$|$suff"], rows,
        "\\emph{Accuracy} is graded heuristically against the gold answers (raw "
        "answers are archived for audit). \\emph{Ceiling} is the model-free "
        "sufficiency bound (Table~\\ref{tab:e6-ceiling}); \\emph{Halluc.(ins.)} is "
        "the fraction of insufficient-context tasks answered wrongly rather than "
        "refused; \\emph{Acc.$|$suff} is accuracy on sufficient-context tasks. "
        "Accuracy rises monotonically with the stack; it exceeds the ceiling at "
        "C1--C2, where the model guesses from naming conventions "
        "(\\S\\ref{sec:e8}), and falls below it at C3--C4, the model-execution gap "
        "the ceiling bounds.", wide=False)


def fig_e11(e11: dict, out: Path) -> None:
    conds = [r["condition"] for r in e11["per_condition"]]
    acc = [r["accuracy"] for r in e11["per_condition"]]
    ceil = [(r["ceiling"] or 0.0) for r in e11["per_condition"]]
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 2.7))
    ax = axes[0]
    x = list(range(len(conds)))
    ax.bar([i - 0.18 for i in x], acc, width=0.36, color=PALETTE[1],
           label="model accuracy")
    ax.bar([i + 0.18 for i in x], ceil, width=0.36, color=PALETTE[2], alpha=0.85,
           label="ceiling (model-free)")
    ax.set_xticks(x)
    ax.set_xticklabels(conds)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("fraction")
    ax.set_title("(a) accuracy vs. ceiling")
    ax.legend(frameon=False, fontsize=7, loc="upper left")
    ax = axes[1]
    cats = [c for c in TK.CATEGORIES if c in e11["per_category"]]
    mat = [[e11["per_category"][cat].get(c, 0.0) for c in conds] for cat in cats]
    im = ax.imshow(mat, cmap="YlGnBu", vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(len(conds)))
    ax.set_xticklabels(conds)
    ax.set_yticks(range(len(cats)))
    ax.set_yticklabels(cats, fontsize=7)
    ax.grid(False)
    ax.set_title("(b) accuracy by category")
    fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    fig.savefig(out / "fig_e11.pdf")
    fig.savefig(out / "fig_e11.png")
    plt.close(fig)


def emit_e11(e11_json_path: str | Path, paper_dir: str | Path = "../paper") -> None:
    """Generate the E11 table, figure and macros from a frozen E11 results file.

    Kept separate from :func:`emit` on purpose: E11 is a dated real-model
    measurement, not part of the deterministic offline pipeline.
    """
    e11 = json.loads(Path(e11_json_path).read_text(encoding="utf-8"))
    paper = Path(paper_dir)
    (paper / "tables").mkdir(parents=True, exist_ok=True)
    (paper / "figures").mkdir(parents=True, exist_ok=True)
    (paper / "tables" / "e11_realmodel.tex").write_text(table_e11(e11), encoding="utf-8")
    fig_e11(e11, paper / "figures")
    m = e11["meta"]
    pc = {r["condition"]: r for r in e11["per_condition"]}
    macros = [
        r"\newcommand{\EllModel}{%s}" % _esc(m["model"]),
        r"\newcommand{\EllDate}{%s}" % m["timestamp"][:10],
        r"\newcommand{\EllRepeats}{%d}" % m["repeats"],
    ]
    for c in ("C0", "C1", "C2", "C3", "C4"):
        if c in pc:
            macros.append(r"\newcommand{\EllAcc%s}{%.0f\%%}"
                          % (_alpha(c), 100 * pc[c]["accuracy"]))
    (paper / "generated_macros_e11.tex").write_text("\n".join(macros) + "\n",
                                                    encoding="utf-8")


def table_e5(res: dict) -> str:
    rows = []
    for w, c in zip(res["e5_writes"], res["e5_commands"]):
        rows.append([w["tier"],
                     f"{w['size']:,}".replace(",", "\\,"), f"{w['reduction_bits']:.2f}",
                     f"{w['precision']:.3f}", f"{w['recall']:.3f}",
                     f"{c['size']:,}".replace(",", "\\,"), f"{c['reduction_bits']:.2f}",
                     f"{c['precision']:.3f}", f"{c['recall']:.3f}"])
    return _table(
        "E5: size and fidelity of the admissible action space.",
        "e5-actionspace", "lrrcc rrcc",
        ["Tier", "$|A|$", "$\\Delta$bits", "Prec.", "Rec.",
         "$|A|$", "$\\Delta$bits", "Prec.", "Rec."], rows,
        "Left block: \\texttt{write\\_setpoint(tag,value,unit)} enumerated over "
        "$73$ tags $\\times$ $35$ units $\\times$ $28$ magnitudes. "
        "Right block: \\texttt{packml\\_command(asset,command)}. "
        "\\emph{Precision} is the probability that an admitted call is genuinely "
        "executable; \\emph{recall} is the fraction of executable calls the tier still "
        "allows. G2 buys its reduction by forbidding legal work.")


def table_e7(res: dict) -> str:
    rows = []
    for p in res["e7_sparql"]:
        stuff = p["stuffing_tokens_C4"]
        suff = "\\checkmark" if p.get("stuffing_sufficient") else "$\\times$"
        rows.append([p["task"], _esc(p["description"]),
                     str(p["query_tokens"]), str(p["result_rows"]),
                     str(p["result_tokens"]), str(p["total_tokens"]),
                     f"{stuff:,}".replace(",", "\\,") if stuff else "--", suff,
                     f"{p['reduction']:.1f}$\\times$" if p["reduction"] else "--"])
    return _table(
        "E7: answering by query execution instead of context stuffing.",
        "e7-sparql", "llrrrrrcr",
        ["Task", "SPARQL probe", "Query", "Rows", "Result", "Total",
         "C4 tok.", "Suff.?", "Saving"], rows,
        "All queries execute against the same RDF graph and return the correct answer. "
        "\\emph{Suff.?} records whether the stuffed C4 context contained every required "
        "fact. RNG-04 is a plant-wide sweep: it is unanswerable by stuffing at any "
        "budget, yet costs "
        f"{[p for p in res['e7_sparql'] if p['task'] == 'RNG-04'][0]['total_tokens']} "
        "tokens as a query.")


def table_schema(res: dict) -> str:
    rows = [[k, f"{v:,}".replace(",", "\\,")]
            for k, v in res["e5_schema_tokens"].items()]
    return _table(
        "E5: size of the generated \\texttt{write\\_setpoint} tool schema for "
        "Line 1.",
        "e5-schema", "lr", ["Cond.", "Schema tokens"], rows,
        "Constraints carried in the schema are enforced by constrained decoding; "
        "constraints left out must be recalled by the model.", wide=False)


def table_e8(res: dict) -> str:
    from . import experiments as EX

    resolvers = [k for k, _c, _d in EX.RESOLVERS]
    by = {(r["scheme"], r["resolver"]): r for r in res["e8_convention"]}
    schemes = list(dict.fromkeys(r["scheme"] for r in res["e8_convention"]))
    rows = []
    for sch in schemes:
        first = by[(sch, resolvers[0])]
        rows.append([_esc(first["scheme_label"]),
                     "\\texttt{" + first["example"] + "}"]
                    + [f"{by[(sch, k)]['top1']:.2f}\\,({by[(sch, k)]['confidently_wrong']:.2f})"
                       for k in resolvers])
    spread = ["\\emph{spread across conventions}", ""]
    for k in resolvers:
        vals = [by[(s, k)]["top1"] for s in schemes]
        spread.append(f"\\textbf{{{max(vals) - min(vals):.2f}}}")
    rows.append(spread)
    return _table(
        "E8: grounding under five tag naming conventions. Descriptions, "
        "relations, units, ranges, states and values are identical in every row; "
        "only the identifier strings differ. Cells are top-1 accuracy with the "
        "fraction resolved \\emph{confidently to the wrong tag} in parentheses.",
        "e8-convention", "ll" + "c" * len(resolvers),
        ["Naming scheme", "Example"] + [_esc(k) for k in resolvers], rows,
        ". ".join(f"\\textbf{{{_esc(k)}}} = {EX.RESOLVER_LABEL[k]}" for k in resolvers)
        + ". Decoding the mnemonic is the strongest available reading of an "
        "un-grounded catalogue, and on the convention it was built for it nearly "
        "matches a typed model. It is also the only resolver whose accuracy "
        "\\emph{falls} when the convention stops being truthful, and the only one "
        "whose accuracy varies with the convention at all.",
        rule_before=(len(schemes),))


def table_e9(res: dict) -> str:
    cats = list(TK.CATEGORIES)
    rows = []
    for r in res["e9_routing"]:
        if r["budget"] != res["config"]["token_budget"]:
            continue
        rows.append([r["condition"], "routed" if r["routed"] else "neighbourhood",
                     f"{r['ceiling']:.3f}", f"{r['coverage']:.3f}",
                     f"{r['verifiable_grounding']:.3f}"]
                    + [f"{r.get('cat_' + c, 0.0):.2f}" for c in cats])
    return _table(
        "E9: neighbourhood projection versus intent-routed projection at a "
        f"{res['config']['token_budget']}-token budget.",
        "e9-routing", "ll ccc " + "c" * len(cats),
        ["Cond.", "Projection", "Ceiling", "Coverage", "Verif@1"] + cats, rows,
        "Routing spends budget on the constraint, event and recipe layers only "
        "when the question gives a reason to, using surface cues available before "
        "retrieval. No category degrades; grounding and provenance recover fully. "
        "The trade-off between semantic richness and context budget is therefore "
        "an artefact of dumping a neighbourhood, not a property of the "
        "representation.")


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------


def fig_ceiling(res: dict, out: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 2.6))
    keys = [c.key for c in C.CONDITIONS]
    ceil = [r["ceiling"] for r in res["e6_ceiling"]]
    lo = [r["ceiling"] - r["ceiling_lo"] for r in res["e6_ceiling"]]
    hi = [r["ceiling_hi"] - r["ceiling"] for r in res["e6_ceiling"]]
    cov = [r["mean_coverage"] for r in res["e6_ceiling"]]
    ax = axes[0]
    ax.bar(keys, cov, color=PALETTE, alpha=0.45, label="fact coverage")
    ax.errorbar(keys, ceil, yerr=[lo, hi], fmt="o-", color="#222", ms=4,
                lw=1.2, capsize=3, label="task ceiling")
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("fraction")
    ax.set_title("(a) sufficiency at a 6k-token budget")
    ax.legend(frameon=False, fontsize=7, loc="upper left")

    ax = axes[1]
    by_cond = defaultdict(list)
    for r in res["e2_sweep"]:
        by_cond[r["condition"]].append((r["budget"], r["ceiling"]))
    for i, k in enumerate(keys):
        xs, ys = zip(*sorted(by_cond[k]))
        ax.plot(xs, ys, "o-", ms=3, lw=1.2, color=PALETTE[i], label=k)
    ax.set_xscale("log")
    ax.set_xlabel("context budget (tokens)")
    ax.set_ylabel("task ceiling")
    ax.set_ylim(0, 1.05)
    ax.set_title("(b) enlarging the window does not close the gap")
    ax.legend(frameon=False, fontsize=7, ncol=2)
    fig.savefig(out / "fig_ceiling.pdf")
    fig.savefig(out / "fig_ceiling.png")
    plt.close(fig)


def fig_guardrails(res: dict, out: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 2.8))
    tiers = [r["tier"] for r in res["e4_tiers"]]
    rec = [r["recall"] for r in res["e4_tiers"]]
    diag = [r["diagnosis_rate"] for r in res["e4_tiers"]]
    fpr = [r["fp_rate"] for r in res["e4_tiers"]]
    x = range(len(tiers))
    ax = axes[0]
    ax.bar([i - 0.22 for i in x], rec, width=0.22, color=PALETTE[3], label="detection")
    ax.bar(x, diag, width=0.22, color=PALETTE[1], label="correct diagnosis")
    ax.bar([i + 0.22 for i in x], fpr, width=0.22, color=PALETTE[4], label="false alarm")
    ax.set_xticks(list(x))
    ax.set_xticklabels(tiers)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("rate")
    ax.set_title("(a) guardrail efficacy")
    ax.legend(frameon=False, fontsize=7)

    ax = axes[1]
    fams = [r["family"] for r in res["e4_families"]]
    mat = [[r[t] / r["n"] for t in V.TIERS] for r in res["e4_families"]]
    im = ax.imshow(mat, cmap="YlGnBu", vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(len(V.TIERS)))
    ax.set_xticklabels(V.TIERS)
    ax.set_yticks(range(len(fams)))
    ax.set_yticklabels(fams, fontsize=6.5)
    ax.grid(False)
    ax.set_title("(b) detection rate by fault family")
    fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    fig.savefig(out / "fig_guardrails.pdf")
    fig.savefig(out / "fig_guardrails.png")
    plt.close(fig)


def fig_actionspace(res: dict, out: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 2.6))
    tiers = [r["tier"] for r in res["e5_writes"]]
    ax = axes[0]
    ax.plot(tiers, [r["bits"] for r in res["e5_writes"]], "o-", color=PALETTE[1],
            label="write_setpoint")
    ax.plot(tiers, [r["bits"] for r in res["e5_commands"]], "s--", color=PALETTE[2],
            label="packml_command")
    ax.set_ylabel("$\\log_2 |A|$  (bits)")
    ax.set_title("(a) size of the admissible action space")
    ax.legend(frameon=False, fontsize=7)
    ax = axes[1]
    ax.plot(tiers, [r["precision"] for r in res["e5_writes"]], "o-",
            color=PALETTE[3], label="precision")
    ax.plot(tiers, [r["recall"] for r in res["e5_writes"]], "s--",
            color=PALETTE[4], label="recall")
    ax.set_ylim(-0.02, 1.05)
    ax.set_ylabel("rate")
    ax.set_title("(b) fidelity of the admitted set (writes)")
    ax.legend(frameon=False, fontsize=7)
    fig.savefig(out / "fig_actionspace.pdf")
    fig.savefig(out / "fig_actionspace.png")
    plt.close(fig)


def fig_tokens(res: dict, out: Path) -> None:
    fig, ax = plt.subplots(figsize=(6.6, 2.6))
    names = [r["format"] for r in res["e3_serialisation"]]
    toks = [r["tokens"] for r in res["e3_serialisation"]]
    ax.barh(names, toks, color=PALETTE[1], alpha=0.85)
    for i, t in enumerate(toks):
        ax.text(t * 1.02, i, f"{t/1000:.1f}k", va="center", fontsize=7)
    ax.set_xscale("log")
    ax.set_xlabel("tokens for the whole plant (log scale)")
    ax.tick_params(axis="y", labelsize=7)
    fig.savefig(out / "fig_tokens.pdf")
    fig.savefig(out / "fig_tokens.png")
    plt.close(fig)


# ---------------------------------------------------------------------------


def fig_convention(res: dict, out: Path) -> None:
    from . import experiments as EX

    resolvers = [k for k, _c, _d in EX.RESOLVERS]
    schemes = list(dict.fromkeys(r["scheme"] for r in res["e8_convention"]))
    by = {(r["scheme"], r["resolver"]): r for r in res["e8_convention"]}
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 2.8))

    ax = axes[0]
    width = 0.8 / len(resolvers)
    x = range(len(schemes))
    for i, k in enumerate(resolvers):
        ax.bar([j + i * width - 0.4 + width / 2 for j in x],
               [by[(s, k)]["top1"] for s in schemes],
               width=width, color=PALETTE[i + 1], label=k)
    ax.set_xticks(list(x))
    ax.set_xticklabels(schemes, rotation=18, ha="right", fontsize=7)
    ax.set_ylim(0, 1.28)
    ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.set_ylabel("top-1 grounding")
    ax.set_title("(a) accuracy vs. naming convention")
    ax.legend(frameon=False, fontsize=6.5, ncol=4, loc="upper center",
              columnspacing=1.0, handlelength=1.2)

    ax = axes[1]
    by_cond = defaultdict(list)
    for r in res["e9_routing"]:
        by_cond[(r["condition"], r["routed"])].append((r["budget"], r["ceiling"]))
    styles = {("C3", False): ("--", PALETTE[3]), ("C3", True): ("-", PALETTE[3]),
              ("C4", False): ("--", PALETTE[4]), ("C4", True): ("-", PALETTE[4])}
    for key, pts in by_cond.items():
        xs, ys = zip(*sorted(pts))
        ls, col = styles[key]
        ax.plot(xs, ys, ls, marker="o", ms=3, lw=1.3, color=col,
                label=f"{key[0]} {'routed' if key[1] else 'neighbourhood'}")
    ax.set_xscale("log")
    ax.set_xlabel("context budget (tokens)")
    ax.set_ylabel("task ceiling")
    ax.set_ylim(0, 1.05)
    ax.set_title("(b) intent routing vs. budget")
    ax.legend(frameon=False, fontsize=6.5)
    fig.savefig(out / "fig_convention.pdf")
    fig.savefig(out / "fig_convention.png")
    plt.close(fig)


# ---------------------------------------------------------------------------


def emit(results_path: str | Path = "../results/results.json",
         paper_dir: str | Path = "../paper") -> None:
    res = json.loads(Path(results_path).read_text(encoding="utf-8"))
    paper = Path(paper_dir)
    tdir, fdir = paper / "tables", paper / "figures"
    tdir.mkdir(parents=True, exist_ok=True)
    fdir.mkdir(parents=True, exist_ok=True)

    for name, fn in [
        ("design_ref", table_design_ref), ("factkeys", table_factkeys),
        ("e1_grounding", table_e1), ("e6_ceiling", table_e6),
        ("e3_serialisation", table_e3),
        ("e4_tiers", table_e4_tiers), ("e4_families", table_e4_families),
        ("e4b_procedural", table_e4b),
        ("e5_actionspace", table_e5), ("e5_schema", table_schema),
        ("e7_sparql", table_e7), ("e8_convention", table_e8),
        ("e9_routing", table_e9),
    ]:
        (tdir / f"{name}.tex").write_text(fn(res), encoding="utf-8")

    fig_ceiling(res, fdir)
    fig_guardrails(res, fdir)
    fig_actionspace(res, fdir)
    fig_tokens(res, fdir)
    fig_convention(res, fdir)

    macros = [
        r"\newcommand{\NTasks}{%d}" % res["config"]["n_tasks"],
        r"\newcommand{\NSignals}{%d}" % res["config"]["n_signals"],
        r"\newcommand{\NAssets}{%d}" % res["config"]["n_assets"],
        r"\newcommand{\NTriples}{%s}" % f"{res['config']['kg_triples']:,}".replace(",", "\\,"),
        r"\newcommand{\NCases}{%d}" % res["e4_meta"]["n_cases"],
        r"\newcommand{\NFaulty}{%d}" % res["e4_meta"]["n_faulty"],
        r"\newcommand{\NHomographs}{%d}" % res["config"]["n_homographs"],
        r"\newcommand{\TokenBudget}{%d}" % res["config"]["token_budget"],
        r"\newcommand{\NFactKinds}{%d}" % len(C.FACT_KINDS),
        r"\newcommand{\NFamilies}{%d}" % len(V.FAULT_FAMILIES),
        r"\newcommand{\NCategories}{%d}" % len(TK.CATEGORIES),
    ]
    for r in res["e6_ceiling"]:
        macros.append(r"\newcommand{\Ceiling%s}{%.0f\%%}"
                      % (_alpha(r["condition"]), 100 * r["ceiling"]))
    for r in res["e4_tiers"]:
        macros.append(r"\newcommand{\Recall%s}{%.0f\%%}"
                      % (_alpha(r["tier"]), 100 * r["recall"]))
        macros.append(r"\newcommand{\FPR%s}{%.1f\%%}"
                      % (_alpha(r["tier"]), 100 * r["fp_rate"]))
    for r in res["e5_writes"]:
        macros.append(r"\newcommand{\ActPrec%s}{%.0f\%%}"
                      % (_alpha(r["tier"]), 100 * r["precision"]))
        macros.append(r"\newcommand{\ActRec%s}{%.0f\%%}"
                      % (_alpha(r["tier"]), 100 * r["recall"]))
    agg = defaultdict(list)
    for r in res["e1_grounding"]:
        agg[r["condition"]].append(r)
    for k, v in agg.items():
        macros.append(r"\newcommand{\GrndTopOne%s}{%.0f\%%}"
                      % (_alpha(k), 100 * sum(1 for x in v if x["top1"]) / len(v)))
    proc = {r["tier"]: r for r in res["e4b_procedural"]}
    if "GP" in proc:
        gp = proc["GP"]
        macros.append(r"\newcommand{\ProcRecall}{%.0f\%%}" % (100 * gp["recall"]))
        macros.append(r"\newcommand{\ProcFalseAlarms}{%d}" % gp["false_alarms"])
        macros.append(r"\newcommand{\ProcBehavCaught}{%d}" % gp["behavioural_caught"])
        macros.append(r"\newcommand{\ProcBehavN}{%d}" % gp["behavioural_n"])
        macros.append(r"\newcommand{\ProcUnitScale}{%d}" % gp["unitscale_caught"])
        macros.append(r"\newcommand{\GTwoFalseAlarms}{%d}" % proc["G2"]["false_alarms"])
    ratio = max(r["ratio_to_csv"] for r in res["e3_serialisation"])
    macros.append(r"\newcommand{\MaxSerialRatio}{%.0f}" % ratio)
    macros.append(r"\newcommand{\MaxQuerySaving}{%.0f}"
                  % max(p["reduction"] for p in res["e7_sparql"] if p["reduction"]))

    # --- E8: convention robustness ------------------------------------
    from . import experiments as EX

    by8 = {(r["scheme"], r["resolver"]): r for r in res["e8_convention"]}
    schemes = list(dict.fromkeys(r["scheme"] for r in res["e8_convention"]))
    for k, _c, _d in EX.RESOLVERS:
        vals = [by8[(s, k)]["top1"] for s in schemes]
        name = _alpha(k.replace("+", "Plus"))
        macros.append(r"\newcommand{\ConvSpread%s}{%.0f}" % (name, 100 * (max(vals) - min(vals))))
        macros.append(r"\newcommand{\ConvBest%s}{%.0f\%%}" % (name, 100 * max(vals)))
        macros.append(r"\newcommand{\ConvWorst%s}{%.0f\%%}" % (name, 100 * min(vals)))
    macros.append(r"\newcommand{\ConvMnemonicDecoded}{%.0f\%%}"
                  % (100 * by8[("mnemonic", "C1+conv")]["top1"]))
    macros.append(r"\newcommand{\ConvLyingDecoded}{%.0f\%%}"
                  % (100 * by8[("inconsistent", "C1+conv")]["top1"]))
    macros.append(r"\newcommand{\ConvLyingWrong}{%.0f\%%}"
                  % (100 * by8[("inconsistent", "C1+conv")]["confidently_wrong"]))
    macros.append(r"\newcommand{\NSchemes}{%d}" % len(schemes))

    # --- E9: intent routing -------------------------------------------
    budget = res["config"]["token_budget"]
    for r in res["e9_routing"]:
        if r["budget"] != budget:
            continue
        tag = _alpha(r["condition"]) + ("Routed" if r["routed"] else "Neigh")
        macros.append(r"\newcommand{\Route%sCeiling}{%.0f\%%}" % (tag, 100 * r["ceiling"]))
        macros.append(r"\newcommand{\Route%sVerif}{%.0f\%%}"
                      % (tag, 100 * r["verifiable_grounding"]))
        macros.append(r"\newcommand{\Route%sTokens}{%.0f}" % (tag, r["mean_tokens"]))
    verif = {r["condition"]: 0.0 for r in res["e9_routing"]}
    agg1 = defaultdict(list)
    for r in res["e1_grounding"]:
        agg1[r["condition"]].append(r)
    for k, v in agg1.items():
        macros.append(r"\newcommand{\Verif%s}{%.0f\%%}"
                      % (_alpha(k), 100 * sum(1 for x in v if x["verifiable"]) / len(v)))
    (paper / "generated_macros.tex").write_text("\n".join(macros) + "\n", encoding="utf-8")
