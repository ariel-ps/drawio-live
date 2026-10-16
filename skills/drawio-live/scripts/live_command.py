#!/usr/bin/env python3
"""Send a single command to a running drawio-live relay and print the result.

Usage:
  python3 live_command.py '{"type":"insertVertex","value":"Hi","x":40,"y":40}'
  python3 live_command.py --relay http://127.0.0.1:9000 '{"type":"undo"}'
"""
import argparse
import json
import urllib.request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", help="JSON command body, e.g. '{\"type\":\"listActions\"}'")
    parser.add_argument("--relay", default="http://127.0.0.1:8089")
    args = parser.parse_args()

    data = args.command.encode("utf-8")
    json.loads(args.command)  # validate before sending
    req = urllib.request.Request(f"{args.relay}/api/command", data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        print(resp.read().decode("utf-8"))


if __name__ == "__main__":
    main()
