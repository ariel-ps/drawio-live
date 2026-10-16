# drawio-live

Live, bidirectional control of a draw.io / diagrams.net diagram that is open
in a real browser — a human and an agent editing the same canvas at once.

This is **not** another "generate a `.drawio` file" tool. Tools like the
sibling [`drawio-skill`](https://github.com/Agents365-ai/drawio-skill) and the
official [`jgraph/drawio-mcp`](https://github.com/jgraph/drawio-mcp) are
generate-and-open: describe a diagram, get a new file. `drawio-live` is for
the opposite situation — a diagram is already open, a person may be looking
at it or editing it right now, and an agent needs to read its current state
or change it live, with both of them able to keep working on it afterward.

## How it works

A small patch to draw.io's own `App.js` (`skills/drawio-live/scripts/app_js.patch`)
exposes the live editor instance in the page and starts a long-poll loop
against a local HTTP relay. The relay (`state_server.py`, stdlib-only Python)
queues commands from external callers, waits for the browser to execute them,
and returns the result — one HTTP call in, one JSON result out. No screenshots,
no UI automation, no CDP.

```
 caller  --POST /api/command-->  relay (state_server.py)  <--long-poll-- draw.io tab (patched App.js)
   ^                                     |                                      |
   |------------------<-- JSON result <--+------------------<-- POST /api/result
```

## Quickstart

```bash
pip install --user nothing   # stdlib only, nothing to install
python3 skills/drawio-live/scripts/setup.py            # clones draw.io + applies the patch
DRAWIO_WEBAPP_DIR=~/drawio-live-instance/src/main/webapp \
  python3 skills/drawio-live/scripts/state_server.py &
open "http://127.0.0.1:8089/?dev=1"                    # dev=1 is required for the patch to load
```

Then from anywhere:

```bash
python3 skills/drawio-live/scripts/live_command.py '{"type":"insertVertex","value":"Hello","x":40,"y":40}'
```

Full command reference, setup details, and the sibling-skill layout-engine
combination are documented in [`skills/drawio-live/SKILL.md`](skills/drawio-live/SKILL.md)
— that file is written for an AI agent to read directly (Claude Code, or any
[Agent Skills](https://agentskills.io)-compatible host), but it's a complete
reference for a human too.

## What's actually interesting here

- **~35 commands** covering the full surface: graph mutation (`insertVertex`,
  `insertEdge`, `setStyle`, `setGeometry`, `group`...), any of draw.io's ~150
  built-in UI actions, undo/redo, page management, full-document save/restore,
  export (SVG/PNG, pure client-side), and a name-addressable URL scheme
  (`/d/<name>` auto-loads a saved diagram).
- **A live pixel-based overlap checker** (`checkOverlaps`) that compares
  actual *rendered* bounding boxes — the thing a static XML linter structurally
  cannot do, since draw.io's live edge routing isn't stored in the XML at all.
- **A real sibling-skill combination**: `live_layout.py` runs `drawio-skill`'s
  Graphviz-based `autolayout.py` on a topology-only graph description, then
  pushes the laid-out result into the live session and verifies it with the
  pixel checker above — clean layout from one tool, live delivery from the
  other.
- **`batch`**: runs multiple commands as one atomic relay round-trip. The
  relay's single poll loop never fetches a new queued command until the
  current one fully finishes, so a batch is atomic with respect to other
  concurrent callers — the only safe way to run multi-step operations against
  a session other processes might also be calling.

## Known limitations (reported honestly, not swept under the rug)

- **`runLayout` with `style:'libavoid'`** is wired into the same pipeline as
  draw.io's other layout algorithms, but its WASM module never actually
  initializes via this call path — it currently silently resets edges to
  default routing instead of doing obstacle-avoiding routing. Don't rely on it
  yet; real root cause not yet found.
- **Browser autosave is not a reliable way to preserve multi-page state across
  a server restart.** It worked on some reloads and silently failed on
  others during development. Use `getFullDocument`/`loadFullDocument`
  explicitly instead — see SKILL.md.
- **A reload leaves a stale long-poll connection behind** that can steal the
  very next command and silently drop it (the command times out; the real
  poll loop gets the one after it). A one-time retry after any reload is the
  current workaround; not yet fixed at the root.
- **Multiple browser tabs/windows pointed at the same relay** will race for
  the same command queue — there's no per-caller session concept. Fine for
  passively viewing the same document from two places; not safe for two
  places issuing commands at once.
- **`autoFixOverlaps`** only resolves label-vs-shape crowding (by trying
  several label offsets and keeping whichever is verifiably better). It
  cannot fix an edge's *path* crossing through a shape — that's a genuinely
  different, unsolved problem here.

## Relationship to sibling projects

| | Approach | Best for |
| --- | --- | --- |
| [`drawio-skill`](https://github.com/Agents365-ai/drawio-skill) | Generate-and-open, from code/IaC/schemas/Mermaid/natural language | One-shot diagram creation, no live session |
| [`jgraph/drawio-mcp`](https://github.com/jgraph/drawio-mcp) | Generate-and-open, via MCP | Same shape as drawio-skill, official |
| **drawio-live** (this repo) | Live control of an already-open session | A human is looking at this diagram right now |

## License

MIT (see `LICENSE`). The included patch modifies
[draw.io](https://github.com/jgraph/drawio) (Apache 2.0) source files — the
patch content itself is original work under this repo's MIT license; applying
it produces a combined work subject to both licenses.
