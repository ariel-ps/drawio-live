#!/usr/bin/env python3
"""One-click setup and launch for drawio-live.

Clones draw.io (if needed), applies the live-control patch to App.js, starts
the relay server in the background, and opens the patched editor in your
browser - all in one command.

Usage: python3 setup.py [target_dir] [--no-run] [--port 8089]
Default target_dir: ~/drawio-live-instance
Idempotent: safe to re-run; skips clone/patch steps already done, and reuses
an already-running server on the target port instead of starting a second one.

--no-run: just clone+patch, print the manual start command, don't launch anything.
"""
import argparse
import os
import platform
import subprocess
import sys
import time
import urllib.request

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PATCH_FILE = os.path.join(SCRIPT_DIR, "app_js.patch")
STATE_SERVER = os.path.join(SCRIPT_DIR, "state_server.py")
REPO_URL = "https://github.com/jgraph/drawio.git"


def run(cmd, **kwargs):
    print("+", " ".join(cmd))
    return subprocess.run(cmd, check=True, **kwargs)


def server_already_running(port):
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/index.html", timeout=1)
        return True
    except Exception:
        return False


def open_browser(url):
    """Launch the OS default browser with fully suppressed stdio, so a
    failing browser (e.g. Chrome's Linux sandbox needing unprivileged user
    namespaces - common in containers/VMs/hardened kernels, exit EPERM) can't
    dump noise into this script's output and make a successful setup look
    like it crashed. The server is already up regardless of whether this
    succeeds - see the fallback message printed unconditionally below.
    """
    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.Popen(["open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        elif system == "Windows":
            os.startfile(url)  # noqa: no subprocess/stdio involved on Windows
        else:
            subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        return True
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("target_dir", nargs="?", default=os.path.expanduser("~/drawio-live-instance"))
    parser.add_argument("--no-run", action="store_true", help="only clone+patch, don't start the server or open a browser")
    parser.add_argument("--port", type=int, default=8089)
    args = parser.parse_args()

    target = os.path.abspath(args.target_dir)
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

    if args.no_run:
        print()
        print("Setup complete. Start the server with:")
        print(f"  DRAWIO_WEBAPP_DIR={webapp_dir} python3 {STATE_SERVER}")
        print(f"Then open http://127.0.0.1:{args.port}/?dev=1 in a real browser (dev=1 is required for the patch to load).")
        return

    url = f"http://127.0.0.1:{args.port}/?dev=1"

    if server_already_running(args.port):
        print(f"Server already running on port {args.port}, reusing it")
    else:
        env = dict(os.environ, DRAWIO_WEBAPP_DIR=webapp_dir, DRAWIO_PORT=str(args.port))
        subprocess.Popen(
            [sys.executable, STATE_SERVER],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        print(f"started relay server on port {args.port} (background)")
        for _ in range(50):
            if server_already_running(args.port):
                break
            time.sleep(0.1)

    launched = open_browser(url)
    print()
    print(f"Server is running at: {url}")
    if launched:
        print("(attempted to open it in your default browser - if nothing appeared, e.g. a")
        print(" sandboxed/headless environment, just open the URL above manually)")
    else:
        print("(could not auto-launch a browser on this system - open the URL above manually)")


if __name__ == "__main__":
    main()
