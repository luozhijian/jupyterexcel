 
// No imports or DOM dependency: also runs in Excel's JavaScript-only runtime.
globalThis.JupyterExcel = (() => {
'use strict';
const config = globalThis.JupyterExcelConfig;
if (!config || !config.apiBase) throw new Error('Jupyter runtime configuration is missing.');
/* global console, OfficeRuntime */

const scope = encodeURIComponent(config.apiBase + "|" + (config.hubUser || ""));
const STORAGE_KEYS = {
  logs: "jupyter.logs." + scope,
  settings: "jupyter.logSettings." + scope,
  clearToken: "jupyter.logClearToken." + scope,
};

const MAX_LOG_ENTRIES = 200;
const MAX_STORAGE_CHARACTERS = 200000;
const MAX_DETAIL_CHARACTERS = 12000;
const DEFAULT_SETTINGS = { enabled: false, level: "NORMAL" };

let entries = [];
let sequence = 0;
let writeQueue = Promise.resolve();
let lastClearToken = null;

function writeLog(level, functionName, event, message, details) {
  const entry = {
    sequence: ++sequence,
    timestamp: new Date().toISOString(),
    level,
    functionName,
    event,
    message: redact(message),
    details: limitDetails(redact(details)),
  };

  writeQueue = writeQueue
    .then(() => publishEntry(entry))
    .catch(() => {});
  return entry;
}

async function publishEntry(entry) {
  if (!storageAvailable()) return;

  const [settingsValue, clearToken] = await Promise.all([
    OfficeRuntime.storage.getItem(STORAGE_KEYS.settings),
    OfficeRuntime.storage.getItem(STORAGE_KEYS.clearToken),
  ]);
  const settings = parseJson(settingsValue, DEFAULT_SETTINGS);

  if (clearToken !== lastClearToken) {
    entries = [];
    lastClearToken = clearToken;
  }
  if (!shouldRecord(entry.level, settings)) return;

  entries.push(entry);
  entries = entries.slice(-MAX_LOG_ENTRIES);
  let snapshot = JSON.stringify({ version: 1, lastSequence: entry.sequence, entries });
  while (snapshot.length > MAX_STORAGE_CHARACTERS && entries.length > 1) {
    entries.shift();
    snapshot = JSON.stringify({ version: 1, lastSequence: entry.sequence, entries });
  }
  await OfficeRuntime.storage.setItem(STORAGE_KEYS.logs, snapshot);
}

async function readLogs() {
  if (!storageAvailable()) return [];
  const snapshot = parseJson(await OfficeRuntime.storage.getItem(STORAGE_KEYS.logs), {
    entries: [],
  });
  return Array.isArray(snapshot.entries) ? snapshot.entries : [];
}

async function readLogSettings() {
  if (!storageAvailable()) return DEFAULT_SETTINGS;
  return {
    ...DEFAULT_SETTINGS,
    ...parseJson(await OfficeRuntime.storage.getItem(STORAGE_KEYS.settings), {}),
  };
}

async function writeLogSettings(settings) {
  if (!storageAvailable()) return;
  await OfficeRuntime.storage.setItem(
    STORAGE_KEYS.settings,
    JSON.stringify({ ...DEFAULT_SETTINGS, ...settings })
  );
}

async function clearLogs() {
  if (!storageAvailable()) return;
  await OfficeRuntime.storage.setItem(STORAGE_KEYS.clearToken, `${Date.now()}-${Math.random()}`);
  await OfficeRuntime.storage.removeItem(STORAGE_KEYS.logs);
}

function summarizeArguments(values) {
  return {
    completeValue: limitDetails(redact(values)),
    json: safeStringify(redact(values)),
    structure: summarizeNode(redact(values)),
  };
}

function summarizeNode(value) {
  if (!Array.isArray(value)) {
    return { kind: "value", type: value === null ? "null" : typeof value, value };
  }
  const typeCounts = {};
  let cellCount = 0;
  visit(value, (item) => {
    const type = item === null ? "null" : typeof item;
    typeCounts[type] = (typeCounts[type] || 0) + 1;
    cellCount += 1;
  });
  return {
    kind: "array",
    dimensions: dimensionsOf(value),
    length: value.length,
    cellCount,
    typeCounts,
    children: value.slice(0, 20).map(summarizeNode),
    truncatedChildren: Math.max(0, value.length - 20),
  };
}

function dimensionsOf(value) {
  const dimensions = [];
  let current = value;
  while (Array.isArray(current)) {
    dimensions.push(current.length);
    current = current[0];
  }
  return dimensions;
}

function visit(value, visitor) {
  if (Array.isArray(value)) value.forEach((item) => visit(item, visitor));
  else visitor(value);
}

function limitDetails(details) {
  const serialized = safeStringify(details);
  if (serialized.length <= MAX_DETAIL_CHARACTERS) return details;
  return {
    truncated: true,
    originalCharacters: serialized.length,
    preview: serialized.slice(0, MAX_DETAIL_CHARACTERS),
  };
}

function safeStringify(value) {
  try {
    return JSON.stringify(value) ?? "null";
  } catch (error) {
    return JSON.stringify({ serializationError: "Unable to serialize log details" });
  }
}

function parseJson(value, fallback) {
  if (!value) return fallback;
  try {
    return JSON.parse(value);
  } catch (error) {
    // Malformed stored data is ignored without echoing it to logs.
    return fallback;
  }
}

function shouldRecord(level, settings) {
  if (settings.enabled === false) return false;
  return !(settings.level === "NORMAL" && level === "VERBOSE");
}

function storageAvailable() {
  return typeof OfficeRuntime !== "undefined" && OfficeRuntime.storage;
}

function redact(value, depth = 0) {
  if (depth > 6) return '[depth limit]';
  if (typeof value === 'string') return value
    .replace(/([?&](?:token|access_token|api_key)=)[^&#\s]*/gi, '$1[redacted]')
    .replace(/\b(?:bearer|token)\s+[A-Za-z0-9._~+\/-]+/gi, '[redacted]')
    .slice(0, 1000);
  if (Array.isArray(value)) return value.slice(0, 20).map(v => redact(v, depth + 1));
  if (value && typeof value === 'object') return Object.fromEntries(
    Object.entries(value).slice(0, 30).map(([key, item]) => [key,
      /token|authorization|password|secret|cookie|api.?key/i.test(key)
        ? '[redacted]' : redact(item, depth + 1)]));
  return value;
}

const authKey = 'jupyter.auth.' + scope;
async function readAuth() {
  if (!storageAvailable()) return {};
  return parseJson(await OfficeRuntime.storage.getItem(authKey), {});
}
async function saveAuth(auth) {
  if (!storageAvailable()) throw new Error('Shared Office storage is unavailable in this Excel runtime.');
  await OfficeRuntime.storage.setItem(authKey, JSON.stringify({token: auth.token, hub: Boolean(config.hubUser)}));
}
async function clearAuth() {
  if (storageAvailable()) await OfficeRuntime.storage.removeItem(authKey);
}

const MISSING_TOKEN_MESSAGE = "No Jupyter access token is available. Click 'Input Access Token' in the Excel ribbon, verify and save your token, then recalculate the formula.";
async function resolveAuth() {
  return typeof globalThis.jupyterExcelAuth === 'function'
    ? await globalThis.jupyterExcelAuth() : await readAuth();
}
function hasAccessToken(auth) {
  return typeof auth?.token === 'string' && auth.token.trim().length > 0;
}
async function getAuthStatus() {
  try {
    const present = hasAccessToken(await resolveAuth());
    return {state: present ? 'present' : 'missing', message: present
      ? 'Token is available. Presence does not confirm validity or permissions.'
      : MISSING_TOKEN_MESSAGE};
  } catch (_) {
    return {state: 'unavailable', message: "Cannot read the Jupyter access token. Open 'Input Access Token' and verify and save it again. If this persists, check Office storage access."};
  }
}

async function validateToken(token) {
  if (!token) throw new Error('Enter an access token.');
  const base = new URL(config.apiBase.replace(/\/$/, '') + '/');
  const identityUrl = config.hubUser
    ? new URL(config.hubApiUrl)
    : new URL('api/kernels', base);
  let response;
  try {
    response = await fetch(identityUrl.href, {
      headers: {Authorization: 'token ' + token}, cache: 'no-store', credentials: 'omit'
    });
  } catch (_) {
    throw new Error('Cannot reach Jupyter. Check the server address and allowed add-in origin.');
  }
  if (!response.ok) throw new Error('Token validation failed (HTTP ' + response.status + ').');
  if (config.hubUser) {
    const identity = await response.json();
    if (identity.name !== config.hubUser) throw new Error('The token belongs to a different JupyterHub user.');
    return identity.name;
  }
  return 'Single-user Jupyter';
}

async function call(endpoint, suppliedArgs) {

  const args = suppliedArgs.slice();
  while (args.length && args[args.length - 1] === undefined) args.pop();
  const url = new URL(endpoint);
  const expected = new URL(config.apiBase.replace(/\/$/, '') + '/');
  if (url.origin !== expected.origin || !url.pathname.startsWith(expected.pathname + 'Excel/')) {
    throw new Error('Function endpoint is outside the configured Jupyter server.');
  }
  const functionName = decodeURIComponent(endpoint.split(/[?#]/, 1)[0].replace(/\/+$/, '').split('/').pop());
  const startedAt = Date.now();
  try {
    const auth = await resolveAuth();
    const present = hasAccessToken(auth);
    writeLog(present ? 'INFO' : 'ERROR', functionName, 'auth.checked',
      present ? 'Jupyter access token is available; sending request.' : MISSING_TOKEN_MESSAGE,
      {credentialPresent: present});
    if (!present) throw new Error(MISSING_TOKEN_MESSAGE);
    writeLog('INFO', functionName, 'request.started', 'Calling jupyter'  , {argumentCount: args.length, endpoint: endpoint.split(/[?#]/)[0]});
    const response = await fetch(endpoint, {
      method: 'POST',
      credentials: 'omit',
      headers: {
        Authorization: 'token ' + auth.token,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(args)
    });
    const text = await response.text();
    if (!response.ok) {
      let message = `Jupyter returned HTTP ${response.status}`;
      try { message = JSON.parse(text).error?.message || message; } catch (_) {}
      throw new Error(message);
    }
    const value = JSON.parse(text);
    if (!value.ok) throw new Error(value.error?.message || 'Jupyter execution failed');
    writeLog('INFO', functionName, 'request.completed', 'Result returned to Excel', {
      status: response.status, durationMs: Date.now() - startedAt
    });
    return value.result;
  } catch (error) {
    // Preserve useful error details; writeLog redacts sensitive values.
    writeLog('ERROR', functionName, 'request.failed', error?.text ?? error?.message ?? 'Jupyter request failed', {durationMs: Date.now() - startedAt});
    throw error;
  }
}
return {call, readAuth, saveAuth, clearAuth, validateToken, getAuthStatus,
  writeLog, readLogs, readLogSettings, writeLogSettings, clearLogs, summarizeArguments,
  flushLogs: () => writeQueue};

})();
async function jupyterExcelCall(endpoint, args) {
  return globalThis.JupyterExcel.call(endpoint, args);
}
