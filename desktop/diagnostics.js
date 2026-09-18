'use strict';

const { app, BrowserWindow, dialog, ipcMain } = require('electron');
const fs = require('fs');
const path = require('path');
const os = require('os');

const MAX_BYTES = 512 * 1024;
const MAX_FILES = 3;
let installed = false;
let reportWindow = null;

function logsDir() {
  return path.join(app.getPath('userData'), 'diagnostics');
}

function logPath(index = 0) {
  return path.join(logsDir(), index ? `desktop.${index}.jsonl` : 'desktop.jsonl');
}

function scrub(value) {
  let s = String(value == null ? '' : value);
  s = s.replace(/([?&](?:token|code|key|secret|session|auth|password)=)[^&#\s]+/ig, '$1[redacted]');
  s = s.replace(/(bearer\s+)[a-z0-9._~+\/-]+/ig, '$1[redacted]');
  s = s.replace(/([a-z0-9._%+-]+)@([a-z0-9.-]+\.[a-z]{2,})/ig, '[email-redacted]');
  s = s.replace(/https?:\/\/[^\s"'<>]+/ig, raw => {
    try {
      const u = new URL(raw);
      return `${u.origin}${u.pathname}`;
    } catch (_) {
      return '[url-redacted]';
    }
  });
  if (s.length > 500) s = s.slice(0, 500) + '…';
  return s;
}

function sanitizeData(data) {
  if (!data || typeof data !== 'object') return {};
  const safe = {};
  for (const [key, value] of Object.entries(data)) {
    if (/token|secret|cookie|authorization|password|message|content|name|email/i.test(key)) {
      safe[key] = '[redacted]';
      continue;
    }
    if (value == null || ['number', 'boolean'].includes(typeof value)) safe[key] = value;
    else if (typeof value === 'string') safe[key] = scrub(value);
    else if (Array.isArray(value)) safe[key] = value.slice(0, 20).map(v => typeof v === 'string' ? scrub(v) : v);
    else safe[key] = '[object]';
  }
  return safe;
}

function rotate() {
  try {
    const current = logPath();
    if (!fs.existsSync(current) || fs.statSync(current).size < MAX_BYTES) return;
    for (let i = MAX_FILES - 1; i >= 1; i--) {
      const src = logPath(i);
      const dst = logPath(i + 1);
      if (fs.existsSync(dst)) fs.rmSync(dst, { force: true });
      if (fs.existsSync(src)) fs.renameSync(src, dst);
    }
    fs.renameSync(current, logPath(1));
  } catch (_) {}
}

function write(event, data = {}) {
  try {
    fs.mkdirSync(logsDir(), { recursive: true });
    rotate();
    const row = {
      ts: new Date().toISOString(),
      event: scrub(event),
      data: sanitizeData(data),
    };
    fs.appendFileSync(logPath(), JSON.stringify(row) + '\n', { encoding: 'utf8', mode: 0o600 });
  } catch (_) {}
}

function recentLogs() {
  const out = [];
  for (let i = 0; i <= MAX_FILES; i++) {
    const p = logPath(i);
    if (!fs.existsSync(p)) continue;
    try {
      const text = fs.readFileSync(p, 'utf8');
      const lines = text.split(/\r?\n/).filter(Boolean).slice(-1200);
      for (const line of lines) {
        try { out.push(JSON.parse(line)); } catch (_) {}
      }
    } catch (_) {}
  }
  return out.slice(-1500);
}

function buildInfo() {
  let version = null;
  try { version = app.getVersion(); } catch (_) {}
  return {
    version,
    build_sha: String(process.env.ADELIA_BUILD_SHA || process.env.GITHUB_SHA || '').trim().slice(0, 12) || null,
    platform: process.platform,
    arch: process.arch,
    os_release: os.release(),
    packaged: app.isPackaged,
  };
}

async function exportBundle(description = '') {
  const safeDescription = String(description || '').slice(0, 2000);
  const result = await dialog.showSaveDialog({
    title: 'Сохранить отчёт Аделии',
    defaultPath: `adelia-diagnostics-${new Date().toISOString().replace(/[:.]/g, '-')}.json`,
    filters: [{ name: 'Adelia diagnostics', extensions: ['json'] }],
  });
  if (result.canceled || !result.filePath) return { status: 'cancelled' };

  const payload = {
    schema: 1,
    generated_at: new Date().toISOString(),
    privacy: {
      note: 'Technical diagnostics only. Tokens, cookies, email addresses and URL query secrets are redacted.',
      user_description_included: !!safeDescription,
    },
    build: buildInfo(),
    user_description: safeDescription,
    events: recentLogs(),
  };
  fs.writeFileSync(result.filePath, JSON.stringify(payload, null, 2) + '\n', { encoding: 'utf8', mode: 0o600 });
  write('diagnostics_exported', { event_count: payload.events.length });
  return { status: 'saved', path: result.filePath };
}

function openReportWindow() {
  if (reportWindow && !reportWindow.isDestroyed()) {
    if (reportWindow.isMinimized()) reportWindow.restore();
    reportWindow.show();
    reportWindow.focus();
    return true;
  }
  reportWindow = new BrowserWindow({
    width: 650, height: 590, minWidth: 540, minHeight: 500,
    show: false, title: 'Сообщить о проблеме — Аделия',
    backgroundColor: '#f5f3f8',
    webPreferences: {
      preload: path.join(__dirname, 'report_preload.js'),
      contextIsolation: true, nodeIntegration: false, sandbox: true, webSecurity: true,
    },
  });
  reportWindow.setMenuBarVisibility(false);
  reportWindow.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  reportWindow.webContents.on('will-navigate', event => event.preventDefault());
  reportWindow.once('ready-to-show', () => reportWindow && !reportWindow.isDestroyed() && reportWindow.show());
  reportWindow.on('closed', () => { reportWindow = null; });
  reportWindow.loadFile(path.join(__dirname, 'report.html'));
  write('report_window_opened');
  return true;
}

function install() {
  if (installed) return;
  installed = true;

  process.on('uncaughtExceptionMonitor', error => {
    write('uncaught_exception', { type: error && error.name, error: error && error.message });
  });
  process.on('unhandledRejection', reason => {
    write('unhandled_rejection', { error: reason && reason.message ? reason.message : String(reason) });
  });

  app.on('render-process-gone', (_event, webContents, details) => {
    write('render_process_gone', {
      reason: details && details.reason,
      exitCode: details && details.exitCode,
      url: webContents && !webContents.isDestroyed() ? webContents.getURL() : '',
    });
  });
  app.on('child-process-gone', (_event, details) => {
    write('child_process_gone', {
      type: details && details.type,
      reason: details && details.reason,
      exitCode: details && details.exitCode,
      serviceName: details && details.serviceName,
    });
  });

  app.whenReady().then(() => {
    write('app_ready', buildInfo());
    ipcMain.handle('adelia:open-report', () => openReportWindow());
    ipcMain.handle('adelia:report-info', event => {
      if (!reportWindow || event.sender !== reportWindow.webContents) return null;
      return buildInfo();
    });
    ipcMain.handle('adelia:report-export', async (event, payload) => {
      if (!reportWindow || event.sender !== reportWindow.webContents) return { status: 'denied' };
      return exportBundle(payload && payload.description);
    });
    ipcMain.handle('adelia:report-close', event => {
      if (!reportWindow || event.sender !== reportWindow.webContents) return false;
      reportWindow.close();
      return true;
    });
  });
}

module.exports = { install, write, scrub, sanitizeData, openReportWindow };
