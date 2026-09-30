/* global Office */
Office.onReady(() => {
  const panel = document.getElementById('jupyter-status-panel');
  const message = document.getElementById('jupyter-status-message');
  const button = document.getElementById('jupyter-status');
  let timer = null, waiting = false, sequence = 0, activeRequest = 0;
  function stop() {
    if (timer !== null) clearTimeout(timer);
    timer = null; waiting = false; activeRequest = ++sequence;
  }
  function request() {
    if (panel.hidden || document.hidden || waiting) return;
    waiting = true;
    activeRequest = ++sequence;
    message.textContent = 'Refreshing Jupyter status...';
    try {
      Office.context.ui.messageParent(JSON.stringify({type:'jupyter-status', requestId:activeRequest}), {targetOrigin:window.location.origin});
      timer = setTimeout(() => {
        waiting = false;
        message.textContent = 'Status request timed out. Select Refresh to retry.';
      }, 12000);
    } catch (_) {
      waiting = false;
      message.textContent = 'Could not request status. Reopen the token dialog.';
    }
  }
  button.onclick = () => {
    panel.hidden = !panel.hidden;
    button.setAttribute('aria-expanded', String(!panel.hidden));
    stop();
    if (!panel.hidden) request();
  };
  document.getElementById('jupyter-status-refresh').onclick = () => { stop(); request(); };
  document.getElementById('replace-token').addEventListener('click', () => { panel.hidden = true; stop(); });
  document.getElementById('reload-confirm').addEventListener('click', stop);
  document.getElementById('ok').addEventListener('click', stop);
  window.addEventListener('pagehide', stop);
  document.addEventListener('visibilitychange', () => { stop(); if (!document.hidden) request(); });
  Office.context.ui.addHandlerAsync(Office.EventType.DialogParentMessageReceived, args => {
    if (args.origin && args.origin !== window.location.origin) return;
    let reply;
    try { reply = JSON.parse(args.message); } catch (_) { return; }
    if (reply.type !== 'jupyter-status-result' || reply.requestId !== activeRequest || panel.hidden || document.hidden) return;
    if (timer !== null) clearTimeout(timer);
    timer = null; waiting = false;
    if (reply.error) {
      message.textContent = reply.error;
      return; // Authentication/network errors require an explicit retry.
    }
    const data = reply.status;
    const percent = value => Math.round(value * 100) + '%';
    const counts = {};
    for (const kernel of data.kernels) counts[kernel.status] = (counts[kernel.status] || 0) + 1;
    document.getElementById('jupyter-status-summary').textContent =
      `Connected | ${data.kernels.length}/${data.settings.max_kernels} kernels | ${counts.idle || 0} idle | ${counts.busy || 0} busy | ${counts.starting || 0} starting | ${counts.unavailable || 0} unavailable. ` +
      `Busy time: ${percent(data.utilization)} over ${data.settings.utilization_window_seconds}s. ` +
      `Queue: ${data.queued_requests}; oldest wait: ${data.oldest_wait_seconds.toFixed(1)}s. ${data.scaling_status}.`;
    const body = document.getElementById('jupyter-status-rows');
    body.replaceChildren();
    for (const kernel of data.kernels) {
      const row = document.createElement('tr');
      for (const value of [kernel.name, kernel.status, percent(kernel.utilization), kernel.current_function || '-', kernel.completed_calls, kernel.failed_calls]) {
        const cell = document.createElement('td'); cell.textContent = String(value); row.appendChild(cell);
      }
      body.appendChild(row);
    }
    document.getElementById('jupyter-status-error').textContent = data.last_error || '';
    message.textContent = 'Updated ' + new Date().toLocaleTimeString() + '. Busy time is not CPU usage.';
    timer = setTimeout(request, 2000);
  });
});
