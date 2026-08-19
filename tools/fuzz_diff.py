#!/usr/bin/env python3
"""Differential fuzzer: generates random ELK graphs, lays each out with both
the real Java ELK oracle and elkrs's own Rust CLI, and reports any
divergence.

Usage:
    python tools/fuzz_diff.py [N] --seed S [--tol T] [--algorithm A] [--keep-going]

Mirrors the shape of the (lost) original tool referenced in elkrs's README:
`tools/fuzz_diff.py [N] --seed S --algorithm A`. `--algorithm` accepts any of
elkrs's 12 algorithm ids (`layered`, `force`, `stress`, `radial`, `mrtree`,
`rectpacking`, `sporeOverlap`, `sporeCompaction`, `disco`, `topdownpacking`,
`fixed`, `box`, `random`) or `all` (default) to pick one at random each
iteration. Reuses the same shape generators as tools/gen_goldens.py (broader
random parameter ranges, not the curated corpus), so the algorithm-specific
gotchas documented in oracle/README.md (seeded `random`, positioned `spore`,
disconnected `disco`, tree-shaped `radial`/`mrtree`) are already handled.

Requires a project-local JDK 17 + Maven on PATH (or set JAVA_HOME / MVN_CMD),
and a release build of elkrs (`cargo build --release`).
"""
import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ORACLE_POM = ROOT / "oracle" / "pom.xml"

sys.path.insert(0, str(ROOT / "tools"))
from gen_goldens import CATEGORIES  # noqa: E402

# elkrs algorithm id -> gen_goldens.py category keys that exercise it.
ALGORITHM_CATEGORIES = {
    "layered": ["chain", "dag", "cycle", "direction", "labels_up", "compound_nested"],
    "fixed": ["fixed"],
    "box": ["box"],
    "random": ["random"],
    "force": ["force"],
    "stress": ["stress"],
    "radial": ["radial"],
    "mrtree": ["mrtree"],
    "rectpacking": ["rectpacking"],
    "topdownpacking": ["topdownpacking"],
    "sporeOverlap": ["sporeoverlap"],
    "sporeCompaction": ["sporecompaction"],
    "disco": ["disco"],
}


def gen_fuzz_case(rng, idx, algorithm):
    """Picks a shape generator for `algorithm` (or a random algorithm, if
    `algorithm` is "all") and calls it — same generators as the curated
    corpus, just with fresh random content each call."""
    algo = algorithm if algorithm != "all" else rng.choice(list(ALGORITHM_CATEGORIES))
    category = rng.choice(ALGORITHM_CATEGORIES[algo])
    _, g = CATEGORIES[category](rng, idx)
    return f"fuzz_{idx:05d}_{category}", g


def find_mvn():
    env_cmd = os.environ.get("MVN_CMD")
    if env_cmd:
        return env_cmd
    found = shutil.which("mvn") or shutil.which("mvn.cmd")
    if found:
        return found
    vendored = ROOT.parent.parent / "layout-kernel" / "elk-rust" / "vendor" / "apache-maven" / "apache-maven-3.9.9" / "bin" / "mvn.cmd"
    if vendored.exists():
        return str(vendored)
    raise SystemExit("Maven not found: set MVN_CMD or put mvn on PATH")


def find_java_home():
    env = os.environ.get("JAVA_HOME")
    if env:
        return env
    vendored = ROOT.parent.parent / "layout-kernel" / "elk-rust" / "vendor" / "jdks" / "jdk-17"
    if vendored.exists():
        return str(vendored)
    return None


def run_oracle_batch(cases_dir, out_dir):
    mvn = find_mvn()
    env = os.environ.copy()
    java_home = find_java_home()
    if java_home:
        env["JAVA_HOME"] = java_home
        env["PATH"] = str(Path(java_home) / "bin") + os.pathsep + env.get("PATH", "")
    args = [mvn, "-q", "--batch-mode", "-f", str(ORACLE_POM), "exec:java",
            f"-Dexec.args=--batch {cases_dir} {out_dir}"]
    proc = subprocess.run(args, env=env, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        raise SystemExit(f"oracle batch failed (exit {proc.returncode})")


def run_rust(elkrs_bin, case_path):
    proc = subprocess.run([str(elkrs_bin), str(case_path)], capture_output=True, text=True)
    if proc.returncode != 0:
        return None, proc.stderr
    return proc.stdout, None


NUMERIC_KEYS = {"x", "y", "width", "height"}


def diff(a, b, path, diffs, tol):
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a:
                diffs.append(f"{path}/{k}: missing in oracle")
            elif k not in b:
                diffs.append(f"{path}/{k}: missing in rust")
            elif k in NUMERIC_KEYS and isinstance(a[k], (int, float)) and isinstance(b[k], (int, float)):
                if abs(a[k] - b[k]) > tol:
                    diffs.append(f"{path}/{k}: oracle={a[k]} rust={b[k]}")
            else:
                diff(a[k], b[k], f"{path}/{k}", diffs, tol)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            diffs.append(f"{path}: length {len(a)} != {len(b)}")
        for i, (ai, bi) in enumerate(zip(a, b)):
            diff(ai, bi, f"{path}[{i}]", diffs, tol)
    else:
        if a != b:
            diffs.append(f"{path}: oracle={a!r} rust={b!r}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("count", type=int, nargs="?", default=100)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--tol", type=float, default=1e-9)
    ap.add_argument("--algorithm", default="all",
                     choices=list(ALGORITHM_CATEGORIES) + ["all"],
                     help="elkrs algorithm id to fuzz, or 'all' (default) to pick one at random per case")
    ap.add_argument("--elkrs-bin", type=Path,
                     default=ROOT / "target" / "release" / "elkrs.exe")
    ap.add_argument("--keep-going", action="store_true",
                     help="don't stop at the first divergence")
    ap.add_argument("--save-dir", type=Path, default=None,
                     help="copy diverging cases here instead of a temp dir")
    args = ap.parse_args()

    if not args.elkrs_bin.exists():
        raise SystemExit(f"elkrs binary not found at {args.elkrs_bin}; run `cargo build --release`")

    rng = random.Random(args.seed)
    with tempfile.TemporaryDirectory(prefix="elkrs_fuzz_") as tmp:
        tmp = Path(tmp)
        cases_dir = tmp / "cases"
        expected_dir = tmp / "expected"
        cases_dir.mkdir()

        names = []
        for i in range(args.count):
            name, g = gen_fuzz_case(rng, i, args.algorithm)
            (cases_dir / f"{name}.json").write_text(json.dumps(g), encoding="utf-8")
            names.append(name)

        print(f"generated {len(names)} cases, running oracle...", file=sys.stderr)
        run_oracle_batch(cases_dir, expected_dir)

        divergences = 0
        errors = 0
        for name in names:
            case_path = cases_dir / f"{name}.json"
            expected_path = expected_dir / f"{name}.json"
            if not expected_path.exists():
                errors += 1
                print(f"{name}: oracle produced no output", file=sys.stderr)
                continue
            rust_out, err = run_rust(args.elkrs_bin, case_path)
            if err is not None:
                errors += 1
                print(f"{name}: rust error: {err.strip()}", file=sys.stderr)
                if not args.keep_going:
                    break
                continue
            expected = json.loads(expected_path.read_text(encoding="utf-8-sig"))
            actual = json.loads(rust_out)
            diffs = []
            diff(expected, actual, "", diffs, args.tol)
            if diffs:
                divergences += 1
                print(f"{name}: {len(diffs)} diffs", file=sys.stderr)
                for d in diffs[:8]:
                    print(f"  {d}", file=sys.stderr)
                if args.save_dir:
                    args.save_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copy(case_path, args.save_dir / f"{name}.json")
                    shutil.copy(expected_path, args.save_dir / f"{name}.expected.json")
                if not args.keep_going:
                    break

        total = len(names)
        print(f"\n{total} cases, {divergences} diverging, {errors} errors "
              f"({total - divergences - errors} bit-identical)")
        sys.exit(1 if (divergences or errors) else 0)


if __name__ == "__main__":
    main()
