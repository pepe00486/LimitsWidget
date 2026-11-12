#!/usr/bin/env python3
"""A local Codex protocol fixture. It never uses credentials or the network."""

import json
import os
from pathlib import Path
import sys


def main():
    scenario = os.environ.get("WIDGET_TEST_SCENARIO", "normal")
    initialized = False
    reads = 0
    for line in sys.stdin:
        request = json.loads(line)
        method = request["method"]
        if method == "initialize":
            result = {}
        elif method == "initialized":
            initialized = True
            continue
        elif not initialized:
            raise RuntimeError("The client must complete initialization first.")
        elif method == "account/read":
            account = None if scenario == "signed-out" else {"type": "chatgpt"}
            result = {"account": account}
        elif method == "account/rateLimits/read":
            if scenario == "timeout":
                marker = Path(os.environ["WIDGET_TEST_MARKER"])
                if not marker.exists():
                    marker.touch()
                    continue
            if scenario == "malformed":
                print("invalid json", flush=True)
                continue
            reads += 1
            result = {"rateLimits": {
                "primary": {"usedPercent": 22 + reads, "windowDurationMins": 300},
                "secondary": {"usedPercent": 47 + reads, "windowDurationMins": 10080},
            }}
        else:
            raise RuntimeError(f"Unexpected method: {method}")
        print(json.dumps({"id": request["id"], "result": result}), flush=True)


if __name__ == "__main__":
    main()
