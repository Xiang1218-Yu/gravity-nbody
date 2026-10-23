#!/bin/sh
set -u
TEST_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REWARD_FILE=${REWARD_FILE:-/logs/verifier/reward.txt}
REPORT_FILE=${REPORT_FILE:-/logs/verifier/scoring-report.json}
# score.py records status "INCOMPLETE" whenever the verifier report is absent, partial, or malformed.
mkdir -p "$(dirname -- "$REWARD_FILE")"
rm -f "$REWARD_FILE"
printf '0.000000\n' > "$REWARD_FILE"
TMP=$(mktemp -d)
DONE=0
cleanup() {
  STATUS=$?
  if [ "$DONE" -eq 0 ]; then
    printf '0.000000\n' > "$REWARD_FILE" 2>/dev/null || true
  fi
  rm -rf "$TMP"
  exit "$STATUS"
}
trap cleanup EXIT INT TERM HUP
export PROGRAM_DIR=${PROGRAM_DIR:-/app}
PYTHON_BIN=${PYTHON_BIN:-python3}
"$PYTHON_BIN" -m venv "$TMP/venv" >"$TMP/venv.stdout" 2>"$TMP/venv.stderr"
if [ "$?" -ne 0 ]; then
  cat "$TMP/venv.stderr" >&2
  exit 1
fi
"$TMP/venv/bin/python" -m pip install --no-index --find-links "$TEST_DIR/wheels" --require-hashes -r "$TEST_DIR/requirements-test.txt" >"$TMP/pip.stdout" 2>"$TMP/pip.stderr"
if [ "$?" -ne 0 ]; then
  cat "$TMP/pip.stderr" >&2
  exit 1
fi
# Outer timeout: alarm terminates the complete pytest subprocess tree rather than
# trusting individual tests.  The trap preserves the fail-closed reward on timeout.
TEST_TIMEOUT_SEC=${TEST_TIMEOUT_SEC:-300}
run_with_timeout() {
  perl -e 'alarm shift; exec @ARGV' "$TEST_TIMEOUT_SEC" "$@"
}
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  run_with_timeout "$TMP/venv/bin/python" -m pytest -p no:cacheprovider -vv \
  "$TEST_DIR/test_outputs.py" \
  --junitxml="$TMP/results.xml" \
  >"$TMP/stdout" 2>"$TMP/stderr"
RUNNER_STATUS=$?
set +e
"$TMP/venv/bin/python" "$TEST_DIR/score.py" \
  --results "$TMP/results.xml" \
  --scoring "$TEST_DIR/scoring.json" \
  --report-out "$REPORT_FILE" \
  --reward-out "$REWARD_FILE" \
  --runner-status "$RUNNER_STATUS" >"$TMP/scorer.stdout" 2>"$TMP/scorer.stderr"
SCORE_STATUS=$?
set -e
cat "$TMP/stdout"
cat "$TMP/stderr" >&2
cat "$TMP/scorer.stderr" >&2
if [ "$SCORE_STATUS" -ne 0 ]; then
  printf '0.000000\n' > "$REWARD_FILE"
  DONE=1
  exit 1
fi
if [ ! -s "$TMP/results.xml" ]; then
  printf '0.000000\n' > "$REWARD_FILE"
  DONE=1
  exit 1
fi
REWARD_VALUE=$(head -n 1 "$REWARD_FILE" 2>/dev/null || true)
if [ -z "$REWARD_VALUE" ]; then
  printf '0.000000\n' > "$REWARD_FILE"
  DONE=1
  exit 1
fi
chmod 0444 "$REWARD_FILE"
DONE=1
exit 0
