#!/usr/bin/env python
"""E11: real-model sanity check --- *not* part of the deterministic pipeline.

The headline results in this paper are model-free: they measure representation
ceilings and validator properties that bound what *any* reader can do
(``run_experiments.py``, offline and deterministic). This script is the optional
corroboration a reviewer asks for: it runs the task suite through a real language
model across the five context conditions and checks that measured accuracy
*tracks* the ceiling and never exceeds it.

It is deliberately separate from ``run_experiments.py`` because a hosted model is
non-deterministic and time-varying. Its output is therefore a frozen, timestamped
artefact (``results/e11_<model>_<date>.json``) that records the model, the date
and every raw answer, and is cited in the paper as a dated measurement rather than
a regenerated number.

Secrets: the API key is read only from the environment (or a git-ignored
``code/.env``). Never pass it on the command line and never commit it.

    # mock (no network, reproduces the ceiling) --- use this to dry-run:
    python run_e11.py --backend mock --limit 5

    # Azure OpenAI (key in code/.env or the environment):
    #   AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_DEPLOYMENT,
    #   AZURE_OPENAI_API_VERSION, AZURE_OPENAI_API_KEY
    python run_e11.py --backend azure --repeats 3
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
from collections import defaultdict
from pathlib import Path

from semantics_bench import conditions as C
from semantics_bench import llm
from semantics_bench import tasks as TK

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

_NUM = re.compile(r"-?\d+(?:\.\d+)?")
_ID = re.compile(r"[A-Z]{1,3}\d?[-_][A-Z0-9][A-Z0-9_\-]*")
GRADER = "heuristic-v1"


def _nums(s: str) -> list[float]:
    return [float(x) for x in _NUM.findall(s.replace(",", ""))]


def grade(answer: str, gold: str) -> str:
    """Heuristic grade of a free-text answer against the gold string.

    Returns correct | incorrect | partial | refused | error | unknown. Grades are
    approximate by design; the raw answers are saved so every grade is auditable.
    """
    a = (answer or "").strip()
    al = a.lower()
    if al.startswith("insufficient"):
        return "refused"
    if al.startswith("error:"):
        return "error"
    if not a:
        return "error"
    gl = gold.strip().lower()
    head = re.split(r"[\s\-]", gl, maxsplit=1)[0].strip(" .,:;") if gl else ""

    # 1. yes / no / none polarity (the dominant answer shape). Decide from the
    # FIRST polarity token, so a "not"/"none" inside the rationale of a "Yes ..."
    # answer does not flip it.
    if head in ("yes", "no", "none"):
        want = "yes" if head == "yes" else "no"
        yes_words = {"yes", "yeah", "yep", "affirmative", "correct", "allowed",
                     "permitted", "legal", "safe"}
        no_words = {"no", "none", "nope", "not", "never", "cannot", "illegal",
                    "forbidden", "unsafe", "nothing"}
        toks = re.findall(r"[a-z']+", al)
        got = "unknown"
        if toks and toks[0] in yes_words:
            got = "yes"
        elif toks and toks[0] in no_words:
            got = "no"
        else:
            for w in toks[:12]:
                if w in yes_words:
                    got = "yes"
                    break
                if w in no_words:
                    got = "no"
                    break
        return "correct" if got == want else "incorrect"

    # 2. id / list gold (tags and asset ids)
    ids = [i for i in _ID.findall(gold)]
    if ids:
        au = a.upper()
        hit = sum(1 for i in ids if i in au)
        return "correct" if hit == len(ids) else ("partial" if hit else "incorrect")

    # 3. numeric + unit gold
    g_nums = _nums(gold)
    if g_nums and re.match(r"^\s*[-\d]", gold):
        target = g_nums[0]
        num_ok = any(abs(x - target) <= max(0.02 * abs(target), 0.05)
                     for x in _nums(a))
        unit_m = re.search(r"[-\d.]+\s*([A-Za-z%°/]+)", gold)
        unit_ok = (unit_m.group(1).lower() in al) if unit_m else True
        return "correct" if (num_ok and unit_ok) else "incorrect"

    # 4. fallback: content-word overlap
    gw = {w for w in re.findall(r"[a-z0-9]+", gl) if len(w) > 3}
    if not gw:
        return "unknown"
    hit = sum(1 for w in gw if w in al)
    return "correct" if hit / len(gw) >= 0.6 else "incorrect"


def load_ceilings() -> dict[str, float]:
    p = ROOT / "results" / "results.json"
    if not p.exists():
        return {}
    res = json.loads(p.read_text(encoding="utf-8"))
    return {r["condition"]: r["ceiling"] for r in res.get("e6_ceiling", [])}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--backend", default=None,
                    help="mock | azure | openai | ollama (else $SEMBENCH_BACKEND)")
    ap.add_argument("--conditions", default="C0,C1,C2,C3,C4")
    ap.add_argument("--budget", type=int, default=6000)
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--limit", type=int, default=0, help="first N tasks only (0 = all)")
    ap.add_argument("--out", default=str(ROOT / "results"))
    args = ap.parse_args()

    llm.load_dotenv()
    import os
    if args.backend:
        os.environ["SEMBENCH_BACKEND"] = args.backend
    backend = llm.get_backend()
    model = getattr(backend, "model", backend.name)

    conds = [C.BY_KEY[k] for k in args.conditions.split(",")]
    all_tasks = list(TK.TASKS)
    tasks = all_tasks[: args.limit] if args.limit else all_tasks
    ceilings = load_ceilings()

    print(f"E11 sanity check | backend={backend.name} model={model} "
          f"| {len(tasks)} tasks x {len(conds)} conditions x {args.repeats} "
          f"repeat(s) | budget={args.budget}")
    if backend.name != "mock":
        print("  (live API calls --- this spends tokens on your account)")

    rows: list[dict] = []
    for cond in conds:
        for task in tasks:
            prompt, facts, tokens = llm.build_prompt(task, cond, args.budget)
            sufficient = not (set(task.required) - facts)
            for rep in range(args.repeats):
                if isinstance(backend, llm.MockBackend):
                    backend.bind(task, facts)
                answer = backend.complete(llm.SYSTEM_PROMPT, prompt)
                g = grade(answer, task.gold_answer)
                rows.append({
                    "condition": cond.key, "task": task.tid,
                    "category": task.category, "repeat": rep,
                    "tokens": tokens, "sufficient": sufficient,
                    "grade": g, "refused": g == "refused",
                    "answer": answer.strip()[:500], "gold": task.gold_answer,
                })

    # ---- aggregates --------------------------------------------------------
    per_condition = []
    for cond in conds:
        sub = [r for r in rows if r["condition"] == cond.key]
        n = len(sub)
        correct = sum(1 for r in sub if r["grade"] == "correct")
        refused = sum(1 for r in sub if r["grade"] == "refused")
        suff = [r for r in sub if r["sufficient"]]
        insuff = [r for r in sub if not r["sufficient"]]
        halluc = sum(1 for r in insuff if r["grade"] not in ("refused", "correct"))
        per_condition.append({
            "condition": cond.key, "n": n,
            "accuracy": correct / n if n else 0.0,
            "refusal_rate": refused / n if n else 0.0,
            "correct_when_sufficient": (sum(1 for r in suff if r["grade"] == "correct")
                                        / len(suff)) if suff else None,
            "hallucination_rate_when_insufficient": (halluc / len(insuff))
            if insuff else None,
            "ceiling": ceilings.get(cond.key),
        })

    per_category: dict[str, dict[str, float]] = {}
    for cond in conds:
        for cat in TK.CATEGORIES:
            sub = [r for r in rows if r["condition"] == cond.key
                   and r["category"] == cat]
            if sub:
                per_category.setdefault(cat, {})[cond.key] = (
                    sum(1 for r in sub if r["grade"] == "correct") / len(sub))

    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M")
    safe_model = re.sub(r"[^A-Za-z0-9._-]", "_", str(model))
    out = {
        "meta": {
            "experiment": "E11 real-model sanity check",
            "backend": backend.name, "model": model,
            "timestamp": _dt.datetime.now().isoformat(timespec="seconds"),
            "budget": args.budget, "repeats": args.repeats,
            "conditions": [c.key for c in conds], "n_tasks": len(tasks),
            "grader": GRADER,
            "note": "Not regenerated by run_experiments.py; a dated measurement.",
        },
        "per_condition": per_condition,
        "per_category": per_category,
        "rows": rows,
    }
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    outfile = outdir / f"e11_{backend.name.replace(':', '_')}_{safe_model}_{stamp}.json"
    outfile.write_text(json.dumps(out, indent=2), encoding="utf-8")

    # ---- console summary ---------------------------------------------------
    print("\n  cond   acc   ceiling  refuse  halluc(insuff)  acc|suff")
    for r in per_condition:
        def _f(x):
            return "  -  " if x is None else f"{x:.2f}"
        print(f"  {r['condition']:4s}  {r['accuracy']:.2f}   "
              f"{_f(r['ceiling'])}    {r['refusal_rate']:.2f}     "
              f"{_f(r['hallucination_rate_when_insufficient'])}         "
              f"{_f(r['correct_when_sufficient'])}")
    print(f"\n  grades are {GRADER} (approximate); raw answers saved for audit")
    print(f"  -> {outfile}")


if __name__ == "__main__":
    main()
