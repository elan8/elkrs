#!/usr/bin/env sh
# Regenerates goldens/cases (random corpus) and goldens/expected (real ELK
# 0.11.0 oracle output for each case), per tests/goldens.rs.
#
# Requires JDK 17 + Maven. Set JAVA_HOME / MVN_CMD, or vendor them via
# ../../layout-kernel/elk-rust/scripts/bootstrap-jdk17.ps1 and
# bootstrap-maven.ps1 (this script will pick those up automatically).

set -eu

SCRIPT_ROOT=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
ROOT=$(CDPATH= cd -- "$SCRIPT_ROOT/.." && pwd)
POM="$ROOT/oracle/pom.xml"
CASES_DIR="$ROOT/goldens/cases"
EXPECTED_DIR="$ROOT/goldens/expected"

SEED=${SEED:-42}
N_PER_CATEGORY=${N_PER_CATEGORY:-8}

if [ -n "${JAVA_HOME:-}" ]; then
  export PATH="$JAVA_HOME/bin:$PATH"
fi
if ! command -v java >/dev/null 2>&1; then
  echo "Java not found; set JAVA_HOME" >&2
  exit 1
fi

if [ -n "${MVN_CMD:-}" ]; then
  : # use as-is
elif command -v mvn >/dev/null 2>&1; then
  MVN_CMD=mvn
else
  VENDORED="$ROOT/../../layout-kernel/elk-rust/vendor/apache-maven/apache-maven-3.9.9/bin/mvn"
  if [ -x "$VENDORED" ] || [ -x "$VENDORED.cmd" ]; then
    MVN_CMD="$VENDORED"
  else
    echo "Maven not found; set MVN_CMD" >&2
    exit 1
  fi
fi

echo "Generating case corpus (seed=$SEED)..." >&2
python3 "$SCRIPT_ROOT/gen_goldens.py" --seed "$SEED" --n-per-category "$N_PER_CATEGORY" --out "$CASES_DIR"

echo "Building oracle..." >&2
"$MVN_CMD" -q --batch-mode -f "$POM" compile

echo "Running oracle over $(ls "$CASES_DIR"/*.json | wc -l) cases..." >&2
"$MVN_CMD" -q --batch-mode -f "$POM" exec:java "-Dexec.args=--batch $CASES_DIR $EXPECTED_DIR"

echo "Done. Run 'cargo test --test goldens' to check elkrs against the regenerated oracle output." >&2
