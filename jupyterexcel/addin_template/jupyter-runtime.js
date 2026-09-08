 
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
  const auth = typeof globalThis.jupyterExcelAuth === 'function'
    ? await globalThis.jupyterExcelAuth() : await readAuth();
  const headers = { "Content-Type": "application/json"};
  // Preserve the generated path across Office URL implementations.
  let requestUrl = endpoint;
  if (auth.token) {
      headers.Authorization = 'token ' + auth.token;
  }
  if (!auth.token && typeof document !== 'undefined') {
    const match = document.cookie.match(/(?:^|; )_xsrf=([^;]*)/);
    if (match) headers['X-XSRFToken'] = decodeURIComponent(match[1]);
  }
  writeLog('INFO', functionName, 'request.started', 'Calling Jupyter', {argumentCount: args.length});
  try {
    console.log("JupyterExcel request diagnostic", JSON.stringify({
  endpoint: endpoint.split('?')[0],
  hasToken: Boolean(auth.token),
  storageAvailable: storageAvailable(),
  hasDocument: typeof document !== "undefined"
}));


const testUrl = requestUrl
  + (requestUrl.includes('?') ? '&' : '?')
  + 'params=' + encodeURIComponent(JSON.stringify(args))
  + (auth.token ? '&token=' + encodeURIComponent(auth.token) : '');

const response = await fetch(testUrl, {
  method: 'GET',
  credentials: 'omit'
});


// const testUrl = endpoint
//   + (endpoint.includes('?') ? '&' : '?')
//   + 'params=' + encodeURIComponent(JSON.stringify(args));

// const response = await fetch(testUrl, {
//   method: 'GET',
//   credentials: 'omit',
//   headers: headers
// });


    // const response = await fetch(requestUrl, {
    //   method: 'POST', credentials: auth.token ? 'same-origin' : 'include',
    //   headers
    //   // , body: JSON.stringify(args)
    //   , body:  args
    // });

    const value = await response.json();
    if (!response.ok || !value.ok) throw new Error(value.error?.message || `Jupyter returned ${response.status}`);
    writeLog('INFO', functionName, 'request.completed', 'Result returned to Excel', {
      status: response.status, durationMs: Date.now() - startedAt
    });
    return value.result;
  } catch (error) {
    // Do not persist URLs, arguments, returned values, or exception text.
    writeLog('ERROR', functionName, 'request.failed', error, {durationMs: Date.now() - startedAt});
    throw error;
  }
}
return {call, readAuth, saveAuth, clearAuth, validateToken,
  writeLog, readLogs, readLogSettings, writeLogSettings, clearLogs, summarizeArguments,
  flushLogs: () => writeQueue};

})();
async function jupyterExcelCall(endpoint, args) {
  return globalThis.JupyterExcel.call(endpoint, args);
}
