"""Create isolated KUKA/IIH NodeSet provenance and projection artifacts.

This is an offline transformation. It does not connect to OPC UA or modify
the original generated bottling-plant benchmark.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from semantics_bench.nodeset_case import write_case

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instance", type=Path, required=True,
                        help="KUKA raw instance NodeSet exported from IIH")
    parser.add_argument("--robotics", type=Path, required=True,
                        help="OPC UA Robotics companion-model NodeSet")
    parser.add_argument("--di", type=Path, required=True,
                        help="OPC UA DI companion-model NodeSet")
    parser.add_argument("--out", type=Path, default=ROOT / "paper_revision" / "adhoc_kuka")
    args = parser.parse_args()
    result = write_case(args.instance, args.robotics, args.di, args.out)
    print(json.dumps(result["comparison"], indent=2))
    print(f"\nProjections written to: {args.out.resolve()}")
    print("No network connection or live-server validation was performed.")


if __name__ == "__main__":
    main()