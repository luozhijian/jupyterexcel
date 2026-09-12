(() => {
/* global Blob, URL, URLSearchParams, document, localStorage, navigator, Office, setInterval, setTimeout, window */

const { clearLogs, readLogs, readLogSettings, writeLogSettings } = globalThis.JupyterExcel;

let allEntries = [];
let paused = false;
let pollInProgress = false;
let entriesFingerprint = "";

const DEBUG_LOG_EXPANDED_KEY = "jupyter.ui.v1.debugLog.expanded";

Office.onReady(async () => {
  document.getElementById("sideload-msg").style.display = "none";
  document.getElementById("app-body").style.display = "flex";
  // The shared runtime uses one canonical task-pane URL for all entry points.
  document.getElementById("debug-log-section").hidden = false;
  bindControls();
  setDebugSectionExpanded(readExpandedPreference());
  const settings = await readLogSettings();
  document.getElementById("logging-enabled").checked = settings.enabled;
  document.getElementById("logging-mode").value = settings.level;
  await refreshAuthStatus();
  await refreshLogs();
  setInterval(refreshLogs, 750);
  setInterval(refreshAuthStatus, 2000);
});

let authStatusPending = false;
async function refreshAuthStatus() {
  if (authStatusPending) return;
  authStatusPending = true;
  try {
    const status = await globalThis.JupyterExcel.getAuthStatus();
    document.getElementById('auth-status-banner').dataset.state = status.state;
    document.getElementById('auth-status-title').textContent = status.state === 'present'
      ? 'Token available' : status.state === 'missing' ? 'NO JUPYTER ACCESS TOKEN'
      : status.state === 'failed' ? 'JUPYTER AUTHORIZATION FAILED' : 'CANNOT READ ACCESS TOKEN';
    document.getElementById('auth-status-message').textContent = status.message;
  } catch (_) {
    document.getElementById('auth-status-banner').dataset.state = 'unavailable';
    document.getElementById('auth-status-title').textContent = 'CANNOT CHECK ACCESS TOKEN';
    document.getElementById('auth-status-message').textContent = 'Open Input Access Token to verify your authorization.';
  } finally {
    authStatusPending = false;
  }
}

function bindControls() {
  document.getElementById("debug-log-collapse").onclick = toggleDebugSection;
  document.getElementById("logging-enabled").onchange = saveSettings;
  document.getElementById("logging-mode").onchange = saveSettings;
  document.getElementById("level-filter").onchange = renderLogs;
  document.getElementById("function-filter").oninput = renderLogs;
  document.getElementById("search-filter").oninput = renderLogs;
  document.getElementById("pause").onclick = togglePause;
  document.getElementById("clear").onclick = clearDisplayedLogs;
  document.getElementById("copy").onclick = copyLogs;
  document.getElementById("export").onclick = exportLogs;
}

async function refreshLogs() {
  if (paused || pollInProgress) return;
  pollInProgress = true;
  try {
    const latestEntries = await readLogs();
    const latestFingerprint = JSON.stringify(latestEntries);
    if (latestFingerprint !== entriesFingerprint) {
      allEntries = latestEntries;
      entriesFingerprint = latestFingerprint;
      renderLogs();
    }
  } finally {
    pollInProgress = false;
  }
}

function renderLogs() {
  const filtered = getFilteredEntries();
  const container = document.getElementById("log-list");
  const expandedSequences = new Set(
    Array.from(container.querySelectorAll(".log-entry[open]")).map(
      (entry) => entry.dataset.sequence
    )
  );
  container.replaceChildren(...filtered.map(createLogElement));
  container.querySelectorAll(".log-entry").forEach((entry) => {
    entry.open = expandedSequences.has(entry.dataset.sequence);
  });
  document.getElementById("log-count").textContent =
    `${filtered.length} shown / ${allEntries.length} stored`;
  document.getElementById("compact-log-count").textContent = `${allEntries.length} logs`;
  if (document.getElementById("auto-scroll").checked) container.scrollTop = container.scrollHeight;
}

function getFilteredEntries() {
  const level = document.getElementById("level-filter").value;
  const functionFilter = document.getElementById("function-filter").value.trim().toLowerCase();
  const search = document.getElementById("search-filter").value.trim().toLowerCase();
  return allEntries.filter((entry) => {
    const levelMatches = level === "ALL" || entry.level === level;
    const functionMatches =
      !functionFilter || (entry.functionName || "").toLowerCase().includes(functionFilter);
    const searchMatches = !search || JSON.stringify(entry).toLowerCase().includes(search);
    return levelMatches && functionMatches && searchMatches;
  });
}

function createLogElement(entry) {
  const details = document.createElement("details");
  details.className = `log-entry level-${entry.level.toLowerCase()}`;
  details.dataset.sequence = String(entry.sequence);
  const summary = document.createElement("summary");
  const time = new Date(entry.timestamp).toLocaleTimeString([], {
    hour12: false,
    fractionalSecondDigits: 3,
  });
  summary.textContent = `${time}  ${entry.level.padEnd(7)}  ${entry.functionName || "SYSTEM"}  ${entry.message}`;
  const pre = document.createElement("pre");
  pre.textContent = JSON.stringify(entry, null, 2);
  details.append(summary, pre);
  return details;
}

async function saveSettings() {
  await writeLogSettings({
    enabled: document.getElementById("logging-enabled").checked,
    level: document.getElementById("logging-mode").value,
  });
  showStatus("Logging settings saved");
}

function togglePause() {
  paused = !paused;
  document.getElementById("pause").textContent = paused ? "Resume" : "Pause";
  showStatus(paused ? "Display paused" : "Display resumed");
  if (!paused) refreshLogs();
}

async function clearDisplayedLogs() {
  await clearLogs();
  allEntries = [];
  entriesFingerprint = "[]";
  renderLogs();
  showStatus("Logs cleared");
}

function toggleDebugSection() {
  const button = document.getElementById("debug-log-collapse");
  setDebugSectionExpanded(button.getAttribute("aria-expanded") !== "true");
}

function setDebugSectionExpanded(expanded) {
  const section = document.getElementById("debug-log-section");
  const button = document.getElementById("debug-log-collapse");
  section.classList.toggle("collapsed", !expanded);
  button.setAttribute("aria-expanded", String(expanded));
  document.getElementById("collapse-icon").textContent = expanded ? "â–¾" : "â–¸";
  writeExpandedPreference(expanded);
}

function readExpandedPreference() {
  try {
    const stored = localStorage.getItem(DEBUG_LOG_EXPANDED_KEY);
    return stored === null ? false : stored === "true";
  } catch {
    return false;
  }
}

function writeExpandedPreference(expanded) {
  try {
    localStorage.setItem(DEBUG_LOG_EXPANDED_KEY, String(expanded));
  } catch {
    // The UI still works for this session if persistent storage is unavailable.
  }
}

async function copyLogs() {
  await navigator.clipboard.writeText(JSON.stringify(getFilteredEntries(), null, 2));
  showStatus("Visible logs copied");
}

function exportLogs() {
  const blob = new Blob([JSON.stringify(getFilteredEntries(), null, 2)], {
    type: "application/json",
  });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `jupyter-excel-logs-${new Date().toISOString().replace(/[:.]/g, "-")}.json`;
  link.click();
  URL.revokeObjectURL(link.href);
  showStatus("Visible logs exported");
}

function showStatus(message) {
  document.getElementById("status").textContent = message;
  setTimeout(() => (document.getElementById("status").textContent = ""), 2500);
}

})();
