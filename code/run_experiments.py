"""Reproduce every number and figure in the paper.

    python run_experiments.py                # full run
    python run_experiments.py --dump-artifacts

Deterministic, offline, single-threaded. Runtime is dominated by the seven
SHACL validation passes and is well under a minute on a laptop.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from semantics_bench import experiments, kg, report

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--results", default=str(ROOT / "results"))
    ap.add_argument("--paper", default=str(ROOT / "paper"))
    ap.add_argument("--artifacts", default=str(ROOT / "artifacts"))
    ap.add_argument("--dump-artifacts", action="store_true",
                    help="also serialise the plant into every interchange format")
    args = ap.parse_args()

    t0 = time.perf_counter()
    if args.dump_artifacts:
        sizes = kg.serialise_all(args.artifacts)
        print("Serialised representations:")
        for name, n in sorted(sizes.items(), key=lambda kv: kv[1]):
            print(f"  {name:32s} {n:>9,d} bytes")

    print("\nRunning experiments E1-E9 ...")
    res = experiments.run_all(args.results)
    cfg = res["config"]
    print(f"  plant: {cfg['n_assets']} assets, {cfg['n_signals']} signals, "
          f"{cfg['kg_triples']:,} triples, {cfg['n_homographs']} homograph descriptions")
    print(f"  suite: {cfg['n_tasks']} tasks, {cfg['n_cases']} proposed agent actions")

    print("\nE1  grounding (top-1 accuracy)")
    from collections import defaultdict
    agg = defaultdict(list)
    for r in res["e1_grounding"]:
        agg[r["condition"]].append(r)
    for k in sorted(agg):
        v = agg[k]
        print(f"  {k}  acc@1={sum(x['top1'] for x in v)/len(v):.3f}  "
              f"verifiable@1={sum(x['verifiable'] for x in v)/len(v):.3f}  "
              f"MRR={sum(x['mrr'] for x in v)/len(v):.3f}  "
              f"distractors@5={sum(x['distractors_in_top5'] for x in v)}")

    print("\nE2/E6  context sufficiency and accuracy ceiling")
    for r in res["e6_ceiling"]:
        print(f"  {r['condition']}  ceiling={r['ceiling']:.3f}  "
              f"coverage={r['mean_coverage']:.3f}  tokens={r['mean_tokens']:.0f}  "
              f"cov/1k={r['coverage_per_1k_tokens']:.3f}")

    print("\nE3  serialisation cost of the whole plant")
    for r in res["e3_serialisation"]:
        print(f"  {r['format']:34s} {r['tokens']:>8,d} tokens  ({r['ratio_to_csv']:.1f}x CSV)")

    print("\nE4  guardrail efficacy")
    for r in res["e4_tiers"]:
        print(f"  {r['tier']}  recall={r['recall']:.3f}  diag={r['diagnosis_rate']:.3f}  "
              f"false alarms={r['false_alarms']} ({r['fp_rate']:.3f})")

    print("\nE5  admissible action space (write_setpoint)")
    for r in res["e5_writes"]:
        print(f"  {r['tier']}  |A|={r['size']:>7,d}  bits={r['bits']:5.2f}  "
              f"precision={r['precision']:.3f}  recall={r['recall']:.3f}")

    print("\nE7  query execution vs. context stuffing")
    for r in res["e7_sparql"]:
        red = f"{r['reduction']:.1f}x" if r["reduction"] else "n/a"
        print(f"  {r['task']:8s} query+answer={r['total_tokens']:>5,d} tokens  "
              f"vs stuffed C4={r['stuffing_tokens_C4']:>6,d}  saving={red}")

    print("\nE8  grounding vs. tag naming convention (top-1 / confidently wrong)")
    from semantics_bench.experiments import RESOLVERS
    resolvers = [k for k, _c, _d in RESOLVERS]
    by8 = {(r["scheme"], r["resolver"]): r for r in res["e8_convention"]}
    schemes = list(dict.fromkeys(r["scheme"] for r in res["e8_convention"]))
    print("  " + " " * 15 + "  ".join(f"{k:>12s}" for k in resolvers))
    for s in schemes:
        cells = "  ".join(f"{by8[(s, k)]['top1']:.2f}/{by8[(s, k)]['confidently_wrong']:.2f}"
                          .rjust(12) for k in resolvers)
        print(f"  {s:15s}{cells}")
    spread = "  ".join(
        f"{max(by8[(s, k)]['top1'] for s in schemes) - min(by8[(s, k)]['top1'] for s in schemes):.2f}"
        .rjust(12) for k in resolvers)
    print(f"  {'spread':15s}{spread}")

    print("\nE9  neighbourhood vs. intent-routed projection")
    for r in res["e9_routing"]:
        if r["budget"] != cfg["token_budget"]:
            continue
        print(f"  {r['condition']}  {'routed       ' if r['routed'] else 'neighbourhood'}  "
              f"ceiling={r['ceiling']:.3f}  coverage={r['coverage']:.3f}  "
              f"verifiable-grounding={r['verifiable_grounding']:.3f}  "
              f"tokens={r['mean_tokens']:.0f}")

    print("\nEmitting LaTeX tables, figures and macros ...")
    report.emit(Path(args.results) / "results.json", args.paper)
    print(f"Done in {time.perf_counter() - t0:.1f}s.")
    print(f"  results  -> {args.results}")
    print(f"  tables   -> {Path(args.paper) / 'tables'}")
    print(f"  figures  -> {Path(args.paper) / 'figures'}")


if __name__ == "__main__":
    main()
