# drawio-live Electron prototype

A terminal command pane beside the real draw.io canvas. The canvas still runs
the patched draw.io web application; terminal commands use the existing
`/api/command` relay.

```bash
cd electron
npm install --registry=https://registry.npmjs.org
npm run setup:drawio
npm start
```

If draw.io is already installed somewhere else, skip setup and provide its
webapp directory:

```bash
DRAWIO_WEBAPP_DIR=/path/to/drawio/src/main/webapp npm start
```

If port 8089 is already occupied by another local service, select another:

```bash
DRAWIO_PORT=8090 npm start
```

Run `help` in the terminal pane for shortcuts. Any drawio-live command can
also be sent directly:

```text
json {"type":"insertVertex","value":"Hello","x":40,"y":40}
```
