#!/usr/bin/env python3
"""Exact numeric diff between two ELK graph JSON files (e.g. oracle vs rust
output). Usage: python tools/compare_layouts.py oracle.json rust.json [tol]
"""
import json
import sys

NUMERIC_KEYS = {"x", "y", "width", "height"}


def load(path):
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def walk(a, b, path, diffs, tol):
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a:
                diffs.append(f"{path}/{k}: missing in first file")
            elif k not in b:
                diffs.append(f"{path}/{k}: missing in second file")
            elif k in NUMERIC_KEYS and isinstance(a[k], (int, float)) and isinstance(b[k], (int, float)):
                if abs(a[k] - b[k]) > tol:
                    diffs.append(f"{path}/{k}: {a[k]} != {b[k]} (delta={a[k]-b[k]})")
            else:
                walk(a[k], b[k], f"{path}/{k}", diffs, tol)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            diffs.append(f"{path}: length {len(a)} != {len(b)}")
        for i, (ai, bi) in enumerate(zip(a, b)):
            walk(ai, bi, f"{path}[{i}]", diffs, tol)
    else:
        if a != b:
            diffs.append(f"{path}: {a!r} != {b!r}")


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    tol = float(sys.argv[3]) if len(sys.argv) > 3 else 1e-9
    a, b = load(sys.argv[1]), load(sys.argv[2])
    diffs = []
    walk(a, b, "", diffs, tol)
    if not diffs:
        print(f"MATCH (tol={tol})")
        sys.exit(0)
    print(f"{len(diffs)} DIFFERENCES (tol={tol}):")
    for d in diffs:
        print(" ", d)
    sys.exit(1)


if __name__ == "__main__":
    main()
