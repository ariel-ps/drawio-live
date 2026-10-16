#!/usr/bin/env python3
"""One-click setup/start/stop for drawio-live.

Usage:
  python3 setup.py [up] [target_dir] [--no-run] [--port 8089]
  python3 setup.py down [--port 8089]

`up` (the default if no command is given, for backward compatibility) clones
draw.io (if needed), applies the live-control patch to App.js, starts the
relay server in the background, and opens the patched editor in your browser.
Default target_dir: ~/drawio-live-instance. Idempotent: safe to re-run; skips
clone/patch steps already done, and reuses an already-running server on the
target port instead of starting a second one.

`down` stops the relay server on the given port. Looks up the PID it recorded
when `up` started it (~/.drawio-live/pids/<port>.pid); if that's missing or
stale (e.g. the server was started some other way), falls back to finding
whatever process is actually listening on that port (POSIX only, via lsof).

--no-run (up only): just clone+patch, print the manual start command, don't
launch anything.
"""
import argparse
import os
import platform
import signal
import subprocess
import sys
import time
import urllib.request

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PATCH_FILE = os.path.join(SCRIPT_DIR, "app_js.patch")
STATE_SERVER = os.path.join(SCRIPT_DIR, "state_server.py")
REPO_URL = "https://github.com/jgraph/drawio.git"
PID_DIR = os.path.expanduser("~/.drawio-live/pids")


def run(cmd, **kwargs):
    print("+", " ".join(cmd))
    return subprocess.run(cmd, check=True, **kwargs)


def pidfile_path(port):
    return os.path.join(PID_DIR, f"{port}.pid")


def server_already_running(port):
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/index.html", timeout=1)
        return True
    except Exception:
        return False


def find_pid_by_port(port):
    """POSIX-only fallback for servers not started via this script's `up`
    (so no pidfile exists) - e.g. started by hand with state_server.py directly.
    -sTCP:LISTEN is required: without it, lsof also matches unrelated processes
    with any connection merely touching this port (e.g. a stale client-side
    socket), not just whoever actually owns the listening server."""
    try:
        out = subprocess.run(
            ["lsof", "-nP", "-t", f"-iTCP:{port}", "-sTCP:LISTEN"],
            capture_output=True, text=True, timeout=3,
        )
        pids = [int(p) for p in out.stdout.split() if p.strip()]
        return pids[0] if pids else None
    except Exception:
        return None


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


def cmd_up(args):
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
        os.makedirs(PID_DIR, exist_ok=True)
        env = dict(os.environ, DRAWIO_WEBAPP_DIR=webapp_dir, DRAWIO_PORT=str(args.port))
        proc = subprocess.Popen(
            [sys.executable, STATE_SERVER],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        with open(pidfile_path(args.port), "w") as f:
            f.write(str(proc.pid))
        print(f"started relay server on port {args.port} (background, pid {proc.pid})")
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
    print(f"Stop it with: python3 {os.path.abspath(__file__)} down --port {args.port}")


def cmd_down(args):
    port = args.port
    pidfile = pidfile_path(port)
    pid = None
    source = None

    if os.path.isfile(pidfile):
        try:
            with open(pidfile) as f:
                pid = int(f.read().strip())
            source = "pidfile"
        except ValueError:
            pid = None

    if pid is None:
        pid = find_pid_by_port(port)
        source = "lsof" if pid is not None else None

    if pid is None:
        print(f"no drawio-live server found on port {port}")
        if os.path.isfile(pidfile):
            os.remove(pidfile)
        return

    try:
        os.kill(pid, signal.SIGTERM)
        print(f"stopped server (pid {pid}, found via {source}) on port {port}")
    except ProcessLookupError:
        print(f"pid {pid} ({source}) was already gone - stale pidfile, nothing to do")
    except PermissionError:
        print(f"found pid {pid} ({source}) on port {port} but don't have permission to stop it")
        return

    if os.path.isfile(pidfile):
        os.remove(pidfile)


def main():
    # Accept an optional leading "up"/"down" command for backward
    # compatibility with the original `setup.py [target_dir] [--port N]`
    # invocation (no command = up), without making argparse subparsers
    # mandatory.
    command = "up"
    rest = sys.argv[1:]
    if rest and rest[0] in ("up", "down"):
        command = rest[0]
        rest = rest[1:]

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8089)

    if command == "down":
        args = parser.parse_args(rest)
        cmd_down(args)
        return

    parser.add_argument("target_dir", nargs="?", default=os.path.expanduser("~/drawio-live-instance"))
    parser.add_argument("--no-run", action="store_true", help="only clone+patch, don't start the server or open a browser")
    args = parser.parse_args(rest)
    cmd_up(args)


if __name__ == "__main__":
    main()
