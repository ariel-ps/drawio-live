const terminal = new Terminal({
  cursorBlink: true,
  convertEol: true,
  fontFamily: 'SFMono-Regular, Menlo, Monaco, Consolas, monospace',
  fontSize: 13,
  theme: {
    background: '#0c0f14',
    foreground: '#d8dee9',
    cursor: '#61afef',
    green: '#98c379',
    red: '#e06c75',
    yellow: '#e5c07b',
  },
});
const fitAddon = new FitAddon.FitAddon();
terminal.loadAddon(fitAddon);
terminal.open(document.getElementById('terminal'));
fitAddon.fit();

const statusElement = document.getElementById('status');
const editor = document.getElementById('editor');
const placeholder = document.getElementById('editor-placeholder');

let input = '';
let historyIndex = 0;
let busy = false;
const history = [];

const commands = {
  actions: { type: 'listActions' },
  overlaps: { type: 'checkOverlaps' },
  pages: { type: 'listPages' },
  redo: { type: 'redo' },
  selection: { type: 'getSelection' },
  undo: { type: 'undo' },
};

function writeLine(value = '') {
  terminal.writeln(String(value).replaceAll('\n', '\r\n'));
}

function prompt() {
  terminal.write('\x1b[36mdrawio\x1b[0m> ');
}

function replaceInput(value) {
  terminal.write('\b \b'.repeat(input.length));
  input = value;
  terminal.write(input);
}

function printHelp() {
  writeLine('Commands:');
  writeLine('  vertex [x y] <label>       insert a vertex');
  writeLine('  edge <source> <target> [label]');
  writeLine('  select <id> [id...]        select cells');
  writeLine('  delete [id...]             delete IDs or current selection');
  writeLine('  undo | redo | pages | actions | selection | overlaps');
  writeLine('  json <object>              send any drawio-live command');
  writeLine('  clear | help');
}

function vertexCommand(args) {
  const match = args.match(/^(?:(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s+)?(.+)$/);
  if (!match) throw new Error('usage: vertex [x y] <label>');
  return {
    type: 'insertVertex',
    x: match[1] == null ? 40 : Number(match[1]),
    y: match[2] == null ? 40 : Number(match[2]),
    value: match[3],
  };
}

function edgeCommand(args) {
  const [source, target, ...label] = args.trim().split(/\s+/);
  if (!source || !target) throw new Error('usage: edge <source> <target> [label]');
  return { type: 'insertEdge', source, target, value: label.join(' ') };
}

async function parseCommand(line) {
  const [name = '', ...parts] = line.trim().split(/\s+/);
  const args = line.trim().slice(name.length).trim();

  if (name === 'help') {
    printHelp();
    return null;
  }
  if (name === 'clear') {
    terminal.clear();
    return null;
  }
  if (name === 'json') return JSON.parse(args);
  if (name.startsWith('{')) return JSON.parse(line);
  if (name === 'vertex') return vertexCommand(args);
  if (name === 'edge') return edgeCommand(args);
  if (name === 'select') return { type: 'setSelection', ids: parts };
  if (name === 'delete') {
    let ids = parts;
    if (ids.length === 0) {
      const selection = await window.drawioDesktop.command({ type: 'getSelection' });
      ids = selection.result || [];
    }
    return { type: 'deleteCells', ids };
  }
  if (commands[name]) return commands[name];
  throw new Error(`unknown command: ${name}; run "help"`);
}

async function execute(line) {
  if (!line.trim()) return;
  const command = await parseCommand(line);
  if (!command) return;
  const result = await window.drawioDesktop.command(command);
  writeLine(JSON.stringify(result, null, 2));
}

async function submitInput() {
  writeLine();
  const line = input;
  input = '';
  if (line.trim()) {
    history.push(line);
    historyIndex = history.length;
  }
  busy = true;
  try {
    await execute(line);
  } catch (error) {
    writeLine(`\x1b[31merror: ${error.message}\x1b[0m`);
  } finally {
    busy = false;
    prompt();
  }
}

function appendInput(value) {
  if (value && !value.startsWith('\x1b') && !/[\u0000-\u001f]/.test(value)) {
    input += value;
    terminal.write(value);
  }
}

terminal.onData(async (data) => {
  if (busy) return;

  if (/[\r\n]/.test(data)) {
    const lines = data.replaceAll('\r\n', '\n').replaceAll('\r', '\n').split('\n');
    for (let index = 0; index < lines.length; index += 1) {
      appendInput(lines[index]);
      if (index < lines.length - 1) await submitInput();
    }
    return;
  }

  if (data === '\u0003') {
    input = '';
    writeLine('^C');
    prompt();
    return;
  }
  if (data === '\u000c') {
    terminal.clear();
    prompt();
    return;
  }
  if (data === '\u007f') {
    if (input) {
      input = input.slice(0, -1);
      terminal.write('\b \b');
    }
    return;
  }
  if (data === '\x1b[A') {
    if (historyIndex > 0) historyIndex -= 1;
    replaceInput(history[historyIndex] || '');
    return;
  }
  if (data === '\x1b[B') {
    if (historyIndex < history.length) historyIndex += 1;
    replaceInput(history[historyIndex] || '');
    return;
  }
  appendInput(data);
});

function setStatus(status, editorUrl) {
  statusElement.textContent = status.phase;
  statusElement.className = status.phase;
  writeLine(`\x1b[33m${status.message}\x1b[0m`);

  if (status.phase === 'ready' && !editor.getAttribute('src')) {
    editor.src = editorUrl;
    editor.addEventListener('load', () => {
      editor.classList.add('ready');
      placeholder.classList.add('hidden');
    }, { once: true });
  } else if (status.phase === 'error') {
    placeholder.textContent = status.message;
  }
}

window.drawioDesktop.onRelayLog((message) => writeLine(message.trimEnd()));
window.addEventListener('resize', () => fitAddon.fit());

let editorUrl;
let latestStatus;
window.drawioDesktop.onRelayStatus((status) => {
  latestStatus = status;
  if (editorUrl) setStatus(status, editorUrl);
});

window.drawioDesktop.runtimeInfo().then((info) => {
  editorUrl = info.editorUrl;
  setStatus(latestStatus || info.status, editorUrl);
  writeLine('Type "help" for commands. Raw JSON is also accepted.');
  prompt();
  terminal.focus();
});
