const { app, BrowserWindow, ipcMain } = require('electron');
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const port = Number(process.env.DRAWIO_PORT || 8089);
const baseUrl = `http://127.0.0.1:${port}`;
const webappDir = process.env.DRAWIO_WEBAPP_DIR
  || path.join(os.homedir(), 'drawio-live-instance', 'src', 'main', 'webapp');
const stateServer = path.join(
  __dirname,
  '..',
  'skills',
  'drawio-live',
  'scripts',
  'state_server.py',
);
const smokeTest = process.argv.includes('--smoke-test');

let mainWindow;
let relayProcess;
let relayStatus = { phase: 'starting', message: 'Checking draw.io relay…' };

function sendToRenderer(channel, value) {
  if (mainWindow && !mainWindow.isDestroyed() && !mainWindow.webContents.isDestroyed()) {
    mainWindow.webContents.send(channel, value);
  }
}

function publishStatus(phase, message) {
  relayStatus = { phase, message };
  sendToRenderer('relay-status', relayStatus);
}

async function relayIsReady() {
  try {
    const response = await fetch(`${baseUrl}/api/health`, {
      signal: AbortSignal.timeout(1000),
    });
    const body = await response.json();
    return response.ok && body.service === 'drawio-live';
  } catch {
    return false;
  }
}

async function waitForRelay() {
  for (let attempt = 0; attempt < 50; attempt += 1) {
    if (await relayIsReady()) return true;
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  return false;
}

async function startRelay() {
  if (await relayIsReady()) {
    publishStatus('ready', `Using draw.io relay at ${baseUrl}`);
    return;
  }

  if (!fs.existsSync(webappDir)) {
    publishStatus(
      'error',
      `draw.io is not set up. Run "npm run setup:drawio" in ${__dirname}`,
    );
    return;
  }

  let spawnError;
  relayProcess = spawn(process.env.PYTHON || 'python3', [stateServer], {
    env: {
      ...process.env,
      DRAWIO_PORT: String(port),
      DRAWIO_WEBAPP_DIR: webappDir,
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  relayProcess.once('error', (error) => {
    spawnError = error;
    publishStatus('error', `Could not start draw.io relay: ${error.message}`);
  });
  relayProcess.stdout.on('data', (data) => {
    sendToRenderer('relay-log', data.toString());
  });
  relayProcess.stderr.on('data', (data) => {
    sendToRenderer('relay-log', data.toString());
  });
  relayProcess.once('exit', (code) => {
    if (!app.isQuitting) {
      publishStatus('error', `draw.io relay exited with code ${code}`);
    }
  });

  if (await waitForRelay()) {
    publishStatus('ready', `Started draw.io relay at ${baseUrl}`);
  } else if (!spawnError) {
    publishStatus('error', `draw.io relay did not become ready at ${baseUrl}`);
  }
}

async function sendCommand(command) {
  const response = await fetch(`${baseUrl}/api/command`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(command),
    signal: AbortSignal.timeout(30000),
  });
  const result = await response.json();
  if (!response.ok) {
    throw new Error(result.error || `relay returned HTTP ${response.status}`);
  }
  return result;
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1500,
    height: 900,
    minWidth: 900,
    minHeight: 600,
    backgroundColor: '#0c0f14',
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      preload: path.join(__dirname, 'preload.js'),
    },
  });

  mainWindow.loadFile(path.join(__dirname, 'index.html'));
  mainWindow.once('closed', () => {
    mainWindow = null;
  });

  if (smokeTest) {
    mainWindow.webContents.once('did-finish-load', async () => {
      try {
        const result = await mainWindow.webContents.executeJavaScript(`({
          bridge: typeof window.drawioDesktop?.command === 'function',
          editor: Boolean(document.getElementById('editor')),
          terminal: Boolean(document.querySelector('.xterm'))
        })`);
        if (!Object.values(result).every(Boolean)) {
          throw new Error(`incomplete renderer: ${JSON.stringify(result)}`);
        }
        console.log(`Electron smoke test passed: ${JSON.stringify(result)}`);
        app.quit();
      } catch (error) {
        console.error(`Electron smoke test failed: ${error.message}`);
        app.exit(1);
      }
    });
  }
}

ipcMain.handle('runtime-info', () => ({
  baseUrl,
  editorUrl: `${baseUrl}/?dev=1`,
  status: relayStatus,
  webappDir,
}));
ipcMain.handle('relay-command', (_event, command) => sendCommand(command));

app.whenReady().then(() => {
  createWindow();
  if (!smokeTest) startRelay();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('before-quit', () => {
  app.isQuitting = true;
  relayProcess?.kill();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
