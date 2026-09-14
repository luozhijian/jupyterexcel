/* global Office, JupyterExcel */
(() => {
  // Required even when the command page has no startup UI.
  Office.onReady(() => {});
  let accessTokenDialog;
  let commandEvent;
  function finishCommand() {
    const event = commandEvent;
    commandEvent = null;
    accessTokenDialog = null;
    if (event) event.completed();
  }
  function openAccessTokenDialog(event) {
    if (commandEvent) {event.completed(); return;}
    commandEvent = event;
    const dialogUrl = new URL('token-dialog.html', window.location.href).href;
    try {
      Office.context.ui.displayDialogAsync(dialogUrl,
        {height: 55, width: 45, displayInIframe: true}, result => {
          if (result.status === Office.AsyncResultStatus.Succeeded) {
            accessTokenDialog = result.value;
            accessTokenDialog.addEventHandler(Office.EventType.DialogMessageReceived, onMessage);
            accessTokenDialog.addEventHandler(Office.EventType.DialogEventReceived, args => {
              if (args.error !== 12006) console.error('JupyterExcel dialog error', args.error);
              finishCommand();
            });
          } else {
            console.error('JupyterExcel dialog could not open', result.error?.code);
            finishCommand();
          }
        });
    } catch (_) {
      console.error('JupyterExcel dialog could not open');
      finishCommand();
    }
  }
  async function onMessage(args) {
    if (args.origin && args.origin !== window.location.origin) return;
    let message;
    try { message = JSON.parse(args.message); } catch (_) { return; }
    if (message.type === 'close') {accessTokenDialog?.close(); finishCommand(); return;}
    try {
      if (message.type === 'auth-status') {
        const auth = await JupyterExcel.readAuth();
        if (!auth.token) return;
        const username = await JupyterExcel.validateToken(auth.token);
        accessTokenDialog?.messageChild(JSON.stringify({type:'saved', username}), {targetOrigin: window.location.origin});
      }
      if (message.type === 'save-token') {
        // Parent validates too; credentials never need to be sent back to the dialog.
        const username = await JupyterExcel.validateToken(message.token);
        await JupyterExcel.saveAuth({token: message.token});
        accessTokenDialog?.messageChild(JSON.stringify({type:'saved', username}), {targetOrigin: window.location.origin});
      }
    } catch (_) {
      accessTokenDialog?.messageChild(JSON.stringify({type:'error', message:'Token verification or shared storage failed.'}), {targetOrigin: window.location.origin});
    }
  }
  async function openNotebookActions(event) {
    try {
      await Office.addin.showAsTaskpane();
      document.getElementById('actions-view').hidden = false;
      document.getElementById('debug-view').hidden = true;
      const details = document.getElementById('action-details');
      if (details) details.open = true;
      document.getElementById('action-select')?.focus();
    } catch (error) {
      console.error('JupyterExcel could not open Notebook Actions', error.message);
    } finally {
      event.completed();
    }
  }
  async function openDebugLog(event) {
    try {
      await Office.addin.showAsTaskpane();
      document.getElementById('actions-view').hidden = true;
      document.getElementById('debug-view').hidden = false;
      const details = document.getElementById('action-details');
      if (details) details.open = false;
      document.getElementById('logging-enabled')?.focus();
    } catch (error) {
      console.error('JupyterExcel could not open Debug Log', error.message);
    } finally {
      event.completed();
    }
  }
  Office.actions.associate('openDebugLog', openDebugLog);
  Office.actions.associate('openNotebookActions', openNotebookActions);
  Office.actions.associate('openAccessTokenDialog', openAccessTokenDialog);
})();
