#!/usr/bin/env python3
"""Lay out a graph (nodes+edges JSON) with drawio-skill's Graphviz engine,
then push the result into a live, already-open draw.io session via the
drawio-live command-relay API, and verify with a rendered-pixel overlap check.

This is the sibling-skill combination: drawio-skill's autolayout.py computes
clean non-overlapping positions from topology alone; drawio-live's relay API
pushes that result into a diagram a human may be actively looking at/editing,
and verifies the *actual rendered* result (edge routing, label sizing) rather
than just the declared XML geometry.

Usage: python3 live_layout.py graph.json [--relay http://127.0.0.1:8089]
                                          [--autolayout /path/to/autolayout.py]
                                          [--screenshot out.png]
"""
import argparse
import base64
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request

DEFAULT_RELAY = "http://127.0.0.1:8089"
SIBLING_AUTOLAYOUT_CANDIDATES = [
    os.path.expanduser("~/.claude/skills/drawio-skill/scripts/autolayout.py"),
    os.path.expanduser("~/src/drawio-skill/skills/drawio-skill/scripts/autolayout.py"),
]


def find_autolayout(explicit):
    if explicit:
        return explicit
    for candidate in SIBLING_AUTOLAYOUT_CANDIDATES:
        if os.path.isfile(candidate):
            return candidate
    raise SystemExit(
        "Could not find drawio-skill's autolayout.py. Install the sibling skill "
        "(https://github.com/Agents365-ai/drawio-skill) or pass --autolayout explicitly."
    )


def relay_command(relay, cmd):
    data = json.dumps(cmd).encode("utf-8")
    req = urllib.request.Request(f"{relay}/api/command", data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("graph_json", help="nodes+edges graph JSON (same schema as drawio-skill's autolayout.py)")
    parser.add_argument("--relay", default=DEFAULT_RELAY, help="drawio-live relay base URL")
    parser.add_argument("--autolayout", default=None, help="path to drawio-skill's autolayout.py (auto-detected if omitted)")
    parser.add_argument("--screenshot", default=None, help="also export a PNG of the result to this path")
    parser.add_argument("--new-page", action="store_true",
                         help="insert a new page first instead of replacing the current one "
                              "(required for safe concurrent use against a shared live session)")
    parser.add_argument("--timing", action="store_true", help="print a stage-by-stage timing breakdown to stderr")
    args = parser.parse_args()

    t0 = time.monotonic()
    autolayout_script = find_autolayout(args.autolayout)

    with tempfile.NamedTemporaryFile(suffix=".drawio", delete=False) as tmp:
        laid_out_path = tmp.name

    subprocess.run(
        [sys.executable, autolayout_script, "--tune", "-o", laid_out_path, args.graph_json],
        check=True,
    )
    t1 = time.monotonic()

    with open(laid_out_path) as f:
        content = f.read()
    os.unlink(laid_out_path)

    match = re.search(r"(<mxGraphModel.*</mxGraphModel>)", content, re.S)
    if not match:
        raise SystemExit("autolayout.py output did not contain an <mxGraphModel> element")
    model_xml = match.group(1)

    # Everything that touches the shared live document is sent as ONE batch
    # call. The relay serializes whole commands (never mid-command), so a
    # single batch is atomic with respect to other concurrent callers; separate
    # load/checkOverlaps calls are NOT, and can interleave with another
    # process's commands against the same live session.
    batch = []
    if args.new_page:
        batch.append({"type": "action", "name": "insertPage"})
    batch.append({"type": "load", "xml": model_xml})
    batch.append({"type": "checkOverlaps"})
    if args.screenshot:
        batch.append({"type": "exportPng"})

    result = relay_command(args.relay, {"type": "batch", "commands": batch})
    t2 = time.monotonic()
    if not result.get("ok"):
        raise SystemExit(f"batch failed: {result.get('error')}")

    if args.timing:
        print(f"timing: autolayout subprocess={t1 - t0:.3f}s relay batch={t2 - t1:.3f}s total={t2 - t0:.3f}s", file=sys.stderr)

    steps = result["result"]
    load_result = steps[1] if args.new_page else steps[0]
    if not load_result.get("ok"):
        raise SystemExit(f"load failed: {load_result.get('error')}")

    overlaps_result = steps[2] if args.new_page else steps[1]
    overlap_count = len(overlaps_result.get("result", []))
    print(f"loaded into live session; checkOverlaps reports {overlap_count} raw overlaps")

    if args.screenshot:
        png_result = steps[-1]
        header, b64 = png_result["result"].split(",", 1)
        with open(args.screenshot, "wb") as f:
            f.write(base64.b64decode(b64))
        print(f"screenshot saved to {args.screenshot}")


if __name__ == "__main__":
    main()
