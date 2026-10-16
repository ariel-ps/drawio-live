---
name: drawio-live
description: Live, bidirectional control of an already-open draw.io/diagrams.net diagram — a human and an agent editing the same canvas at once. Complements drawio-skill (which generates standalone .drawio files): use drawio-live when the user wants an agent to read or change a diagram they are actively looking at, or wants new diagrams auto-laid-out without manual coordinates. Requires a self-hosted draw.io instance patched with this skill's command-relay API (see scripts/setup.py).
---

# drawio-live

A command-relay API for controlling a draw.io diagram that is open in a real
browser, live, while a human may be simultaneously editing it. This is
different from generate-and-open tools (including the sibling `drawio-skill`
and the official `jgraph/drawio-mcp`): nothing here produces a new file —
every command acts on the diagram currently on screen.

## How it works

A small patch to draw.io's own `App.js` exposes the live editor instance and
polls a local HTTP server for commands; a Python relay server (`state_server.py`)
queues commands from external callers, waits for the browser to execute them,
and returns the result. One `curl`/script call in, one JSON result out — no
screenshots, no UI automation.

## Setup (one-time per machine)

```bash
python3 scripts/setup.py
```

One command: clones draw.io, applies the patch, starts the relay in the
background, opens the patched editor in a real browser. Safe to re-run
(skips clone/patch if already done, reuses an already-running server). Pass
`--no-run` to stop after clone+patch instead. `scripts/drawio-debug` is a thin
wrapper around this same script for a short PATH-installed alias (see the
repo's `install.sh`).

Stop it with:

```bash
python3 scripts/setup.py down --port 8089
```

`up` is implied when no subcommand is given (backward compatible with the
original invocation). `down` stops the server `up` started: it reads the PID
recorded in `~/.drawio-live/pids/<port>.pid`, and if that's missing or stale
(e.g. the server was started some other way), falls back to finding whatever
process is actually listening on that port (POSIX only, via `lsof -sTCP:LISTEN`
— the `LISTEN` state filter matters, without it lsof can also match an
unrelated process with a merely-passing connection on the same port).

`?dev=1` must stay in the URL for the life of the tab — a reload without it
falls back to the unpatched production bundle. Use a real browser (Chrome,
etc.), not a terminal-embedded one — the diagram needs to actually render
for a human to look at it.

## Sending commands

```bash
python3 scripts/live_command.py '{"type":"insertVertex","value":"Hello","x":40,"y":40,"width":120,"height":60}'
```

Every command returns `{"ok": true, "result": ...}` or `{"ok": false, "error": "..."}`.

| type | payload | notes |
| --- | --- | --- |
| `action` | `{name}` | invoke any of draw.io's ~150 built-in UI actions (`ui.actions.get(name).funct()`) — save, undo-via-action, align*, zoom*, export dialogs, toggles. Actions whose name originally ended `...` (saveAs, export, editDiagram, etc.) open a modal and won't complete headlessly. |
| `listActions` | — | enumerate every registered action name live |
| `insertVertex` | `{value,x,y,width,height,style}` | all fields optional except position/size defaults apply |
| `insertEdge` | `{source,target,value,style}` | source/target are cell ids |
| `deleteCells` | `{ids}` | |
| `setStyle` | `{ids,key,value}` | changes one style key, leaves the rest of the style string untouched |
| `setFullStyle` | `{ids,style}` | replaces the whole style string |
| `setValue` | `{id,value}` | cell label |
| `setGeometry` | `{id,x,y,width,height}` | any subset; unset fields keep current value |
| `group` / `ungroup` | `{ids}` | |
| `getSelection` / `setSelection` | `{ids}` (set only) | |
| `getStyle` | `{id}` | raw style string, not merged with stylesheet defaults |
| `load` | `{xml}` | replace the current page's content from a bare `<mxGraphModel>` string (not `<mxfile>`-wrapped) |
| `undo` / `redo` / `canUndo` / `canRedo` | — | |
| `exportSvg` / `exportPng` | — | both pure client-side, no server round-trip; PNG returns a data URI |
| `checkOverlaps` | — | **the thing a static XML linter can't do**: compares actual rendered pixel bounding boxes (`shape.boundingBox` / `text.boundingBox`) of every cell and label, pairwise, for real intersections — catches edges whose *live-rendered* orthogonal routing cuts through a vertex, which static geometry analysis (e.g. drawio-skill's `validate.py`) cannot see since that routing isn't stored in the XML |
| `runLayout` | `{style}` | draw.io's own ELK-backed layout (`horizontalTree`/`verticalTree`/`horizontalFlow`/`verticalFlow`/`organic`). Incremental — nudges from current positions, doesn't fully recompute. Good for light cleanup, not for untangling an already-bad manual layout. `style:'libavoid'` (obstacle-avoiding routing) is wired into the same pipeline but its WASM module isn't actually initializing via this call path yet — currently a no-op that silently resets edges to default routing; don't rely on it. |
| `setEdgeLabelPosition` | `{id,x,y}` | moves where an edge's label sits along its path (`x`: -1..1, 0=midpoint) and its perpendicular offset (`y`, px). Only fixes label-vs-shape crowding, not an edge's *path* crossing a shape — those are two different problems. |
| `autoFixOverlaps` | `{maxRounds}` | greedy, verified fix for label-position overlaps only: for each edge whose label overlaps something, tries several offsets and keeps whichever genuinely minimizes that edge's overlap count (reverts to baseline if nothing helps — never makes a specific edge worse). Returns `{roundsRun, startingOverlaps, remainingOverlaps}`. Does not and cannot address edge-path-crosses-shape overlaps (a harder, unsolved problem here — see `runLayout`'s libavoid note). |
| `listPages` / `renamePage` / `removePage` / `setCurrentPage` | `{index,name}` | page management by index (`ui.pages[index]`). The built-in `action` names `renamePage`/`removePage` only open UI dialogs — these commands call the underlying `RenamePage` edit / `ui.removePage()` / `ui.selectPage()` directly, headlessly. `setCurrentPage` forces a synchronous `graph.refresh()` + `view.validate()` afterward — without it, a following `exportPng` in the same batch captures the *previous* page's stale canvas (a real bug found and fixed here). |
| `getFullDocument` / `loadFullDocument` | `{xml}` (load only) | the **whole multi-page document** (`<mxfile>` with every `<diagram>` page), not just the current page like `load`/`checkOverlaps` operate on. Use this to save/restore full state around a server restart — **do not rely on browser autosave for this**: it silently failed to restore a full 10-page document across one reload during this session even though it had worked on prior reloads. Always `getFullDocument` → save to disk → restart → `loadFullDocument` when you need the whole document to survive a code change. |
| `saveDiagram` / (load via URL) | `{name}` | `saveDiagram` POSTs the full document (via `getFullDocument`) to the relay server, which writes it to `<server>/diagrams/<name>.drawio`. Visiting `http://<relay>/d/<name>` then 302-redirects to `/?dev=1&loadDiagram=<name>`, and the client fetches and loads that named diagram on boot. This is a simple name-addressable save/restore scheme — not a general multi-user storage system, just enough to reopen a specific diagram by name. |
| `setDocumentTitle` | `{name}` | sets the browser tab title. Handles two different internal states that occur depending on how the page came up (normal load vs. autosave-restored): renames the `LocalFile` if one exists, otherwise sets `ui.defaultFilename`, and *always* also sets `document.title` directly as a third fallback — relying on only one of these paths left the tab showing "Untitled Diagram" in one of the two states. |
| `batch` | `{commands: [...]}` | runs multiple commands as one relay round-trip, **executed atomically relative to other callers** — the relay's single poll loop never fetches a new queued command until the current one (including everything inside a batch) fully finishes. This is the only safe way to run multiple commands against a live session that other processes might be concurrently calling — unbatched sequential calls can and will interleave with another caller's commands, since nothing else gives one caller exclusive access to the session. Required for e.g. `live_layout.py --new-page` precisely because other instances may be running concurrently against the same shared document. |
| `eval` | `{expression}` | arbitrary JS escape hatch, runs via indirect `eval` (global scope — use `window.__drawioUi`, not the closure-local `ui`). Use this to discover real underlying mechanisms (e.g. `ui.renamePage`/`ui.removePage` turned out to be dialog-only wrappers around `RenamePage`/direct calls — found via `eval`, then promoted to real commands above) rather than reaching for an out-of-band tool like CDP. When you find yourself using `eval` for something routine more than once, that's the signal to add a proper command instead. |
| `describeGraph` | — | a clean, structured read of the whole current page: `{revision, page, cells: [{id, type, value, parentId, geometry, style, source?, target?}], selection}`. The default-layer cell (id `"1"`, direct child of root) is filtered out — only real shapes/edges appear. Verified live; found and fixed one real bug (was leaking the layer cell before that filter existed). |
| `transaction` | `{expectedRevision?, commands}` | like `batch`, but with optimistic concurrency and real rollback: rejects immediately (no model changes at all) if `expectedRevision` doesn't match the live `window.__drawioRevision`; wraps all sub-commands in one `beginUpdate/endUpdate` (one undo step); if any sub-command throws, restores a pre-transaction XML snapshot via `replaceDiagramData` and re-throws, so the whole thing fails atomically. Success and stale-revision-rejection paths verified live. The rollback *mechanics* were verified live (state genuinely restored after a mid-transaction failure); a follow-up fix (rollback must `throw`, not `return {ok:false}` — the poll loop's outer wrapper unconditionally sets `ok:true` on any non-throwing return) was applied but not yet re-verified live due to unrelated environment flakiness — re-test before depending on the failure path's `ok` field. |
| `getCapabilities` | — | server-side only, never reaches the browser: `{protocolVersion, commands: [...]}`. Static, so no round-trip needed — works even if the browser's poll loop is dead. |
| `health` | — | server-side only, never reaches the browser — **this is the point**: `{browserConnected, lastPolledSecondsAgo, activePage, revision, queueDepth}` tells you if the relay is actually alive *even when it's stuck*, which is exactly when you need it most. `browserConnected` reflects whether a `/api/poll` request is currently blocked waiting (i.e. the browser's poll loop is actually running right now), not just "a browser loaded the page once." Verified live, multiple times, including correctly reporting a dead poll loop. |
| `waitForChange` | `{afterRevision}` | server-side long-poll (up to the server's command timeout), **not dispatched to the browser** — blocks the *caller's* connection only, using the same revision counter the browser pushes to `/api/revision` on every model change. Returns `{timedOut, revision, page}` either way. This is what makes an agent able to react to human edits without polling `describeGraph` in a loop. Not yet tested live (ran out of a stable browser connection before reaching it) — verify before relying on it. |

## Building a new diagram with a clean layout (the sibling-skill combination)

Hand-picking `x`/`y` for every shape doesn't scale and produces overlaps.
Instead, describe the diagram as topology only (no coordinates) using
`drawio-skill`'s graph-JSON schema, and let its Graphviz-based `autolayout.py`
compute positions from scratch — a properly from-scratch layout, unlike
`runLayout`'s incremental nudge:

```bash
python3 scripts/live_layout.py graph.json --new-page --screenshot out.png --timing
```

`--new-page` inserts a fresh page instead of replacing the current one — required when other
processes may be running concurrently against the same shared document (it's wrapped in
`batch` internally, so it's atomic relative to other callers). `--timing` prints a stage
breakdown to stderr; measured on a 7-node/10-edge graph, the Graphviz subprocess took ~240ms
and the relay round-trip ~30ms — the mechanical overhead is negligible. If a run of this
script takes much longer than that, the time is being spent by whatever composed the graph
JSON, not by this script.

```json
{
  "direction": "TB",
  "nodes": [{"id": "a", "label": "Service A", "style": "rounded=1;whiteSpace=wrap;html=1;"}],
  "edges": [{"source": "a", "target": "b", "label": "calls"}]
}
```

This script: runs `drawio-skill`'s `autolayout.py --tune` on the graph JSON,
extracts the resulting `<mxGraphModel>`, pushes it live via `{"type":"load"}`,
then runs `{"type":"checkOverlaps"}` against the *actual rendered* result to
confirm it's really clean (not just clean-on-paper). Requires `drawio-skill`
installed as a sibling skill (auto-detected at
`~/.claude/skills/drawio-skill/scripts/autolayout.py`); pass
`--autolayout /path/to/autolayout.py` to override.

## When to use this vs. the alternatives

- **drawio-skill** (sibling): generating a diagram from code/IaC/schemas/Mermaid as a standalone file, or one-shot "describe it, get a .drawio" with no live session involved.
- **jgraph/drawio-mcp** (official): same generate-and-open shape as drawio-skill, via MCP instead of a skill.
- **drawio-live** (this skill): the user is looking at a diagram right now and an agent needs to read its current state or change it, with both of them able to keep working on it afterward.
