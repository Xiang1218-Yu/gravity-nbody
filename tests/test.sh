#!/bin/sh
set -u
# Harbor uploads this directory to /tests and runs /tests/test.sh.  The
# submitted program is in /app, so do not infer a task-package root from $0.
TEST_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# Harbor collects the verifier reward only from this mounted path. Keep the
# override for author-side runs, where /logs may not be available.
REWARD_FILE=${REWARD_FILE:-/logs/verifier/reward.txt}
mkdir -p "$(dirname -- "$REWARD_FILE")"
printf '0.000000\n' > "$REWARD_FILE"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
export PROGRAM_DIR=${PROGRAM_DIR:-/app}
python3 -m venv "$TMP/venv" >"$TMP/venv.stdout" 2>"$TMP/venv.stderr"
venv_status=$?
if [ "$venv_status" -ne 0 ]; then
  cat "$TMP/venv.stdout"
  cat "$TMP/venv.stderr" >&2
  exit "$venv_status"
fi
"$TMP/venv/bin/python" -m pip install --no-index --find-links "$TEST_DIR/wheels" --require-hashes -r "$TEST_DIR/requirements-test.txt" >"$TMP/pip.stdout" 2>"$TMP/pip.stderr"
pip_status=$?
if [ "$pip_status" -ne 0 ]; then
  cat "$TMP/pip.stdout"
  cat "$TMP/pip.stderr" >&2
  exit "$pip_status"
fi
set +e
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 "$TMP/venv/bin/python" -m pytest -p no:cacheprovider -q "$TEST_DIR/test_gravity.py" --junitxml="$TMP/results.xml" >"$TMP/stdout" 2>"$TMP/stderr"
status=$?
set -e
python3 - "$TMP/results.xml" "$REWARD_FILE" <<'PY'
import sys, xml.etree.ElementTree as ET
weights = {
'test_free_drift_and_time_grid':0.05,
'test_pairwise_acceleration_direction_and_softening_power':0.13,
'test_velocity_verlet_uses_new_acceleration':0.10,
'test_diagnostics_pair_once_and_momentum':0.10,
'test_single_collision_conserves_mass_momentum_and_com':0.15,
'test_chain_contact_is_one_simultaneous_component':0.10,
'test_permutation_invariance_of_merger_and_output_order':0.07,
'test_invalid_structure_and_boolean_numbers_are_rejected':0.08,
'test_invalid_ranges_and_nonfinite_values_preserve_output':0.08,
'test_zero_softening_coincident_initial_pair_is_rejected':0.05,
'test_atomic_success_leaves_no_temp_files':0.04,
'test_output_schema_is_complete_and_deterministic':0.05,
}
score = 0.0
seen = set()
cases = []
try:
    root = ET.parse(sys.argv[1]).getroot()
    seen = set()
    for case in root.findall('.//testcase'):
        name = case.attrib.get('name','')
        seen.add(name)
        cases.append(name)
        if case.find('failure') is None and case.find('error') is None and case.find('skipped') is None:
            score += weights.get(name, 0.0)
except Exception:
    score = 0.0
if seen != set(weights) or len(cases) != len(weights): score = 0.0
with open(sys.argv[2], 'w', encoding='utf-8') as f: f.write(f'{score:.6f}\n')
PY
cat "$TMP/stdout"
cat "$TMP/stderr" >&2
exit "$status"
