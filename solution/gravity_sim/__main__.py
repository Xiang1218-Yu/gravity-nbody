from __future__ import annotations
import argparse, json, os, sys, tempfile
from .core import InputError, simulate

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    try:
        with open(args.input, encoding="utf-8") as f:
            req = json.load(f)
        result = simulate(req)
        parent = os.path.dirname(os.path.abspath(args.output)) or "."
        fd, tmp = tempfile.mkstemp(prefix=".gravity-", suffix=".tmp", dir=parent, text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(result, f, sort_keys=True, separators=(",", ":"))
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, args.output)
        finally:
            if os.path.exists(tmp): os.unlink(tmp)
        return 0
    except (OSError, ValueError, InputError, json.JSONDecodeError) as exc:
        print(f"INPUT_ERROR: {exc}", file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
