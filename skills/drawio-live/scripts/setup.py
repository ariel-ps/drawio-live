#!/usr/bin/env python3
"""Clone draw.io (if needed) and apply the live-control patch to App.js.

Usage: python3 setup.py [target_dir]
Default target_dir: ~/drawio-live-instance
Idempotent: safe to re-run; skips clone/patch steps already done.
"""
import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PATCH_FILE = os.path.join(SCRIPT_DIR, "app_js.patch")
REPO_URL = "https://github.com/jgraph/drawio.git"


def run(cmd, **kwargs):
    print("+", " ".join(cmd))
    return subprocess.run(cmd, check=True, **kwargs)


def main():
    target = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.expanduser("~/drawio-live-instance")
    app_js = os.path.join(target, "src/main/webapp/js/diagramly/App.js")

    if not os.path.isdir(target):
        run(["git", "clone", "--depth", "1", REPO_URL, target])
    else:
        print(f"{target} already exists, skipping clone")

    with open(app_js) as f:
        already_patched = "window.__drawioUi" in f.read()

    if already_patched:
        print("App.js already patched, skipping")
    else:
        run(["git", "apply", PATCH_FILE], cwd=target)
        print("applied app_js.patch")

    webapp_dir = os.path.join(target, "src/main/webapp")
    print()
    print("Setup complete. Start the server with:")
    print(f"  DRAWIO_WEBAPP_DIR={webapp_dir} python3 {os.path.join(SCRIPT_DIR, 'state_server.py')}")
    print("Then open http://127.0.0.1:8089/?dev=1 in a real browser (dev=1 is required for the patch to load).")


if __name__ == "__main__":
    main()
