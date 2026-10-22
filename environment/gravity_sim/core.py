"""Starter implementation for the gravity simulation task."""
import json

class InputError(ValueError):
    pass

def simulate(req):
    # The starter deliberately handles only the simplest shape. Replace it with
    # a complete implementation satisfying instruction.md.
    if not isinstance(req, dict) or not isinstance(req.get("bodies"), list):
        raise InputError("bodies must be a list")
    return {"status": "ok", "time": 0.0, "bodies": req["bodies"], "mergers": [], "diagnostics": {}}
