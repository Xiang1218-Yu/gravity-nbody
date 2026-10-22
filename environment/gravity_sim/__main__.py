import argparse, json, sys
from .core import InputError, simulate

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    a = p.parse_args()
    try:
        with open(a.input, encoding="utf-8") as f:
            result = simulate(json.load(f))
        with open(a.output, "w", encoding="utf-8") as f:
            json.dump(result, f)
        return 0
    except Exception as exc:
        print(f"INPUT_ERROR: {exc}", file=sys.stderr)
        return 2
if __name__ == "__main__": raise SystemExit(main())
