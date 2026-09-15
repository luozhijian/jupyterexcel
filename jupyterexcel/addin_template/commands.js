/* global Office, JupyterExcel */
(() => {
  // Required even when the command page has no startup UI.
  Office.onReady(() => {});
  let accessTokenDialog;
  let commandEvent;
  let reloadPending = false;
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
    if (message.type === 'reload-addin') {
      if (!accessTokenDialog || reloadPending) return;
      reloadPending = true;
      try {
        // Refresh cached assets before restarting the entire shared runtime.
        // Do not evaluate scripts in the existing runtime or change its URL.
        const pageUrl = new URL(window.location.href);
        const page = await fetch(pageUrl.href, {cache:'reload', credentials:'omit'});
        if (!page.ok) throw new Error('Could not refresh the add-in page.');
        const html = new DOMParser().parseFromString(await page.text(), 'text/html');
        const resources = new Set();
        for (const element of html.querySelectorAll('script[src], link[rel="stylesheet"][href]')) {
          const url = new URL(element.getAttribute('src') || element.getAttribute('href'), pageUrl);
          if (url.origin === pageUrl.origin) resources.add(url.href);
        }
        await Promise.all(Array.from(resources, async url => {
          const response = await fetch(url, {cache:'reload', credentials:'omit'});
          if (!response.ok) throw new Error('Could not refresh an add-in resource.');
          await response.arrayBuffer();
        }));
        accessTokenDialog?.close();
        finishCommand();
        window.location.reload();
      } catch (_) {
        reloadPending = false;
        accessTokenDialog?.messageChild(JSON.stringify({
          type:'reload-error', message:'Could not reload the add-in. Check the asset server and try again.'
        }), {targetOrigin:window.location.origin});
      }
      return;
    }
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
