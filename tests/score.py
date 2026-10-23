#!/usr/bin/env python3
"""Convert a complete pytest JUnit report into a deterministic weighted reward."""
from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", required=True)
    parser.add_argument("--scoring", required=True)
    parser.add_argument("--report-out", required=True)
    parser.add_argument("--reward-out", required=True)
    parser.add_argument("--runner-status", required=True, type=int)
    args = parser.parse_args()

    report_path = Path(args.report_out)
    reward_path = Path(args.reward_out)
    report = {"status": "INCOMPLETE", "reward": 0.0, "gate_passed": False, "tests": {}}
    try:
        scoring = json.loads(Path(args.scoring).read_text(encoding="utf-8"))
        weights = scoring["tests"]
        if not isinstance(weights, dict) or not weights:
            raise ValueError("tests must be a non-empty object")
        configured_total = sum(weights.values())
        if abs(configured_total - 1.0) > 1e-9:
            raise ValueError(f"weights total {configured_total!r} is not 1.0")
        root = ET.parse(args.results).getroot()
        cases = root.findall(".//testcase")
        seen = []
        passed = []
        for case in cases:
            name = case.attrib.get("name", "")
            seen.append(name)
            if case.find("failure") is None and case.find("error") is None and case.find("skipped") is None:
                passed.append(name)
        configured = set(weights)
        actual = set(seen)
        complete = len(seen) == len(actual) == len(configured) and actual == configured
        if not complete:
            report["status"] = "INCOMPLETE"
            report["reason"] = "JUnit test set does not match scoring.json"
            report["tests"] = {name: ("PASS" if name in passed else "NOT_PASS") for name in sorted(actual)}
        else:
            gate_passed = args.runner_status == 0 and all(name in passed for name in configured)
            # Fail closed: any failed/errored test, partial run, or non-zero runner
            # status yields zero reward.  Partial credit would let a shortcut that
            # only implements free drift collect points for a non-solution.
            reward = 1.0 if gate_passed else 0.0
            report = {
                "status": "COMPLETED",
                "reward": round(reward, 6),
                "gate_passed": gate_passed,
                "tests": {name: ("PASS" if name in passed else "NOT_PASS") for name in sorted(actual)},
                "runner_status": args.runner_status,
            }
    except Exception as exc:
        report = {"status": "INCOMPLETE", "reward": 0.0, "gate_passed": False, "reason": str(exc), "tests": {}}

    report_path.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    reward_path.write_text(f"{float(report['reward']):.6f}\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
