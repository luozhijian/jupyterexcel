/* global Office */
Office.onReady(() => {
  const config = globalThis.JupyterExcelConfig;
  const serverAddress = document.getElementById('server-address');
  serverAddress.textContent = config.apiBase;
  serverAddress.href = config.apiBase;
  document.getElementById('verify').onclick = () => {
    const input = document.getElementById('access-token');
    const token = input.value.trim();
    if (!token) return status('Enter an access token.', 'error');
    document.getElementById('verify').disabled = true;
    status('Verifying token and saving in shared Office storage…', 'working');
    Office.context.ui.messageParent(JSON.stringify({type:'save-token', token}), {targetOrigin: window.location.origin});
    input.value = '';
  };
  document.getElementById('ok').onclick = () => Office.context.ui.messageParent(JSON.stringify({type:'close'}), {targetOrigin:window.location.origin});
  document.getElementById('replace-token').onclick = () => {
    document.getElementById('token-form').hidden = false;
    document.getElementById('success').hidden = true;
  };
  const help = document.getElementById('token-help');
  help.href = config.hubUser ? config.hubApiUrl.replace(/api\/user$/, 'token') : config.apiBase;
  document.getElementById('new-token-help').href = help.href;
  Office.context.ui.addHandlerAsync(Office.EventType.DialogParentMessageReceived, args => {
    if (args.origin && args.origin !== window.location.origin) return;
    let message;
    try {message = JSON.parse(args.message);} catch (_) {return;}
    document.getElementById('verify').disabled = false;
    if (message.type === 'saved') {
      document.getElementById('token-form').hidden = true;
      document.getElementById('success').hidden = false;
      document.getElementById('username').textContent = message.username;
      document.getElementById('function-uri').textContent = config.apiBase;
      document.getElementById('ok').disabled = false;
      status('Token verified and saved in shared Office storage.', 'success');
    } else if (message.type === 'error') status(message.message, 'error');
  }, () => {
    Office.context.ui.messageParent(JSON.stringify({type:'auth-status'}), {targetOrigin:window.location.origin});
  });
});
function status(message, kind) {
  const element = document.getElementById('status');
  element.textContent = message;
  element.className = 'status ' + kind;
}
