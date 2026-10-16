const { contextBridge, ipcRenderer } = require('electron');

function subscribe(channel, callback) {
  const listener = (_event, value) => callback(value);
  ipcRenderer.on(channel, listener);
  return () => ipcRenderer.removeListener(channel, listener);
}

contextBridge.exposeInMainWorld('drawioDesktop', {
  command: (command) => ipcRenderer.invoke('relay-command', command),
  runtimeInfo: () => ipcRenderer.invoke('runtime-info'),
  onRelayLog: (callback) => subscribe('relay-log', callback),
  onRelayStatus: (callback) => subscribe('relay-status', callback),
});
